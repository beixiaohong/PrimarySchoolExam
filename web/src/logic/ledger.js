// logic/ledger.js：个人账本视图（tab='ledger'）专属的 data / computed / methods。
//
// 由来（docs/IM与账本前端实现方案.md §3.1）：与 parent.js 同构——导出三个纯字典，
// 由 appOptions.js 用展开运算符合并（刻意不用 Vue mixin 数组）：
//   data()    { return { ...ledgerData(),  ...其余 } }
//   computed:  { ...ledgerComputed, ...其余 }
//   methods:   { ...ledgerMethods,  ...其余 }
// 展开后 this 仍绑定同一个 App 实例（App.vue provide appCtx=this），LedgerView 及其子组件
// 仅 inject appCtx 访问，自身零业务 data/methods。
// 收尾强制校验：本文件全部键带 ledger/ldg 语义前缀，与 appOptions/parent 键交集必须为空。
//
// 金额口径（关键）：后端 Bill.amount / Account.balance 为 Numeric(15,2)「元」单位，
// schema 为 float——前端提交一律送「元」（round 2 位小数），**不做 ×100 转分**
// （实现方案 §3.2 的「×100 转分」与后端口径矛盾，以后端为准）。
//
// 多账本口径（M1）：ledgerCurrentBookId 为当前账本；为空串/0 时不带 book_id，
// 由后端 _resolve_book_id 回落到默认账本。切换账本后必须整树重载（六维/统计/借贷/模板）。
// 注意：只有 accounts / projects / recurring 三类维度在 POST 时接受 book_id，
// 而 GET 仅 accounts 接受 book_id 过滤（分类/地点/商户/人员/项目/周期交易为共享或后端未过滤）。

// 可选币种（M4 多币种）：本位币 CNY，其余按 rate_to_base 折算后入账。
// 必须声明在 LEDGER_DIMS 之前——LEDGER_DIMS 是模块级常量，求值时会读取本数组
// （const 有暂时性死区，反序声明会抛 ReferenceError）。
export const LEDGER_CURRENCY_OPTIONS = [
  { v: 'CNY', t: '人民币 CNY（本位币）' },
  { v: 'USD', t: '美元 USD' }, { v: 'EUR', t: '欧元 EUR' }, { v: 'HKD', t: '港币 HKD' },
  { v: 'JPY', t: '日元 JPY' }, { v: 'GBP', t: '英镑 GBP' }, { v: 'KRW', t: '韩元 KRW' },
  { v: 'SGD', t: '新币 SGD' }, { v: 'AUD', t: '澳元 AUD' }, { v: 'TWD', t: '新台币 TWD' },
];

// 设置 tab 的六个 CRUD 维度 + 周期交易的表单字段定义（LedgerSettings.vue 渲染用）。
// bookScoped=true 表示创建时需随 body 带上当前 book_id（账户/项目/周期交易）。
export const LEDGER_DIMS = {
  accounts:  { label: '账户', path: 'accounts', bookScoped: true, fields: [
    { k: 'account_name', label: '账户名称', ph: '如：零花钱卡' },
    { k: 'account_type', label: '账户类型', type: 'select', options: [
      { v: 'savings_card', t: '储蓄卡' }, { v: 'credit_card', t: '信用卡' }, { v: 'virtual_account', t: '虚拟账户' }] },
    { k: 'balance', label: '初始余额(元)', num: true, def: 0 },
    { k: 'currency', label: '币种', type: 'select', def: 'CNY', options: LEDGER_CURRENCY_OPTIONS },
    { k: 'rate_to_base', label: '折算汇率(1 外币 = ? 元)', num: true, def: 1, ph: '本位币 CNY 填 1' },
    { k: 'due_day', label: '还款日(1-31，仅信用卡)', num: true, int: true, ph: '可空' }] },
  categories: { label: '分类', path: 'categories', fields: [
    { k: 'category_type', label: '分类类型', type: 'select', options: [
      { v: 'EXPENSE', t: '支出' }, { v: 'INCOME', t: '收入' }] },
    { k: 'level1', label: '一级分类', ph: '如：餐饮' },
    { k: 'level2', label: '二级分类', ph: '可空' },
    { k: 'level3', label: '三级分类', ph: '可空' }] },
  locations: { label: '地点', path: 'locations', fields: [
    { k: 'name', label: '地点名称', ph: '如：学校门口' },
    { k: 'address', label: '地址', ph: '可空' }] },
  merchants: { label: '商户', path: 'merchants', fields: [
    { k: 'name', label: '商户名称', ph: '如：新华书店' },
    { k: 'description', label: '描述', ph: '可空' }] },
  persons:   { label: '人员', path: 'persons', fields: [
    { k: 'name', label: '姓名', ph: '如：妈妈' },
    { k: 'phone', label: '电话', ph: '可空' },
    { k: 'relationship', label: '关系', ph: '可空' }] },
  projects:  { label: '项目', path: 'projects', bookScoped: true, fields: [
    { k: 'name', label: '项目名称', ph: '如：暑期旅行' },
    { k: 'description', label: '描述', ph: '可空' },
    { k: 'budget', label: '预算(元)', num: true }] },
  recurring: { label: '周期交易', path: 'recurring', bookScoped: true, fields: [
    { k: 'name', label: '名称', ph: '如：每月零花钱' },
    { k: 'transaction_type', label: '类型', type: 'select', options: [
      { v: 'expense', t: '支出' }, { v: 'income', t: '收入' }] },
    { k: 'amount', label: '金额(元)', num: true },
    { k: 'from_account_id', label: '账户', type: 'account' },
    { k: 'category_id', label: '分类', type: 'category' },
    { k: 'frequency', label: '频率', type: 'select', options: [
      { v: 'daily', t: '每日' }, { v: 'weekly', t: '每周' }, { v: 'monthly', t: '每月' }, { v: 'yearly', t: '每年' }] },
    { k: 'next_run', label: '下次执行', type: 'datetime' },
    { k: 'note', label: '备注', ph: '可空' }] },
};

// 账本类型（M1）：book_type 仅作展示分类，后端不校验取值
export const LEDGER_BOOK_TYPES = [
  { v: 'daily', t: '日常' }, { v: 'travel', t: '旅行' }, { v: 'family', t: '家庭' },
  { v: 'business', t: '生意' }, { v: 'other', t: '其他' },
];

// 分析环形图配色（Top6 + 其他；与全站紫色系协调的手写 SVG 用色）
const DONUT_COLORS = ['#8b7cf6', '#f6a87c', '#7cc5f6', '#7cf6b8', '#f67ca8', '#c5f67c', '#b9b3d0'];

// 币种符号（仅展示用，折算一律走后端 rate_to_base）
const CURRENCY_SYMBOL = { CNY: '¥', USD: '$', EUR: '€', HKD: 'HK$', JPY: '¥', GBP: '£', KRW: '₩', SGD: 'S$', AUD: 'A$', TWD: 'NT$' };

// ─────────── 账本 data（由 appOptions.data 用 ...ledgerData() 合并）───────────
export function ledgerData() {
  return {
    ledgerTab: 'add',           // 内部 4 tab：add 记一笔 / bills 账单 / analysis 分析 / settings 设置
    ledgerLoading: false,       // 基础维度（账户/分类等）首次加载中
    ledgerBaseLoaded: false,
    // Tab1 记一笔表单（editId 非空 = 编辑既有账单）
    ledgerForm: {
      editId: null, transaction_type: 'expense', amount: '',
      from_account_id: '', to_account_id: '',
      catL1: '', catL2: '', catL3: '',
      location_id: '', merchant_id: '', person_id: '', project_id: '',
      note: '', transaction_time: '',
      // M4 多币种：currency=CNY 时 amount 即本位币金额；非 CNY 时填 amount_orig + rate_to_base
      currency: 'CNY', amount_orig: '', rate_to_base: '',
      // M3 退款：refund_of_id 指向被退的那一笔
      refund_of_id: '', attachment_url: '',
    },
    ledgerRecentCats: [],       // 最近使用分类（localStorage 缓存最近 6 个 id）
    // Tab2 账单：筛选 + 列表 + 分页
    ledgerBills: [],
    ledgerBillsPage: 0,
    ledgerBillsMore: false,
    ledgerBillFilter: {
      range: 'month',           // month 本月 / last 上月 / quarter 近3月 / custom 自定义 / '' 全部
      start_date: '', end_date: '',
      transaction_type: '', category_id: '', account_id: '', project_id: '',
      min_amount: '', max_amount: '', keyword: '',
    },
    // Tab3 分析
    ledgerSummary: null,        // {total_assets, monthly_income, monthly_expense, monthly_balance, month_budget}
    ledgerCatStats: [],         // statistics/category 原始行
    ledgerMonthly: [],          // statistics/monthly 的 monthly_data
    ledgerMonthlyYear: new Date().getFullYear(),
    ledgerBudget: [],           // statistics/budget 行（项目预算，M2 之前的旧口径）
    ledgerPeriod: 'month',      // 分类统计周期：month / quarter / year
    // Tab4 设置：六维数据 + 周期交易 + 通用编辑弹窗
    ledgerAccounts: [], ledgerCategories: [], ledgerLocations: [],
    ledgerMerchants: [], ledgerPersons: [], ledgerProjects: [], ledgerRecurring: [],
    ledgerDimDialog: { show: false, dim: '', id: null, form: {} },
    ledgerNewDim: '',           // 各区块「+ 新建」下拉暂存（快捷新建入口）

    /* ─────────── M1 多账本 ─────────── */
    ledgerBooks: [],            // 账本列表（GET books/，含 balance 聚合）
    ledgerCurrentBookId: null,  // 当前账本 id（null = 交后端回落到默认账本）
    ledgerBookDialog: { show: false, id: null, form: { name: '', book_type: 'daily', icon: '📘', color: '#8b7cf6', is_default: false } },

    /* ─────────── M2 预算 ─────────── */
    ledgerBudgetList: [],       // budgets/ 列表（管理用，原始行）
    ledgerBudgetExec: null,     // statistics/budgets → {month_start, month_end, budgets:[...]}
    ledgerBudgetDialog: { show: false, id: null, form: { scope_type: 'month', scope_id: '', amount: '', notify_threshold: '0.8' } },
    ledgerNotifications: [],    // notifications/ 提醒列表（预算超支等）

    /* ─────────── M3 借贷 / 净资产 / 退款 ─────────── */
    ledgerDebts: [],            // debts/ 借贷清单
    ledgerDebtFilter: 'active', // '' 全部 / active 未结清 / cleared 已结清
    ledgerDebtDialog: { show: false, id: null, form: { person_id: '', direction: 'lend', total: '', due_date: '', note: '' } },
    ledgerRepayDialog: { show: false, debt: null, form: { amount: '', from_account_id: '', note: '', transaction_time: '' } },
    ledgerNetWorth: null,       // statistics/networth
    ledgerRefundDialog: { show: false, bill: null, form: { amount: '', from_account_id: '', note: '', transaction_time: '' } },

    /* ─────────── M4 记账模板 ─────────── */
    ledgerTemplates: [],        // templates/ 模板列表
    ledgerTemplateDialog: { show: false, id: null, form: { name: '', transaction_type: 'expense', amount: '', category_id: '', from_account_id: '', to_account_id: '', note: '' } },

    ledgerNotifOpen: false,     // 顶部提醒铃铛面板展开态
  };
}

// ─────────── 账本 computed（由 appOptions.computed 用 ...ledgerComputed 合并）───────────
export const ledgerComputed = {
  /* ─────────── M1 多账本 ─────────── */
  // 当前账本对象（未选定则回落 is_default 账本）
  ledgerCurrentBook() {
    const id = Number(this.ledgerCurrentBookId) || 0;
    if (id) return (this.ledgerBooks || []).find(b => b.id === id) || null;
    return (this.ledgerBooks || []).find(b => b.is_default) || null;
  },
  // 当前账本名（卡片头展示）
  ledgerCurrentBookName() {
    const b = this.ledgerCurrentBook;
    return b ? b.name : '默认账本';
  },

  /* ─────────── Tab1 记一笔 ─────────── */
  // 当前记账类型对应的分类列表（category_type 按类型过滤：expense→EXPENSE / income→INCOME）
  ledgerCatsForType() {
    const t = (this.ledgerForm.transaction_type === 'income') ? 'INCOME' : 'EXPENSE';
    return (this.ledgerCategories || []).filter(c => c.category_type === t);
  },
  // 三级级联：一级选项
  ledgerCatL1Options() {
    return [...new Set(this.ledgerCatsForType.map(c => c.level1).filter(Boolean))];
  },
  // 三级级联：二级选项（随一级联动）
  ledgerCatL2Options() {
    const f = this.ledgerForm;
    return [...new Set(this.ledgerCatsForType
      .filter(c => c.level1 === f.catL1)
      .map(c => c.level2).filter(Boolean))];
  },
  // 三级级联：三级选项（随一二级联动）
  ledgerCatL3Options() {
    const f = this.ledgerForm;
    return [...new Set(this.ledgerCatsForType
      .filter(c => c.level1 === f.catL1 && (f.catL2 ? c.level2 === f.catL2 : !c.level2))
      .map(c => c.level3).filter(Boolean))];
  },
  // 级联当前命中的分类行（提交用 category_id）
  ledgerSelectedCategory() {
    const f = this.ledgerForm;
    if (!f.catL1) return null;
    return this.ledgerCatsForType.find(c =>
      c.level1 === f.catL1 &&
      (f.catL2 ? c.level2 === f.catL2 : !c.level2) &&
      (f.catL3 ? c.level3 === f.catL3 : !c.level3)) || null;
  },
  // 最近使用分类快捷区（id → 分类行）
  ledgerRecentCatItems() {
    return (this.ledgerRecentCats || [])
      .map(id => (this.ledgerCategories || []).find(c => c.id === id))
      .filter(Boolean);
  },
  // 当前是否为外币记账（决定表单显示「原币金额 + 汇率」还是直接「金额」）
  ledgerIsForeign() {
    return String(this.ledgerForm.currency || 'CNY').toUpperCase() !== 'CNY';
  },
  // 折算后的本位币金额（外币=原币×汇率；CNY=直接取 amount）
  ledgerFxBase() {
    const f = this.ledgerForm;
    if (!this.ledgerIsForeign) return Math.round((Number(String(f.amount).trim()) || 0) * 100) / 100;
    const o = Number(String(f.amount_orig).trim()) || 0;
    const r = Number(String(f.rate_to_base).trim()) || 0;
    return Math.round(o * r * 100) / 100;
  },
  // 外币折算提示语（原币 → 本位币）
  ledgerFxHint() {
    if (!this.ledgerIsForeign) return '';
    const f = this.ledgerForm;
    const o = Number(String(f.amount_orig).trim()) || 0;
    const r = Number(String(f.rate_to_base).trim()) || 0;
    if (!(o > 0) || !(r > 0)) return '';
    return `≈ ${this.ledgerFmt(this.ledgerFxBase)} 元（1 ${String(f.currency).toUpperCase()} = ${r} 元）`;
  },
  // 当前表单类型下的可用模板（M4 速记）
  ledgerTemplatesForType() {
    const t = this.ledgerForm.transaction_type;
    return (this.ledgerTemplates || []).filter(x => x.transaction_type === t);
  },
  // 选中项目后的预算执行率提示（分析 budget 数据复用；未加载/无预算返回空）
  ledgerProjectBudgetHint() {
    const pid = Number(this.ledgerForm.project_id);
    if (!pid) return '';
    const row = (this.ledgerBudget || []).find(b => b.project_id === pid);
    if (!row || !row.budget) return '';
    const pct = Math.round((row.spent / row.budget) * 100);
    return `「${row.project_name}」预算 ${this.ledgerFmt(row.budget)} 元，已用 ${this.ledgerFmt(row.spent)} 元（${pct}%）`;
  },
  // 超预算项目列表（顶部「预算提醒」横幅用；无预算或未超支返回空）
  ledgerBudgetOverruns() {
    return (this.ledgerBudget || []).filter(b => b && b.budget > 0 && b.spent > b.budget);
  },

  /* ─────────── M2 预算 / 提醒 ─────────── */
  // 预算执行行（statistics/budgets 的 budgets[]；未加载返回空数组）
  ledgerBudgetExecRows() {
    const d = this.ledgerBudgetExec;
    return (d && d.budgets) || [];
  },
  // 月度总预算（summary.month_budget，只读口径，不产生通知）
  ledgerMonthBudget() {
    const s = this.ledgerSummary;
    return (s && s.month_budget) || null;
  },
  // 未处理提醒条数（铃铛角标）
  ledgerUnreadNotifCount() {
    return (this.ledgerNotifications || []).filter(n => n && n.status === 'pending').length;
  },
  // 提醒面板行（content 为后端 JSON：{scope_type, scope_name, amount, spent, ratio, status}）
  ledgerNotifItems() {
    return (this.ledgerNotifications || []).map(n => {
      const c = (n && typeof n.content === 'object' && n.content) || {};
      return {
        id: n.id,
        status: n.status,
        created_at: n.created_at,
        scope_name: c.scope_name || (c.scope_type === 'month' ? '本月总预算' : '预算'),
        scope_type: c.scope_type || '',
        amount: Number(c.amount) || 0,
        spent: Number(c.spent) || 0,
        ratio: Number(c.ratio) || 0,
        level: c.status || 'warning',
      };
    });
  },

  /* ─────────── M3 借贷 / 净资产 ─────────── */
  // 借贷汇总：借出未收 / 借入未还（仅统计 active）
  ledgerDebtSummary() {
    let lend = 0, borrow = 0;
    for (const d of this.ledgerDebts || []) {
      if (d.status !== 'active') continue;
      const b = Number(d.balance) || 0;
      if (d.direction === 'lend') lend += b; else borrow += b;
    }
    return { lend: Math.round(lend * 100) / 100, borrow: Math.round(borrow * 100) / 100 };
  },

  /* ─────────── Tab2 账单 ─────────── */
  // 账单按日期分组（保持后端 transaction_time 倒序）
  ledgerBillGroups() {
    const groups = [];
    const idx = {};
    for (const b of this.ledgerBills) {
      const day = (b.transaction_time || '').slice(0, 10) || '未知日期';
      if (!(day in idx)) {
        idx[day] = groups.length;
        groups.push({ day, items: [], income: 0, expense: 0 });
      }
      const g = groups[idx[day]];
      g.items.push(b);
      const amt = Number(b.amount) || 0;
      if (b.transaction_type === 'income') g.income += amt;
      else if (b.transaction_type === 'expense') g.expense += amt;
    }
    return groups;
  },
  // id → 名称 映射（账单行展示账户/商户/地点/人员/项目名）
  ledgerNameMaps() {
    const m = (arr, key) => { const o = {}; for (const x of arr || []) o[x.id] = x[key] || ''; return o; };
    return {
      account: m(this.ledgerAccounts, 'account_name'),
      category: (() => { const o = {}; for (const c of this.ledgerCategories || []) o[c.id] = this.ledgerCatLabel(c); return o; })(),
      location: m(this.ledgerLocations, 'name'),
      merchant: m(this.ledgerMerchants, 'name'),
      person: m(this.ledgerPersons, 'name'),
      project: m(this.ledgerProjects, 'name'),
    };
  },
  // 分析·分类占比：按一级分类聚合，Top6 + 其他 → 环形图扇区（手写 SVG stroke-dasharray）
  ledgerDonut() {
    const agg = {};
    for (const r of this.ledgerCatStats || []) {
      const k = r.level1 || '未分类';
      agg[k] = (agg[k] || 0) + (Number(r.total_amount) || 0);
    }
    let rows = Object.keys(agg).map(k => ({ name: k, amount: agg[k] })).sort((a, b) => b.amount - a.amount);
    if (!rows.length) return { total: 0, segments: [], legend: [] };
    const total = rows.reduce((s, r) => s + r.amount, 0);
    let top = rows.slice(0, 6);
    const rest = rows.slice(6);
    if (rest.length) top = top.concat([{ name: `其他(${rest.length}类)`, amount: rest.reduce((s, r) => s + r.amount, 0) }]);
    const C = 2 * Math.PI * 60;   // r=60 周长
    let acc = 0;
    const segments = top.map((r, i) => {
      const frac = total ? r.amount / total : 0;
      const seg = { color: DONUT_COLORS[i % DONUT_COLORS.length], name: r.name,
        dash: `${(frac * C).toFixed(2)} ${C.toFixed(2)}`, offset: (-acc * C).toFixed(2),
        pct: Math.round(frac * 100) };
      acc += frac;
      return seg;
    });
    return { total, segments, legend: top.map((r, i) => ({ ...r, color: DONUT_COLORS[i % DONUT_COLORS.length], pct: total ? Math.round((r.amount / total) * 100) : 0 })) };
  },
  // 分析·月度趋势：双柱图缩放数据（收入绿/支出红，hover 用 <title>）
  ledgerMonthlyChart() {
    const rows = this.ledgerMonthly || [];
    const max = Math.max(1, ...rows.map(r => Math.max(Number(r.income) || 0, Number(r.expense) || 0)));
    return rows.map(r => ({
      month: r.month,
      income: Number(r.income) || 0,
      expense: Number(r.expense) || 0,
      ih: Math.round(((Number(r.income) || 0) / max) * 100),
      eh: Math.round(((Number(r.expense) || 0) / max) * 100),
    }));
  },
};

// ─────────── 账本 methods（由 appOptions.methods 用 ...ledgerMethods 合并）───────────
export const ledgerMethods = {
  /* ─────────── 基础 ─────────── */
  ledgerFmt(n) {
    return (Number(n) || 0).toFixed(2);
  },
  // 币种符号（仅展示；未知币种回退代码本身）
  ledgerCurrencySymbol(c) {
    return CURRENCY_SYMBOL[String(c || '').toUpperCase()] || String(c || '').toUpperCase() + ' ';
  },
  async ledgerExportCsv() {
    // 导出本人（当前账本）全部交易为 CSV（后端 /api/ledger/users/{uid}/export/csv 返回文件流）。
    // 自带 Bearer 鉴权：直接 window.location 会丢掉 token 触发 403，故用 fetch+blob 下载。
    const qs = new URLSearchParams({ user_id: this.user });
    this._ledgerPutBook(qs);
    const url = `/api/ledger/users/${encodeURIComponent(this.user)}/export/csv?${qs.toString()}`;
    const tk = (typeof localStorage !== 'undefined') ? localStorage.getItem('zx_token') : '';
    const headers = {};
    if (tk) headers['Authorization'] = 'Bearer ' + tk;
    try {
      const res = await fetch(url, { headers });
      if (!res.ok) {
        let msg = '导出失败';
        try { const j = await res.json(); msg = j.message || msg; } catch (e) { /* 非 JSON 响应忽略 */ }
        return this.showToast(msg);
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      const u = URL.createObjectURL(blob);
      a.href = u;
      a.download = `账本导出_${this.user}_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(u), 1000);
      this.showToast('已导出 CSV ✅');
    } catch (e) {
      this.showToast('导出失败：' + (e && e.message ? e.message : e));
    }
  },
  ledgerTypeLabel(t) {
    return { income: '收入', expense: '支出', transfer: '转账' }[t] || t || '';
  },
  ledgerFreqLabel(f) {
    return { daily: '每日', weekly: '每周', monthly: '每月', yearly: '每年' }[f] || f || '—';
  },
  ledgerCatLabel(c) {
    return [c && c.level1, c && c.level2, c && c.level3].filter(Boolean).join(' > ');
  },
  ledgerDtLocal(s) {
    // ISO datetime → datetime-local 输入值（本地时区，分钟精度）
    if (!s) return '';
    const d = new Date(s);
    if (isNaN(d)) return '';
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  },
  ledgerDateLocal(s) {
    // ISO datetime → date 输入值（YYYY-MM-DD）
    if (!s) return '';
    const d = new Date(s);
    if (isNaN(d)) return '';
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  },

  /* ─────────── M1 账本作用域：query/body 注入 ─────────── */
  // 把当前账本 id 写入 URLSearchParams（缺省不写，由后端回落默认账本）
  _ledgerPutBook(qs) {
    const id = Number(this.ledgerCurrentBookId) || 0;
    if (id) qs.set('book_id', String(id));
    return qs;
  },
  // 拼在已有 query 串后的账本参数（'' 或 '&book_id=N'）
  _ledgerBookQs() {
    const id = Number(this.ledgerCurrentBookId) || 0;
    return id ? `&book_id=${id}` : '';
  },
  // 创建类请求 body 里的账本归属（仅接受 book_id 的模型才带）
  _ledgerBookBody() {
    const id = Number(this.ledgerCurrentBookId) || 0;
    return id ? { book_id: id } : {};
  },
  _ledgerBase(dim) {
    // 六维列表 GET（返回数组；失败回空数组，不弹错打扰首屏）。
    // 仅 accounts 的 GET 支持 book_id 过滤，其余维度为共享参照数据/后端未过滤。
    const qs = new URLSearchParams({ user_id: this.user });
    if (dim === 'accounts') this._ledgerPutBook(qs);
    return this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/${dim}/?${qs.toString()}`).catch(() => []);
  },
  // 账本列表（先于六维加载：后续请求都要带 book_id）
  async ledgerLoadBooks() {
    const books = await this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/books/?user_id=${encodeURIComponent(this.user)}`)
      .catch(() => []);
    this.ledgerBooks = books || [];
    let stored = null;
    try { stored = Number(localStorage.getItem('zx_ledger_book_id') || 0) || null; } catch (e) { /* 隐私模式忽略 */ }
    const ids = (this.ledgerBooks || []).map(b => b.id);
    if (stored && ids.indexOf(stored) >= 0) {
      this.ledgerCurrentBookId = stored;
    } else {
      // 回落默认账本（后端 _resolve_book_id 的口径一致）；本地缓存失效时同步清理
      const dft = (this.ledgerBooks || []).find(b => b.is_default);
      this.ledgerCurrentBookId = dft ? dft.id : null;
      try { localStorage.removeItem('zx_ledger_book_id'); } catch (e) { /* 忽略 */ }
    }
  },
  ledgerSwitchBook(id) {
    const n = Number(id) || null;
    if (n === this.ledgerCurrentBookId) return;
    this.ledgerCurrentBookId = n;
    try {
      if (n) localStorage.setItem('zx_ledger_book_id', String(n));
      else localStorage.removeItem('zx_ledger_book_id');
    } catch (e) { /* 隐私模式忽略 */ }
    this.ledgerNotifOpen = false;
    this.ledgerReloadAll();
  },
  // 切账本后整树重载（六维 + 当前 tab + 预算/借贷/模板/净资产）
  async ledgerReloadAll() {
    this.ledgerLoading = true;
    try {
      await this._ledgerReloadBase();
      this.ledgerLoadDebts();
      this.ledgerLoadTemplates();
      this.loadLedgerBudget();
      this.loadLedgerTabData();
    } finally {
      this.ledgerLoading = false;
    }
  },
  ledgerOpenBookDialog(item) {
    this.ledgerBookDialog = {
      show: true,
      id: item ? item.id : null,
      form: {
        name: (item && item.name) || '',
        book_type: (item && item.book_type) || 'daily',
        icon: (item && item.icon) || '📘',
        color: (item && item.color) || '#8b7cf6',
        is_default: !!(item && item.is_default),
      },
    };
  },
  ledgerCloseBookDialog() {
    this.ledgerBookDialog = { show: false, id: null, form: { name: '', book_type: 'daily', icon: '📘', color: '#8b7cf6', is_default: false } };
  },
  ledgerSaveBook() {
    const { id, form } = this.ledgerBookDialog;
    const name = String(form.name || '').trim();
    if (!name) return this.showToast('请填写账本名称');
    const body = { name, book_type: form.book_type || null, icon: form.icon || null, color: form.color || null };
    if (!id) body.is_default = !!form.is_default;
    else if (form.is_default) body.is_default = true;
    const base = `/api/ledger/users/${encodeURIComponent(this.user)}/books/`;
    const req = id
      ? this.api(base + id, { method: 'PUT', body: JSON.stringify(body) })
      : this.api(base, { method: 'POST', body: JSON.stringify(body) });
    req.then(bk => {
      this.showToast(id ? '账本已更新 ✅' : '账本已创建 ✅');
      this.ledgerCloseBookDialog();
      return this.ledgerLoadBooks().then(() => {
        // 新建且设为默认 → 自动切过去，避免用户困惑「建了但还在旧账本」
        if (!id && bk && bk.id) this.ledgerSwitchBook(bk.id);
        else this.ledgerReloadAll();
      });
    }).catch(e => this.showToast(e.message));
  },
  ledgerDeleteBook(b) {
    if (!b || b.is_default) return this.showToast('默认账本不可删除');
    if (!confirm(`删除账本「${b.name}」？账本内还有账户/账单/周期交易时需先清空。`)) return;
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/books/${b.id}`, { method: 'DELETE' })
      .then(() => {
        this.showToast('账本已删除');
        return this.ledgerLoadBooks();
      })
      .then(() => this.ledgerReloadAll())
      .catch(e => this.showToast(e.message));
  },

  async initLedger() {
    // 进入账本 tab：先定账本（后续请求带 book_id），再并行拉六维 + 周期交易 + 模板 + 借贷；最后拉当前 tab 数据
    this.ledgerLoading = true;
    try {
      await this.ledgerLoadBooks();
      const [accounts, categories, locations, merchants, persons, projects, recurring] = await Promise.all([
        this._ledgerBase('accounts'), this._ledgerBase('categories'), this._ledgerBase('locations'),
        this._ledgerBase('merchants'), this._ledgerBase('persons'), this._ledgerBase('projects'),
        this._ledgerBase('recurring'),
      ]);
      this.ledgerAccounts = accounts || [];
      this.ledgerCategories = categories || [];
      this.ledgerLocations = locations || [];
      this.ledgerMerchants = merchants || [];
      this.ledgerPersons = persons || [];
      this.ledgerProjects = projects || [];
      this.ledgerRecurring = recurring || [];
      this.ledgerBaseLoaded = true;
      try {
        this.ledgerRecentCats = JSON.parse(localStorage.getItem('zx_ledger_recent_cats') || '[]');
      } catch (e) { this.ledgerRecentCats = []; }
      this.ledgerLoadDebts();
      this.ledgerLoadTemplates();
      this.ledgerLoadNotifications();
      this.loadLedgerTabData();
      this.loadLedgerBudget();   // 顶部「预算提醒」横幅需 budget 数据，与当前 tab 无关，统一预拉
    } finally {
      this.ledgerLoading = false;
    }
  },
  ledgerGoTab(t) {
    this.ledgerTab = t;
    this.loadLedgerTabData();
  },
  loadLedgerTabData() {
    if (this.ledgerTab === 'add') { this.loadLedgerBudget(); return; }
    if (this.ledgerTab === 'bills') { this.ledgerReloadBills(); return; }
    if (this.ledgerTab === 'analysis') { this.loadLedgerAnalysis(); return; }
    // settings 无独立拉取（基础维度已在 initLedger 拉齐），但预算/借贷/模板管理在此 tab
    if (this.ledgerTab === 'settings') { this.ledgerLoadBudgetList(); this.ledgerLoadDebts(); this.ledgerLoadTemplates(); }
  },
  async _ledgerReloadBase() {
    // 记账/CRUD 后回刷六维（余额、分类等可能变化）
    const [accounts, categories, projects, recurring] = await Promise.all([
      this._ledgerBase('accounts'), this._ledgerBase('categories'),
      this._ledgerBase('projects'), this._ledgerBase('recurring'),
    ]);
    this.ledgerAccounts = accounts || [];
    this.ledgerCategories = categories || [];
    this.ledgerProjects = projects || [];
    this.ledgerRecurring = recurring || [];
  },

  /* ─────────── Tab1 记一笔 ─────────── */
  ledgerResetForm(keepType = true) {
    const t = keepType ? this.ledgerForm.transaction_type : 'expense';
    this.ledgerForm = {
      editId: null, transaction_type: t, amount: '',
      from_account_id: '', to_account_id: '',
      catL1: '', catL2: '', catL3: '',
      location_id: '', merchant_id: '', person_id: '', project_id: '',
      note: '', transaction_time: '',
      currency: 'CNY', amount_orig: '', rate_to_base: '',
      refund_of_id: '', attachment_url: '',
    };
  },
  ledgerPickType(t) {
    this.ledgerForm.transaction_type = t;
    // 类型切换后分类级联清空（EXPENSE/INCOME 分类集不同）
    this.ledgerForm.catL1 = ''; this.ledgerForm.catL2 = ''; this.ledgerForm.catL3 = '';
  },
  ledgerUseRecentCat(c) {
    if (!c) return;
    this.ledgerPickType((c.category_type === 'INCOME') ? 'income' : 'expense');
    this.ledgerForm.catL1 = c.level1 || '';
    this.ledgerForm.catL2 = c.level2 || '';
    this.ledgerForm.catL3 = c.level3 || '';
  },
  _ledgerRememberCat(id) {
    if (!id) return;
    let arr = (this.ledgerRecentCats || []).filter(x => x !== id);
    arr.unshift(id);
    arr = arr.slice(0, 6);
    this.ledgerRecentCats = arr;
    try { localStorage.setItem('zx_ledger_recent_cats', JSON.stringify(arr)); } catch (e) { /* 隐私模式忽略 */ }
  },
  // M4：把模板要素灌进记一笔表单（速记：点模板即预填，可改后再提交）
  ledgerUseTemplate(tpl) {
    if (!tpl) return;
    this.ledgerPickType(tpl.transaction_type || 'expense');
    const cat = (this.ledgerCategories || []).find(c => c.id === tpl.category_id);
    this.ledgerForm.amount = (tpl.amount != null && tpl.amount !== '') ? String(tpl.amount) : '';
    this.ledgerForm.from_account_id = tpl.from_account_id ? String(tpl.from_account_id) : '';
    this.ledgerForm.to_account_id = tpl.to_account_id ? String(tpl.to_account_id) : '';
    this.ledgerForm.catL1 = (cat && cat.level1) || '';
    this.ledgerForm.catL2 = (cat && cat.level2) || '';
    this.ledgerForm.catL3 = (cat && cat.level3) || '';
    this.ledgerForm.note = tpl.note || '';
    this.showToast(`已套用模板「${tpl.name}」，确认后点记一笔`);
  },
  // M4：把当前表单存为新模板（名称必填，其余沿用表单）
  ledgerSaveAsTemplate(name) {
    const f = this.ledgerForm;
    const nm = String(name || '').trim();
    if (!nm) return this.showToast('请填写模板名称');
    const cat = this.ledgerSelectedCategory;
    const body = Object.assign(this._ledgerBookBody(), {
      name: nm,
      transaction_type: f.transaction_type,
      amount: (Number(String(f.amount).trim()) || 0) > 0 ? Math.round((Number(String(f.amount).trim()) || 0) * 100) / 100 : null,
      category_id: cat ? cat.id : null,
      from_account_id: f.from_account_id ? Number(f.from_account_id) : null,
      to_account_id: f.transaction_type === 'transfer' && f.to_account_id ? Number(f.to_account_id) : null,
      note: (f.note || '').trim() || null,
    });
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/templates/`, { method: 'POST', body: JSON.stringify(body) })
      .then(() => { this.showToast('已存为模板 ✅'); this.ledgerLoadTemplates(); })
      .catch(e => this.showToast(e.message));
  },
  ledgerSubmitTx() {
    const f = this.ledgerForm;
    // M4 多币种：CNY 直接用 amount；外币按 amount_orig × rate_to_base 折算（后端同口径）
    const cur = String(f.currency || 'CNY').toUpperCase();
    let amount, amount_orig = null, rate = null;
    if (cur === 'CNY') {
      amount = Math.round((Number(String(f.amount).trim()) || 0) * 100) / 100;  // 元，round 2 位
    } else {
      amount_orig = Math.round((Number(String(f.amount_orig).trim()) || 0) * 100) / 100;
      rate = Number(String(f.rate_to_base).trim()) || 0;
      if (!(amount_orig > 0)) return this.showToast('请输入大于 0 的原币金额');
      if (!(rate > 0)) return this.showToast('请输入大于 0 的折算汇率');
      amount = Math.round(amount_orig * rate * 100) / 100;
    }
    if (!amount || amount <= 0) return this.showToast('请输入大于 0 的金额');
    if (f.transaction_type === 'transfer') {
      // 转账不强制分类（后端要求分类存在，故仍必选）；双账户必选且不可相同
      if (!f.from_account_id || !f.to_account_id) return this.showToast('转账需选择转出与转入两个账户');
      if (Number(f.from_account_id) === Number(f.to_account_id)) return this.showToast('转出与转入账户不能相同');
    } else if (!f.from_account_id) {
      return this.showToast(f.transaction_type === 'income' ? '请选择收款账户' : '请选择付款账户');
    }
    const cat = this.ledgerSelectedCategory;
    if (!cat) return this.showToast('请选择分类');
    const body = Object.assign(this._ledgerBookBody(), {
      transaction_type: f.transaction_type,
      amount,   // 元单位（Numeric(15,2)），不做 ×100 转分
      category_id: cat.id,
      from_account_id: f.from_account_id ? Number(f.from_account_id) : null,
      to_account_id: f.transaction_type === 'transfer' ? Number(f.to_account_id) : null,
      location_id: f.location_id ? Number(f.location_id) : null,
      merchant_id: f.merchant_id ? Number(f.merchant_id) : null,
      person_id: f.person_id ? Number(f.person_id) : null,
      project_id: f.project_id ? Number(f.project_id) : null,
      refund_of_id: f.refund_of_id ? Number(f.refund_of_id) : null,
      attachment_url: (f.attachment_url || '').trim() || null,
      currency: cur,
      note: (f.note || '').trim() || null,
      transaction_time: f.transaction_time ? new Date(f.transaction_time).toISOString() : null,
    });
    if (cur !== 'CNY') { body.amount_orig = amount_orig; body.rate_to_base = rate; }
    const base = `/api/ledger/users/${encodeURIComponent(this.user)}/transactions/`;
    const req = f.editId
      ? this.api(base + f.editId, { method: 'PUT', body: JSON.stringify(body) })
      : this.api(base, { method: 'POST', body: JSON.stringify(body) });
    req.then(() => {
      this._ledgerRememberCat(cat.id);
      this.showToast(f.editId ? '账单已更新 ✅' : '记好了 ✅');
      this.ledgerResetForm(true);           // 清空表单（保留类型）
      this._ledgerReloadBase();             // 刷新账户余额等
      this.loadLedgerBudget();
      this.ledgerLoadBudgetExec();          // 刷新预算执行并产出超支提醒（后端去重）
    }).catch(e => this.showToast(e.message));
  },
  ledgerEditBill(b) {
    // 账单 → 跳记一笔预填（编辑模式）
    const cat = (this.ledgerCategories || []).find(c => c.id === b.category_id);
    const cur = String(b.currency || 'CNY').toUpperCase();
    this.ledgerForm = {
      editId: b.id,
      transaction_type: b.transaction_type || 'expense',
      amount: b.amount != null ? String(b.amount) : '',
      from_account_id: b.from_account_id || '',
      to_account_id: b.to_account_id || '',
      catL1: (cat && cat.level1) || '', catL2: (cat && cat.level2) || '', catL3: (cat && cat.level3) || '',
      location_id: b.location_id || '', merchant_id: b.merchant_id || '',
      person_id: b.person_id || '', project_id: b.project_id || '',
      note: b.note || '',
      transaction_time: this.ledgerDtLocal(b.transaction_time),
      currency: cur,
      amount_orig: (cur !== 'CNY' && b.amount_orig != null) ? String(b.amount_orig) : '',
      rate_to_base: (cur !== 'CNY' && b.rate_to_base != null) ? String(b.rate_to_base) : '',
      refund_of_id: b.refund_of_id || '',
      attachment_url: b.attachment_url || '',
    };
    this.ledgerGoTab('add');
  },
  ledgerDeleteBill(b) {
    if (!confirm(`删除这笔 ${this.ledgerTypeLabel(b.transaction_type)} ${this.ledgerFmt(b.amount)} 元？删除后账户余额将自动回滚。`)) return;
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/transactions/${b.id}`, { method: 'DELETE' })
      .then(() => {
        this.showToast('已删除，余额已回滚');
        this.ledgerReloadBills();
        this._ledgerReloadBase();
      }).catch(e => this.showToast(e.message));
  },

  /* ─────────── M3 退款 ─────────── */
  ledgerOpenRefundDialog(b) {
    if (!b) return;
    const now = new Date();
    const p = n => String(n).padStart(2, '0');
    this.ledgerRefundDialog = {
      show: true,
      bill: b,
      form: {
        amount: b.amount != null ? String(b.amount) : '',
        from_account_id: b.from_account_id ? String(b.from_account_id) : '',
        note: `退款：${b.note || this.ledgerNameMaps.category[b.category_id] || '原账单'}`,
        transaction_time: `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}T${p(now.getHours())}:${p(now.getMinutes())}`,
      },
    };
  },
  ledgerCloseRefundDialog() {
    this.ledgerRefundDialog = { show: false, bill: null, form: { amount: '', from_account_id: '', note: '', transaction_time: '' } };
  },
  ledgerSubmitRefund() {
    const { bill, form } = this.ledgerRefundDialog;
    if (!bill) return;
    const amount = Math.round((Number(String(form.amount).trim()) || 0) * 100) / 100;
    if (!(amount > 0)) return this.showToast('请输入大于 0 的退款金额');
    if (amount > (Number(bill.amount) || 0) + 0.0001) return this.showToast(`退款金额不能超过原笔 ${this.ledgerFmt(bill.amount)} 元`);
    if (!form.from_account_id) return this.showToast('请选择退款入账账户');
    if (!bill.category_id) return this.showToast('原账单缺分类，无法生成退款');
    // 退款 = 一笔反向收入（借出场景为支出），沿用原账单分类，并回填 refund_of_id 串联两笔
    const body = Object.assign(this._ledgerBookBody(), {
      transaction_type: bill.transaction_type === 'income' ? 'expense' : 'income',
      amount,
      category_id: bill.category_id,
      from_account_id: Number(form.from_account_id),
      refund_of_id: bill.id,
      person_id: bill.person_id || null,
      project_id: bill.project_id || null,
      merchant_id: bill.merchant_id || null,
      location_id: bill.location_id || null,
      note: (form.note || '').trim() || null,
      transaction_time: form.transaction_time ? new Date(form.transaction_time).toISOString() : null,
    });
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/transactions/`, { method: 'POST', body: JSON.stringify(body) })
      .then(() => {
        this.showToast('退款已记账 ✅');
        this.ledgerCloseRefundDialog();
        this.ledgerReloadBills();
        this._ledgerReloadBase();
      }).catch(e => this.showToast(e.message));
  },

  /* ─────────── Tab2 账单 ─────────── */
  ledgerApplyRange(r) {
    const f = this.ledgerBillFilter;
    f.range = r;
    const now = new Date();
    const p = n => String(n).padStart(2, '0');
    const fmt = d => `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    if (r === 'month') {
      f.start_date = fmt(new Date(now.getFullYear(), now.getMonth(), 1));
      f.end_date = fmt(now);
    } else if (r === 'last') {
      f.start_date = fmt(new Date(now.getFullYear(), now.getMonth() - 1, 1));
      f.end_date = fmt(new Date(now.getFullYear(), now.getMonth(), 0));
    } else if (r === 'quarter') {
      f.start_date = fmt(new Date(now.getFullYear(), now.getMonth() - 2, 1));
      f.end_date = fmt(now);
    } else { f.start_date = ''; f.end_date = ''; }   // '' 全部 / custom 由日期输入框控制
  },
  ledgerResetBillFilter() {
    // 重置全部筛选并回到「本月」默认口径
    this.ledgerBillFilter = {
      range: 'month', start_date: '', end_date: '',
      transaction_type: '', category_id: '', account_id: '', project_id: '',
      min_amount: '', max_amount: '', keyword: '',
    };
    this.ledgerApplyRange('month');
    this.ledgerReloadBills();
  },
  ledgerBuildBillQuery(skip) {
    const f = this.ledgerBillFilter;
    const qs = new URLSearchParams({ user_id: this.user, skip: String(skip), limit: '20' });
    this._ledgerPutBook(qs);
    for (const k of ['transaction_type', 'category_id', 'account_id', 'project_id', 'start_date', 'end_date', 'min_amount', 'max_amount', 'keyword']) {
      const v = String(f[k] == null ? '' : f[k]).trim();
      if (v) qs.set(k, v);
    }
    return qs.toString();
  },
  ledgerReloadBills() {
    this.ledgerBillsPage = 0;
    this.ledgerBills = [];
    this.ledgerLoadBills();
  },
  ledgerLoadBills() {
    // 分页 20：首屏/筛选重拉（page=0 覆盖），「加载更多」追加
    const skip = this.ledgerBillsPage * 20;
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/transactions/?${this.ledgerBuildBillQuery(skip)}`)
      .then(d => {
        const rows = d || [];
        this.ledgerBills = skip === 0 ? rows : this.ledgerBills.concat(rows);
        this.ledgerBillsMore = rows.length >= 20;
      }).catch(e => { this.showToast(e.message); this.ledgerBillsMore = false; });
  },
  ledgerLoadMoreBills() {
    this.ledgerBillsPage += 1;
    this.ledgerLoadBills();
  },

  /* ─────────── Tab3 分析 ─────────── */
  loadLedgerAnalysis() {
    const uid = encodeURIComponent(this.user);
    const bk = this._ledgerBookQs();
    this.api(`/api/ledger/users/${uid}/statistics/summary?user_id=${uid}${bk}`)
      .then(d => { this.ledgerSummary = d; }).catch(() => { this.ledgerSummary = null; });
    this.api(`/api/ledger/users/${uid}/statistics/monthly?user_id=${uid}&year=${this.ledgerMonthlyYear}${bk}`)
      .then(d => { this.ledgerMonthly = (d && d.monthly_data) || []; }).catch(() => { this.ledgerMonthly = []; });
    this.api(`/api/ledger/users/${uid}/statistics/budget?user_id=${uid}${bk}`)
      .then(d => { this.ledgerBudget = d || []; }).catch(() => { this.ledgerBudget = []; });
    this.loadLedgerCatStats();
    this.ledgerLoadNetWorth();
    this.ledgerLoadDebts();
    // 预算执行（有副作用：后端会按阈值产出 NotificationLog，故只在进分析 tab 时调一次，不做高频轮询）
    this.ledgerLoadBudgetExec();
  },
  loadLedgerCatStats() {
    // 分类占比按周期切换（本月/近3月/本年）；start/end 传日期，后端 datetime 可解析
    const now = new Date();
    const p = n => String(n).padStart(2, '0');
    const fmt = d => `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    let start = '';
    if (this.ledgerPeriod === 'month') start = fmt(new Date(now.getFullYear(), now.getMonth(), 1));
    else if (this.ledgerPeriod === 'quarter') start = fmt(new Date(now.getFullYear(), now.getMonth() - 2, 1));
    else start = fmt(new Date(now.getFullYear(), 0, 1));
    const qs = new URLSearchParams({ user_id: this.user, start_date: start, end_date: fmt(now) });
    this._ledgerPutBook(qs);
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/statistics/category?${qs.toString()}`)
      .then(d => { this.ledgerCatStats = (d && d.categories) || []; })
      .catch(() => { this.ledgerCatStats = []; });
  },
  ledgerSetPeriod(p) {
    this.ledgerPeriod = p;
    this.loadLedgerCatStats();
  },
  ledgerSetYear(y) {
    // 月度趋势年份切换：仅重拉 monthly（概览/分类/预算不受年份影响）
    const nowY = new Date().getFullYear();
    if (y > nowY) return;                 // 不允许看未来年份（后端也无数据）
    this.ledgerMonthlyYear = y;
    const uid = encodeURIComponent(this.user);
    this.api(`/api/ledger/users/${uid}/statistics/monthly?user_id=${uid}&year=${y}${this._ledgerBookQs()}`)
      .then(d => { this.ledgerMonthly = (d && d.monthly_data) || []; })
      .catch(() => { this.ledgerMonthly = []; });
  },
  ledgerDonutClick(seg) {
    // 环形图扇区点击 → 账单列表按该一级分类筛选。统计行不含 category_id，
    // 故按 level1 反查分类表：恰有一个分类时带 category_id 精确筛，
    // 多个子分类时清空筛选并提示手动选。
    const ids = (this.ledgerCategories || []).filter(c => c.level1 === seg.name).map(c => c.id);
    this.ledgerApplyRange('');
    this.ledgerBillFilter.category_id = ids.length === 1 ? String(ids[0]) : '';
    this.ledgerGoTab('bills');
    if (ids.length !== 1) this.showToast(`已切到账单列表，「${seg.name}」含多个子分类，请在筛选栏选择具体分类`);
  },
  // 账单行筛选下拉用的分类选项（当前类型不限，全量分类）
  ledgerAllCats() {
    return this.ledgerCategories || [];
  },

  /* ─────────── M2 预算 ─────────── */
  ledgerLoadBudgetList() {
    const uid = encodeURIComponent(this.user);
    this.api(`/api/ledger/users/${uid}/budgets/?user_id=${uid}${this._ledgerBookQs()}`)
      .then(d => { this.ledgerBudgetList = d || []; }).catch(() => { this.ledgerBudgetList = []; });
  },
  ledgerLoadBudgetExec() {
    // 预算执行率 + 超支提醒（后端带去重写 NotificationLog，故仅在必要时机调用）
    const uid = encodeURIComponent(this.user);
    this.api(`/api/ledger/users/${uid}/statistics/budgets?user_id=${uid}${this._ledgerBookQs()}`)
      .then(d => {
        this.ledgerBudgetExec = d || null;
        this.ledgerLoadNotifications();   // 执行率刷新后同步拉取提醒
      }).catch(() => { this.ledgerBudgetExec = null; });
  },
  ledgerBudgetScopeName(b) {
    // 预算对象名（month 为总预算；category/project 反查维度表）
    if (!b) return '';
    if (b.scope_type === 'month') return '本月总预算';
    if (b.scope_type === 'category') {
      const c = (this.ledgerCategories || []).find(x => x.id === b.scope_id);
      return c ? this.ledgerCatLabel(c) : `分类#${b.scope_id}`;
    }
    const p = (this.ledgerProjects || []).find(x => x.id === b.scope_id);
    return p ? p.name : `项目#${b.scope_id}`;
  },
  ledgerOpenBudgetDialog(item) {
    this.ledgerBudgetDialog = {
      show: true,
      id: item ? item.id : null,
      form: {
        scope_type: (item && item.scope_type) || 'month',
        scope_id: (item && item.scope_id) ? String(item.scope_id) : '',
        amount: (item && item.amount != null) ? String(item.amount) : '',
        notify_threshold: (item && item.notify_threshold != null) ? String(item.notify_threshold) : '0.8',
      },
    };
  },
  ledgerCloseBudgetDialog() {
    this.ledgerBudgetDialog = { show: false, id: null, form: { scope_type: 'month', scope_id: '', amount: '', notify_threshold: '0.8' } };
  },
  ledgerSaveBudget() {
    const { id, form } = this.ledgerBudgetDialog;
    const scope_type = form.scope_type || 'month';
    const amount = Math.round((Number(String(form.amount).trim()) || 0) * 100) / 100;
    if (!(amount > 0)) return this.showToast('请输入大于 0 的预算金额');
    const thr = Number(String(form.notify_threshold).trim());
    if (!(thr > 0) || thr > 1.5) return this.showToast('预警阈值需在 0 ~ 1.5 之间（如 0.8 = 80%）');
    const body = { scope_type, amount, notify_threshold: thr };
    if (scope_type !== 'month') {
      if (!form.scope_id) return this.showToast(scope_type === 'category' ? '请选择预算分类' : '请选择预算项目');
      body.scope_id = Number(form.scope_id);
    } else {
      body.scope_id = null;
    }
    const base = `/api/ledger/users/${encodeURIComponent(this.user)}/budgets/`;
    const req = id
      ? this.api(base + id, { method: 'PUT', body: JSON.stringify(body) })
      : this.api(base, { method: 'POST', body: JSON.stringify(Object.assign(this._ledgerBookBody(), body)) });
    req.then(() => {
      this.showToast(id ? '预算已更新 ✅' : '预算已设置 ✅');
      this.ledgerCloseBudgetDialog();
      this.ledgerLoadBudgetList();
      this.ledgerLoadBudgetExec();
    }).catch(e => this.showToast(e.message));
  },
  ledgerDeleteBudget(b) {
    if (!b) return;
    if (!confirm(`删除该预算（${this.ledgerBudgetScopeName(b)} ${this.ledgerFmt(b.amount)} 元）？`)) return;
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/budgets/${b.id}`, { method: 'DELETE' })
      .then(() => { this.showToast('预算已删除'); this.ledgerLoadBudgetList(); this.ledgerLoadBudgetExec(); })
      .catch(e => this.showToast(e.message));
  },
  ledgerLoadNotifications() {
    const uid = encodeURIComponent(this.user);
    this.api(`/api/ledger/users/${uid}/notifications/?user_id=${uid}`)
      .then(d => { this.ledgerNotifications = d || []; }).catch(() => { this.ledgerNotifications = []; });
  },
  ledgerToggleNotif() {
    this.ledgerNotifOpen = !this.ledgerNotifOpen;
    if (this.ledgerNotifOpen) this.ledgerLoadNotifications();
  },

  /* ─────────── M3 借贷 / 净资产 ─────────── */
  ledgerLoadNetWorth() {
    const uid = encodeURIComponent(this.user);
    this.api(`/api/ledger/users/${uid}/statistics/networth?user_id=${uid}${this._ledgerBookQs()}`)
      .then(d => { this.ledgerNetWorth = d || null; }).catch(() => { this.ledgerNetWorth = null; });
  },
  ledgerLoadDebts() {
    const uid = encodeURIComponent(this.user);
    const qs = new URLSearchParams({ user_id: this.user });
    this._ledgerPutBook(qs);
    if (this.ledgerDebtFilter) qs.set('status', this.ledgerDebtFilter);
    this.api(`/api/ledger/users/${uid}/debts/?${qs.toString()}`)
      .then(d => { this.ledgerDebts = d || []; }).catch(() => { this.ledgerDebts = []; });
  },
  ledgerSetDebtFilter(s) {
    this.ledgerDebtFilter = s;
    this.ledgerLoadDebts();
  },
  ledgerDebtPersonName(d) {
    const p = (this.ledgerPersons || []).find(x => x.id === d.person_id);
    return p ? p.name : '未指定';
  },
  ledgerOpenDebtDialog(item) {
    this.ledgerDebtDialog = {
      show: true,
      id: item ? item.id : null,
      form: {
        person_id: (item && item.person_id) ? String(item.person_id) : '',
        direction: (item && item.direction) || 'lend',
        total: (item && item.total != null) ? String(item.total) : '',
        due_date: (item && item.due_date) ? this.ledgerDateLocal(item.due_date) : '',
        note: (item && item.note) || '',
      },
    };
  },
  ledgerCloseDebtDialog() {
    this.ledgerDebtDialog = { show: false, id: null, form: { person_id: '', direction: 'lend', total: '', due_date: '', note: '' } };
  },
  ledgerSaveDebt() {
    const { id, form } = this.ledgerDebtDialog;
    const total = Math.round((Number(String(form.total).trim()) || 0) * 100) / 100;
    if (!(total > 0)) return this.showToast('请输入大于 0 的金额');
    const body = {
      direction: form.direction,
      total,
      person_id: form.person_id ? Number(form.person_id) : null,
      due_date: form.due_date ? new Date(form.due_date + 'T00:00:00').toISOString() : null,
      note: (form.note || '').trim() || null,
    };
    const base = `/api/ledger/users/${encodeURIComponent(this.user)}/debts/`;
    const req = id
      ? this.api(base + id, { method: 'PUT', body: JSON.stringify(body) })
      : this.api(base, { method: 'POST', body: JSON.stringify(Object.assign(this._ledgerBookBody(), body)) });
    req.then(() => {
      this.showToast(id ? '借贷已更新 ✅' : '已记录 ✅');
      this.ledgerCloseDebtDialog();
      this.ledgerLoadDebts();
      this.ledgerLoadNetWorth();
    }).catch(e => this.showToast(e.message));
  },
  ledgerDeleteDebt(d) {
    if (!d) return;
    if (!confirm(`删除这笔${d.direction === 'lend' ? '借出' : '借入'}记录（${this.ledgerDebtPersonName(d)} ${this.ledgerFmt(d.total)} 元）？`)) return;
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/debts/${d.id}`, { method: 'DELETE' })
      .then(() => { this.showToast('已删除'); this.ledgerLoadDebts(); this.ledgerLoadNetWorth(); })
      .catch(e => this.showToast(e.message));
  },
  ledgerOpenRepayDialog(d) {
    if (!d) return;
    const now = new Date();
    const p = n => String(n).padStart(2, '0');
    this.ledgerRepayDialog = {
      show: true,
      debt: d,
      form: {
        amount: (d.balance != null) ? String(d.balance) : '',
        from_account_id: '',
        note: d.direction === 'lend' ? '收回借款' : '偿还借款',
        transaction_time: `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}T${p(now.getHours())}:${p(now.getMinutes())}`,
      },
    };
  },
  ledgerCloseRepayDialog() {
    this.ledgerRepayDialog = { show: false, debt: null, form: { amount: '', from_account_id: '', note: '', transaction_time: '' } };
  },
  ledgerSubmitRepay() {
    const { debt, form } = this.ledgerRepayDialog;
    if (!debt) return;
    const amount = Math.round((Number(String(form.amount).trim()) || 0) * 100) / 100;
    if (!(amount > 0)) return this.showToast('请输入大于 0 的金额');
    if (amount > (Number(debt.balance) || 0) + 0.0001) return this.showToast(`不能超过未结余额 ${this.ledgerFmt(debt.balance)} 元`);
    if (!form.from_account_id) return this.showToast('请选择资金进出账户');
    const body = {
      amount,
      from_account_id: Number(form.from_account_id),
      note: (form.note || '').trim() || null,
      transaction_time: form.transaction_time ? new Date(form.transaction_time).toISOString() : null,
    };
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/debts/${debt.id}/repay`, { method: 'POST', body: JSON.stringify(body) })
      .then(() => {
        this.showToast(debt.direction === 'lend' ? '收款已记账 ✅' : '还款已记账 ✅');
        this.ledgerCloseRepayDialog();
        this.ledgerLoadDebts();
        this.ledgerLoadNetWorth();
        this._ledgerReloadBase();
      }).catch(e => this.showToast(e.message));
  },

  /* ─────────── M4 记账模板 ─────────── */
  ledgerLoadTemplates() {
    const uid = encodeURIComponent(this.user);
    this.api(`/api/ledger/users/${uid}/templates/?user_id=${uid}${this._ledgerBookQs()}`)
      .then(d => { this.ledgerTemplates = d || []; }).catch(() => { this.ledgerTemplates = []; });
  },
  ledgerTemplateDesc(t) {
    // 模板一行摘要：金额 + 分类 + 账户
    const parts = [];
    if (t.amount != null) parts.push(this.ledgerFmt(t.amount) + ' 元');
    const c = (this.ledgerCategories || []).find(x => x.id === t.category_id);
    if (c) parts.push(this.ledgerCatLabel(c));
    const a = (this.ledgerAccounts || []).find(x => x.id === t.from_account_id);
    if (a) parts.push(a.account_name);
    return parts.join(' · ') || '—';
  },
  ledgerOpenTemplateDialog(item) {
    this.ledgerTemplateDialog = {
      show: true,
      id: item ? item.id : null,
      form: {
        name: (item && item.name) || '',
        transaction_type: (item && item.transaction_type) || 'expense',
        amount: (item && item.amount != null) ? String(item.amount) : '',
        category_id: (item && item.category_id) ? String(item.category_id) : '',
        from_account_id: (item && item.from_account_id) ? String(item.from_account_id) : '',
        to_account_id: (item && item.to_account_id) ? String(item.to_account_id) : '',
        note: (item && item.note) || '',
      },
    };
  },
  ledgerCloseTemplateDialog() {
    this.ledgerTemplateDialog = { show: false, id: null, form: { name: '', transaction_type: 'expense', amount: '', category_id: '', from_account_id: '', to_account_id: '', note: '' } };
  },
  ledgerSaveTemplate() {
    const { id, form } = this.ledgerTemplateDialog;
    const name = String(form.name || '').trim();
    if (!name) return this.showToast('请填写模板名称');
    const amtRaw = String(form.amount || '').trim();
    const body = {
      name,
      transaction_type: form.transaction_type,
      amount: amtRaw ? Math.round((Number(amtRaw) || 0) * 100) / 100 : null,
      category_id: form.category_id ? Number(form.category_id) : null,
      from_account_id: form.from_account_id ? Number(form.from_account_id) : null,
      to_account_id: form.to_account_id ? Number(form.to_account_id) : null,
      note: (form.note || '').trim() || null,
    };
    const base = `/api/ledger/users/${encodeURIComponent(this.user)}/templates/`;
    const req = id
      ? this.api(base + id, { method: 'PUT', body: JSON.stringify(body) })
      : this.api(base, { method: 'POST', body: JSON.stringify(Object.assign(this._ledgerBookBody(), body)) });
    req.then(() => {
      this.showToast(id ? '模板已更新 ✅' : '模板已创建 ✅');
      this.ledgerCloseTemplateDialog();
      this.ledgerLoadTemplates();
    }).catch(e => this.showToast(e.message));
  },
  ledgerDeleteTemplate(t) {
    if (!t) return;
    if (!confirm(`删除模板「${t.name}」？`)) return;
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/templates/${t.id}`, { method: 'DELETE' })
      .then(() => { this.showToast('模板已删除'); this.ledgerLoadTemplates(); })
      .catch(e => this.showToast(e.message));
  },

  /* ─────────── Tab4 设置：六维 CRUD + 周期交易 ─────────── */
  loadLedgerBudget() {
    // 记一笔选中项目时的预算提示数据（复用 statistics/budget）
    const uid = encodeURIComponent(this.user);
    this.api(`/api/ledger/users/${uid}/statistics/budget?user_id=${uid}${this._ledgerBookQs()}`)
      .then(d => { this.ledgerBudget = d || []; }).catch(() => {});
  },
  ledgerOpenDimDialog(dim, item) {
    // item 为空 = 新建；否则编辑预填（表单值统一转字符串便于 input 绑定）
    const defs = LEDGER_DIMS[dim];
    if (!defs) return;
    const form = {};
    for (const fd of defs.fields) {
      if (!item && fd.def !== undefined) { form[fd.k] = String(fd.def); continue; }
      const v = item ? item[fd.k] : '';
      form[fd.k] = (v == null ? '' : (fd.type === 'datetime' ? this.ledgerDtLocal(v) : String(v)));
    }
    if (!item && dim === 'recurring') {
      form.transaction_type = 'expense';
      form.frequency = 'monthly';
    }
    if (!item && dim === 'accounts') form.account_type = 'savings_card';
    if (!item && dim === 'categories') form.category_type = 'EXPENSE';
    this.ledgerDimDialog = { show: true, dim, id: item ? item.id : null, form };
  },
  ledgerCloseDimDialog() {
    this.ledgerDimDialog = { show: false, dim: '', id: null, form: {} };
  },
  ledgerSaveDim() {
    const { dim, id, form } = this.ledgerDimDialog;
    const defs = LEDGER_DIMS[dim];
    if (!defs) return;
    const body = {};
    for (const fd of defs.fields) {
      let v = (form[fd.k] == null ? '' : String(form[fd.k])).trim();
      if (fd.num) {
        if (v === '') {
          // 有默认值的字段回落默认值（如 rate_to_base=1），其余可空字段传 null
          if (fd.def !== undefined) { body[fd.k] = fd.def; continue; }
          body[fd.k] = dim === 'accounts' && fd.k === 'balance' ? 0 : null;
          continue;
        }
        const n = fd.int ? Math.round(Number(v) || 0) : Math.round((Number(v) || 0) * 100) / 100;   // 元，round 2 位
        if (isNaN(n)) return this.showToast(`${fd.label}需为数字`);
        if (fd.int && (n < 1 || n > 31)) return this.showToast(`${fd.label}需在 1~31 之间`);
        body[fd.k] = n;
        continue;
      }
      if (fd.type === 'account' || fd.type === 'category') {
        body[fd.k] = v ? Number(v) : null;
        continue;
      }
      if (fd.type === 'datetime') {
        body[fd.k] = v ? new Date(v).toISOString() : null;
        continue;
      }
      if (fd.type === 'select') {
        if (!v) return this.showToast(`请选择${fd.label}`);
        body[fd.k] = v;
        continue;
      }
      // 普通文本：第一个字段视为名称必填，其余可空传 null
      if (!v) { body[fd.k] = null; continue; }
      body[fd.k] = v;
    }
    // 名称类首字段必填校验
    const nameKey = defs.fields[0].k;
    if (!body[nameKey]) return this.showToast(`请填写${defs.fields[0].label}`);
    if (dim === 'recurring' && !id && !(body.amount > 0)) return this.showToast('请输入大于 0 的金额');
    // M1：账户/项目/周期交易创建时归属当前账本
    if (!id && defs.bookScoped) Object.assign(body, this._ledgerBookBody());
    const base = `/api/ledger/users/${encodeURIComponent(this.user)}/${defs.path}/`;
    const req = id
      ? this.api(base + id, { method: 'PUT', body: JSON.stringify(body) })
      : this.api(base, { method: 'POST', body: JSON.stringify(body) });
    req.then(() => {
      this.showToast(id ? '已保存 ✅' : '已新建 ✅');
      this.ledgerCloseDimDialog();
      this.ledgerReloadDim(dim);
    }).catch(e => this.showToast(e.message));
  },
  ledgerReloadDim(dim) {
    // CRUD 后只回刷对应维度（周期交易影响账户余额也顺带刷账户）
    const dims = dim === 'recurring' ? ['recurring', 'accounts'] : [dim];
    Promise.all(dims.map(d => this._ledgerBase(d))).then(results => {
      const key = { accounts: 'ledgerAccounts', categories: 'ledgerCategories', locations: 'ledgerLocations',
        merchants: 'ledgerMerchants', persons: 'ledgerPersons', projects: 'ledgerProjects', recurring: 'ledgerRecurring' };
      dims.forEach((d, i) => { this[key[d]] = results[i] || []; });
      if (dims.includes('projects')) this.loadLedgerBudget();
    });
  },
  ledgerDeleteDim(dim, item) {
    const defs = LEDGER_DIMS[dim];
    if (!defs || !item) return;
    const label = item.account_name || item.name || this.ledgerCatLabel(item) || `#${item.id}`;
    if (!confirm(`确定删除${defs.label}「${label}」？`)) return;
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/${defs.path}/${item.id}`, { method: 'DELETE' })
      .then(() => { this.showToast('已删除'); this.ledgerReloadDim(dim); })
      .catch(e => this.showToast(e.message));
  },
  ledgerToggleRecurring(rt) {
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/recurring/${rt.id}/toggle`, { method: 'POST' })
      .then(d => {
        rt.is_active = !!(d && d.is_active);
        this.showToast(rt.is_active ? '已启用，到期将自动记账' : '已停用');
      }).catch(e => this.showToast(e.message));
  },
  ledgerRunDueNow() {
    // 手动「立即补跑」：调用本人到期周期交易端点（全量自动执行由 scheduler 每日 01:00 跑 B9）
    this.api('/api/ledger/recurring/run-due', { method: 'POST' })
      .then(d => {
        const n = (d && d.processed) || 0;
        this.showToast(n ? `已补跑 ${n} 笔到期周期交易 ✅` : '当前没有到期的周期交易');
        this.ledgerReloadDim('recurring');
      }).catch(e => this.showToast(e.message));
  },
};
