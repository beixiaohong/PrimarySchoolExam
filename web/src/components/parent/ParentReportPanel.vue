<template>
  <!-- 家长学习报告（/api/parent/report）：可选周/月/30天窗口，含分科/趋势/薄弱点。默认收起。
       纯 inject appCtx，业务动作与状态全部委托 logic/parent.js（parentReport / reportRange / loadParentReport）。 -->
  <details class="pc-fold">
    <summary class="pc-fold-head">
      <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
      <span class="pc-fold-title">📈 学习报告</span>
      <span class="more">分科 · 趋势 · 薄弱点</span>
    </summary>
    <div class="pc-fold-body">
      <div class="pc-row pc-range-toggle">
        <button :class="['btn','btn-sm', appCtx.reportRange==='week' ? 'btn-primary':'btn-ghost']" @click="appCtx.loadParentReport('week')">本周</button>
        <button :class="['btn','btn-sm', appCtx.reportRange==='month' ? 'btn-primary':'btn-ghost']" @click="appCtx.loadParentReport('month')">本月</button>
        <button :class="['btn','btn-sm', appCtx.reportRange==='30d' ? 'btn-primary':'btn-ghost']" @click="appCtx.loadParentReport('30d')">近30天</button>
        <span class="more" style="margin-left:auto">{{appCtx.parentReport.range_label}}</span>
      </div>

      <div class="stats-grid">
        <div class="sg"><b>{{appCtx.parentReport.summary.total_attempts}}</b><span>做题(套)</span></div>
        <div class="sg"><b>{{appCtx.parentReport.summary.avg_score}}%</b><span>平均分</span></div>
        <div class="sg"><b>{{appCtx.parentReport.summary.avg_correct_rate}}%</b><span>平均正确率</span></div>
        <div class="sg"><b>{{appCtx.parentReport.summary.active_days}}</b><span>学习天数</span></div>
        <div class="sg"><b>{{appCtx.parentReport.summary.tasks_done}}</b><span>完成任务</span></div>
        <div class="sg"><b>{{appCtx.parentReport.summary.focus_minutes}}</b><span>专注(分)</span></div>
        <div class="sg"><b>{{appCtx.parentReport.summary.streak_days}}</b><span>连续天数</span></div>
        <div class="sg"><b>{{appCtx.parentReport.summary.unmastered_wrong}}</b><span>未消灭错题</span></div>
      </div>

      <div class="pc-subtitle">分科明细</div>
      <div v-if="appCtx.parentReport.by_subject.length" class="rep-subj">
        <div v-for="s in appCtx.parentReport.by_subject" :key="s.subject" class="rep-subj-row">
          <span class="rep-subj-name">{{s.subject}}</span>
          <span class="rep-subj-meta">做题{{s.attempts}} · 正确率{{s.correct_rate}}% · 错题{{s.wrong_count}}</span>
          <div class="rep-bar"><div class="rep-bar-fill" :style="{width: barWidth(s.attempts)}"></div></div>
        </div>
      </div>
      <p v-else class="pc-empty">该时间窗内还没有做题记录</p>

      <div class="pc-subtitle">每日做题趋势</div>
      <div v-if="appCtx.parentReport.trend.length" class="rep-trend">
        <div v-for="t in appCtx.parentReport.trend" :key="t.date" class="rep-trend-col"
             :title="t.date + ' 做题' + t.attempts + ' 平均' + t.avg_score + '分'">
          <div class="rep-trend-bar" :style="{height: trendHeight(t.attempts)}"></div>
          <span class="rep-trend-d">{{t.date}}</span>
        </div>
      </div>

      <div class="pc-subtitle">薄弱知识点 <span class="more">未掌握错题归因 Top5</span></div>
      <div v-if="appCtx.parentReport.weak_points.length" class="rep-weak">
        <div v-for="w in appCtx.parentReport.weak_points" :key="w.kp_title" class="rep-weak-row">
          <span class="rep-weak-tag">{{w.subject}}</span>
          <b>{{w.kp_title}}</b>
          <span class="more">{{w.unit}} · 错{{w.wrong_count}}次</span>
        </div>
      </div>
      <p v-else class="pc-empty">暂无可归因的薄弱知识点，继续保持 🎉</p>
    </div>
  </details>
</template>

<script>
// 家长管理·学习报告面板。仅 inject appCtx，纯模板，无自身业务 data/methods。
export default {
  name: 'ParentReportPanel',
  inject: ['appCtx'],
  computed: {
    maxAttempts() {
      const bs = (this.appCtx.parentReport && this.appCtx.parentReport.by_subject) || [];
      return Math.max(1, ...bs.map(s => s.attempts));
    },
    maxTrend() {
      const tr = (this.appCtx.parentReport && this.appCtx.parentReport.trend) || [];
      return Math.max(1, ...tr.map(t => t.attempts));
    },
  },
  methods: {
    barWidth(a) { return Math.round((a || 0) / this.maxAttempts * 100) + '%'; },
    trendHeight(a) { return Math.max(4, Math.round((a || 0) / this.maxTrend * 64)) + 'px'; },
  },
};
</script>
