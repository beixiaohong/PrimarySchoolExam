// logic/im.js：即时通讯视图（tab='im'）专属的 data / computed / methods。
//
// 由来（docs/IM与账本前端实现方案.md §3.6）：与 ledger/parent 同构。
// 三个纯字典 + App.vue 展开合并；ImView 及其子组件仅 inject appCtx 访问，自身零业务 data/methods。
//
// 键前缀：im* / ic*（ic = im-chat / im-contact），与 ledger/parent/appOptions 零冲突。
//
// 资产口径（D5 决策：红包改用钻石）：
//   红包金额单位是「毫钻」（1 钻石 = 1000 毫钻，整数），前端展示用 milli/1000 折算为钻石。
//   钱包模块（WalletView）的 diamonds 字段是「钻」，语义一致；本模块不重复展示余额。
//
// 实时通道：WebSocket `/api/im/ws/chat?token=...`（鉴权同 REST 走 Bearer token）。
//   客户端状态机：connecting → open → reconnecting/closed，断线 3/9/27s 退避重连。
//   入口：imConnectWS()；切换 tab 时不主动断开（允许后台收消息 + 角标提醒）。

import { message as elMessage } from 'element-plus'

// ──────────────────── data ────────────────────
export function imData() {
  return {
    // Tab
    imTab: 'chats',                   // chats | contacts | settings

    // 会话列表
    imChats: [],                      // [{id, name, chat_type, avatar, last_message, last_time, unread}]
    imChatsLoading: false,
    imActiveChat: null,               // 当前选中的会话对象
    imActiveChatId: '',

    // 消息列表
    imMessages: [],                   // [{id, chat_id, sender_id, sender_nickname, content, message_type, file_path, file_name, file_size, created_at, red_packet_id, recalled, edited_at, is_self}]
    imMessagesLoading: false,
    imDraft: '',                      // 输入框草稿
    imSending: false,
    imShowEmoji: false,

    // 上传中
    imUploading: false,
    imRecording: false,
    imRecStartTs: 0,
    imRecDuration: 0,
    imRecTimer: null,
    imRecVolume: 0,
    imRecStream: null,
    imRecRecorder: null,
    imRecChunks: [],

    // 红包
    imRedPacketDialog: false,
    imRedPacketForm: { total_diamond: '', count: '', blessing: '' },

    // 好友
    imFriends: [],                    // [{user_id, nickname, avatar, grade, is_online, last_seen}]
    imFriendsLoading: false,
    imPendingRequests: [],            // 待我接受的申请
    imBlockedUsers: [],               // 黑名单
    imSearchKeyword: '',
    imSearchResults: [],
    imSearching: false,

    // 个人资料（用于私聊 / 群成员卡片）
    imProfile: null,                  // GET /api/im/users/me 缓存
    imGroupMembers: {},               // {chat_id: [user_id...]}

    // 群公告
    imAnnouncement: '',
    imEditingAnnouncement: false,

    // 未读
    imUnreadTotal: 0,                 // 总未读
    imUnreadByChat: {},               // {chat_id: count}

    // WebSocket
    imWS: null,
    imWSReady: false,
    imWSReconnectTimer: null,
    imWSReconnectDelay: 3000,         // 退避 3/9/27s
    imWSTypingMap: {},                // {chat_id: {user_id, ts}}
    imTypingTimers: {},               // 5s 清除打字状态

    // 设置
    imSettings: { mute_notification: false, enter_to_send: true },
  }
}

// ──────────────────── computed ────────────────────
export const imComputed = {
  // 按最近消息时间倒序（后端已排，前端再防一手 null）
  imChatsSorted() {
    return (this.imChats || []).slice().sort((a, b) => {
      const ta = a.last_time ? new Date(a.last_time).getTime() : 0
      const tb = b.last_time ? new Date(b.last_time).getTime() : 0
      return tb - ta
    })
  },
  // 当前会话的展示名（私聊：对方昵称；群聊：群名）
  imActiveChatName() {
    const c = this.imActiveChat
    if (!c) return ''
    if (c.chat_type === 'private') {
      const me = String(this.user)
      const peer = (c.members || []).find(m => String(m.user_id) !== me)
      return peer ? peer.nickname : (c.name || '私聊')
    }
    return c.name || '群聊'
  },
  // 当前会话是否私聊
  imIsPrivate() {
    return this.imActiveChat && this.imActiveChat.chat_type === 'private'
  },
  // 当前会话是否群聊
  imIsGroup() {
    return this.imActiveChat && this.imActiveChat.chat_type === 'group'
  },
  // 输入框是否可发（防空 + 防抖）
  imCanSend() {
    return !this.imSending && !!this.imActiveChatId
  },
  // 录音是否进行中
  imIsRecording() {
    return this.imRecording
  },
  // 录音秒数（UI 显示用）
  imRecSec() {
    return Math.floor(this.imRecDuration / 1000)
  },
}

// ──────────────────── methods ────────────────────
export const imMethods = {
  // ───── 入口：进入 IM Tab ─────
  async initIm() {
    // 并行拉：会话 + 好友 + 个人资料；再决定要不要连 WS
    this.imChatsLoading = true
    try {
      const [chats, friends, profile, unread] = await Promise.all([
        this.api('/api/im/chats').catch(() => []),
        this.api('/api/im/friends').catch(() => []),
        this.api('/api/im/users/me').catch(() => null),
        this.api('/api/im/messages/unread-count').catch(() => null),
      ])
      this.imChats = chats || []
      this.imFriends = friends || []
      this.imProfile = profile
      if (unread && unread.unread_counts) this.imUnreadByChat = unread.unread_counts
      this.imUnreadTotal = unread ? unread.total : 0
    } finally {
      this.imChatsLoading = false
    }
    this.imConnectWS()
  },

  // ───── Tab 切换 ─────
  imGoTab(t) {
    this.imTab = t
    if (t === 'contacts' && !this.imFriends.length) this.imLoadFriends()
  },

  // ───── 会话选择 ─────
  async imOpenChat(chat) {
    this.imActiveChat = chat
    this.imActiveChatId = chat.id
    // 加载消息
    this.imMessagesLoading = true
    try {
      const list = await this.api(`/api/im/chats/${encodeURIComponent(chat.id)}/messages`)
      this.imMessages = (list || []).map(m => ({ ...m, is_self: String(m.sender_id) === String(this.user) }))
      // 清本会话未读
      this.imUnreadByChat = { ...this.imUnreadByChat, [chat.id]: 0 }
      this.imUnreadTotal = Object.values(this.imUnreadByChat).reduce((a, b) => a + b, 0)
      // 群聊：拉群成员
      if (chat.chat_type === 'group') {
        const members = await this.api(`/api/im/chats/${encodeURIComponent(chat.id)}/members`).catch(() => [])
        this.$set(this.imGroupMembers, chat.id, members || [])
        // 拉群公告
        const ann = await this.api(`/api/im/chats/${encodeURIComponent(chat.id)}/announcement`).catch(() => null)
        this.imAnnouncement = ann ? (ann.content || '') : ''
      }
      // 滚到底
      this.$nextTick(() => this.imScrollToBottom())
    } finally {
      this.imMessagesLoading = false
    }
  },

  imScrollToBottom() {
    const el = document.querySelector('.im-message-list')
    if (el) el.scrollTop = el.scrollHeight
  },

  // ───── 发送消息（走 WS 优先；WS 未就绪降级走 REST） ─────
  async imSend() {
    const content = (this.imDraft || '').trim()
    if (!content || !this.imActiveChatId) return
    if (this.imWSReady && this.imWS) {
      this.imWS.send(JSON.stringify({ type: 'message', chat_id: this.imActiveChatId, content, message_type: 'text' }))
      this.imDraft = ''
      return
    }
    // REST 降级（无 WS）：仍调通，留作最后兜底
    this.imSending = true
    try {
      // IM 没有 /messages POST（走 WS），REST 暂无兜底；显示错误
      elMessage.warning('正在连接中，请稍后再试')
    } finally {
      this.imSending = false
    }
  },

  // ───── 表情 ─────
  imEmoji(emo) {
    this.imDraft = (this.imDraft || '') + emo
    this.imShowEmoji = false
  },

  // ───── 上传（图片 / 文件） ─────
  async imUploadFile(file) {
    if (!this.imActiveChatId) {
      elMessage.warning('请先选择会话')
      return
    }
    this.imUploading = true
    try {
      const fd = new FormData()
      fd.append('file', file)
      const token = localStorage.getItem('zx_token') || ''
      const r = await fetch('/api/im/upload/file', {
        method: 'POST',
        headers: token ? { 'Authorization': 'Bearer ' + token } : {},
        body: fd,
      })
      if (!r.ok) {
        const t = await r.text()
        throw new Error('上传失败: ' + t)
      }
      const d = await r.json()
      const mt = (file.type || '').startsWith('image/') ? 'image' : 'file'
      if (this.imWSReady && this.imWS) {
        this.imWS.send(JSON.stringify({
          type: 'message',
          chat_id: this.imActiveChatId,
          content: mt === 'image' ? '[图片]' : '[文件]',
          message_type: mt,
          file_path: d.file_url,
          file_name: d.file_name,
          file_size: d.file_size,
        }))
      } else {
        elMessage.warning('正在连接中，请稍后再试')
      }
    } catch (e) {
      elMessage.error(e.message || '上传失败')
    } finally {
      this.imUploading = false
    }
  },

  imPickFile() {
    // 触发隐藏 input
    const inp = document.getElementById('im-file-input')
    if (inp) inp.click()
  },

  async imOnFileChange(e) {
    const f = (e.target.files || [])[0]
    if (f) await this.imUploadFile(f)
    e.target.value = ''
  },

  // ───── 录音（D6：后端统一转 MP3） ─────
  async imStartRec() {
    if (this.imRecording) return
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      elMessage.error('当前环境不支持录音（请使用 HTTPS 访问）')
      return
    }
    if (!window.MediaRecorder) {
      elMessage.error('浏览器不支持 MediaRecorder，请升级浏览器')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4'
        : ''
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      this.imRecChunks = []
      rec.ondataavailable = (e) => { if (e.data && e.data.size) this.imRecChunks.push(e.data) }
      rec.start(200)
      this.imRecRecorder = rec
      this.imRecStream = stream
      this.imRecording = true
      this.imRecStartTs = Date.now()
      this.imRecDuration = 0
      this.imRecTimer = setInterval(() => {
        this.imRecDuration = Date.now() - this.imRecStartTs
        if (this.imRecDuration >= 60000) this.imStopRec()  // 60s 上限
      }, 200)
    } catch (e) {
      elMessage.error('无法获取麦克风：' + (e.message || e))
    }
  },

  async imStopRec(send = true) {
    if (!this.imRecording) return
    this.imRecording = false
    clearInterval(this.imRecTimer)
    this.imRecTimer = null
    const rec = this.imRecRecorder
    const stream = this.imRecStream
    this.imRecRecorder = null
    this.imRecStream = null
    if (stream) stream.getTracks().forEach(t => t.stop())
    if (!rec) return
    return new Promise(resolve => {
      rec.onstop = async () => {
        const mime = rec.mimeType || 'audio/webm'
        const ext = mime.includes('mp4') ? '.m4a' : mime.includes('ogg') ? '.ogg' : '.webm'
        const blob = new Blob(this.imRecChunks, { type: mime })
        if (!send || blob.size < 1000) {
          elMessage.info(send ? '说话时间太短' : '已取消')
          this.imRecChunks = []
          resolve()
          return
        }
        const file = new File([blob], 'voice' + ext, { type: mime })
        await this.imUploadFile(file)
        this.imRecChunks = []
        resolve()
      }
      rec.stop()
    })
  },

  imCancelRec() {
    return this.imStopRec(false)
  },

  // ───── 撤回 / 编辑 / 删除 ─────
  async imRecall(messageId) {
    try {
      await this.api(`/api/im/messages/${encodeURIComponent(messageId)}/recall`, { method: 'POST' })
      const m = this.imMessages.find(x => x.id === messageId)
      if (m) { m.recalled = true; m.content = '（消息已撤回）' }
    } catch (e) { elMessage.error(e.message || '撤回失败') }
  },

  async imDelete(messageId) {
    try {
      await this.api(`/api/im/messages/${encodeURIComponent(messageId)}`, { method: 'DELETE' })
      this.imMessages = this.imMessages.filter(x => x.id !== messageId)
    } catch (e) { elMessage.error(e.message || '删除失败') }
  },

  imStartEdit(messageId) {
    const m = this.imMessages.find(x => x.id === messageId)
    if (m) { m._editing = true; m._draft = m.content }
  },
  async imSaveEdit(messageId) {
    const m = this.imMessages.find(x => x.id === messageId)
    if (!m) return
    const v = (m._draft || '').trim()
    if (!v) { elMessage.warning('内容不能为空'); return }
    try {
      await this.api(`/api/im/messages/${encodeURIComponent(messageId)}`, {
        method: 'PUT', body: JSON.stringify({ content: v }),
      })
      m.content = v
      m.edited_at = new Date().toISOString()
      m._editing = false
    } catch (e) { elMessage.error(e.message || '编辑失败') }
  },

  // ───── 红包（D5：钻石） ─────
  imOpenRedPacket() {
    if (!this.imActiveChatId) { elMessage.warning('请先选择会话'); return }
    this.imRedPacketDialog = true
    this.imRedPacketForm = { total_diamond: '', count: '', blessing: '' }
  },
  async imSendRedPacket() {
    const f = this.imRedPacketForm
    const td = Number(f.total_diamond), cn = Number(f.count)
    if (!td || td <= 0) { elMessage.warning('请输入红包总钻石数'); return }
    if (!cn || cn < 1) { elMessage.warning('请输入红包份数'); return }
    if (td < cn * 0.01) { elMessage.warning('每份至少 0.01 钻石'); return }
    const total_milli = Math.round(td * 1000)  // 元 → 毫钻
    try {
      await this.api('/api/im/red-packets', {
        method: 'POST',
        body: JSON.stringify({
          chat_id: this.imActiveChatId,
          total_amount: total_milli,
          total_count: cn,
          blessing_words: f.blessing || '',
        }),
      })
      elMessage.success('红包已发送')
      this.imRedPacketDialog = false
    } catch (e) { elMessage.error(e.message || '发送失败') }
  },

  async imClaimPacket(redPacketId) {
    try {
      const d = await this.api(`/api/im/red-packets/${encodeURIComponent(redPacketId)}/claim`, { method: 'POST' })
      const diamond = (d.amount || 0) / 1000
      elMessage.success(`抢到 ${diamond.toFixed(2)} 钻石`)
      // 刷新红包消息的剩余个数
      const m = this.imMessages.find(x => x.red_packet_id === redPacketId)
      if (m && m._red_packet) {
        m._red_packet.remaining_count = d.remaining_count
        m._red_packet.remaining_amount = d.remaining_amount
        m._red_packet.status = d.remaining_count === 0 ? 'finished' : 'active'
      }
    } catch (e) { elMessage.error(e.message || '抢红包失败') }
  },

  // ───── 好友 / 搜索 / 添加 ─────
  async imLoadFriends() {
    this.imFriendsLoading = true
    try {
      this.imFriends = await this.api('/api/im/friends').catch(() => [])
      const pending = await this.api('/api/im/friends/pending').catch(() => [])
      this.imPendingRequests = pending || []
    } finally {
      this.imFriendsLoading = false
    }
  },

  async imSearchUser() {
    const kw = (this.imSearchKeyword || '').trim()
    if (!kw) { this.imSearchResults = []; return }
    this.imSearching = true
    try {
      this.imSearchResults = await this.api(`/api/im/users/search?q=${encodeURIComponent(kw)}`).catch(() => [])
    } finally {
      this.imSearching = false
    }
  },

  async imAddFriend(uid) {
    try {
      await this.api('/api/im/friends/add', { method: 'POST', body: JSON.stringify({ target_user_id: uid }) })
      elMessage.success('好友申请已发送')
    } catch (e) { elMessage.error(e.message || '申请失败') }
  },

  async imAcceptFriend(friendshipId) {
    try {
      await this.api(`/api/im/friends/accept/${encodeURIComponent(friendshipId)}`, { method: 'POST' })
      elMessage.success('已接受')
      this.imLoadFriends()
    } catch (e) { elMessage.error(e.message || '操作失败') }
  },

  // ───── 创建会话 ─────
  async imStartPrivate(targetUserId) {
    try {
      const chat = await this.api('/api/im/chats', {
        method: 'POST',
        body: JSON.stringify({ chat_type: 'private', target_user_id: targetUserId }),
      })
      // 列表里如果没有则插入
      if (!this.imChats.find(c => c.id === chat.id)) {
        this.imChats = [{ ...chat, members: [{ user_id: targetUserId }] }, ...this.imChats]
      }
      this.imOpenChat(this.imChats.find(c => c.id === chat.id) || chat)
      this.imGoTab('chats')
    } catch (e) { elMessage.error(e.message || '发起私聊失败') }
  },

  async imCreateGroup(name, memberIds) {
    if (!name || !memberIds || !memberIds.length) { elMessage.warning('请填写群名并选择成员'); return }
    try {
      const chat = await this.api('/api/im/chats', {
        method: 'POST',
        body: JSON.stringify({ chat_type: 'group', name, member_ids: memberIds }),
      })
      this.imChats = [chat, ...this.imChats]
      this.imOpenChat(chat)
      this.imGoTab('chats')
    } catch (e) { elMessage.error(e.message || '建群失败') }
  },

  // ───── 群公告 ─────
  async imSaveAnnouncement() {
    if (!this.imActiveChatId) return
    try {
      await this.api(`/api/im/chats/${encodeURIComponent(this.imActiveChatId)}/announcement`, {
        method: 'PUT',
        body: JSON.stringify({ content: this.imAnnouncement }),
      })
      elMessage.success('已更新群公告')
      this.imEditingAnnouncement = false
    } catch (e) { elMessage.error(e.message || '更新失败') }
  },

  // ───── 黑名单 ─────
  async imLoadBlocked() {
    this.imBlockedUsers = await this.api('/api/im/friends/blocked').catch(() => [])
  },
  async imBlock(uid) {
    try {
      await this.api(`/api/im/friends/${encodeURIComponent(uid)}/block`, { method: 'POST' })
      elMessage.success('已拉黑')
      this.imLoadBlocked()
    } catch (e) { elMessage.error(e.message || '操作失败') }
  },
  async imUnblock(uid) {
    try {
      await this.api(`/api/im/friends/${encodeURIComponent(uid)}/block`, { method: 'DELETE' })
      elMessage.success('已解除')
      this.imLoadBlocked()
    } catch (e) { elMessage.error(e.message || '操作失败') }
  },

  // ───── WebSocket ─────
  imConnectWS() {
    if (this.imWS) return  // 已连接/重连中
    const token = localStorage.getItem('zx_token') || ''
    if (!token) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/api/im/ws/chat?token=${encodeURIComponent(token)}`
    try {
      const ws = new WebSocket(url)
      this.imWS = ws
      ws.onopen = () => {
        this.imWSReady = true
        this.imWSReconnectDelay = 3000
      }
      ws.onmessage = (ev) => {
        try { this.imHandleWSMsg(JSON.parse(ev.data)) }
        catch (e) { /* 非 JSON 忽略 */ }
      }
      ws.onerror = () => { /* onclose 兜底 */ }
      ws.onclose = () => {
        this.imWSReady = false
        this.imWS = null
        // 退避重连
        clearTimeout(this.imWSReconnectTimer)
        this.imWSReconnectTimer = setTimeout(() => {
          this.imWSReconnectDelay = Math.min(this.imWSReconnectDelay * 3, 27000)
          this.imConnectWS()
        }, this.imWSReconnectDelay)
      }
    } catch (e) {
      elMessage.error('WebSocket 启动失败：' + (e.message || e))
    }
  },

  imHandleWSMsg(msg) {
    if (!msg || !msg.type) return
    switch (msg.type) {
      case 'message': {
        const m = msg.message || {}
        m.is_self = String(m.sender_id) === String(this.user)
        // 当前会话：追加
        if (this.imActiveChatId && m.chat_id === this.imActiveChatId) {
          this.imMessages = [...this.imMessages, m]
          this.$nextTick(() => this.imScrollToBottom())
        }
        // 更新会话列表
        const c = this.imChats.find(x => x.id === m.chat_id)
        if (c) {
          c.last_message = m.content
          c.last_time = m.created_at
        } else {
          // 未知会话：轻量刷新
          this.api('/api/im/chats').then(d => { this.imChats = d || [] }).catch(() => {})
        }
        // 未读 +1（非当前会话 / 非自己）
        if (!m.is_self && m.chat_id !== this.imActiveChatId) {
          this.imUnreadByChat = { ...this.imUnreadByChat, [m.chat_id]: (this.imUnreadByChat[m.chat_id] || 0) + 1 }
          this.imUnreadTotal = Object.values(this.imUnreadByChat).reduce((a, b) => a + b, 0)
          // 桌面通知（可静默）
          try { if (Notification && Notification.permission === 'granted') new Notification(m.sender_nickname || '新消息', { body: m.content || '' }) } catch (e) {}
        }
        break
      }
      case 'red_packet_claimed': {
        // 红包领取广播：刷新对应消息
        const m = this.imMessages.find(x => x.red_packet_id === msg.red_packet_id)
        if (m && m._red_packet) {
          m._red_packet.remaining_count = msg.remaining_count
          m._red_packet.remaining_amount = msg.remaining_amount
        }
        break
      }
      case 'typing': {
        this.$set(this.imWSTypingMap, msg.chat_id, { user_id: msg.user_id, ts: Date.now() })
        // 5s 清除
        clearTimeout(this.imTypingTimers[msg.chat_id])
        this.$set(this.imTypingTimers, msg.chat_id, setTimeout(() => {
          this.$set(this.imWSTypingMap, msg.chat_id, null)
        }, 5000))
        break
      }
      case 'offline_summary': {
        if (msg.unread_counts) {
          this.imUnreadByChat = msg.unread_counts
          this.imUnreadTotal = msg.total || 0
        }
        break
      }
      case 'error': {
        elMessage.warning(msg.message || '消息发送失败')
        break
      }
      default: break
    }
  },

  // ───── 辅助 ─────
  imTimeFmt(s) {
    if (!s) return ''
    const d = new Date(s)
    if (isNaN(d)) return ''
    const now = new Date()
    const sameDay = d.toDateString() === now.toDateString()
    const p = n => String(n).padStart(2, '0')
    if (sameDay) return `${p(d.getHours())}:${p(d.getMinutes())}`
    const yest = new Date(now); yest.setDate(yest.getDate() - 1)
    if (d.toDateString() === yest.toDateString()) return '昨天'
    if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}/${d.getDate()}`
    return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
  },

  imFileSizeFmt(n) {
    if (!n) return ''
    if (n < 1024) return n + ' B'
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
    return (n / 1024 / 1024).toFixed(2) + ' MB'
  },

  imDiamondFmt(milli) {
    return ((milli || 0) / 1000).toFixed(2)
  },

  imAvatarText(c) {
    if (!c) return '?'
    if (c.chat_type === 'group') return '群'
    const me = String(this.user)
    const peer = (c.members || []).find(m => String(m.user_id) !== me)
    const n = peer ? peer.nickname : (c.name || '')
    return (n || '?').slice(0, 1)
  },
}
