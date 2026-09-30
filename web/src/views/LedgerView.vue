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
        <!-- M2 提醒铃铛：预算超支提醒条数角标 -->
        <button class="ldg-bell" :class="{ on: appCtx.ledgerNotifOpen }" title="预算提醒"
                @click="appCtx.ledgerToggleNotif()">
          🔔<i v-if="appCtx.ledgerUnreadNotifCount" class="ldg-bell-dot">{{ appCtx.ledgerUnreadNotifCount }}</i>
        </button>
      </div>

      <!-- 提醒面板（预算超支/预警，数据来自 notifications/） -->
      <div v-if="appCtx.ledgerNotifOpen" class="ldg-notif">
        <div v-if="!appCtx.ledgerNotifItems.length" class="ldg-notif-empty">暂无提醒</div>
        <div v-for="n in appCtx.ledgerNotifItems" :key="'nf' + n.id" class="ldg-notif-row" :class="n.level">
          <span class="ldg-notif-name">{{ n.scope_name }}</span>
          <span class="ldg-notif-txt">已用 {{ appCtx.ledgerFmt(n.spent) }} / {{ appCtx.ledgerFmt(n.amount) }} 元（{{ Math.round(n.ratio * 100) }}%）</span>
          <span class="ldg-notif-time">{{ (n.created_at || '').slice(5, 16).replace('T', ' ') }}</span>
        </div>
      </div>

      <!-- M1 账本切换条：多账本横向切换，当前账本高亮；可新建/改名/删除 -->
      <div class="ldg-books">
        <button v-for="b in appCtx.ledgerBooks" :key="'bk' + b.id" class="ldg-book"
                :class="{ on: appCtx.ledgerCurrentBookId === b.id }"
                @click="appCtx.ledgerSwitchBook(b.id)">
          <i class="ldg-book-ico">{{ b.icon || '📘' }}</i>
          <span class="ldg-book-name">{{ b.name }}</span>
          <span class="ldg-book-bal">{{ appCtx.ledgerFmt(b.balance) }}</span>
          <i v-if="b.is_default" class="ldg-book-def" title="默认账本">默</i>
        </button>
        <button class="ldg-book ldg-book-add" title="新建账本" @click="appCtx.ledgerOpenBookDialog(null)">＋ 账本</button>
        <button v-if="appCtx.ledgerCurrentBook" class="ldg-book-edit" title="编辑当前账本"
                @click="appCtx.ledgerOpenBookDialog(appCtx.ledgerCurrentBook)">⚙️</button>
      </div>

      <!-- 预算提醒横幅：任一项目超支即提示（数据来自 statistics/budget） -->
      <div v-if="appCtx.ledgerBudgetOverruns.length" class="ldg-budget-alert">
        ⚠️ 预算提醒：<template v-for="(b, i) in appCtx.ledgerBudgetOverruns" :key="'ba' + b.project_id"><template v-if="i">、</template>{{ b.project_name }} 已超 {{ appCtx.ledgerFmt(b.spent - b.budget) }} 元</template>
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

    <!-- M1 账本新建/编辑弹窗 -->
    <div v-if="appCtx.ledgerBookDialog.show" class="modal-mask on" @click.self="appCtx.ledgerCloseBookDialog()">
      <div class="modal-card ldg-dialog">
        <div class="modal-head">
          <b>{{ appCtx.ledgerBookDialog.id ? '编辑账本' : '新建账本' }}</b>
          <button class="icon-btn" @click="appCtx.ledgerCloseBookDialog()">✕</button>
        </div>
        <div class="ldg-dialog-body">
          <div class="ldg-field">
            <label class="ldg-field-label">账本名称</label>
            <input v-model="appCtx.ledgerBookDialog.form.name" class="fill-input" maxlength="30" placeholder="如：暑期旅行账本">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">类型</label>
            <select v-model="appCtx.ledgerBookDialog.form.book_type" class="fill-input">
              <option v-for="t in bookTypes" :key="t.v" :value="t.v">{{ t.t }}</option>
            </select>
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">图标</label>
            <input v-model="appCtx.ledgerBookDialog.form.icon" class="fill-input" maxlength="4" placeholder="📘">
          </div>
          <div class="ldg-field">
            <label class="ldg-field-label">颜色</label>
            <input v-model="appCtx.ledgerBookDialog.form.color" type="color" class="fill-input ldg-color">
          </div>
          <label class="ldg-check" v-if="!appCtx.ledgerBookDialog.id">
            <input type="checkbox" v-model="appCtx.ledgerBookDialog.form.is_default"> 设为默认账本
          </label>
        </div>
        <div class="ldg-dialog-foot">
          <button v-if="appCtx.ledgerBookDialog.id && appCtx.ledgerCurrentBook && !appCtx.ledgerCurrentBook.is_default"
                  class="btn btn-ghost btn-sm ldg-foot-del" @click="appCtx.ledgerDeleteBook(appCtx.ledgerCurrentBook)">删除</button>
          <button class="btn btn-ghost btn-sm" @click="appCtx.ledgerCloseBookDialog()">取消</button>
          <button class="btn btn-primary btn-sm" @click="appCtx.ledgerSaveBook()">保存</button>
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
import { LEDGER_DIMS, LEDGER_BOOK_TYPES } from '../logic/ledger.js'

export default {
  name: 'LedgerView',
  inject: ['appCtx'],
  components: { LedgerRecord, LedgerBills, LedgerAnalysis, LedgerSettings },
  data() {
    return {
      // 纯 UI 常量（非业务状态）：内部 tab 定义 + 账本类型下拉
      tabs: [
        { k: 'add', label: '✏️ 记一笔' },
        { k: 'bills', label: '📄 账单' },
        { k: 'analysis', label: '📊 分析' },
        { k: 'settings', label: '⚙️ 设置' },
      ],
      bookTypes: LEDGER_BOOK_TYPES,
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
.ldg-budget-alert { background: #fdecec; color: #c0392b; border: 1px solid #f5c6c6; border-radius: 10px; padding: 8px 12px; font-size: 13px; margin-bottom: 12px; }
.ldg-dialog { width: min(420px, 92vw); }
.ldg-dialog-body { max-height: 60vh; overflow-y: auto; padding: 4px 0; }
.ldg-field { margin-bottom: 10px; }
.ldg-field-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 4px; }
.ldg-dialog-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.ldg-color { height: 38px; padding: 2px; }
.ldg-check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #5a5470; }
.ldg-foot-del { margin-right: auto; color: #c0392b; }
/* 提醒铃铛 */
.ldg-bell { position: relative; margin-left: auto; border: none; background: transparent; font-size: 15px; cursor: pointer; opacity: .7; }
.ldg-bell:hover, .ldg-bell.on { opacity: 1; }
.ldg-bell-dot {
  position: absolute; top: -4px; right: -6px; min-width: 15px; height: 15px; padding: 0 3px;
  background: #e57373; color: #fff; border-radius: 999px; font-size: 10px; font-style: normal;
  line-height: 15px; text-align: center;
}
.ldg-notif { background: #f9f8fd; border: 1px solid #efedf7; border-radius: 10px; padding: 8px 10px; margin-bottom: 12px; }
.ldg-notif-empty { text-align: center; color: #a8a3b8; font-size: 12.5px; padding: 6px 0; }
.ldg-notif-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 12.5px; border-bottom: 1px dashed #efedf7; }
.ldg-notif-row:last-child { border-bottom: none; }
.ldg-notif-row.over .ldg-notif-txt { color: #c0392b; font-weight: 600; }
.ldg-notif-name { font-weight: 600; color: #5a5470; flex: none; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ldg-notif-txt { flex: 1; color: #8a8fa3; }
.ldg-notif-time { flex: none; color: #a8a3b8; font-size: 11px; }
/* 账本切换条 */
.ldg-books { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.ldg-book {
  display: inline-flex; align-items: center; gap: 6px; border: 1px solid #e5e1f5; background: #fff;
  color: #5a5470; border-radius: 999px; padding: 5px 12px; font-size: 13px; cursor: pointer;
  transition: background .12s, border-color .12s;
}
.ldg-book:hover { background: #f3f0fc; }
.ldg-book.on { background: #8b7cf6; border-color: #8b7cf6; color: #fff; font-weight: 600; }
.ldg-book-ico { font-style: normal; }
.ldg-book-name { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ldg-book-bal { font-size: 11.5px; opacity: .75; }
.ldg-book-def {
  font-style: normal; font-size: 10px; background: rgba(255, 255, 255, .28);
  border-radius: 4px; padding: 0 4px;
}
.ldg-book.on .ldg-book-def { background: rgba(255, 255, 255, .3); }
.ldg-book-add { border-style: dashed; color: #8b7cf6; }
.ldg-book-edit { border: none; background: transparent; cursor: pointer; opacity: .55; font-size: 14px; }
.ldg-book-edit:hover { opacity: 1; }
</style>
