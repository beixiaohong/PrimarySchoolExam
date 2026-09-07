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

// 设置 tab 的六个 CRUD 维度 + 周期交易的表单字段定义（LedgerSettings.vue 渲染用）
export const LEDGER_DIMS = {
  accounts:  { label: '账户', path: 'accounts',  fields: [
    { k: 'account_name', label: '账户名称', ph: '如：零花钱卡' },
    { k: 'account_type', label: '账户类型', type: 'select', options: [
      { v: 'savings_card', t: '储蓄卡' }, { v: 'credit_card', t: '信用卡' }, { v: 'virtual_account', t: '虚拟账户' }] },
    { k: 'balance', label: '初始余额(元)', num: true }] },
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
  projects:  { label: '项目', path: 'projects', fields: [
    { k: 'name', label: '项目名称', ph: '如：暑期旅行' },
    { k: 'description', label: '描述', ph: '可空' },
    { k: 'budget', label: '预算(元)', num: true }] },
  recurring: { label: '周期交易', path: 'recurring', fields: [
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

// 分析环形图配色（Top6 + 其他；与全站紫色系协调的手写 SVG 用色）
const DONUT_COLORS = ['#8b7cf6', '#f6a87c', '#7cc5f6', '#7cf6b8', '#f67ca8', '#c5f67c', '#b9b3d0'];

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
    ledgerSummary: null,        // {total_assets, monthly_income, monthly_expense, monthly_balance}
    ledgerCatStats: [],         // statistics/category 原始行
    ledgerMonthly: [],          // statistics/monthly 的 monthly_data
    ledgerMonthlyYear: new Date().getFullYear(),
    ledgerBudget: [],           // statistics/budget 行
    ledgerPeriod: 'month',      // 分类统计周期：month / quarter / year
    // Tab4 设置：六维数据 + 周期交易 + 通用编辑弹窗
    ledgerAccounts: [], ledgerCategories: [], ledgerLocations: [],
    ledgerMerchants: [], ledgerPersons: [], ledgerProjects: [], ledgerRecurring: [],
    ledgerDimDialog: { show: false, dim: '', id: null, form: {} },
    ledgerNewDim: '',           // 各区块「+ 新建」下拉暂存（快捷新建入口）
  };
}

// ─────────── 账本 computed（由 appOptions.computed 用 ...ledgerComputed 合并）───────────
export const ledgerComputed = {
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
  // 选中项目后的预算执行率提示（分析 budget 数据复用；未加载/无预算返回空）
  ledgerProjectBudgetHint() {
    const pid = Number(this.ledgerForm.project_id);
    if (!pid) return '';
    const row = (this.ledgerBudget || []).find(b => b.project_id === pid);
    if (!row || !row.budget) return '';
    const pct = Math.round((row.spent / row.budget) * 100);
    return `「${row.project_name}」预算 ${this.ledgerFmt(row.budget)} 元，已用 ${this.ledgerFmt(row.spent)} 元（${pct}%）`;
  },
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
  _ledgerBase(dim) {
    // 六维列表 GET（返回数组；失败回空数组，不弹错打扰首屏）
    return this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/${dim}/`).catch(() => []);
  },
  async initLedger() {
    // 进入账本 tab：并行拉六维 + 周期交易 + 最近分类；再拉当前 tab 数据
    this.ledgerLoading = true;
    try {
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
      this.loadLedgerTabData();
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
    // settings 无独立拉取（基础维度已在 initLedger 拉齐）
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
  ledgerSubmitTx() {
    const f = this.ledgerForm;
    const amount = Math.round((Number(String(f.amount).trim()) || 0) * 100) / 100;  // 元，round 2 位
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
    const body = {
      transaction_type: f.transaction_type,
      amount,   // 元单位（Numeric(15,2)），不做 ×100 转分
      category_id: cat.id,
      from_account_id: f.from_account_id ? Number(f.from_account_id) : null,
      to_account_id: f.transaction_type === 'transfer' ? Number(f.to_account_id) : null,
      location_id: f.location_id ? Number(f.location_id) : null,
      merchant_id: f.merchant_id ? Number(f.merchant_id) : null,
      person_id: f.person_id ? Number(f.person_id) : null,
      project_id: f.project_id ? Number(f.project_id) : null,
      note: (f.note || '').trim() || null,
      transaction_time: f.transaction_time ? new Date(f.transaction_time).toISOString() : null,
    };
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
    }).catch(e => this.showToast(e.message));
  },
  ledgerEditBill(b) {
    // 账单 → 跳记一笔预填（编辑模式）
    const cat = (this.ledgerCategories || []).find(c => c.id === b.category_id);
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
    const base = `/api/ledger/users/${encodeURIComponent(this.user)}/statistics`;
    this.api(`${base}/summary?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.ledgerSummary = d; }).catch(() => { this.ledgerSummary = null; });
    this.api(`${base}/monthly?year=${this.ledgerMonthlyYear}`)
      .then(d => { this.ledgerMonthly = (d && d.monthly_data) || []; }).catch(() => { this.ledgerMonthly = []; });
    this.api(`${base}/budget?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.ledgerBudget = d || []; }).catch(() => { this.ledgerBudget = []; });
    this.loadLedgerCatStats();
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
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/statistics/monthly?year=${y}`)
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

  /* ─────────── Tab4 设置：六维 CRUD + 周期交易 ─────────── */
  loadLedgerBudget() {
    // 记一笔选中项目时的预算提示数据（复用 statistics/budget）
    this.api(`/api/ledger/users/${encodeURIComponent(this.user)}/statistics/budget?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.ledgerBudget = d || []; }).catch(() => {});
  },
  ledgerOpenDimDialog(dim, item) {
    // item 为空 = 新建；否则编辑预填（表单值统一转字符串便于 input 绑定）
    const defs = LEDGER_DIMS[dim];
    if (!defs) return;
    const form = {};
    for (const fd of defs.fields) {
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
        if (v === '') { body[fd.k] = dim === 'accounts' && fd.k === 'balance' ? 0 : null; continue; }
        const n = Math.round((Number(v) || 0) * 100) / 100;   // 元，round 2 位
        if (isNaN(n)) return this.showToast(`${fd.label}需为数字`);
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
