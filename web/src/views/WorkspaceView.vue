<template>
  <!-- 工作台（tab='workspace'）：平台聚合首页。
       定位（temp/blog.md §6.2）：只做聚合与展示，不含任何业务逻辑——
       我的应用 / 最新内容 / 最近使用 / 数据摘要 / 应用中心入口。
       业务状态全在 logic/workspace.js（经 appOptions 合并进 App 壳），本视图仅 inject appCtx。 -->
  <div class="fade-enter">
    <div class="card ws-card">

      <!-- 问候 + 应用中心入口 -->
      <div class="card-head">
        <b><app-icon name="workspace" :size="18"></app-icon> 你好，{{ appCtx.userName || appCtx.user || '同学' }}</b>
        <span class="more">欢迎回来</span>
        <button class="btn btn-ghost btn-sm" @click="appCtx.goTab('apps')">🧩 应用中心</button>
      </div>

      <div v-if="appCtx.wsLoading" class="ws-empty">🔄 正在加载工作台…</div>

      <template v-else>
        <!-- 数据摘要（只展示能拿到的；拿不到就不渲染，不为首页改业务模块） -->
        <div v-if="summaryCards.length" class="ws-cards">
          <div v-for="c in summaryCards" :key="'sc' + c.k" class="ws-card-item">
            <span class="ws-card-label">{{ c.label }}</span>
            <b class="ws-card-val" :class="c.cls">{{ c.value }}</b>
          </div>
        </div>

        <!-- 我的应用（固定优先 → 访问次数 → 默认顺序） -->
        <div class="ws-block">
          <div class="ws-block-head">
            <b>⭐ 我的应用</b>
            <span class="more">点图钉可固定到前面</span>
          </div>
          <div class="ws-apps">
            <div v-for="a in appCtx.wsMyApps" :key="'wa' + a.key" class="ws-app" @click="appCtx.wsOpenApp(a)">
              <button class="ws-pin" :class="{ on: appCtx.wsIsPinned(a.key) }"
                      :title="appCtx.wsIsPinned(a.key) ? '取消固定' : '固定到前面'"
                      @click.stop="appCtx.wsTogglePin(a.key)">📌</button>
              <app-icon :name="a.icon" :size="26" class="ws-app-icon"></app-icon>
              <span class="ws-app-name">{{ a.name }}</span>
            </div>
          </div>
        </div>

        <!-- 最新内容（来自内容模块的已发布文章聚合） -->
        <div class="ws-block">
          <div class="ws-block-head">
            <b>📰 最新内容</b>
            <button class="btn btn-ghost btn-sm" @click="appCtx.goTab('blog')">全部 ›</button>
          </div>
          <div v-if="!appCtx.wsLatest.length" class="ws-empty-sm">还没有已发布的内容</div>
          <div v-else class="ws-latest">
            <div v-for="n in appCtx.wsLatest" :key="'wl' + n.id" class="ws-latest-item"
                 @click="appCtx.wsOpenBlog(n.id)">
              <span class="ws-latest-title">{{ n.title }}</span>
              <span v-if="n.category_name" class="ws-latest-cat">{{ n.category_name }}</span>
              <span class="ws-latest-time">{{ appCtx.wsFmtTime(n.published_at) }}</span>
            </div>
          </div>
        </div>

        <!-- 最近使用（按后端记录的最后访问时间倒序） -->
        <div v-if="appCtx.wsRecentApps.length" class="ws-block">
          <div class="ws-block-head"><b>🕘 最近使用</b></div>
          <div class="ws-recent">
            <div v-for="r in appCtx.wsRecentApps" :key="'wr' + r.app.key" class="ws-recent-item"
                 @click="appCtx.wsOpenApp(r.app)">
              <app-icon :name="r.app.icon" :size="18"></app-icon>
              <span class="ws-recent-name">{{ r.app.name }}</span>
              <span class="ws-recent-time">{{ appCtx.wsFmtTime(r.last_visit_at) }}</span>
            </div>
          </div>
        </div>
      </template>

    </div>
  </div>
</template>

<script>
// 工作台（tab='workspace'）。纯模板组件：仅 inject appCtx，无自身业务 data/methods。
export default {
  name: 'WorkspaceView',
  inject: ['appCtx'],
  computed: {
    // 摘要卡片：只挑「确实拿到数据」的模块（blog.md §10：优先用已有接口，不强求）
    summaryCards() {
      const out = []
      const lg = this.appCtx.wsSummary.ledger
      if (lg) {
        out.push({
          k: 'ledger', label: '本月支出',
          value: '¥' + this.appCtx.ledgerFmt(lg.monthly_expense),
          cls: 'expense',
        })
      }
      // /api/study/dashboard/today 返回 {date,total_todo,subjects:{数学/英语/语文}}，无 tasks 数组
      const st = this.appCtx.wsSummary.study
      if (st && (st.total_todo || 0) > 0) {
        out.push({ k: 'study', label: '今日任务', value: st.total_todo + ' 项', cls: '' })
      }
      // /api/im/messages/unread-count → {total}
      const im = this.appCtx.wsSummary.im
      if (im && (im.total || 0) > 0) {
        out.push({ k: 'im', label: '未读消息', value: im.total + ' 条', cls: 'im' })
      }
      // /api/gx/progress → summary.accuracy（百分比）
      const gx = this.appCtx.wsSummary.gx
      const acc = gx && gx.summary ? gx.summary.accuracy : null
      if (acc !== null && acc !== undefined && (gx.summary.quiz_total || 0) > 0) {
        out.push({ k: 'gx', label: '高项正确率', value: acc + '%', cls: '' })
      }
      if (this.appCtx.wsLatest.length) {
        out.push({ k: 'blog', label: '内容', value: this.appCtx.wsLatest.length + ' 篇最新', cls: '' })
      }
      return out
    },
  },
}
</script>

<style scoped>
.ws-card { max-width: 860px; }
.ws-card .card-head b { display: inline-flex; align-items: center; gap: 6px; }
.ws-card .card-head .more { flex: 1; }
.ws-empty { text-align: center; color: #999; padding: 40px 0; font-size: 14px; }
.ws-empty-sm { text-align: center; color: #a8a3b8; font-size: 13px; padding: 16px 0; }
/* 摘要 */
.ws-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }
.ws-card-item { background: #f9f8fd; border-radius: 12px; padding: 12px 10px; text-align: center; }
.ws-card-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 6px; }
.ws-card-val { font-size: 17px; font-weight: 800; color: #5a5470; }
.ws-card-val.expense { color: #c0392b; }
.ws-card-val.im { color: #5b4bc4; }
/* 区块 */
.ws-block { margin-bottom: 18px; padding: 12px 14px; border: 1px solid #efedf7; border-radius: 12px; }
.ws-block-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.ws-block-head b { font-size: 14px; color: #5a5470; }
.ws-block-head .more { font-size: 11.5px; color: #a8a3b8; }
/* 我的应用 */
.ws-apps { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; }
.ws-app {
  position: relative; display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 12px 6px; border: 1px solid #efedf7; border-radius: 12px; cursor: pointer;
  transition: background .12s, border-color .12s;
}
.ws-app:hover { background: #f9f8fd; border-color: #ddd6f5; }
.ws-app-icon { color: #8b7cf6; }
.ws-app-name { font-size: 12.5px; color: #5a5470; text-align: center; }
.ws-pin { position: absolute; top: 3px; right: 4px; border: none; background: transparent; cursor: pointer; font-size: 12px; opacity: .3; padding: 0; }
.ws-pin.on { opacity: 1; }
/* 最新内容 */
.ws-latest { display: flex; flex-direction: column; }
.ws-latest-item { display: flex; align-items: center; gap: 8px; padding: 8px 2px; border-bottom: 1px dashed #f1eff8; cursor: pointer; }
.ws-latest-item:last-child { border-bottom: none; }
.ws-latest-item:hover { background: #f9f8fd; border-radius: 6px; }
.ws-latest-title { flex: 1; font-size: 13.5px; color: #3b3555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-latest-cat { flex: none; font-size: 11px; color: #5b4bc4; background: #f3f0fe; border-radius: 5px; padding: 1px 6px; }
.ws-latest-time { flex: none; font-size: 11.5px; color: #a8a3b8; }
/* 最近使用 */
.ws-recent { display: flex; flex-wrap: wrap; gap: 8px; }
.ws-recent-item { display: inline-flex; align-items: center; gap: 6px; border: 1px solid #e5e1f5; border-radius: 999px; padding: 5px 12px; font-size: 12.5px; color: #5a5470; cursor: pointer; }
.ws-recent-item:hover { background: #f3f0fc; }
.ws-recent-time { color: #a8a3b8; font-size: 11px; }
@media (max-width: 640px) {
  .ws-apps { grid-template-columns: repeat(3, 1fr); }
}
</style>
