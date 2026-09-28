// gaoxiang.js：软考高项备考（面向非学生成人用户）的 data / computed / methods。
// 仅依赖通用 api/goTab/showToast（通用方法保留在主文件）；与其他 logic/* 经展开运算符
// 合并后 this 仍绑定同一实例。后端契约见 app/domains/assessment/routers/gaoxiang.py：
//   GET  /api/gx/domains                    -> {domains:[十大知识域], qtypes}
//   GET  /api/gx/knowledge?user_id&domain   -> {items:[{id,domain,code,title,summary}]}
//   GET  /api/gx/knowledge/{kid}?user_id    -> {id,...,content}
//   POST /api/gx/knowledge/generate         {user_id,domain} -> {generated,added}
//   POST /api/gx/quiz/generate              {user_id,domain,qtype,count} -> {questions:[{id,qtype,question,options}]}
//   POST /api/gx/quiz/submit                {user_id,answers:[{question_id,answer,duration_ms}]} -> {results:[{question_id,is_correct,correct,analysis}]}
//   GET  /api/gx/wrong?user_id              -> {items:[...],count}
//   POST /api/gx/wrong/master               {user_id,question_id}
//   POST /api/gx/case/generate              {user_id,domain} -> {question_id,background,sub_questions:[{q,points}]}
//   POST /api/gx/case/grade                 {user_id,question_id,user_answer} -> {score,feedback}
//   GET  /api/gx/progress?user_id           -> {domains:[...], summary:{...}}
//
// 设计约定：判分在服务端（答案不下发前端），前端只做展示与提交；AI 生成均可能慢
// （数秒），相关按钮一律带 loading 防重复点击。

export function gaoxiangData() {
  return {
    // ── 通用 ──
    gxSub: 'quiz',          // 子页签：knowledge / quiz / case / wrong / progress（默认刷题，备考主路径）
    gxDomains: [],          // 十大知识域
    gxLoading: false,       // 首次进入总开关
    // ── 知识点 ──
    gxKDomain: '整体管理',
    gxKList: [],            // 列表（无正文）
    gxKLoading: false,
    gxKDetail: null,        // 当前阅读的知识点（含 content）
    gxKGenning: false,      // AI 生成中
    // ── 刷题 ──
    gxQDomain: '整体管理',
    gxQType: 'single',      // single / multi
    gxQCount: 5,
    gxQuestions: [],        // [{id,qtype,question,options}]
    gxAnswers: {},          // qid → 'A'/'ABD'
    gxQResult: null,        // {results:[{question_id,is_correct,correct,analysis}]}
    gxQLoading: false,
    gxQSubmitting: false,
    gxQStartAt: 0,          // 本组题开始时间（算用时）
    // ── 案例分析 ──
    gxC_domain: '风险管理',
    gxC_question: null,     // {question_id, background, sub_questions}
    gxC_answer: '',         // 作答全文（一个文本框，考生自己组织分点）
    gxC_result: null,       // {score, feedback}
    gxC_loading: false,
    gxC_grading: false,
    // ── 错题本 ──
    gxWrong: [],
    gxWrongLoading: false,
    // ── 进度 ──
    gxProgress: null,
  };
}

export const gaoxiangComputed = {
  // 刷题结果按 qid 索引，模板取用方便
  gxResultMap() {
    const m = {};
    ((this.gxQResult && this.gxQResult.results) || []).forEach(r => { m[r.question_id] = r; });
    return m;
  },
  // 本组题是否全部作答（未答完禁用提交）
  gxAllAnswered() {
    return this.gxQuestions.length > 0 &&
      this.gxQuestions.every(q => (this.gxAnswers[q.id] || '').trim());
  },
  // 本组题对了几道（提交后顶部的结算条）
  gxCorrectCount() {
    return ((this.gxQResult && this.gxQResult.results) || [])
      .filter(r => r.is_correct === true).length;
  },
  // 案例作答是否可提交（至少 20 字，避免空跑一次 AI）
  gxC_canSubmit() {
    return (this.gxC_answer || '').trim().length >= 20 && !this.gxC_grading;
  },
  // 进度总览（未加载时兜底空结构）
  gxProgressRows() {
    return (this.gxProgress && this.gxProgress.domains) || [];
  },
};

export const gaoxiangMethods = {
  /* ─────────── 进入页面（goTab('gaoxiang') 钩子调用） ─────────── */
  initGaoxiang() {
    if (!this.user) return;
    if (!this.gxDomains.length) {
      this.api('/api/gx/domains').then(d => {
        this.gxDomains = (d && d.domains) || [];
      }).catch(() => {});
    }
    this.gxLoadProgress();
    this.gxLoadKnowledge();
    this.gxLoadWrong();
  },

  /* ─────────── 知识点 ─────────── */
  gxLoadKnowledge() {
    this.gxKLoading = true;
    this.api(`/api/gx/knowledge?user_id=${encodeURIComponent(this.user)}&domain=${encodeURIComponent(this.gxKDomain)}`)
      .then(d => { this.gxKList = (d && d.items) || []; })
      .catch(() => { this.gxKList = []; })
      .finally(() => { this.gxKLoading = false; });
  },
  gxPickDomain(d) {
    this.gxKDomain = d;
    this.gxKDetail = null;
    this.gxLoadKnowledge();
  },
  gxOpenKnowledge(k) {
    this.api(`/api/gx/knowledge/${k.id}?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.gxKDetail = d || null; })
      .catch(() => this.showToast('读取失败，稍后再试'));
  },
  gxClearKnowledge() { this.gxKDetail = null; },
  gxCloseKnowledge() { this.gxKDetail = null; },
  // AI 生成该知识域知识点（慢操作，按钮转圈防重复）
  gxGenerateKnowledge() {
    if (this.gxKGenning) return;
    this.gxKGenning = true;
    this.api('/api/gx/knowledge/generate', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, domain: this.gxKDomain }),
    }).then(d => {
      const added = (d && d.added) || 0;
      this.showToast(added > 0 ? `已生成 ${added} 个新知识点` : '该知识域知识点已齐（无新增）');
      this.gxLoadKnowledge();
    }).catch(() => this.showToast('AI 生成失败，稍后再试'))
      .finally(() => { this.gxKGenning = false; });
  },

  /* ─────────── 刷题 ─────────── */
  gxQuizDomain(d) { this.gxQDomain = d; },
  gxQuizType(t) { this.gxQType = t; },
  gxQuizStart() {
    if (this.gxQLoading) return;
    this.gxQLoading = true;
    this.gxQuestions = []; this.gxAnswers = {}; this.gxQResult = null;
    this.api('/api/gx/quiz/generate', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, domain: this.gxQDomain,
                             qtype: this.gxQType, count: this.gxQCount }),
    }).then(d => {
      this.gxQuestions = (d && d.questions) || [];
      if (!this.gxQuestions.length) this.showToast('没出出题来，稍后再试一次');
      this.gxQStartAt = Date.now();
    }).catch(() => this.showToast('出题失败，稍后再试'))
      .finally(() => { this.gxQLoading = false; });
  },
  // 多选点击选项：切换选中（归一为字母升序），单选直接置值
  gxToggleOption(q, opt) {
    if (this.gxQResult) return;   // 已提交锁定
    const letter = (opt || '').trim().charAt(0).toUpperCase();
    if (!/^[A-Z]$/.test(letter)) return;
    if (q.qtype === 'multi') {
      const cur = new Set((this.gxAnswers[q.id] || '').split('')).add(letter);
      this.gxAnswers = Object.assign({}, this.gxAnswers,
        { [q.id]: [...cur].sort().join('') });
    } else {
      this.gxAnswers = Object.assign({}, this.gxAnswers, { [q.id]: letter });
    }
  },
  gxIsPicked(q, opt) {
    const letter = (opt || '').trim().charAt(0).toUpperCase();
    return ((this.gxAnswers[q.id] || '').indexOf(letter) >= 0);
  },
  gxSubmitQuiz() {
    if (this.gxQSubmitting || !this.gxAllAnswered) return;
    this.gxQSubmitting = true;
    const dur = Date.now() - (this.gxQStartAt || Date.now());
    this.api('/api/gx/quiz/submit', {
      method: 'POST',
      body: JSON.stringify({
        user_id: this.user,
        answers: this.gxQuestions.map(q => ({
          question_id: q.id, answer: this.gxAnswers[q.id] || '',
          duration_ms: Math.round(dur / this.gxQuestions.length),
        })),
      }),
    }).then(d => {
      this.gxQResult = d || { results: [] };
      this.gxLoadWrong();      // 答错可能新增错题，静默刷新错题本
      this.gxLoadProgress();   // 进度同步刷新
    }).catch(() => this.showToast('提交失败，稍后再试'))
      .finally(() => { this.gxQSubmitting = false; });
  },
  // 单题反馈样式：对/错/未找到
  gxResultClass(qid) {
    const r = this.gxResultMap[qid];
    if (!r) return '';
    return r.is_correct === true ? 'ok' : 'bad';
  },

  /* ─────────── 案例分析 ─────────── */
  gxCdomain(d) { this.gxC_domain = d; },
  gxCaseStart() {
    if (this.gxC_loading) return;
    this.gxC_loading = true;
    this.gxC_question = null; this.gxC_answer = ''; this.gxC_result = null;
    this.api('/api/gx/case/generate', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, domain: this.gxC_domain }),
    }).then(d => {
      this.gxC_question = d || null;
      if (!d) this.showToast('没出出来，稍后再试一次');
    }).catch(() => this.showToast('出题失败，稍后再试'))
      .finally(() => { this.gxC_loading = false; });
  },
  gxCaseGrade() {
    if (!this.gxC_canSubmit || !this.gxC_question) return;
    this.gxC_grading = true;
    this.api('/api/gx/case/grade', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user,
                             question_id: this.gxC_question.question_id,
                             user_answer: this.gxC_answer }),
    }).then(d => {
      this.gxC_result = d || null;
      this.gxLoadProgress();
    }).catch(() => this.showToast('批改失败，稍后再试'))
      .finally(() => { this.gxC_grading = false; });
  },

  /* ─────────── 错题本 ─────────── */
  gxLoadWrong() {
    this.gxWrongLoading = true;
    this.api(`/api/gx/wrong?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.gxWrong = (d && d.items) || []; })
      .catch(() => { this.gxWrong = []; })
      .finally(() => { this.gxWrongLoading = false; });
  },
  gxMasterWrong(w) {
    this.api('/api/gx/wrong/master', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user, question_id: w.question_id }),
    }).then(() => this.gxLoadWrong())
      .catch(() => this.showToast('操作失败，稍后再试'));
  },
  // 从错题重做：复用刷题区（把这道题装进刷题组）
  gxRetryWrong(w) {
    this.gxSub = 'quiz';
    this.gxQDomain = w.domain;
    this.gxQType = w.qtype === 'multi' ? 'multi' : 'single';
    this.gxQuestions = [{ id: w.question_id, qtype: w.qtype || 'single',
                          question: w.question, options: w.options }];
    this.gxAnswers = {}; this.gxQResult = null;
    this.gxQStartAt = Date.now();
  },

  /* ─────────── 进度 ─────────── */
  gxLoadProgress() {
    this.api(`/api/gx/progress?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.gxProgress = d || null; })
      .catch(() => {});
  },
  // 正确率文案（null=还没做过）
  gxAccText(row) {
    return row.accuracy === null || row.accuracy === undefined ? '未开始' : row.accuracy + '%';
  },
  /* ─────────── 子页签 ─────────── */
  gxPickSub(sub) {
    this.gxSub = sub;
    if (sub === 'wrong') this.gxLoadWrong();
    if (sub === 'progress') this.gxLoadProgress();
    if (sub === 'knowledge' && !this.gxKList.length) this.gxLoadKnowledge();
  },
};
