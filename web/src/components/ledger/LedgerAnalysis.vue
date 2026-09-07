<template>
  <!-- Tab3 分析：收支概览（4 数字块）+ 分类占比（手写 SVG 环形图）+ 月度趋势（双柱）+ 预算执行。
       纯模板：状态走 appCtx（logic/ledger.js），图表全部手写 SVG/CSS（项目无图表库）。 -->
  <div class="ldg-analysis">
    <!-- 周期切换（作用于分类占比；概览/预算为后端默认口径） -->
    <div class="ldg-period">
      <button v-for="p in periods" :key="p.k" class="ldg-chip"
              :class="{ 'ldg-chip-on': appCtx.ledgerPeriod === p.k }"
              @click="appCtx.ledgerSetPeriod(p.k)">{{ p.label }}</button>
    </div>

    <!-- 卡片 1：收支概览 -->
    <div class="ldg-cards">
      <div class="ldg-card-item">
        <span class="ldg-card-label">本期收入</span>
        <b class="ldg-card-val income">+{{ appCtx.ledgerFmt(summary.monthly_income) }}</b>
      </div>
      <div class="ldg-card-item">
        <span class="ldg-card-label">本期支出</span>
        <b class="ldg-card-val expense">−{{ appCtx.ledgerFmt(summary.monthly_expense) }}</b>
      </div>
      <div class="ldg-card-item">
        <span class="ldg-card-label">本期结余</span>
        <b class="ldg-card-val" :class="balanceClass">{{ balanceText }}</b>
      </div>
      <div class="ldg-card-item">
        <span class="ldg-card-label">总余额</span>
        <b class="ldg-card-val">{{ appCtx.ledgerFmt(summary.total_assets) }}</b>
      </div>
    </div>

    <!-- 卡片 2：分类占比（环形图，扇区可点 → 跳账单） -->
    <div class="ldg-block">
      <div class="ldg-block-head"><b>📊 分类占比</b><span class="more">点击扇区查看该分类账单</span></div>
      <div v-if="!donut.segments.length" class="ldg-empty-sm">这段时间还没有支出记录</div>
      <div v-else class="ldg-donut-wrap">
        <svg class="ldg-donut" viewBox="0 0 160 160" role="img" aria-label="分类占比环形图">
          <circle cx="80" cy="80" r="60" fill="none" stroke="#f1eff8" stroke-width="22"></circle>
          <circle v-for="(s, i) in donut.segments" :key="'sg' + i"
                  cx="80" cy="80" r="60" fill="none"
                  :stroke="s.color" stroke-width="22"
                  :stroke-dasharray="s.dash" :stroke-dashoffset="s.offset"
                  class="ldg-seg" transform="rotate(-90 80 80)"
                  @click="appCtx.ledgerDonutClick(s)">
            <title>{{ s.name }} {{ s.pct }}%</title>
          </circle>
          <text x="80" y="74" text-anchor="middle" class="ldg-donut-total-label">总支出</text>
          <text x="80" y="94" text-anchor="middle" class="ldg-donut-total">{{ appCtx.ledgerFmt(donut.total) }}</text>
        </svg>
        <ul class="ldg-legend">
          <li v-for="(l, i) in donut.legend" :key="'lg' + i" @click="appCtx.ledgerDonutClick(l)">
            <i class="ldg-dot" :style="{ background: l.color }"></i>
            <span class="ldg-legend-name">{{ l.name }}</span>
            <span class="ldg-legend-amt">{{ appCtx.ledgerFmt(l.amount) }}</span>
            <span class="ldg-legend-pct">{{ l.pct }}%</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- 卡片 3：月度趋势（双柱：收入绿 / 支出红） -->
    <div class="ldg-block">
      <div class="ldg-block-head">
        <b>📈 月度趋势</b>
        <span class="ldg-year">
          <button class="ldg-year-btn" @click="appCtx.ledgerSetYear(appCtx.ledgerMonthlyYear - 1)">‹</button>
          <b>{{ appCtx.ledgerMonthlyYear }}</b>
          <button class="ldg-year-btn" @click="appCtx.ledgerSetYear(appCtx.ledgerMonthlyYear + 1)">›</button>
        </span>
      </div>
      <div v-if="!monthly.length" class="ldg-empty-sm">该年度还没有数据</div>
      <div v-else class="ldg-bars">
        <div v-for="m in monthly" :key="m.month" class="ldg-bar-col">
          <div class="ldg-bar-pair">
            <div class="ldg-bar income" :style="{ height: m.ih + '%' }"><title>收 {{ appCtx.ledgerFmt(m.income) }}</title></div>
            <div class="ldg-bar expense" :style="{ height: m.eh + '%' }"><title>支 {{ appCtx.ledgerFmt(m.expense) }}</title></div>
          </div>
          <span class="ldg-bar-label">{{ m.month }}</span>
        </div>
      </div>
      <div class="ldg-bar-tip"><i class="ldg-dot income"></i>收入　<i class="ldg-dot expense"></i>支出</div>
    </div>

    <!-- 卡片 4：项目预算执行 -->
    <div class="ldg-block">
      <div class="ldg-block-head"><b>🎯 项目预算</b><span class="more">超支标红</span></div>
      <div v-if="!budgets.length" class="ldg-empty-sm">还没有设置项目预算，可到「设置」新建项目</div>
      <div v-for="b in budgets" :key="'bg' + b.project_id" class="ldg-budget">
        <div class="ldg-budget-top">
          <span class="ldg-budget-name">{{ b.project_name }}</span>
          <span class="ldg-budget-amt" :class="{ over: b.spent > b.budget }">
            {{ appCtx.ledgerFmt(b.spent) }} / {{ appCtx.ledgerFmt(b.budget) }}
          </span>
        </div>
        <div class="ldg-bar-track">
          <div class="ldg-bar-fill" :class="{ over: b.spent > b.budget }"
               :style="{ width: Math.min(100, Math.round((b.spent / (b.budget || 1)) * 100)) + '%' }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 账本·分析（LedgerView Tab3）。纯模板组件：仅 inject appCtx，无自身业务 data/methods。
export default {
  name: 'LedgerAnalysis',
  inject: ['appCtx'],
  data() {
    return {
      // 纯 UI 常量：分类统计周期
      periods: [
        { k: 'month', label: '本月' },
        { k: 'quarter', label: '近 3 月' },
        { k: 'year', label: '本年' },
      ],
    }
  },
  computed: {
    // 概览：后端未返回时给全 0，避免模板反复判空
    summary() {
      return this.appCtx.ledgerSummary || { total_assets: 0, monthly_income: 0, monthly_expense: 0, monthly_balance: 0 };
    },
    donut() { return this.appCtx.ledgerDonut || { total: 0, segments: [], legend: [] }; },
    monthly() { return this.appCtx.ledgerMonthlyChart || []; },
    budgets() {
      return (this.appCtx.ledgerBudget || []).filter(b => b && b.budget > 0);
    },
    // 结余正负（中国习惯：负=红）
    balanceClass() {
      const v = Number(this.summary.monthly_balance) || 0;
      return v < 0 ? 'expense' : 'income';
    },
    balanceText() {
      const v = Number(this.summary.monthly_balance) || 0;
      return (v < 0 ? '−' : '+') + this.appCtx.ledgerFmt(Math.abs(v));
    },
  },
}
</script>

<style scoped>
.ldg-period { display: flex; gap: 8px; margin-bottom: 14px; }
.ldg-chip { border: 1px solid #e5e1f5; background: #fff; color: #5a5470; border-radius: 999px; padding: 4px 14px; font-size: 12px; cursor: pointer; }
.ldg-chip-on { background: #8b7cf6; border-color: #8b7cf6; color: #fff; }
.ldg-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px; }
.ldg-card-item { background: #f9f8fd; border-radius: 12px; padding: 12px 10px; text-align: center; }
.ldg-card-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 6px; }
.ldg-card-val { font-size: 17px; font-weight: 800; color: #5a5470; }
.ldg-card-val.income { color: #2e7d32; }
.ldg-card-val.expense { color: #c0392b; }
.ldg-block { margin-bottom: 18px; padding: 12px 14px; border: 1px solid #efedf7; border-radius: 12px; }
.ldg-block-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.ldg-block-head b { font-size: 14px; color: #5a5470; }
.ldg-block-head .more { font-size: 11.5px; color: #a8a3b8; }
.ldg-empty-sm { text-align: center; color: #a8a3b8; font-size: 13px; padding: 18px 0; }
/* 环形图 */
.ldg-donut-wrap { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.ldg-donut { width: 150px; height: 150px; flex: none; }
.ldg-seg { cursor: pointer; transition: opacity .12s; }
.ldg-seg:hover { opacity: .78; }
.ldg-donut-total-label { font-size: 11px; fill: #a8a3b8; }
.ldg-donut-total { font-size: 15px; font-weight: 700; fill: #5a5470; }
.ldg-legend { flex: 1; min-width: 180px; list-style: none; margin: 0; padding: 0; }
.ldg-legend li { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 12.5px; cursor: pointer; }
.ldg-legend li:hover { background: #f9f8fd; border-radius: 6px; }
.ldg-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; display: inline-block; }
.ldg-dot.income { background: #2e7d32; }
.ldg-dot.expense { background: #c0392b; }
.ldg-legend-name { flex: 1; color: #5a5470; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ldg-legend-amt { color: #8a8fa3; }
.ldg-legend-pct { width: 38px; text-align: right; color: #a8a3b8; }
/* 月度双柱 */
.ldg-year { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #5a5470; }
.ldg-year-btn { border: none; background: #f1eff8; color: #5a5470; border-radius: 6px; width: 22px; height: 22px; cursor: pointer; font-size: 14px; line-height: 1; }
.ldg-year-btn:hover { background: #e5e1f5; }
.ldg-bars { display: flex; align-items: flex-end; gap: 6px; height: 130px; padding: 6px 0; }
.ldg-bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.ldg-bar-pair { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; gap: 3px; }
.ldg-bar { width: 9px; border-radius: 3px 3px 0 0; min-height: 2px; }
.ldg-bar.income { background: #2e7d32; }
.ldg-bar.expense { background: #c0392b; }
.ldg-bar-label { font-size: 10.5px; color: #a8a3b8; margin-top: 4px; }
.ldg-bar-tip { text-align: center; font-size: 11.5px; color: #a8a3b8; display: flex; align-items: center; justify-content: center; gap: 4px; }
/* 预算 */
.ldg-budget { margin-bottom: 10px; }
.ldg-budget-top { display: flex; justify-content: space-between; font-size: 12.5px; margin-bottom: 4px; }
.ldg-budget-name { color: #5a5470; font-weight: 600; }
.ldg-budget-amt { color: #8a8fa3; }
.ldg-budget-amt.over { color: #c0392b; font-weight: 700; }
.ldg-bar-track { height: 8px; background: #f1eff8; border-radius: 999px; overflow: hidden; }
.ldg-bar-fill { height: 100%; background: #8b7cf6; border-radius: 999px; transition: width .25s; }
.ldg-bar-fill.over { background: #c0392b; }
@media (max-width: 640px) {
  .ldg-cards { grid-template-columns: repeat(2, 1fr); }
  .ldg-donut-wrap { justify-content: center; }
  .ldg-bars { height: 110px; }
}
</style>
