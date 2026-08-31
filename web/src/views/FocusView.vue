<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#ff512f,#dd2476)">
          <div style="flex:1">
            <h1>⏰ 番茄专注钟</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">专注 25 分钟，休息 5 分钟。每完成一次专注 +2 金币，保护眼睛也攒金币！</p>
          </div>
          <div class="focus-stats" v-if="appCtx.focusToday">
            <div class="focus-stats-num">{{appCtx.focusToday.count}}<em>次</em></div>
            <div class="focus-stats-label">今日专注 {{appCtx.focusToday.minutes}} 分钟</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="focus-pick-row" v-if="!appCtx.focusTimer.running && !appCtx.focusTimer.paused">
            <button v-for="m in [10, 15, 25]" :key="m" class="focus-pick-btn" :class="{on: appCtx.focusTimer.total === m}" @click="appCtx.focusSet(m)">
              {{m}} 分钟
            </button>
          </div>

          <div class="focus-clock" :class="{running: appCtx.focusTimer.running, done: appCtx.focusDone}">
            <div class="focus-ring" :style="{background: appCtx.focusRingStyle}">
              <div class="focus-time">{{appCtx.focusTimeText}}</div>
              <div class="focus-state">{{appCtx.focusTimer.running ? '专注中…' : appCtx.focusDone ? '完成！' : (appCtx.focusTimer.paused ? '已暂停' : '准备好就开始')}}</div>
            </div>
          </div>

          <div class="focus-actions">
            <template v-if="!appCtx.focusDone">
              <button v-if="!appCtx.focusTimer.running && !appCtx.focusTimer.paused" class="btn btn-primary" @click="appCtx.focusStart()">▶ 开始专注</button>
              <button v-if="appCtx.focusTimer.running && !appCtx.focusTimer.paused" class="btn" @click="appCtx.focusPause()">⏸ 暂停</button>
              <button v-if="appCtx.focusTimer.paused" class="btn btn-primary" @click="appCtx.focusResume()">▶ 继续</button>
              <button v-if="appCtx.focusTimer.running || appCtx.focusTimer.paused" class="btn" @click="appCtx.focusReset()">↺ 放弃</button>
            </template>
            <button v-else class="btn btn-primary" @click="appCtx.focusReset()">🔁 再来一次</button>
          </div>

          <div v-if="appCtx.focusMsg" class="focus-msg">{{appCtx.focusMsg}}</div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📊 专注统计</b></div>
          <div v-if="!appCtx.focusStats" class="card-desc">完成一次专注后，这里会显示你的专注数据</div>
          <div v-else class="focus-stat-grid">
            <div class="focus-stat-item"><b>{{appCtx.focusStats.today.count}}</b><span>今日（{{appCtx.focusStats.today.minutes}} 分钟）</span></div>
            <div class="focus-stat-item"><b>{{appCtx.focusStats.week.count}}</b><span>本周（{{appCtx.focusStats.week.minutes}} 分钟）</span></div>
            <div class="focus-stat-item"><b>{{appCtx.focusStats.total.count}}</b><span>累计（{{appCtx.focusStats.total.minutes}} 分钟）</span></div>
          </div>
          <p class="card-desc" style="margin-top:8px">💡 小贴士：每专注 25 分钟记得站起来看看远处，眼睛休息一下哦</p>
        </div>
</div>
</template>

<script>
// FocusView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'FocusView',
  inject: ['appCtx'],
}
</script>
