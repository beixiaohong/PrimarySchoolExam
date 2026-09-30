<template>
  <!-- Tab4 设置：六维（账户/分类/地点/商户/人员/项目）CRUD + 周期交易（启用开关 + 立即补跑）。
       增删改统一走 LedgerView 的通用弹窗（字段由 LEDGER_DIMS 驱动）。
       纯模板：状态与方法全走 appCtx（logic/ledger.js）。 -->
  <div class="ldg-settings">
    <div v-for="s in sections" :key="s.k" class="ldg-sec">
      <div class="ldg-sec-head">
        <b>{{ s.icon }} {{ s.label }}</b>
        <span class="more">{{ itemsOf(s.k).length }} 条</span>
        <button class="btn btn-ghost btn-sm" @click="openNew(s.k)">＋ 新建</button>
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
            <!-- 预算（M2）：月 / 分类 / 项目三种口径 + 预警阈值 -->
            <template v-else-if="s.k === 'budgets'">
              <b>{{ appCtx.ledgerBudgetScopeName(it) }}</b>
              <span class="ldg-row-sub">
                {{ appCtx.ledgerFmt(it.amount) }} 元 · 预警 {{ Math.round((it.notify_threshold || 0.8) * 100) }}%
              </span>
            </template>
            <!-- 借贷（M3）：方向 + 人员 + 未结余额 + 到期日 -->
            <template v-else-if="s.k === 'debts'">
              <b>{{ appCtx.ledgerDebtPersonName(it) }}</b>
              <span class="ldg-row-sub" :class="it.direction === 'lend' ? 'income' : 'expense'">
                {{ it.direction === 'lend' ? '借出' : '借入' }} ·
                未结 {{ appCtx.ledgerFmt(it.balance) }} / {{ appCtx.ledgerFmt(it.total) }} 元
                <template v-if="it.due_date"> · 到期 {{ (it.due_date || '').slice(0, 10) }}</template>
                <template v-if="it.status === 'cleared'"> · 已结清</template>
              </span>
            </template>
            <!-- 记账模板（M4）：要素摘要 -->
            <template v-else-if="s.k === 'templates'">
              <b>{{ it.name }}</b>
              <span class="ldg-row-sub">
                {{ appCtx.ledgerTypeLabel(it.transaction_type) }} · {{ appCtx.ledgerTemplateDesc(it) }}
              </span>
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
            <!-- 借贷专属：未结清时提供「还款/收款」入口 -->
            <button v-if="s.k === 'debts' && it.status === 'active'" class="ldg-op" title="还款 / 收款"
                    @click="appCtx.ledgerOpenRepayDialog(it)">💰</button>
            <button class="ldg-op" title="编辑" @click="openEdit(s.k, it)">✎</button>
            <button class="ldg-op ldg-op-del" title="删除" @click="removeDim(s.k, it)">🗑</button>
          </span>
        </div>
      </div>

      <!-- 借贷专属：状态筛选 + 还款说明 -->
      <div v-if="s.k === 'debts'" class="ldg-sec-foot">
        <button v-for="f in debtFilters" :key="'df' + f.k" class="ldg-chip"
                :class="{ 'ldg-chip-on': appCtx.ledgerDebtFilter === f.k }"
                @click="appCtx.ledgerSetDebtFilter(f.k)">{{ f.label }}</button>
        <span class="ldg-tip">点 💰 登记还款/收款：借出→生成收入，借入→生成支出，并自动扣减未结余额</span>
      </div>

      <!-- 周期交易专属：手动补跑（全量自动执行由 scheduler 每日 01:00 跑） -->
      <div v-if="s.k === 'recurring'" class="ldg-sec-foot">
        <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerRunDueNow()">⏱ 立即补跑到期交易</button>
        <span class="ldg-tip">到期交易每天凌晨 01:00 自动记账，也可点此手动补跑</span>
      </div>
    </div>

    <!-- ─────────── 预算弹窗（M2）─────────── -->
    <div v-if="appCtx.ledgerBudgetDialog.show" class="modal-mask on" @click.self="appCtx.ledgerCloseBudgetDialog()">
      <div class="modal-card ldg-dialog">
        <div class="modal-head">
          <b>{{ appCtx.ledgerBudgetDialog.id ? '编辑预算' : '新建预算' }}</b>
          <button class="icon-btn" @click="appCtx.ledgerCloseBudgetDialog()">✕</button>
        </div>
        <div class="ldg-dialog-body">
          <div class="ldg-field">
            <label class="ldg-field-label">预算口径</label>
            <select v-model="appCtx.ledgerBudgetDialog.form.scope_type" class="fill-input">
              <option value="month">本月总预算</option>
              <option value="category">分类预算</option>
              <option value="project">项目预算</option>
            </select>
          </div>
          <div v-if="appCtx.ledgerBudgetDialog.form.scope_type === 'category'" class="ldg-field">
            <label class="ldg-field-label">分类</label>
            <select v-model="appCtx.ledgerBudgetDialog.form.scope_id" class="fill-input">
              <option value="">选择分类</option>
              <option v-for="c in appCtx.ledgerAllCats()" :key="'bc' + c.id" :value="String(c.id)">{{ appCtx.ledgerCatLabel(c) }}</option>
            </select>
          </div>
          <div v-else-if="appCtx.ledgerBudgetDialog.form.scope_type === 'project'" class="ldg-field">
            <label class="ldg-field-label">项目</label>
            <select v-model="appCtx.ledgerBudgetDialog.form.scope_id" class="fill-input">
              <option value="">选择项目</option>
              <option v-for="p in appCtx.ledgerProjects" :key="'bp' + p.id" :value="String(p.id)">{{ p.name }}</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">预算金额(元)</label>
            <input v-model="appCtx.ledgerBudgetDialog.form.amount" type="number" step="0.01" min="0" class="fill-input">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">预警阈值（0~1.5，0.8 = 用到 80% 时提醒）</label>
            <input v-model="appCtx.ledgerBudgetDialog.form.notify_threshold" type="number" step="0.05" min="0" max="1.5" class="fill-input">
          </div>
        </div>
        <div class="ldg-dialog-foot">
          <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerCloseBudgetDialog()">取消</button>
          <button class="btn btn-primary btn-sm" @click="appCtx.ledgerSaveBudget()">保存</button>
        </div>
      </div>
    </div>

    <!-- ─────────── 借贷弹窗（M3）─────────── -->
    <div v-if="appCtx.ledgerDebtDialog.show" class="modal-mask on" @click.self="appCtx.ledgerCloseDebtDialog()">
      <div class="modal-card ldg-dialog">
        <div class="modal-head">
          <b>{{ appCtx.ledgerDebtDialog.id ? '编辑借贷' : '记一笔借贷' }}</b>
          <button class="icon-btn" @click="appCtx.ledgerCloseDebtDialog()">✕</button>
        </div>
        <div class="ldg-dialog-body">
          <div class="ldg-field">
            <label class="ldg-field-label">方向</label>
            <select v-model="appCtx.ledgerDebtDialog.form.direction" class="fill-input">
              <option value="lend">借出（别人欠我）</option>
              <option value="borrow">借入（我欠别人）</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">对方</label>
            <select v-model="appCtx.ledgerDebtDialog.form.person_id" class="fill-input">
              <option value="">（不指定）</option>
              <option v-for="p in appCtx.ledgerPersons" :key="'dp' + p.id" :value="String(p.id)">{{ p.name }}</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">金额(元)</label>
            <input v-model="appCtx.ledgerDebtDialog.form.total" type="number" step="0.01" min="0" class="fill-input">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">到期日</label>
            <input v-model="appCtx.ledgerDebtDialog.form.due_date" type="date" class="fill-input">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">备注</label>
            <input v-model="appCtx.ledgerDebtDialog.form.note" class="fill-input" maxlength="200">
          </div>
        </div>
        <div class="ldg-dialog-foot">
          <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerCloseDebtDialog()">取消</button>
          <button class="btn btn-primary btn-sm" @click="appCtx.ledgerSaveDebt()">保存</button>
        </div>
      </div>
    </div>

    <!-- ─────────── 还款 / 收款弹窗（M3）─────────── -->
    <div v-if="appCtx.ledgerRepayDialog.show" class="modal-mask on" @click.self="appCtx.ledgerCloseRepayDialog()">
      <div class="modal-card ldg-dialog">
        <div class="modal-head">
          <b>{{ appCtx.ledgerRepayDialog.debt && appCtx.ledgerRepayDialog.debt.direction === 'lend' ? '登记收款' : '登记还款' }}</b>
          <button class="icon-btn" @click="appCtx.ledgerCloseRepayDialog()">✕</button>
        </div>
        <div class="ldg-dialog-body" v-if="appCtx.ledgerRepayDialog.debt">
          <p class="ldg-refund-src">
            {{ appCtx.ledgerDebtPersonName(appCtx.ledgerRepayDialog.debt) }} ·
            {{ appCtx.ledgerRepayDialog.debt.direction === 'lend' ? '借出' : '借入' }}
            {{ appCtx.ledgerFmt(appCtx.ledgerRepayDialog.debt.total) }} 元 ·
            未结 {{ appCtx.ledgerFmt(appCtx.ledgerRepayDialog.debt.balance) }} 元
          </p>
          <div class="ldg-field">
            <label class="ldg-field-label">本次金额(元)</label>
            <input v-model="appCtx.ledgerRepayDialog.form.amount" type="number" step="0.01" min="0" class="fill-input">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">资金进出账户</label>
            <select v-model="appCtx.ledgerRepayDialog.form.from_account_id" class="fill-input">
              <option value="">选择账户</option>
              <option v-for="a in appCtx.ledgerAccounts" :key="'rp' + a.id" :value="String(a.id)">{{ a.account_name }}</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">备注</label>
            <input v-model="appCtx.ledgerRepayDialog.form.note" class="fill-input" maxlength="200">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">交易时间</label>
            <input v-model="appCtx.ledgerRepayDialog.form.transaction_time" type="datetime-local" class="fill-input">
          </div>
        </div>
        <div class="ldg-dialog-foot">
          <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerCloseRepayDialog()">取消</button>
          <button class="btn btn-primary btn-sm" @click="appCtx.ledgerSubmitRepay()">确认</button>
        </div>
      </div>
    </div>

    <!-- ─────────── 记账模板弹窗（M4）─────────── -->
    <div v-if="appCtx.ledgerTemplateDialog.show" class="modal-mask on" @click.self="appCtx.ledgerCloseTemplateDialog()">
      <div class="modal-card ldg-dialog">
        <div class="modal-head">
          <b>{{ appCtx.ledgerTemplateDialog.id ? '编辑模板' : '新建模板' }}</b>
          <button class="icon-btn" @click="appCtx.ledgerCloseTemplateDialog()">✕</button>
        </div>
        <div class="ldg-dialog-body">
          <div class="ldg-field">
            <label class="ldg-field-label">模板名称</label>
            <input v-model="appCtx.ledgerTemplateDialog.form.name" class="fill-input" maxlength="30" placeholder="如：早餐豆浆油条">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">类型</label>
            <select v-model="appCtx.ledgerTemplateDialog.form.transaction_type" class="fill-input">
              <option value="expense">支出</option>
              <option value="income">收入</option>
              <option value="transfer">转账</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">金额(元，可空＝用时再填)</label>
            <input v-model="appCtx.ledgerTemplateDialog.form.amount" type="number" step="0.01" min="0" class="fill-input">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">分类</label>
            <select v-model="appCtx.ledgerTemplateDialog.form.category_id" class="fill-input">
              <option value="">（不指定）</option>
              <option v-for="c in appCtx.ledgerAllCats()" :key="'tc' + c.id" :value="String(c.id)">{{ appCtx.ledgerCatLabel(c) }}</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">账户</label>
            <select v-model="appCtx.ledgerTemplateDialog.form.from_account_id" class="fill-input">
              <option value="">（不指定）</option>
              <option v-for="a in appCtx.ledgerAccounts" :key="'ta' + a.id" :value="String(a.id)">{{ a.account_name }}</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">备注</label>
            <input v-model="appCtx.ledgerTemplateDialog.form.note" class="fill-input" maxlength="200">
          </div>
        </div>
        <div class="ldg-dialog-foot">
          <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerCloseTemplateDialog()">取消</button>
          <button class="btn btn-primary btn-sm" @click="appCtx.ledgerSaveTemplate()">保存</button>
        </div>
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
        { k: 'budgets', label: '预算', icon: '🎯' },
        { k: 'debts', label: '借贷', icon: '🤝' },
        { k: 'templates', label: '记账模板', icon: '📋' },
      ],
      // 借贷清单的状态筛选（'' 全部 / active 未结清 / cleared 已结清）
      debtFilters: [
        { k: 'active', label: '未结清' },
        { k: 'cleared', label: '已结清' },
        { k: '', label: '全部' },
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
        budgets: this.appCtx.ledgerBudgetList,
        debts: this.appCtx.ledgerDebts,
        templates: this.appCtx.ledgerTemplates,
      };
      return map[k] || [];
    },
    // 新建：六维/周期交易走通用弹窗，预算/借贷/模板各有专属弹窗（字段差异大，不强行塞进 LEDGER_DIMS）
    openNew(k) {
      if (k === 'budgets') return this.appCtx.ledgerOpenBudgetDialog(null);
      if (k === 'debts') return this.appCtx.ledgerOpenDebtDialog(null);
      if (k === 'templates') return this.appCtx.ledgerOpenTemplateDialog(null);
      return this.appCtx.ledgerOpenDimDialog(k, null);
    },
    openEdit(k, item) {
      if (k === 'budgets') return this.appCtx.ledgerOpenBudgetDialog(item);
      if (k === 'debts') return this.appCtx.ledgerOpenDebtDialog(item);
      if (k === 'templates') return this.appCtx.ledgerOpenTemplateDialog(item);
      return this.appCtx.ledgerOpenDimDialog(k, item);
    },
    removeDim(k, item) {
      if (k === 'budgets') return this.appCtx.ledgerDeleteBudget(item);
      if (k === 'debts') return this.appCtx.ledgerDeleteDebt(item);
      if (k === 'templates') return this.appCtx.ledgerDeleteTemplate(item);
      return this.appCtx.ledgerDeleteDim(k, item);
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
/* 预算/借贷/模板/还款 弹窗（与 LedgerView 通用弹窗同款，此处独立一份避免跨组件样式依赖） */
.ldg-dialog { width: min(420px, 92vw); }
.ldg-dialog-body { max-height: 60vh; overflow-y: auto; padding: 4px 0; }
.ldg-field { margin-bottom: 10px; }
.ldg-field-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 4px; }
.ldg-dialog-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.ldg-refund-src { font-size: 12.5px; color: #8a8fa3; background: #f9f8fd; border-radius: 8px; padding: 8px 10px; margin: 0 0 12px; }
.ldg-chip { border: 1px solid #e5e1f5; background: #fff; color: #5a5470; border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; }
.ldg-chip-on { background: #8b7cf6; border-color: #8b7cf6; color: #fff; }
.ldg-tip { font-size: 11.5px; color: #a8a3b8; }
@media (max-width: 640px) {
  .ldg-row-main { flex-wrap: wrap; }
  .ldg-row-sub { flex-basis: 100%; }
}
</style>
