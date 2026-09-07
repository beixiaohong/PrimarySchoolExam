<template>
  <!-- Tab1 记一笔：类型三选一 + 金额（AntiCheatInput 防 IME）+ 分类三级级联 + 账户
       + 地点/商户/人员/项目下拉（可空，前三者带快捷新建）+ 备注 + 交易时间。
       纯模板：全部状态/方法走 appCtx（logic/ledger.js）。 -->
  <div class="ldg-rec">
    <!-- 编辑模式提示（从账单 tab 点「编辑」跳入预填） -->
    <div v-if="appCtx.ledgerForm.editId" class="ldg-edit-bar">
      ✏️ 正在编辑账单 #{{ appCtx.ledgerForm.editId }}
      <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerResetForm(true)">取消编辑</button>
    </div>

    <!-- 交易类型三选一 -->
    <div class="ldg-type-row">
      <button v-for="t in types" :key="t.k" class="ldg-type" :class="[t.k, { on: appCtx.ledgerForm.transaction_type === t.k }]"
              @click="appCtx.ledgerPickType(t.k)">{{ t.label }}</button>
    </div>

    <!-- 最近使用分类快捷区（localStorage 缓存最近 6 个） -->
    <div v-if="appCtx.ledgerRecentCatItems.length" class="ldg-recent">
      <span class="ldg-recent-label">最近使用：</span>
      <button v-for="c in appCtx.ledgerRecentCatItems" :key="'rc' + c.id" class="ldg-chip"
              @click="appCtx.ledgerUseRecentCat(c)">{{ appCtx.ledgerCatLabel(c) }}</button>
    </div>

    <!-- 金额（元，两位小数；AntiCheatInput text 模式） -->
    <div class="ldg-amount-row">
      <span class="ldg-amount-sign" :class="appCtx.ledgerForm.transaction_type">
        {{ appCtx.ledgerForm.transaction_type === 'income' ? '+' : (appCtx.ledgerForm.transaction_type === 'expense' ? '−' : '⇄') }}
      </span>
      <anti-cheat-input mode="text" v-model="appCtx.ledgerForm.amount" placeholder="金额（元，如 12.50）"></anti-cheat-input>
      <span class="ldg-amount-unit">元</span>
    </div>

    <div class="ldg-grid">
      <!-- 分类三级级联（按类型过滤 category_type） -->
      <div class="ldg-field">
        <label class="ldg-field-label">分类 <i class="ldg-req">*</i></label>
        <div class="ldg-cascade">
          <select v-model="appCtx.ledgerForm.catL1" class="fill-input" @change="appCtx.ledgerForm.catL2 = ''; appCtx.ledgerForm.catL3 = ''">
            <option value="">选择一级</option>
            <option v-for="l in appCtx.ledgerCatL1Options" :key="'l1' + l" :value="l">{{ l }}</option>
          </select>
          <select v-if="appCtx.ledgerCatL2Options.length" v-model="appCtx.ledgerForm.catL2" class="fill-input" @change="appCtx.ledgerForm.catL3 = ''">
            <option value="">选择二级</option>
            <option v-for="l in appCtx.ledgerCatL2Options" :key="'l2' + l" :value="l">{{ l }}</option>
          </select>
          <select v-if="appCtx.ledgerCatL3Options.length" v-model="appCtx.ledgerForm.catL3" class="fill-input">
            <option value="">选择三级</option>
            <option v-for="l in appCtx.ledgerCatL3Options" :key="'l3' + l" :value="l">{{ l }}</option>
          </select>
        </div>
        <p v-if="!appCtx.ledgerCatL1Options.length" class="ldg-hint">
          该类型下还没有分类，请到 <a href="javascript:void(0)" @click="appCtx.ledgerGoTab('settings')">设置</a> 新建
        </p>
      </div>

      <!-- 账户（转账显示两个下拉） -->
      <div class="ldg-field">
        <label class="ldg-field-label">
          {{ appCtx.ledgerForm.transaction_type === 'income' ? '收款账户' : '付款账户' }} <i class="ldg-req">*</i>
        </label>
        <select v-model="appCtx.ledgerForm.from_account_id" class="fill-input">
          <option value="">选择账户</option>
          <option v-for="a in appCtx.ledgerAccounts" :key="'fa' + a.id" :value="String(a.id)">
            {{ a.account_name }}（余额 {{ appCtx.ledgerFmt(a.balance) }}）
          </option>
        </select>
      </div>
      <div class="ldg-field" v-if="appCtx.ledgerForm.transaction_type === 'transfer'">
        <label class="ldg-field-label">转入账户 <i class="ldg-req">*</i></label>
        <select v-model="appCtx.ledgerForm.to_account_id" class="fill-input"
                :class="{ 'ldg-invalid': appCtx.ledgerForm.to_account_id && appCtx.ledgerForm.to_account_id === appCtx.ledgerForm.from_account_id }">
          <option value="">选择账户</option>
          <option v-for="a in appCtx.ledgerAccounts" :key="'ta' + a.id" :value="String(a.id)">
            {{ a.account_name }}（余额 {{ appCtx.ledgerFmt(a.balance) }}）
          </option>
        </select>
        <p v-if="appCtx.ledgerForm.to_account_id && appCtx.ledgerForm.to_account_id === appCtx.ledgerForm.from_account_id" class="ldg-hint ldg-err">
          转出与转入账户不能相同
        </p>
      </div>

      <!-- 地点 / 商户 / 人员（可空 + 快捷新建） -->
      <div class="ldg-field">
        <label class="ldg-field-label">地点</label>
        <div class="ldg-with-add">
          <select v-model="appCtx.ledgerForm.location_id" class="fill-input">
            <option value="">（不选）</option>
            <option v-for="x in appCtx.ledgerLocations" :key="'lo' + x.id" :value="String(x.id)">{{ x.name }}</option>
          </select>
          <button class="ldg-add-btn" title="新建地点" @click="appCtx.ledgerOpenDimDialog('locations', null)">＋</button>
        </div>
      </div>
      <div class="ldg-field">
        <label class="ldg-field-label">商户</label>
        <div class="ldg-with-add">
          <select v-model="appCtx.ledgerForm.merchant_id" class="fill-input">
            <option value="">（不选）</option>
            <option v-for="x in appCtx.ledgerMerchants" :key="'me' + x.id" :value="String(x.id)">{{ x.name }}</option>
          </select>
          <button class="ldg-add-btn" title="新建商户" @click="appCtx.ledgerOpenDimDialog('merchants', null)">＋</button>
        </div>
      </div>
      <div class="ldg-field">
        <label class="ldg-field-label">人员</label>
        <div class="ldg-with-add">
          <select v-model="appCtx.ledgerForm.person_id" class="fill-input">
            <option value="">（不选）</option>
            <option v-for="x in appCtx.ledgerPersons" :key="'pe' + x.id" :value="String(x.id)">{{ x.name }}</option>
          </select>
          <button class="ldg-add-btn" title="新建人员" @click="appCtx.ledgerOpenDimDialog('persons', null)">＋</button>
        </div>
      </div>

      <!-- 项目（可空；选中后实时提示预算执行率） -->
      <div class="ldg-field">
        <label class="ldg-field-label">项目</label>
        <select v-model="appCtx.ledgerForm.project_id" class="fill-input">
          <option value="">（不选）</option>
          <option v-for="x in appCtx.ledgerProjects" :key="'pr' + x.id" :value="String(x.id)">{{ x.name }}</option>
        </select>
        <p v-if="appCtx.ledgerProjectBudgetHint" class="ldg-hint">💡 {{ appCtx.ledgerProjectBudgetHint }}</p>
      </div>

      <!-- 备注 + 交易时间 -->
      <div class="ldg-field ldg-span2">
        <label class="ldg-field-label">备注</label>
        <input v-model="appCtx.ledgerForm.note" class="fill-input" maxlength="200" placeholder="记点什么（可空）">
      </div>
      <div class="ldg-field">
        <label class="ldg-field-label">交易时间</label>
        <input v-model="appCtx.ledgerForm.transaction_time" type="datetime-local" class="fill-input">
        <p class="ldg-hint">不填默认当前时间</p>
      </div>
    </div>

    <div class="ldg-submit-row">
      <button class="btn btn-primary" @click="appCtx.ledgerSubmitTx()">
        {{ appCtx.ledgerForm.editId ? '保存修改' : '记一笔 ✅' }}
      </button>
    </div>
  </div>
</template>

<script>
// 账本·记一笔（LedgerView Tab1）。纯模板组件：仅 inject appCtx，无自身业务 data/methods。
export default {
  name: 'LedgerRecord',
  inject: ['appCtx'],
  data() {
    return {
      // 纯 UI 常量：交易类型三选一
      types: [
        { k: 'expense', label: '支出' },
        { k: 'income', label: '收入' },
        { k: 'transfer', label: '转账' },
      ],
    }
  },
}
</script>

<style scoped>
.ldg-rec { padding: 2px 0 8px; }
.ldg-edit-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  background: #fff7e8; border: 1px solid #f5d9a8; color: #9a6b1f;
  border-radius: 10px; padding: 8px 12px; font-size: 13px; margin-bottom: 12px;
}
.ldg-type-row { display: flex; gap: 10px; margin-bottom: 12px; }
.ldg-type {
  flex: 1; max-width: 140px; padding: 10px 0; border-radius: 12px; font-size: 15px; font-weight: 600;
  border: 1.5px solid #e5e1f5; background: #fff; color: #5a5470; cursor: pointer; transition: all .12s;
}
.ldg-type.expense.on { background: #fdecec; border-color: #e57373; color: #c0392b; }
.ldg-type.income.on { background: #e9f7ef; border-color: #66bb6a; color: #2e7d32; }
.ldg-type.transfer.on { background: #eef0fd; border-color: #8b7cf6; color: #5b4bc4; }
.ldg-recent { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.ldg-recent-label { font-size: 12px; color: #8a8fa3; }
.ldg-chip {
  border: 1px solid #e5e1f5; background: #f7f5fd; color: #5b4bc4; border-radius: 999px;
  padding: 4px 12px; font-size: 12px; cursor: pointer;
}
.ldg-chip:hover { background: #ece7fb; }
.ldg-amount-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.ldg-amount-sign { font-size: 26px; font-weight: 700; width: 30px; text-align: center; }
.ldg-amount-sign.expense { color: #c0392b; }
.ldg-amount-sign.income { color: #2e7d32; }
.ldg-amount-sign.transfer { color: #5b4bc4; }
.ldg-amount-row :deep(.anti-cheat-input) { max-width: 260px; }
.ldg-amount-row :deep(.aci-input) { font-size: 24px; font-weight: 700; }
.ldg-amount-unit { font-size: 14px; color: #8a8fa3; }
.ldg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; }
.ldg-span2 { grid-column: span 2; }
.ldg-field-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 4px; }
.ldg-req { color: #e57373; font-style: normal; }
.ldg-cascade { display: flex; gap: 6px; flex-wrap: wrap; }
.ldg-cascade .fill-input { flex: 1; min-width: 90px; }
.ldg-with-add { display: flex; gap: 6px; align-items: center; }
.ldg-with-add .fill-input { flex: 1; }
.ldg-add-btn {
  flex: none; width: 34px; height: 34px; border-radius: 10px; border: 1px dashed #b9b3d0;
  background: #fff; color: #8b7cf6; font-size: 16px; cursor: pointer;
}
.ldg-add-btn:hover { background: #f3f0fc; border-color: #8b7cf6; }
.ldg-hint { font-size: 12px; color: #8a8fa3; margin: 4px 0 0; }
.ldg-hint a { color: #8b7cf6; }
.ldg-err { color: #c0392b; }
.ldg-invalid { border-color: #e57373 !important; }
.ldg-submit-row { margin-top: 16px; text-align: center; }
.ldg-submit-row .btn { min-width: 180px; }
@media (max-width: 640px) {
  .ldg-grid { grid-template-columns: 1fr; }
  .ldg-span2 { grid-column: span 1; }
}
</style>
