<template>
  <!-- IM 消息区：消息列表 + 输入栏 -->
  <div class="im-msg-shell">
    <!-- 顶部：会话标题 + 群公告 -->
    <header class="im-msg-header">
      <button class="im-icon-btn im-back" @click="ctx.imActiveChat = null" title="返回">←</button>
      <span class="im-msg-name">{{ ctx.imActiveChatName }}</span>
      <span v-if="ctx.imIsGroup" class="im-msg-tip">群聊 · {{ (ctx.imGroupMembers[ctx.imActiveChatId] || []).length }} 人</span>
      <span class="im-pane-spacer"></span>
      <button v-if="ctx.imIsGroup" class="im-icon-btn" @click="ctx.imGoTab('group')" title="群信息">群</button>
      <button class="im-icon-btn" @click="ctx.imGoTab('settings')" title="设置">⚙</button>
    </header>

    <!-- 群公告条 -->
    <div v-if="ctx.imIsGroup && ctx.imAnnouncement" class="im-announce">
      <span class="im-announce-label">群公告</span>
      <span class="im-announce-text">{{ ctx.imAnnouncement }}</span>
    </div>

    <!-- 消息列表 -->
    <div class="im-message-list" ref="listEl">
      <div v-if="ctx.imMessagesLoading" class="im-loading">加载中...</div>
      <div v-else-if="!ctx.imMessages.length" class="im-empty-tip">还没有消息，发个招呼吧</div>
      <div
        v-for="m in ctx.imMessages"
        :key="m.id"
        class="im-msg"
        :class="{ 'is-self': m.is_self, 'is-recalled': m.recalled }"
      >
        <div class="im-msg-avatar">{{ (m.sender_nickname || '?').slice(0, 1) }}</div>
        <div class="im-msg-body">
          <div class="im-msg-meta">
            <span class="im-msg-sender">{{ m.sender_nickname || '我' }}</span>
            <span class="im-msg-time">{{ ctx.imTimeFmt(m.created_at) }}</span>
          </div>

          <!-- 文本 -->
          <div v-if="m.message_type === 'text'" class="im-msg-bubble">
            <template v-if="!m._editing">
              <span>{{ m.content }}</span>
              <i v-if="m.edited_at" class="im-msg-edited">（已编辑）</i>
            </template>
            <template v-else>
              <textarea v-model="m._draft" class="im-msg-edit" rows="2" />
              <div class="im-msg-edit-actions">
                <button @click="m._editing = false">取消</button>
                <button class="primary" @click="ctx.imSaveEdit(m.id)">保存</button>
              </div>
            </template>
          </div>

          <!-- 图片 -->
          <div v-else-if="m.message_type === 'image'" class="im-msg-bubble im-msg-image">
            <a :href="m.file_path" target="_blank">
              <img :src="m.file_path" :alt="m.file_name || '图片'" />
            </a>
          </div>

          <!-- 文件 -->
          <div v-else-if="m.message_type === 'file'" class="im-msg-bubble im-msg-file">
            <a :href="m.file_path" target="_blank">📎 {{ m.file_name || '文件' }}</a>
            <span class="im-msg-size">{{ ctx.imFileSizeFmt(m.file_size) }}</span>
          </div>

          <!-- 语音（后端转码后为 audio/mpeg） -->
          <div v-else-if="m.message_type === 'voice'" class="im-msg-bubble im-msg-voice" @click="ctx._imPlayVoice && ctx._imPlayVoice(m)">
            <span class="im-msg-voice-icon">▶</span>
            <span class="im-msg-voice-bar" :style="{ width: Math.min(80, (m.file_size || 0) / 200) + 'px' }"></span>
            <span class="im-msg-voice-dur">{{ Math.max(1, Math.round((m.file_size || 0) / 2000)) }}''</span>
          </div>

          <!-- 红包 -->
          <div v-else-if="m.message_type === 'red_packet'" class="im-msg-bubble im-msg-redpacket">
            <div class="im-msg-rp-head">
              <span class="im-msg-rp-from">{{ m.sender_nickname }} 的红包</span>
              <span v-if="m._red_packet" class="im-msg-rp-amount">{{ ctx.imDiamondFmt(m._red_packet.total_amount) }} 钻</span>
            </div>
            <div class="im-msg-rp-blessing">{{ m._red_packet ? m._red_packet.blessing_words : '' }}</div>
            <button
              v-if="m._red_packet && m._red_packet.remaining_count > 0"
              class="im-msg-rp-btn"
              @click="ctx.imClaimPacket(m.red_packet_id)"
            >
              拆红包
            </button>
            <div v-else class="im-msg-rp-finished">已领完</div>
          </div>

          <!-- 操作（自己的消息：2 分钟内可撤回；自己的可编辑/删除） -->
          <div v-if="m.is_self && !m._editing && !m.recalled" class="im-msg-actions">
            <button v-if="m.message_type === 'text'" @click="ctx.imStartEdit(m.id)">编辑</button>
            <button v-if="canRecall(m)" @click="ctx.imRecall(m.id)">撤回</button>
            <button @click="ctx.imDelete(m.id)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 录音中提示条 -->
    <div v-if="ctx.imIsRecording" class="im-rec-bar">
      <span class="im-rec-dot"></span>
      <span>正在录音 {{ ctx.imRecSec }}'' · 上滑取消</span>
      <span class="im-pane-spacer"></span>
      <button @click="ctx.imCancelRec">取消</button>
      <button class="primary" @click="ctx.imStopRec()">发送</button>
    </div>

    <!-- 输入栏 -->
    <footer v-else class="im-input-bar">
      <button class="im-icon-btn" :disabled="ctx.imUploading" @click="ctx.imPickFile" title="图片/文件">📎</button>
      <button class="im-icon-btn" @click="ctx.imStartRec" title="语音">🎙</button>
      <textarea
        v-model="ctx.imDraft"
        class="im-input"
        rows="1"
        placeholder="说点什么..."
        @keydown.enter.exact.prevent="ctx.imSend"
        @input="autoGrow($event)"
      />
      <button class="im-icon-btn" @click="ctx.imShowEmoji = !ctx.imShowEmoji" title="表情">😊</button>
      <button
        class="im-send-btn"
        :disabled="!ctx.imDraft.trim()"
        @click="ctx.imSend"
      >发送</button>
      <button class="im-icon-btn" @click="ctx.imOpenRedPacket" title="红包">🧧</button>
    </footer>

    <!-- 表情面板 -->
    <div v-if="ctx.imShowEmoji" class="im-emoji">
      <span v-for="e in emojis" :key="e" @click="ctx.imEmoji(e)">{{ e }}</span>
    </div>

    <!-- 红包弹窗（自研 modal——web 学生端未接入 element-plus，勿用 el-dialog） -->
    <div v-if="ctx.imRedPacketDialog" class="im-rp-mask" @click.self="ctx.imRedPacketDialog = false">
      <div class="im-rp-dialog">
        <div class="im-rp-dialog-head">
          <span>发红包（钻石）</span>
          <button class="im-rp-x" @click="ctx.imRedPacketDialog = false">×</button>
        </div>
        <div class="im-rp-form">
          <label>总钻石数：<input v-model="ctx.imRedPacketForm.total_diamond" type="number" min="0.01" step="0.01" /></label>
          <label>份数：<input v-model="ctx.imRedPacketForm.count" type="number" min="1" /></label>
          <label>祝福语：<input v-model="ctx.imRedPacketForm.blessing" maxlength="20" placeholder="恭喜发财" /></label>
        </div>
        <div class="im-rp-dialog-foot">
          <button @click="ctx.imRedPacketDialog = false">取消</button>
          <button class="primary" @click="ctx.imSendRedPacket">塞钱</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { emoji } from './emoji-list.js'
export default {
  name: 'ImMessages',
  inject: ['appCtx'],
  data() { return { emojis: emoji } },
  computed: {
    ctx() { return this.appCtx },
  },
  methods: {
    canRecall(m) {
      if (!m.created_at) return false
      const t = new Date(m.created_at).getTime()
      return Date.now() - t < 2 * 60 * 1000
    },
    autoGrow(e) {
      e.target.style.height = 'auto'
      e.target.style.height = Math.min(120, e.target.scrollHeight) + 'px'
    },
  },
}
</script>

<style scoped>
.im-msg-shell { display: flex; flex-direction: column; height: 100%; background: #f7f8fa; }
.im-msg-header {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid #ebeef2;
  background: #fff;
}
.im-msg-name { font-weight: 600; font-size: 15px; }
.im-msg-tip { font-size: 12px; color: #909399; }
.im-pane-spacer { flex: 1; }
.im-back { display: none; }
@media (max-width: 768px) { .im-back { display: inline-block; } }
.im-icon-btn {
  border: 0; background: transparent; cursor: pointer;
  font-size: 18px; width: 30px; height: 30px; border-radius: 6px;
  color: #606266;
}
.im-icon-btn:hover { background: #f0f2f5; }
.im-icon-btn:disabled { color: #c0c4cc; cursor: not-allowed; }

.im-announce {
  padding: 6px 14px; background: #fffbe6; border-bottom: 1px solid #ffe58f;
  font-size: 12px; color: #876800;
}
.im-announce-label { font-weight: 600; margin-right: 6px; }

.im-message-list {
  flex: 1; overflow-y: auto; padding: 14px 18px;
}
.im-loading, .im-empty-tip { text-align: center; color: #909399; padding: 24px; font-size: 13px; }
.im-msg { display: flex; gap: 8px; margin-bottom: 14px; }
.im-msg.is-self { flex-direction: row-reverse; }
.im-msg.is-recalled .im-msg-bubble { color: #c0c4cc; font-style: italic; }
.im-msg-avatar {
  width: 34px; height: 34px; border-radius: 50%;
  background: linear-gradient(135deg, #6da9ff, #6ee2c5);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 14px; flex: 0 0 34px;
}
.im-msg-body { max-width: 70%; min-width: 0; }
.im-msg.is-self .im-msg-body { display: flex; flex-direction: column; align-items: flex-end; }
.im-msg-meta { font-size: 11px; color: #909399; margin-bottom: 4px; }
.im-msg-sender { margin-right: 6px; font-weight: 500; }
.im-msg-bubble {
  display: inline-block; padding: 8px 12px; background: #fff;
  border-radius: 10px; word-break: break-word; max-width: 100%;
  box-shadow: 0 1px 2px rgba(0,0,0,.04);
  position: relative;
}
.im-msg.is-self .im-msg-bubble { background: #95d6ff; }
.im-msg-edited { color: #c0c4cc; font-size: 11px; margin-left: 4px; }
.im-msg-image img { max-width: 220px; max-height: 220px; border-radius: 6px; display: block; }
.im-msg-file { display: flex; gap: 8px; align-items: center; }
.im-msg-size { color: #909399; font-size: 11px; }
.im-msg-voice {
  display: flex; gap: 6px; align-items: center; cursor: pointer;
  min-width: 100px;
}
.im-msg-voice-icon { color: #409eff; }
.im-msg-voice-bar { display: inline-block; height: 4px; background: #d6e8ff; border-radius: 2px; }
.im-msg-voice-dur { color: #909399; font-size: 11px; }

.im-msg-redpacket {
  background: linear-gradient(135deg, #ff7e7e, #ffb86c);
  color: #fff; padding: 12px 16px; min-width: 200px;
}
.im-msg-rp-head { display: flex; justify-content: space-between; align-items: center; }
.im-msg-rp-from { font-size: 13px; opacity: .9; }
.im-msg-rp-amount { font-size: 18px; font-weight: 600; }
.im-msg-rp-blessing { font-size: 12px; margin: 6px 0; opacity: .9; }
.im-msg-rp-btn {
  display: block; margin: 8px auto 0; padding: 6px 20px;
  background: #fff; color: #ff7e7e; border: 0; border-radius: 18px;
  font-weight: 600; cursor: pointer;
}
.im-msg-rp-finished { text-align: center; opacity: .8; font-size: 12px; margin-top: 6px; }

.im-msg-actions {
  margin-top: 4px; display: flex; gap: 8px; font-size: 11px;
}
.im-msg-actions button {
  border: 0; background: transparent; color: #909399; cursor: pointer;
  padding: 0 2px;
}
.im-msg-actions button:hover { color: #409eff; }

.im-msg-edit { width: 100%; border: 1px solid #dcdfe6; border-radius: 4px; padding: 4px 6px; }
.im-msg-edit-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 4px; }
.im-msg-edit-actions button { border: 1px solid #dcdfe6; background: #fff; padding: 2px 10px; border-radius: 4px; cursor: pointer; }
.im-msg-edit-actions button.primary { background: #409eff; color: #fff; border-color: #409eff; }

.im-rec-bar {
  display: flex; gap: 10px; align-items: center;
  padding: 10px 14px; background: #fff; border-top: 1px solid #ebeef2;
  color: #f56c6c; font-size: 13px;
}
.im-rec-bar button { border: 1px solid #dcdfe6; background: #fff; padding: 4px 12px; border-radius: 4px; cursor: pointer; }
.im-rec-bar button.primary { background: #409eff; color: #fff; border-color: #409eff; }
.im-rec-dot { width: 8px; height: 8px; border-radius: 50%; background: #f56c6c; animation: pulse 1s infinite; }
@keyframes pulse { 0% { opacity: 1; } 50% { opacity: .4; } 100% { opacity: 1; } }

.im-input-bar {
  display: flex; gap: 6px; align-items: flex-end; padding: 8px 12px;
  background: #fff; border-top: 1px solid #ebeef2;
}
.im-input {
  flex: 1; resize: none; border: 1px solid #dcdfe6; border-radius: 6px;
  padding: 6px 10px; font-size: 14px; min-height: 32px; max-height: 120px;
  outline: none; transition: border-color .15s;
}
.im-input:focus { border-color: #409eff; }
.im-send-btn {
  border: 0; background: #409eff; color: #fff; padding: 6px 14px;
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.im-send-btn:disabled { background: #c0c4cc; cursor: not-allowed; }

.im-emoji {
  background: #fff; border-top: 1px solid #ebeef2; padding: 8px 12px;
  display: flex; flex-wrap: wrap; gap: 4px; max-height: 160px; overflow-y: auto;
}
.im-emoji span { font-size: 22px; padding: 2px 4px; cursor: pointer; border-radius: 4px; }
.im-emoji span:hover { background: #f0f2f5; }

.im-rp-form { display: flex; flex-direction: column; gap: 12px; }
.im-rp-form label { display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
.im-rp-form input { width: 180px; border: 1px solid #dcdfe6; border-radius: 4px; padding: 4px 8px; }

/* 自研红包弹窗（原 el-dialog，web 未接 element-plus） */
.im-rp-mask {
  position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 999;
  display: flex; align-items: center; justify-content: center;
}
.im-rp-dialog {
  width: 360px; max-width: 92vw; background: #fff; border-radius: 12px;
  padding: 18px 20px 16px; box-shadow: 0 8px 30px rgba(0,0,0,.18);
}
.im-rp-dialog-head {
  display: flex; justify-content: space-between; align-items: center;
  font-weight: 600; font-size: 15px; margin-bottom: 14px;
}
.im-rp-x { border: 0; background: transparent; font-size: 18px; cursor: pointer; color: #909399; line-height: 1; }
.im-rp-dialog-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.im-rp-dialog-foot button { border: 1px solid #dcdfe6; background: #fff; padding: 4px 14px; border-radius: 4px; cursor: pointer; }
.im-rp-dialog-foot button.primary { background: #409eff; color: #fff; border-color: #409eff; }
</style>
