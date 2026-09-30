<template>
  <!-- Tab2 账单：筛选栏（时间范围快捷 + 类型/分类/账户/项目 + 金额区间 + 关键词）
       + 日期分组列表（支出红/收入绿）+ 编辑/删除 + 分页 20「加载更多」。
       纯模板：全部状态/方法走 appCtx（logic/ledger.js）。 -->
  <div class="ldg-bills">
    <!-- 筛选栏 -->
    <div class="ldg-filter">
      <div class="ldg-filter-row">
        <button v-for="r in ranges" :key="r.k" class="ldg-chip"
                :class="{ 'ldg-chip-on': appCtx.ledgerBillFilter.range === r.k }"
                @click="appCtx.ledgerApplyRange(r.k); appCtx.ledgerReloadBills()">{{ r.label }}</button>
        <template v-if="appCtx.ledgerBillFilter.range === 'custom'">
          <input v-model="appCtx.ledgerBillFilter.start_date" type="date" class="fill-input ldg-date">
          <span class="ldg-sep">至</span>
          <input v-model="appCtx.ledgerBillFilter.end_date" type="date" class="fill-input ldg-date">
        </template>
      </div>
      <div class="ldg-filter-row">
        <select v-model="appCtx.ledgerBillFilter.transaction_type" class="fill-input ldg-sel">
          <option value="">全部类型</option>
          <option value="expense">支出</option>
          <option value="income">收入</option>
          <option value="transfer">转账</option>
        </select>
        <select v-model="appCtx.ledgerBillFilter.category_id" class="fill-input ldg-sel">
          <option value="">全部分类</option>
          <option v-for="c in appCtx.ledgerAllCats()" :key="'fc' + c.id" :value="String(c.id)">{{ appCtx.ledgerCatLabel(c) }}</option>
        </select>
        <select v-model="appCtx.ledgerBillFilter.account_id" class="fill-input ldg-sel">
          <option value="">全部账户</option>
          <option v-for="a in appCtx.ledgerAccounts" :key="'fa' + a.id" :value="String(a.id)">{{ a.account_name }}</option>
        </select>
        <select v-model="appCtx.ledgerBillFilter.project_id" class="fill-input ldg-sel">
          <option value="">全部项目</option>
          <option v-for="p in appCtx.ledgerProjects" :key="'fp' + p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </div>
      <div class="ldg-filter-row">
        <input v-model="appCtx.ledgerBillFilter.min_amount" type="number" min="0" step="0.01" placeholder="最小金额" class="fill-input ldg-amt">
        <span class="ldg-sep">—</span>
        <input v-model="appCtx.ledgerBillFilter.max_amount" type="number" min="0" step="0.01" placeholder="最大金额" class="fill-input ldg-amt">
        <input v-model="appCtx.ledgerBillFilter.keyword" class="fill-input ldg-kw" maxlength="50" placeholder="备注关键词" @keyup.enter="appCtx.ledgerReloadBills()">
        <button class="btn btn-primary btn-sm" @click="appCtx.ledgerReloadBills()">查询</button>
        <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerResetBillFilter()">重置</button>
        <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerExportCsv()">⬇️ 导出 CSV</button>
      </div>
    </div>

    <!-- 日期分组列表 -->
    <div v-if="!appCtx.ledgerBillGroups.length" class="ldg-empty-bills">
      <p>这段时间还没有账单</p>
      <button class="btn btn-primary btn-sm" @click="appCtx.ledgerGoTab('add')">去记一笔 ✏️</button>
    </div>
    <div v-for="g in appCtx.ledgerBillGroups" :key="g.day" class="ldg-day">
      <div class="ldg-day-head">
        <b>{{ g.day }}</b>
        <span class="more">
          <template v-if="g.income">收 {{ appCtx.ledgerFmt(g.income) }}</template>
          <template v-if="g.income && g.expense"> · </template>
          <template v-if="g.expense">支 {{ appCtx.ledgerFmt(g.expense) }}</template>
        </span>
      </div>
      <div v-for="b in g.items" :key="b.id" class="ldg-bill">
        <span class="ldg-bill-cat">{{ appCtx.ledgerNameMaps.category[b.category_id] || '未分类' }}</span>
        <span class="ldg-bill-mid">
          <span class="ldg-bill-type" :class="b.transaction_type">{{ appCtx.ledgerTypeLabel(b.transaction_type) }}</span>
          <span class="ldg-bill-acct">{{ appCtx.ledgerNameMaps.account[b.from_account_id] || '' }}</span>
          <template v-if="b.transaction_type === 'transfer' && b.to_account_id">
            → {{ appCtx.ledgerNameMaps.account[b.to_account_id] || '' }}
          </template>
          <span v-if="b.note" class="ldg-bill-note">{{ b.note }}</span>
          <!-- M3 退款标记：refund_of_id 非空说明这笔是某笔账单的退款 -->
          <span v-if="b.refund_of_id" class="ldg-bill-tag ldg-tag-refund">退款</span>
          <!-- M4 多币种：外币账单额外展示原币金额 -->
          <span v-if="b.currency && b.currency !== 'CNY'" class="ldg-bill-tag ldg-tag-fx">
            {{ b.currency }} {{ appCtx.ledgerFmt(b.amount_orig) }}
          </span>
          <span class="ldg-bill-time">{{ (b.transaction_time || '').slice(11, 16) }}</span>
        </span>
        <span class="ldg-bill-amount" :class="b.transaction_type">
          {{ b.transaction_type === 'income' ? '+' : (b.transaction_type === 'expense' ? '−' : '') }}{{ appCtx.ledgerFmt(b.amount) }}
        </span>
        <span class="ldg-bill-ops">
          <button v-if="b.transaction_type !== 'transfer'" class="ldg-op" title="登记退款（生成反向账单并关联原笔）"
                  @click="appCtx.ledgerOpenRefundDialog(b)">↩</button>
          <button class="ldg-op" title="编辑" @click="appCtx.ledgerEditBill(b)">✎</button>
          <button class="ldg-op ldg-op-del" title="删除（余额自动回滚）" @click="appCtx.ledgerDeleteBill(b)">🗑</button>
        </span>
      </div>
    </div>

    <div v-if="appCtx.ledgerBillsMore" class="ldg-more-row">
      <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerLoadMoreBills()">加载更多（每页 20）</button>
    </div>

    <!-- M3 退款弹窗：生成一笔反向账单（支出→收入收款 / 收入→支出退款），并用 refund_of_id 关联原笔 -->
    <div v-if="appCtx.ledgerRefundDialog.show" class="modal-mask on" @click.self="appCtx.ledgerCloseRefundDialog()">
      <div class="modal-card ldg-dialog">
        <div class="modal-head">
          <b>登记退款</b>
          <button class="icon-btn" @click="appCtx.ledgerCloseRefundDialog()">✕</button>
        </div>
        <div class="ldg-dialog-body" v-if="appCtx.ledgerRefundDialog.bill">
          <p class="ldg-refund-src">
            原笔：{{ appCtx.ledgerTypeLabel(appCtx.ledgerRefundDialog.bill.transaction_type) }}
            {{ appCtx.ledgerFmt(appCtx.ledgerRefundDialog.bill.amount) }} 元
            · {{ appCtx.ledgerNameMaps.category[appCtx.ledgerRefundDialog.bill.category_id] || '未分类' }}
          </p>
          <div class="ldg-field">
            <label class="ldg-field-label">退款金额(元)</label>
            <input v-model="appCtx.ledgerRefundDialog.form.amount" type="number" step="0.01" min="0" class="fill-input">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">
              {{ appCtx.ledgerRefundDialog.bill.transaction_type === 'income' ? '退款付出账户' : '退款入账账户' }}
            </label>
            <select v-model="appCtx.ledgerRefundDialog.form.from_account_id" class="fill-input">
              <option value="">选择账户</option>
              <option v-for="a in appCtx.ledgerAccounts" :key="'rf' + a.id" :value="String(a.id)">{{ a.account_name }}</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">备注</label>
            <input v-model="appCtx.ledgerRefundDialog.form.note" class="fill-input" maxlength="200">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">交易时间</label>
            <input v-model="appCtx.ledgerRefundDialog.form.transaction_time" type="datetime-local" class="fill-input">
          </div>
        </div>
        <div class="ldg-dialog-foot">
          <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerCloseRefundDialog()">取消</button>
          <button class="btn btn-primary btn-sm" @click="appCtx.ledgerSubmitRefund()">确认退款</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 账本·账单（LedgerView Tab2）。纯模板组件：仅 inject appCtx，无自身业务 data/methods。
export default {
  name: 'LedgerBills',
  inject: ['appCtx'],
  data() {
    return {
      // 纯 UI 常量：时间范围快捷项
      ranges: [
        { k: 'month', label: '本月' },
        { k: 'last', label: '上月' },
        { k: 'quarter', label: '近 3 月' },
        { k: 'custom', label: '自定义' },
        { k: '', label: '全部' },
      ],
    }
  },
  methods: {
    // 仅 UI 层的筛选重置（业务重载仍走 appCtx）
    resetFilter() { this.appCtx.ledgerResetBillFilter() },
  },
}
</script>

<style scoped>
.ldg-filter { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; background: #f9f8fd; border-radius: 12px; margin-bottom: 14px; }
.ldg-filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ldg-chip { border: 1px solid #e5e1f5; background: #fff; color: #5a5470; border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; }
.ldg-chip-on { background: #8b7cf6; border-color: #8b7cf6; color: #fff; }
.ldg-sel { flex: 1; min-width: 110px; max-width: 180px; }
.ldg-date { max-width: 150px; }
.ldg-amt { width: 100px; }
.ldg-kw { flex: 1; min-width: 120px; max-width: 220px; }
.ldg-sep { color: #8a8fa3; font-size: 12px; }
.ldg-empty-bills { text-align: center; color: #999; padding: 36px 0; }
.ldg-empty-bills p { margin: 0 0 12px; font-size: 14px; }
.ldg-day { margin-bottom: 14px; }
.ldg-day-head { display: flex; justify-content: space-between; align-items: baseline; padding: 6px 2px; border-bottom: 1px solid #efedf7; margin-bottom: 4px; }
.ldg-day-head b { font-size: 13px; color: #5a5470; }
.ldg-day-head .more { font-size: 12px; color: #8a8fa3; }
.ldg-bill { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-bottom: 1px dashed #f1eff8; }
.ldg-bill-cat {
  flex: none; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 13px; font-weight: 600; color: #5a5470;
}
.ldg-bill-mid { flex: 1; display: flex; align-items: center; gap: 6px; font-size: 12px; color: #8a8fa3; min-width: 0; overflow: hidden; }
.ldg-bill-type { flex: none; border-radius: 6px; padding: 1px 6px; font-size: 11px; }
.ldg-bill-type.expense { background: #fdecec; color: #c0392b; }
.ldg-bill-type.income { background: #e9f7ef; color: #2e7d32; }
.ldg-bill-type.transfer { background: #eef0fd; color: #5b4bc4; }
.ldg-bill-note { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ldg-bill-time { flex: none; margin-left: auto; }
/* 退款 / 外币 角标 */
.ldg-bill-tag { flex: none; border-radius: 6px; padding: 1px 6px; font-size: 11px; }
.ldg-tag-refund { background: #eef0fd; color: #5b4bc4; }
.ldg-tag-fx { background: #f3f0fe; color: #8a7ad6; }
/* 退款弹窗 */
.ldg-dialog { width: min(420px, 92vw); }
.ldg-dialog-body { max-height: 60vh; overflow-y: auto; padding: 4px 0; }
.ldg-field { margin-bottom: 10px; }
.ldg-field-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 4px; }
.ldg-dialog-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.ldg-refund-src { font-size: 12.5px; color: #8a8fa3; background: #f9f8fd; border-radius: 8px; padding: 8px 10px; margin: 0 0 12px; }
.ldg-bill-amount { flex: none; font-size: 15px; font-weight: 700; min-width: 84px; text-align: right; }
.ldg-bill-amount.expense { color: #c0392b; }
.ldg-bill-amount.income { color: #2e7d32; }
.ldg-bill-amount.transfer { color: #5b4bc4; }
.ldg-bill-ops { flex: none; display: flex; gap: 4px; }
.ldg-op { border: none; background: transparent; cursor: pointer; font-size: 14px; opacity: .55; padding: 2px 4px; }
.ldg-op:hover { opacity: 1; }
.ldg-op-del:hover { filter: drop-shadow(0 0 2px rgba(192, 57, 43, .5)); }
.ldg-more-row { text-align: center; padding: 8px 0 4px; }
@media (max-width: 640px) {
  .ldg-bill { flex-wrap: wrap; }
  .ldg-bill-mid { order: 3; flex-basis: 100%; }
  .ldg-bill-time { margin-left: 0; }
}
</style>
