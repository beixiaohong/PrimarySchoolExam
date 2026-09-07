<template>
  <!-- 账本壳视图（tab='ledger'）：4 个内部 tab（记一笔/账单/分析/设置）。
       业务逻辑全部在 logic/ledger.js（经 appOptions 展开合并进 App 壳），
       本视图与子组件仅 inject appCtx，自身零业务 data/methods（沿用 ParentView 约定）。 -->
  <div class="fade-enter">
    <div class="card ledger-card">
      <div class="card-head">
        <b><app-icon name="ledger" :size="18"></app-icon> 记账本</b>
        <span class="more" v-if="appCtx.ledgerSummary">总余额 {{ appCtx.ledgerFmt(appCtx.ledgerSummary.total_assets) }} 元</span>
        <span class="more" v-else>零花钱收支，自己管</span>
      </div>

      <div class="ldg-tabs">
        <button v-for="t in tabs" :key="t.k" class="ldg-tab" :class="{ on: appCtx.ledgerTab === t.k }"
                @click="appCtx.ledgerGoTab(t.k)">{{ t.label }}</button>
      </div>

      <div v-if="appCtx.ledgerLoading" class="ldg-empty">🔄 正在加载账本数据…</div>
      <template v-else>
        <ledger-record v-if="appCtx.ledgerTab === 'add'"></ledger-record>
        <ledger-bills v-if="appCtx.ledgerTab === 'bills'"></ledger-bills>
        <ledger-analysis v-if="appCtx.ledgerTab === 'analysis'"></ledger-analysis>
        <ledger-settings v-if="appCtx.ledgerTab === 'settings'"></ledger-settings>
      </template>
    </div>

    <!-- 六维 CRUD / 周期交易 通用编辑弹窗（字段由 LEDGER_DIMS 定义驱动） -->
    <div v-if="appCtx.ledgerDimDialog.show" class="modal-mask on" @click.self="appCtx.ledgerCloseDimDialog()">
      <div class="modal-card ldg-dialog">
        <div class="modal-head">
          <b>{{ appCtx.ledgerDimDialog.id ? '编辑' : '新建' }}{{ dimLabel }}</b>
          <button class="icon-btn" @click="appCtx.ledgerCloseDimDialog()">✕</button>
        </div>
        <div class="ldg-dialog-body">
          <div v-for="fd in dimFields" :key="fd.k" class="ldg-field">
            <label class="ldg-field-label">{{ fd.label }}</label>
            <select v-if="fd.type === 'select'" v-model="appCtx.ledgerDimDialog.form[fd.k]" class="fill-input">
              <option v-for="o in fd.options" :key="o.v" :value="o.v">{{ o.t }}</option>
            </select>
            <select v-else-if="fd.type === 'account'" v-model="appCtx.ledgerDimDialog.form[fd.k]" class="fill-input">
              <option value="">（未选择）</option>
              <option v-for="a in appCtx.ledgerAccounts" :key="a.id" :value="String(a.id)">{{ a.account_name }}</option>
            </select>
            <select v-else-if="fd.type === 'category'" v-model="appCtx.ledgerDimDialog.form[fd.k]" class="fill-input">
              <option value="">（未选择）</option>
              <option v-for="c in appCtx.ledgerAllCats()" :key="c.id" :value="String(c.id)">{{ appCtx.ledgerCatLabel(c) }}</option>
            </select>
            <input v-else-if="fd.type === 'datetime'" v-model="appCtx.ledgerDimDialog.form[fd.k]" type="datetime-local" class="fill-input">
            <input v-else-if="fd.num" v-model="appCtx.ledgerDimDialog.form[fd.k]" type="number" step="0.01" min="0" class="fill-input">
            <input v-else v-model="appCtx.ledgerDimDialog.form[fd.k]" class="fill-input" :placeholder="fd.ph || ''">
          </div>
        </div>
        <div class="ldg-dialog-foot">
          <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerCloseDimDialog()">取消</button>
          <button class="btn btn-primary btn-sm" @click="appCtx.ledgerSaveDim()">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// LedgerView（个人账本独立视图，tab='ledger'）。壳 provide appCtx=this，本视图 inject 使用；
// 4 个内部 tab 拆为 components/ledger/ 下的 4 个子组件（与 components/parent/ 同构）。
import LedgerRecord from '../components/ledger/LedgerRecord.vue'
import LedgerBills from '../components/ledger/LedgerBills.vue'
import LedgerAnalysis from '../components/ledger/LedgerAnalysis.vue'
import LedgerSettings from '../components/ledger/LedgerSettings.vue'
import { LEDGER_DIMS } from '../logic/ledger.js'

export default {
  name: 'LedgerView',
  inject: ['appCtx'],
  components: { LedgerRecord, LedgerBills, LedgerAnalysis, LedgerSettings },
  data() {
    return {
      // 纯 UI 常量（非业务状态）：内部 tab 定义
      tabs: [
        { k: 'add', label: '✏️ 记一笔' },
        { k: 'bills', label: '📄 账单' },
        { k: 'analysis', label: '📊 分析' },
        { k: 'settings', label: '⚙️ 设置' },
      ],
    }
  },
  computed: {
    dimLabel() {
      const d = LEDGER_DIMS[this.appCtx.ledgerDimDialog.dim]
      return d ? d.label : ''
    },
    dimFields() {
      const d = LEDGER_DIMS[this.appCtx.ledgerDimDialog.dim]
      return d ? d.fields : []
    },
  },
}
</script>

<style scoped>
/* 账本样式独立 scoped（style.css 当前混有并行任务未提交改动，避免提交纠缠；
   项目已有 scoped 先例：AntiCheatInput.vue） */
.ledger-card { max-width: 860px; }
.ledger-card .card-head b { display: inline-flex; align-items: center; gap: 6px; }
.ldg-tabs { display: flex; gap: 8px; margin: 10px 0 14px; flex-wrap: wrap; }
.ldg-tab {
  border: 1px solid #e5e1f5; background: #fff; color: #5a5470;
  border-radius: 999px; padding: 6px 16px; font-size: 14px; cursor: pointer;
  transition: background .12s, color .12s;
}
.ldg-tab:hover { background: #f3f0fc; }
.ldg-tab.on { background: #8b7cf6; border-color: #8b7cf6; color: #fff; font-weight: 600; }
.ldg-empty { text-align: center; color: #999; padding: 32px 0; font-size: 14px; }
.ldg-dialog { width: min(420px, 92vw); }
.ldg-dialog-body { max-height: 60vh; overflow-y: auto; padding: 4px 0; }
.ldg-field { margin-bottom: 10px; }
.ldg-field-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 4px; }
.ldg-dialog-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
</style>
