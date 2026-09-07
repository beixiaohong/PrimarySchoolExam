<template>
  <!-- Tab4 设置：六维（账户/分类/地点/商户/人员/项目）CRUD + 周期交易（启用开关 + 立即补跑）。
       增删改统一走 LedgerView 的通用弹窗（字段由 LEDGER_DIMS 驱动）。
       纯模板：状态与方法全走 appCtx（logic/ledger.js）。 -->
  <div class="ldg-settings">
    <div v-for="s in sections" :key="s.k" class="ldg-sec">
      <div class="ldg-sec-head">
        <b>{{ s.icon }} {{ s.label }}</b>
        <span class="more">{{ itemsOf(s.k).length }} 条</span>
        <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerOpenDimDialog(s.k, null)">＋ 新建</button>
      </div>

      <div v-if="!itemsOf(s.k).length" class="ldg-sec-empty">还没有{{ s.label }}，点右上角新建</div>

      <div v-else class="ldg-sec-list">
        <div v-for="it in itemsOf(s.k)" :key="s.k + it.id" class="ldg-row">
          <span class="ldg-row-main">
            <!-- 账户：名称 + 类型 + 余额 -->
            <template v-if="s.k === 'accounts'">
              <b>{{ it.account_name }}</b>
              <span class="ldg-row-sub">{{ accountTypeLabel(it.account_type) }} · 余额 {{ appCtx.ledgerFmt(it.balance) }} 元</span>
            </template>
            <!-- 分类：三级路径 + 收支类型 -->
            <template v-else-if="s.k === 'categories'">
              <b>{{ appCtx.ledgerCatLabel(it) }}</b>
              <span class="ldg-row-sub" :class="it.category_type === 'INCOME' ? 'income' : 'expense'">
                {{ it.category_type === 'INCOME' ? '收入' : '支出' }}
              </span>
            </template>
            <!-- 地点 / 商户 / 人员 / 项目：名称 + 附加说明 -->
            <template v-else-if="s.k === 'locations'">
              <b>{{ it.name }}</b><span class="ldg-row-sub">{{ it.address || '—' }}</span>
            </template>
            <template v-else-if="s.k === 'merchants'">
              <b>{{ it.name }}</b><span class="ldg-row-sub">{{ it.description || '—' }}</span>
            </template>
            <template v-else-if="s.k === 'persons'">
              <b>{{ it.name }}</b>
              <span class="ldg-row-sub">{{ [it.relationship, it.phone].filter(Boolean).join(' · ') || '—' }}</span>
            </template>
            <template v-else-if="s.k === 'projects'">
              <b>{{ it.name }}</b>
              <span class="ldg-row-sub">{{ it.budget ? `预算 ${appCtx.ledgerFmt(it.budget)} 元` : '未设预算' }}{{ it.description ? ' · ' + it.description : '' }}</span>
            </template>
            <!-- 周期交易：名称 + 金额/频率/下次执行 -->
            <template v-else-if="s.k === 'recurring'">
              <b>{{ it.name }}</b>
              <span class="ldg-row-sub">
                {{ appCtx.ledgerTypeLabel(it.transaction_type) }} {{ appCtx.ledgerFmt(it.amount) }} 元 ·
                {{ appCtx.ledgerFreqLabel(it.frequency) }} ·
                下次 {{ (appCtx.ledgerDtLocal(it.next_run) || '').replace('T', ' ') || '—' }}
              </span>
            </template>
          </span>

          <span class="ldg-row-ops">
            <template v-if="s.k === 'recurring'">
              <label class="ldg-switch" :title="it.is_active ? '点击停用' : '点击启用'">
                <input type="checkbox" :checked="it.is_active" @change="appCtx.ledgerToggleRecurring(it)">
                <i></i>
              </label>
            </template>
            <button class="ldg-op" title="编辑" @click="appCtx.ledgerOpenDimDialog(s.k, it)">✎</button>
            <button class="ldg-op ldg-op-del" title="删除" @click="appCtx.ledgerDeleteDim(s.k, it)">🗑</button>
          </span>
        </div>
      </div>

      <!-- 周期交易专属：手动补跑（全量自动执行由 scheduler 每日 01:00 跑） -->
      <div v-if="s.k === 'recurring'" class="ldg-sec-foot">
        <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerRunDueNow()">⏱ 立即补跑到期交易</button>
        <span class="ldg-tip">到期交易每天凌晨 01:00 自动记账，也可点此手动补跑</span>
      </div>
    </div>
  </div>
</template>

<script>
// 账本·设置（LedgerView Tab4）。纯模板组件：仅 inject appCtx，无自身业务 data/methods。
export default {
  name: 'LedgerSettings',
  inject: ['appCtx'],
  data() {
    return {
      // 纯 UI 常量：区块定义（顺序与 LEDGER_DIMS 一致，末位为周期交易）
      sections: [
        { k: 'accounts', label: '账户', icon: '💳' },
        { k: 'categories', label: '分类', icon: '🏷️' },
        { k: 'locations', label: '地点', icon: '📍' },
        { k: 'merchants', label: '商户', icon: '🏪' },
        { k: 'persons', label: '人员', icon: '👤' },
        { k: 'projects', label: '项目', icon: '🎯' },
        { k: 'recurring', label: '周期交易', icon: '🔁' },
      ],
    }
  },
  methods: {
    // 维度 key → 对应列表（避免模板里写一长串三元）
    itemsOf(k) {
      const map = {
        accounts: this.appCtx.ledgerAccounts,
        categories: this.appCtx.ledgerCategories,
        locations: this.appCtx.ledgerLocations,
        merchants: this.appCtx.ledgerMerchants,
        persons: this.appCtx.ledgerPersons,
        projects: this.appCtx.ledgerProjects,
        recurring: this.appCtx.ledgerRecurring,
      };
      return map[k] || [];
    },
    accountTypeLabel(t) {
      return { savings_card: '储蓄卡', credit_card: '信用卡', virtual_account: '虚拟账户' }[t] || t || '账户';
    },
  },
}
</script>

<style scoped>
.ldg-sec { margin-bottom: 16px; padding: 12px 14px; border: 1px solid #efedf7; border-radius: 12px; }
.ldg-sec-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.ldg-sec-head b { font-size: 14px; color: #5a5470; }
.ldg-sec-head .more { flex: 1; font-size: 11.5px; color: #a8a3b8; }
.ldg-sec-empty { text-align: center; color: #a8a3b8; font-size: 13px; padding: 12px 0; }
.ldg-sec-list { display: flex; flex-direction: column; }
.ldg-row { display: flex; align-items: center; gap: 10px; padding: 7px 2px; border-bottom: 1px dashed #f1eff8; }
.ldg-row:last-child { border-bottom: none; }
.ldg-row-main { flex: 1; display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.ldg-row-main b { font-size: 13.5px; color: #5a5470; font-weight: 600; }
.ldg-row-sub { font-size: 11.5px; color: #a8a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ldg-row-sub.income { color: #2e7d32; }
.ldg-row-sub.expense { color: #c0392b; }
.ldg-row-ops { flex: none; display: flex; align-items: center; gap: 4px; }
.ldg-op { border: none; background: transparent; cursor: pointer; font-size: 14px; opacity: .55; padding: 2px 4px; }
.ldg-op:hover { opacity: 1; }
.ldg-op-del:hover { filter: drop-shadow(0 0 2px rgba(192, 57, 43, .5)); }
/* 启用开关（纯 CSS，无第三方组件依赖） */
.ldg-switch { position: relative; display: inline-block; width: 34px; height: 19px; cursor: pointer; }
.ldg-switch input { opacity: 0; width: 0; height: 0; position: absolute; }
.ldg-switch i { position: absolute; inset: 0; background: #d9d5e6; border-radius: 999px; transition: background .15s; }
.ldg-switch i::before {
  content: ''; position: absolute; width: 15px; height: 15px; left: 2px; top: 2px;
  background: #fff; border-radius: 50%; transition: transform .15s;
}
.ldg-switch input:checked + i { background: #8b7cf6; }
.ldg-switch input:checked + i::before { transform: translateX(15px); }
.ldg-sec-foot { display: flex; align-items: center; gap: 10px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #efedf7; flex-wrap: wrap; }
.ldg-tip { font-size: 11.5px; color: #a8a3b8; }
@media (max-width: 640px) {
  .ldg-row-main { flex-wrap: wrap; }
  .ldg-row-sub { flex-basis: 100%; }
}
</style>
