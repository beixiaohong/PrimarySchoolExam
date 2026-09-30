// logic/workspace.js：工作台（tab='workspace'）与应用中心（tab='apps'）的 data/computed/methods。
//
// 定位（temp/blog.md §6.2）：工作台是**聚合层**，不承载任何业务逻辑——
// 只做三件事：聚合模块信息、展示我的应用/最近使用/最新内容、提供应用中心入口。
// 模块注册表在 ../apps.js（不在 Vue 页面里硬编码，blog.md §8.1）。
//
// 数据摘要只复用已有接口（blog.md §32「首页适配业务，不为首页重构业务」）：
//   账本本月支出 → /api/ledger/.../statistics/summary（账本开关关闭时静默跳过）
//   今日学习     → /api/study/dashboard/today
//   最新内容     → /api/workspace/latest（内容域提供的轻量聚合）
import { appByKey, enabledApps } from '../apps.js'

export function workspaceData() {
  return {
    wsLoading: false,
    wsUsage: [],        // 后端模块使用记录 [{app_key, visit_count, last_visit_at}]
    wsLatest: [],       // 最新内容（已发布文章，不含正文）
    wsSummary: {        // 各模块摘要（只放能拿到的，拿不到保持 null，前端不渲染）
      ledger: null,
      study: null,
    },
    wsPinned: [],       // 用户手动固定的 app_key（blog.md §7.3，存 localStorage）
  }
}

export const workspaceComputed = {
  // 「我的应用」：手动固定优先 → 访问次数 → 默认顺序（blog.md §7.2 的优先级）
  wsMyApps() {
    const pinned = this.wsPinned || []
    const usage = {}
    for (const u of this.wsUsage || []) usage[u.app_key] = u
    const apps = enabledApps().filter(a => a.key !== 'blog')   // 内容单独走「最新内容」区
    const score = a => {
      const i = pinned.indexOf(a.key)
      if (i >= 0) return [0, i]
      const u = usage[a.key]
      if (u && u.visit_count) return [1, -u.visit_count]
      return [2, 0]
    }
    return apps.slice().sort((x, y) => {
      const sx = score(x), sy = score(y)
      return sx[0] - sy[0] || sx[1] - sy[1]
    }).slice(0, 6)
  },
  // 「最近使用」：按最近访问时间倒序，最多 5 条
  wsRecentApps() {
    const out = []
    for (const u of this.wsUsage || []) {
      const app = appByKey(u.app_key)
      if (app) out.push({ app, visit_count: u.visit_count, last_visit_at: u.last_visit_at })
    }
    return out.slice(0, 5)
  },
  wsIsPinned() {
    return key => (this.wsPinned || []).indexOf(key) >= 0
  },
}

export const workspaceMethods = {
  _wsQs(extra) {
    const qs = new URLSearchParams({ user_id: this.user })
    if (extra) for (const k of Object.keys(extra)) {
      const v = extra[k]
      if (v !== '' && v !== null && v !== undefined) qs.set(k, String(v))
    }
    return qs.toString()
  },
  async initWorkspace() {
    this.wsLoading = true
    try {
      try { this.wsPinned = JSON.parse(localStorage.getItem('zx_ws_pinned') || '[]') } catch (e) { this.wsPinned = [] }
      await Promise.all([this.wsLoadUsage(), this.wsLoadLatest(), this.wsLoadSummaries()])
    } finally {
      this.wsLoading = false
    }
  },
  async wsLoadUsage() {
    const d = await this.api(`/api/workspace/usage?${this._wsQs()}`).catch(() => [])
    this.wsUsage = d || []
  },
  async wsLoadLatest() {
    const d = await this.api(`/api/workspace/latest?${this._wsQs({ limit: 5 })}`).catch(() => [])
    this.wsLatest = d || []
  },
  // 摘要全部「尽力而为」：任一接口不可用（模块开关关闭/无数据）就保持 null，不打扰用户
  async wsLoadSummaries() {
    const ledger = this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/statistics/summary?${this._wsQs()}`)
      .then(d => { this.wsSummary.ledger = d || null }).catch(() => { this.wsSummary.ledger = null })
    const study = this.api(`/api/study/dashboard/today?${this._wsQs({ grade: this.grade })}`)
      .then(d => { this.wsSummary.study = d || null }).catch(() => { this.wsSummary.study = null })
    await Promise.all([ledger, study])
  },
  // 打开模块：先上报一次访问（驱动「我的应用/最近使用」排序），再跳 tab
  async wsOpenApp(app) {
    if (!app) return
    try {
      await this.api(`/api/workspace/usage?${this._wsQs()}`, {
        method: 'POST', body: JSON.stringify({ app_key: app.key }),
      })
    } catch (e) { /* 上报失败不阻塞跳转 */ }
    this.goTab(app.tab)
  },
  wsTogglePin(key) {
    const arr = (this.wsPinned || []).slice()
    const i = arr.indexOf(key)
    if (i >= 0) arr.splice(i, 1); else arr.push(key)
    this.wsPinned = arr
    try { localStorage.setItem('zx_ws_pinned', JSON.stringify(arr)) } catch (e) { /* 隐私模式忽略 */ }
  },
  wsOpenBlog(id) {
    // 从工作台「最新内容」跳到内容模块并直接打开详情
    this.goTab('blog')
    this.$nextTick(() => { if (id) this.blogOpenDetail({ id }) })
  },
  wsFmtTime(s) {
    if (!s) return ''
    const d = new Date(s)
    if (isNaN(d)) return ''
    const mins = Math.floor((Date.now() - d.getTime()) / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs} 小时前`
    const days = Math.floor(hrs / 24)
    if (days < 30) return `${days} 天前`
    return String(s).slice(0, 10)
  },
}
