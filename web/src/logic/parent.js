// logic/parent.js：家长管理视图（tab='parent'）专属的 data / computed / methods。
//
// 由来（doc02 §八 红线 5：appOptions.js 按视图切分，一次一个视图）：从 3600+ 行的
// appOptions.js 中抽出「家长管理」这一块，导出三个纯字典，由 appOptions.js 用展开运算符合并：
//   data()    { return { ...parentData(),  ...其余 } }
//   computed:  { ...parentComputed, ...其余 }
//   methods:   { ...parentMethods,  ...其余 }
// 展开后 this 仍绑定同一个 App 实例（App.vue provide appCtx=this），所有 appCtx.xxx / this.xxx
// 调用点零改动。**刻意不用 Vue mixin 数组**——App.vue 是手工展开 appOptions，混入 mixin 数组会
// 改变合并语义。收尾强制校验：parentMethods 的键集合与 appOptions.methods 剩余键集合交集为空。
//
// 边界：本文件不含钻石充值相关逻辑（recharge*），那属于「用户端商城与支付闭环」任务范围。
// 留言（parent_messages）与周报寄语（weekly_reports.parent_note）后端两处存储与接口都不动，
// 仅在 ParentView 的 UI 层合并「给孩子写信」入口。

// ─────────── 家长管理 data（由 appOptions.data 用 ...parentData() 合并）───────────
export function parentData() {
  return {
    // 学习同步（家长面板）：预习/课堂同步/小升初衔接 + 教学进度
    studyFlags: { include_next: false, sync_mode: false, xsc_bridge: false },
    teachBooks: [], teachProgressItems: [], teachProgress: { book_id: 0, chapter: '' },
    recheckingId: null,        // 家长申诉列表中正在 AI 复核的申诉 id
    // 奖励闭环（家长面板）：兑换券管理 + 待确认心愿 + 新建券表单
    allCoupons: [], pendingWishes: [],
    newCoupon: { title: '', kind: 'custom', reason: '', requiredDays: 0, requiredWithinDays: 0 },
    parentNote: '',            // 周报寄语（放进本周周报，weekly_reports.parent_note）
    // 家长功能（Sprint 6）：密码解锁 + 留言 + 学习数据 + 题数设置 + 成长记录
    parentPhase: '',           // '' / loading / unset / locked / reset / open（加载态用 loading 避免误显已解锁面板）
    pwdForm: { pwd: '', pwd2: '', hintQ: '', hintA: '', unlock: '', resetA: '', resetPwd: '', old: '', new1: '', new2: '' },
    parentMsg: '', sentMsgs: [],
    examMin: { math_min: 5, chi_min: 5, eng_min: 5 },
    childStats: { week_attempts: 0, week_avg_score: 0, unmastered_wrong: 0, streak_days: 0, week_tasks_done: 0 },
    // 家长待处理申诉 + 补签（家长面板待办）
    pendingAppeals: [],
    showAllPending: false,    // 待处理申诉是否展开全部（避免一次渲染过多卡顿）
    appealNotes: {},          // {id: '备注'} 家长判题时填写的备注
    pendingMakeups: [],
    // 每日任务设置
    taskSettings: { items: [] },
    // mandatory: 每科强制任务完整列表（可替换默认固定项）；mandOpts: 每科可选类型库；_add: 各科下拉暂存
    taskDialog: { show: false, mandatory: { math: [], chi: [], eng: [] }, mandOpts: { math: [], chi: [], eng: [] },
      _add: { math: '', chi: '', eng: '' }, optional: [], subOpts: { math: [], chi: [], eng: [] }, disabled: [] },
    parentCustomTasks: [],
    customTaskForm: { title: '', subject: '数学', task_type: 'optional', target: 1 },
    // 网课（家长单独配置）
    parentCourses: [],
    courseForm: { title: '', video_url: '', subject: '', grade: 0, description: '' },
  };
}

// ─────────── 家长管理 computed（由 appOptions.computed 用 ...parentComputed 合并）───────────
export const parentComputed = {
  teachUnitOptions() {
    const b = (this.teachBooks || []).find(x => x.book_id === this.teachProgress.book_id);
    return b ? b.units : [];
  },
  teachProgressText() {
    const it = (this.teachProgressItems || []).find(x => x.subject === '英语');
    if (!it || (!it.book_name && !it.chapter)) return '';
    return [it.book_name, it.chapter].filter(Boolean).join(' · ');
  },
  // 家长端「每日任务设置」概览：各科强制任务条数
  mandatorySummary() {
    const m = (this.taskSettings && this.taskSettings.mandatory) || {};
    return ['数学', '语文', '英语'].map(s => `${s} ${(m[s] || []).length || 1}`).join(' · ');
  },
  // 家长待办角标合计：读 /api/parent/notices 的 todo_total（缺省 0）。对孩子也可见（提醒去找家长）
  parentTodoTotal() {
    return (this.notices && this.notices.todo_total) || 0;
  },
  // 家长模式是否已解锁（parentPhase==='open'），供 ParentView / 跳转卡判定
  parentOpen() {
    return this.parentPhase === 'open';
  },
};

// ─────────── 家长管理 methods（由 appOptions.methods 用 ...parentMethods 合并）───────────
export const parentMethods = {
  /* 家长管理：网课设置 */
  async loadParentCourses() {
    const d = await this.api(`/api/courses/parent?user_id=${encodeURIComponent(this.user)}`).catch(() => null);
    this.parentCourses = (d && d.courses) || [];
  },
  async addParentCourse() {
    const f = this.courseForm;
    if (!f.title.trim() || !f.video_url.trim()) { this.showToast('请填写标题和视频链接'); return; }
    try {
      await this.api('/api/courses/parent', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, title: f.title.trim(), video_url: f.video_url.trim(), subject: f.subject, grade: f.grade, description: f.description }),
      });
      this.showToast('网课已添加，孩子能在「网课」里看到 🎬');
      this.courseForm = { title: '', video_url: '', subject: '', grade: 0, description: '' };
      this.loadParentCourses(); this.loadCourses();
    } catch (e) { this.showToast(e.message); }
  },
  async removeParentCourse(c) {
    try {
      await this.api(`/api/courses/parent/${c.id}?user_id=${encodeURIComponent(this.user)}`, { method: 'DELETE' });
      this.showToast('已删除该网课');
      this.loadParentCourses(); this.loadCourses();
    } catch (e) { this.showToast(e.message); }
  },
  /* ─────────── 补签卡待确认（孩子发起 → 家长确认/拒绝）───────────
     调用关系：
       makeupCompleteTask（留在 appOptions.js）孩子用补签卡发起 → 服务端扣卡并把任务置为 makeup_pending（待家长确认）
       loadPendingMakeup  家长面板拉取这些待确认申请（pendingMakeups，供「补签卡待确认」区块渲染）
       confirmMakeup      家长确认生效/拒绝退回 → 回刷待确认列表与每日任务
     三者串成「孩子补签 → 家长审核」闭环。 */
  loadPendingMakeup() {
    this.api(`/api/tasks/makeup/pending?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.pendingMakeups = (d && d.items) || []; })
      .catch(() => { this.pendingMakeups = []; });
  },
  confirmMakeup(logId, action) {
    this.api('/api/tasks/makeup/confirm', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, log_id: logId, action }),
    }).then(() => {
      this.showToast(action === 'confirm' ? '补签已生效，任务完成 ✅' : '已拒绝，补签卡已退回 🔄');
      this.loadPendingMakeup();
      this.loadDailyTasks();
    }).catch(e => this.showToast(e.message));
  },
  parentConfirmTask(task) {
    // 手动确认（讲题/朗读/自定义任务等）：按任务 id 精确确认，支持同一学科多个手动任务
    this.api('/api/tasks/daily/claim', { method: 'POST', body: JSON.stringify({ user_id: this.user, task_id: task.id }) })
      .then(() => { this.loadDailyTasks(); this.showToast('已确认完成 ✅'); })
      .catch(e => this.showToast(e.message));
  },
  couponIcon(k) {
    return { cartoon: '📺', snack: '🍪', sticker: '🌟', toy: '🧸', outing: '🎡', custom: '🎫' }[k] || '🎫';
  },
  loadParentPanel() {
    this.api(`/api/rewards/parent-note?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.parentNote = (d && d.note) || ''; }).catch(() => { this.parentNote = ''; });
    this.api(`/api/rewards/parent-panel?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        this.allCoupons = (d && d.coupons) || [];
        this.pendingWishes = (d && d.wishes) || [];
      }).catch(() => { this.allCoupons = []; this.pendingWishes = []; });
    this.loadTaskSettings();
    this.loadAppeals();
    this.loadPendingMakeup();
    this.loadTeachPanel();
  },
  loadAppeals() {
    this.api(`/api/appeal/list?user_id=${encodeURIComponent(this.user)}&status=pending`)
      .then(d => { this.pendingAppeals = (d && d.appeals) || []; })
      .catch(() => { this.pendingAppeals = []; });
  },
  toggleAppeal(id) {
    this.appealExpanded[id] = !this.appealExpanded[id];
  },
  decideAppeal(a, ok) {
    if (a._deciding) return;            // 防重复提交（连点）
    try {
      a._deciding = true;
      this.showToast('正在处理申诉，请稍候…');   // 即时反馈：让用户知道按钮已响应
      const note = (this.appealNotes[a.id] || '').trim();
      // 兜底：15s 内请求未返回（网络挂起/401 等异常），强制解除禁用，避免按钮永久卡在「处理中…」
      const guard = setTimeout(() => { a._deciding = false; }, 15000);
      this.api('/api/appeal/decide', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, appeal_id: a.id, action: ok ? 'approve' : 'reject', note }),
      }).then(d => {
        // 立即本地移除该条，避免列表刷新前二次点击「已处理过」报错
        const idx = this.pendingAppeals.findIndex(x => x.id === a.id);
        if (idx >= 0) this.pendingAppeals.splice(idx, 1);
        delete this.appealNotes[a.id];
        if (ok) {
          // 后端可能降级批准（无做题记录）：按返回 note 提示，避免误报「已改判得分」
          this.showToast((d && d.note) || '已确认孩子做对了，本题改判正确、得分已重算 ✅');
        } else {
          this.showToast('已驳回申诉，维持原判');
        }
        this.loadDecidedAppeals();
        this.loadChildStats();
      }).catch(e => this.showToast('申诉处理失败：' + (e.message || e))).finally(() => {
        clearTimeout(guard);
        a._deciding = false;
      });
    } catch (e) {
      console.error('[decideAppeal] sync error:', e);
      this.showToast('申诉操作异常：' + (e.message || e));
      a._deciding = false;
    }
  },
  async aiRecheckAppeal(a) {
    if (!a) return;
    this.recheckingId = a.id;
    // 兜底：15s 内 AI 调用未返回（模型慢/异常），强制解除禁用，避免按钮卡死
    const guard = setTimeout(() => { this.recheckingId = null; }, 15000);
    let d = null;
    try {
      d = await this.aiRejudge({
        question_id: a.question_id || null,
        question: a.question,
        answer: a.correct_answer || '',
        user_answer: a.user_answer || '',
        subject: a.subject || '',
      });
    } catch (e) { this.showToast(e.message); }
    clearTimeout(guard);
    this.recheckingId = null;
    if (!d) return;
    if (d.correct) {
      let msg = '🤖 AI 复核：孩子答案正确';
      if (d.fixed) msg += '，参考答案已修正为 ' + d.correct_answer;
      this.showToast(msg);
      this.decideAppeal(a, true); // 同步通过申诉（家长免手动确认）
    } else if (d.ai_unavailable) {
      this.showToast('⚠️ AI 服务不可用，无法复查（' + (d.reason || '') + '）');
    } else if (d.ai_limited) {
      this.showToast('⏳ ' + (d.reason || 'AI 复查过于频繁，请稍后再试'));
    } else {
      this.showToast('🤖 AI 复核：' + (d.reason || '认为作答不正确'));
    }
  },
  /* ─────────── 家长功能（Sprint 6）：密码 + 留言 + 数据 + 题数 ─────────── */
  exitParentMode() {
    sessionStorage.removeItem('zx_parent_pwd');
    this.parentPhase = 'locked';
    this._resetPwdForm();
    this.loadRewards(); // 刷新孩子端数据（券状态等）
    this.showToast('已退出家长模式 🔒');
  },
  initParentPanel() {
    // 每次进入家长管理都重新校验密码状态：已设密码则必须输密码解锁，不再依赖会话记忆免密进入
    // （sessionStorage 在同标签页刷新时不清除，会导致「解锁一次→刷新仍是家长模式」的安全隐患）
    this.parentPhase = 'loading'; // 进入即置加载态，避免首屏 '' 误落已解锁面板（#181 闪烁修复）
    this.api(`/api/parent/status?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        this.parentPhase = (d && d.has_password) ? 'locked' : 'unset';
        if (this.parentPhase === 'locked') this.pwdForm.hintQ = (d && d.hint_question) || '';
      })
      .catch(() => { this.parentPhase = 'unset'; });
  },
  _resetPwdForm() {
    this.pwdForm = { pwd: '', pwd2: '', hintQ: '', hintA: '', unlock: '', resetA: '', resetPwd: '', old: '', new1: '', new2: '' };
  },
  setupParentPwd() {
    const { pwd, pwd2, hintQ, hintA } = this.pwdForm;
    if (!pwd || pwd.length < 4 || pwd.length > 32) return this.showToast('密码需 4-32 位');
    if (pwd !== pwd2) return this.showToast('两次输入的密码不一致');
    if (!hintQ.trim() || !hintA.trim()) return this.showToast('请填写密保问题和答案（忘记密码时重置用）');
    this.api('/api/parent/setup', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, password: pwd, hint_question: hintQ.trim(), hint_answer: hintA.trim() }),
    }).then(() => {
      this._resetPwdForm();
      this.parentPhase = 'open';
      sessionStorage.setItem('zx_parent_pwd', pwd);
      this.loadParentPanel(); this.loadChildStats(); this.loadExamSettings(); this.loadSentMsgs(); this.loadDailyTasks(); this.loadParentCourses();
      this.showToast('家长密码已设置，家长管理已解锁 🔓');
    }).catch(e => this.showToast(e.message));
  },
  unlockParent() {
    const pwd = this.pwdForm.unlock;
    if (!pwd) return this.showToast('请输入家长密码');
    this.api('/api/parent/unlock', {
      method: 'POST', body: JSON.stringify({ user_id: this.user, password: pwd }),
    }).then(() => {
      this._resetPwdForm();
      this.parentPhase = 'open';
      sessionStorage.setItem('zx_parent_pwd', pwd);
      this.loadParentPanel(); this.loadChildStats(); this.loadExamSettings(); this.loadSentMsgs(); this.loadDailyTasks(); this.loadParentCourses();
      this.showToast('欢迎回来，家长 👋');
    }).catch(e => this.showToast(e.message));
  },
  resetParentPwd() {
    const { resetA, resetPwd } = this.pwdForm;
    if (!resetA.trim() || !resetPwd) return this.showToast('请填写密保答案和新密码');
    this.api('/api/parent/reset-password', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, hint_answer: resetA.trim(), new_password: resetPwd }),
    }).then(() => {
      this._resetPwdForm();
      sessionStorage.removeItem('zx_parent_pwd');
      this.parentPhase = 'locked';
      this.showToast('密码已重置，请用新密码解锁 🔓');
    }).catch(e => this.showToast(e.message));
  },
  changeParentPwd() {
    const { old, new1, new2 } = this.pwdForm;
    if (!old || !new1) return this.showToast('请填写当前密码和新密码');
    if (new1 !== new2) return this.showToast('两次输入的新密码不一致');
    this.api('/api/parent/change-password', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, old_password: old, new_password: new1 }),
    }).then(() => {
      this._resetPwdForm();
      // 家长面板处于解锁态时同步更新本地缓存密码，避免后续敏感接口 403
      if (sessionStorage.getItem('zx_parent_pwd')) sessionStorage.setItem('zx_parent_pwd', new1);
      this.showToast('家长密码已修改 ✅');
    }).catch(e => this.showToast(e.message));
  },
  loadChildStats() {
    this.api(`/api/parent/child-stats?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.childStats = d || this.childStats; })
      .catch(() => {});
  },
  loadExamSettings() {
    this.api(`/api/parent/exam-settings?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.examMin = d || this.examMin; })
      .catch(() => {});
  },
  saveExamSettings() {
    const m = { math_min: Number(this.examMin.math_min), chi_min: Number(this.examMin.chi_min), eng_min: Number(this.examMin.eng_min) };
    for (const k in m) {
      if (!Number.isInteger(m[k]) || m[k] < 1 || m[k] > 50) return this.showToast(`每科最少题数需为 1-50 的整数`);
    }
    this.api('/api/parent/exam-settings', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, ...m }),
    }).then(d => { this.examMin = d || this.examMin; this.showToast('试卷最少题数已保存 ✅'); })
      .catch(e => this.showToast(e.message));
  },
  sendParentMsg() {
    const content = (this.parentMsg || '').trim();
    if (!content) return this.showToast('写点什么再发送吧');
    this.api('/api/parent/message', {
      method: 'POST', body: JSON.stringify({ user_id: this.user, content }),
    }).then(() => {
      this.parentMsg = '';
      this.loadSentMsgs();
      this.showToast('留言已发送，孩子登录就能看到 💌');
    }).catch(e => this.showToast(e.message));
  },
  loadSentMsgs() {
    this.api(`/api/parent/messages?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.sentMsgs = (d && d.messages) || []; })
      .catch(() => { this.sentMsgs = []; });
  },
  loadTaskSettings() {
    this.api(`/api/tasks/settings?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        this.taskSettings = d || { items: [] };
        this.studyFlags = Object.assign(
          { include_next: false, sync_mode: false, xsc_bridge: false },
          (d && d.study_flags) || {},
        );
      })
      .catch(() => { this.taskSettings = { items: [] }; });
  },
  /* ─────────── 学习同步（预习/课堂同步/衔接开关 + 教学进度） ─────────── */
  toggleStudyFlag(key) {
    const next = !this.studyFlags[key];
    this.api('/api/tasks/settings', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, settings: { [key]: next } }),
    }).then(d => {
      this.studyFlags[key] = next;
      if (d && d.study_flags) this.studyFlags = Object.assign(this.studyFlags, d.study_flags);
      const label = { include_next: '预习下学期', sync_mode: '课堂同步', xsc_bridge: '小升初衔接' }[key] || key;
      this.showToast((next ? '已开启：' : '已关闭：') + label);
    }).catch(e => this.showToast(e.message));
  },
  loadTeachPanel() {
    this.api(`/api/study/progress/options?user_id=${encodeURIComponent(this.user)}&grade=${this.grade}&subject=英语`)
      .then(d => { this.teachBooks = (d && d.books) || []; })
      .catch(() => { this.teachBooks = []; });
    this.api(`/api/study/progress?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        this.teachProgressItems = (d && d.items) || [];
        const eng = this.teachProgressItems.find(x => x.subject === '英语');
        if (eng) this.teachProgress = { book_id: eng.book_id || 0, chapter: eng.chapter || '' };
      }).catch(() => { this.teachProgressItems = []; });
  },
  onTeachBookChange() {
    // 切册后当前单元不在新册内则清空
    if (this.teachProgress.chapter && this.teachUnitOptions.indexOf(this.teachProgress.chapter) < 0) {
      this.teachProgress.chapter = '';
    }
  },
  saveTeachProgress() {
    this.api('/api/study/progress', {
      method: 'PUT',
      body: JSON.stringify({
        user_id: this.user, subject: '英语',
        book_id: this.teachProgress.book_id || 0,
        chapter: this.teachProgress.chapter || '',
      }),
    }).then(() => { this.showToast('教学进度已保存'); this.loadTeachPanel(); })
      .catch(e => this.showToast(e.message));
  },
  showTaskSettingsDialog() {
    // 初始化弹窗数据
    const items = this.taskSettings.items || [];
    const disabled = [];
    const optional = [];
    // 从当前设置中提取（映射中文到英文key）
    const subjMap = { '数学': 'math', '语文': 'chi', '英语': 'eng' };
    const revMap = { math: '数学', chi: '语文', eng: '英语' };
    const DEFAULTS = { math: 'math_exam', chi: 'chi_classical', eng: 'eng_vocab' };
    const KEYS = ['math', 'chi', 'eng'];
    // ── 强制任务：每科为「完整 code 列表」，家长可替换默认固定项（后端 mandatory 语义）
    const cur = this.taskSettings.mandatory || {};
    const choices = this.taskSettings.mandatory_choices || {};
    const mandatory = {};
    const mandOpts = {};
    for (const key of KEYS) {
      const subj = revMap[key];
      // 下拉选项优先用后端下发的该科可选类型库（含标题/默认目标/是否全量），缺失时回退前端内置列表
      mandOpts[key] = (choices[subj] && choices[subj].length)
        ? choices[subj].map(o => ({ code: o.code, title: o.title, target: o.target,
          is_default: !!o.is_default, manual: !!o.manual, locked: !!o.locked }))
        : this.allTaskOptions.filter(t => t.subject === subj);
      // 后端返回完整列表；未配置/空则回退该科默认项
      const codes = (Array.isArray(cur[subj]) && cur[subj].length) ? cur[subj] : [DEFAULTS[key]];
      mandatory[key] = codes.map(code => {
        const opt = mandOpts[key].find(o => o.code === code);
        const item = items.find(i => i.code === code);
        return { code, title: opt ? opt.title : code, locked: opt ? !!opt.locked : false,
          target: item ? item.target : (opt ? opt.target : 1) };
      });
    }
    for (const it of items) {
      if (it.enabled === false) disabled.push(it.code);
    }
    // 回显家长已添加的可选任务（后端 settings.optional 存 code 列表）
    for (const code of this.taskSettings.optional || []) {
      const def = this.allTaskOptions.find(o => o.code === code);
      if (!def) continue;
      const item = items.find(i => i.code === code);
      optional.push({ subject: subjMap[def.subject] || 'math', code, target: item ? item.target : 1 });
    }
    // 预计算各科选项（避免模板中调用方法）；可选任务下拉排除背诵类全量任务
    const all = this.allTaskOptions;
    const UNCONFIGURABLE = ['chi_classical', 'eng_vocab'];
    const subOpts = {
      math: all.filter(t => t.subject === '数学' && !UNCONFIGURABLE.includes(t.code)),
      chi: all.filter(t => t.subject === '语文' && !UNCONFIGURABLE.includes(t.code)),
      eng: all.filter(t => t.subject === '英语' && !UNCONFIGURABLE.includes(t.code)),
    };
    this.taskDialog = { show: true, mandatory, mandOpts, optional, disabled, subOpts,
      _add: { math: '', chi: '', eng: '' } };
    this.loadParentCustomTasks();
  },
  /* ─────────── 强制任务自定义（每科下拉多选） ─────────── */
  mandSubjectLabel(key) {
    return { math: '数学', chi: '语文', eng: '英语' }[key] || key;
  },
  mandDefaultCode(key) {
    return { math: 'math_exam', chi: 'chi_classical', eng: 'eng_vocab' }[key];
  },
  // 该科尚未选中的强制任务类型（下拉可选）
  mandAvail(key) {
    const used = (this.taskDialog.mandatory[key] || []).map(m => m.code);
    return (this.taskDialog.mandOpts[key] || []).filter(o => used.indexOf(o.code) < 0);
  },
  addMandatory(key) {
    const code = this.taskDialog._add[key];
    if (!code) return this.showToast('先选择要添加的任务类型');
    const opt = (this.taskDialog.mandOpts[key] || []).find(o => o.code === code);
    if (!opt) return;
    const item = (this.taskSettings.items || []).find(i => i.code === code);
    this.taskDialog.mandatory[key].push({ code, title: opt.title, locked: !!opt.locked,
      target: item ? item.target : opt.target });
    this.taskDialog._add[key] = '';
  },
  removeMandatory(key, idx) {
    const rows = this.taskDialog.mandatory[key] || [];
    if (rows.length <= 1) {
      return this.showToast(`${this.mandSubjectLabel(key)}至少保留 1 项强制任务，可换成其它类型`);
    }
    rows.splice(idx, 1);
  },
  loadParentCustomTasks() {
    this.api(`/api/tasks/custom-task?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.parentCustomTasks = d || []; })
      .catch(() => { this.parentCustomTasks = []; });
  },
  addParentCustomTask() {
    const f = this.customTaskForm;
    if (!f.title || !f.title.trim()) return this.showToast('请输入自定义任务标题');
    this.api('/api/tasks/custom-task', {
      method: 'POST',
      body: JSON.stringify({
        user_id: this.user, title: f.title.trim(),
        subject: f.subject, task_type: f.task_type, target: Number(f.target) || 1,
      }),
    }).then(() => {
      this.customTaskForm = { title: '', subject: '数学', task_type: 'optional', target: 1 };
      this.loadParentCustomTasks();
      this.loadDailyTasks();
      this.showToast('自定义任务已添加 ✅');
    }).catch(e => this.showToast(e.message));
  },
  deleteParentCustomTask(id) {
    this.api(`/api/tasks/custom-task/${id}?user_id=${encodeURIComponent(this.user)}`, { method: 'DELETE' })
      .then(() => {
        this.loadParentCustomTasks();
        this.loadDailyTasks();
        this.showToast('已删除自定义任务');
      }).catch(e => this.showToast(e.message));
  },
  _optForSubj(subj) {
    return this.allTaskOptions.filter(t => t.subject === subj);
  },
  saveTaskDialog() {
    const targets = {};
    const enabled = {};
    const { mandatory, optional, disabled } = this.taskDialog;
    // 背诵类固定「全量完成」语义，不可作为可选任务，但作为强制任务时数量仍回传供回显
    const UNCONFIGURABLE = ['chi_classical', 'eng_vocab'];
    // 处理所有任务的目标数量
    for (const it of this.taskSettings.items || []) {
      if (UNCONFIGURABLE.includes(it.code)) continue;
      targets[it.code] = it.target;
      enabled[it.code] = !disabled.includes(it.code);
    }
    // 强制任务：每科回传「完整 code 列表」（替换默认固定项），并写入各自目标数
    const revMap = { math: '数学', chi: '语文', eng: '英语' };
    const mandatoryOut = {};
    for (const key of ['math', 'chi', 'eng']) {
      const rows = mandatory[key] || [];
      const codes = [];
      for (const m of rows) {
        if (!m.code || codes.includes(m.code)) continue;
        codes.push(m.code);
        targets[m.code] = m.target || 1;
        if (!UNCONFIGURABLE.includes(m.code)) enabled[m.code] = true;
      }
      mandatoryOut[revMap[key]] = codes;
    }
    // 处理可选任务（新增的）
    for (const opt of optional) {
      if (opt.code && opt.target) {
        if (UNCONFIGURABLE.includes(opt.code)) continue;
        targets[opt.code] = opt.target;
        enabled[opt.code] = true;
      }
    }
    // 家长添加的可选任务 code 列表（去重去空）
    const optionalCodes = [...new Set(optional.filter(o => o.code).map(o => o.code))];
    const settings = { targets, enabled, mandatory: mandatoryOut, optional: optionalCodes };
    this.api('/api/tasks/settings', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, settings }),
    }).then(d => {
      this.taskSettings = d || { items: [] };
      this.taskDialog.show = false;
      this.loadDailyTasks();
      this.showToast('任务设置已保存 ✅');
    }).catch(e => this.showToast(e.message));
  },
  createCoupon() {
    const title = (this.newCoupon.title || '').trim();
    if (!title) return this.showToast('先写下兑换券内容');
    const requiredDays = Math.max(0, Math.min(30, Number(this.newCoupon.requiredDays) || 0));
    const within = Math.max(0, Math.min(365, Number(this.newCoupon.requiredWithinDays) || 0));
    const finalWithin = (within && within < requiredDays) ? requiredDays : within; // 限期不能短于所需天数
    this.api('/api/rewards/coupon', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, title, kind: this.newCoupon.kind, reason: this.newCoupon.reason || '', required_days: requiredDays, required_within_days: finalWithin }),
    }).then(() => {
      this.newCoupon.title = ''; this.newCoupon.reason = ''; this.newCoupon.requiredDays = 0; this.newCoupon.requiredWithinDays = 0;
      this.loadParentPanel(); this.loadRewards();
      if (requiredDays > 0 && finalWithin > 0) {
        this.showToast(`已添加：需在 ${finalWithin} 天内三科全勤 ${requiredDays} 天得 1 张，超时进度清零 🎫`);
      } else if (requiredDays > 0) {
        this.showToast(`已添加：三科全勤 ${requiredDays} 天获取后才计入成长奖励记录 🎫`);
      } else {
        this.showToast('兑换券已添加，孩子已即时获得 🎫');
      }
    }).catch(e => this.showToast(e.message));
  },
  redeemCoupon(c) {
    this.api(`/api/rewards/coupon/${c.id}/redeem`, {
      method: 'POST', body: JSON.stringify({ user_id: this.user }),
    }).then(() => {
      this.loadParentPanel(); this.loadRewards();
      this.showToast(`已核销 1 张「${c.title}」✅`);
    }).catch(e => this.showToast(e.message));
  },
  toggleCoupon(c) {
    this.api(`/api/rewards/coupon/${c.id}/toggle`, {
      method: 'POST', body: JSON.stringify({ user_id: this.user }),
    }).then(() => {
      this.loadParentPanel(); this.loadRewards();
    }).catch(e => this.showToast(e.message));
  },
  confirmWish(w) {
    const url = w.status === 'pending' ? `/api/rewards/wish/${w.id}/confirm` : `/api/rewards/wish/${w.id}/redeem`;
    const body = { user_id: this.user };
    if (w.status === 'pending_redeem') body.reason = (w.redeemReason || '').trim();
    this.api(url, { method: 'POST', body: JSON.stringify(body) })
      .then(() => {
        this.loadParentPanel(); this.loadRewards();
        this.showToast(w.status === 'pending' ? '心愿已确认开始，孩子加油 🌟' : '已兑现，太棒了 🎉');
      }).catch(e => this.showToast(e.message));
  },
  taskOptTitle(t, target) {
    // 任务标题随目标数量动态变化：替换标题中最后一个数字（如“完成 1 套”→“完成 3 套”），与后端 _display_title 规则一致
    const n = Number(target) || 1;
    return String(t.title || '').replace(/\d+(?![\s\S]*\d)/, String(n));
  },
  archiveWish(w) {
    this.api(`/api/rewards/wish/${w.id}/archive`, {
      method: 'POST', body: JSON.stringify({ user_id: this.user }),
    }).then(() => {
      this.loadParentPanel(); this.loadRewards();
      this.showToast('心愿已移除');
    }).catch(e => this.showToast(e.message));
  },
  saveParentNote() {
    this.api('/api/rewards/parent-note', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, note: this.parentNote || '' }),
    }).then(() => {
      this.showToast('悄悄话已保存 💌');
    }).catch(e => this.showToast(e.message));
  },
};
