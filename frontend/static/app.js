const { createApp } = Vue;

createApp({
  data() {
    return {
      // 登录
      user: '', username: '', grade: 6, subject: '英语',
      // 导航
      tab: 'home',
      // 全局统计
      streakDays: 0, totalTodo: 0, avgScore: 0,
      masteredTotal: 0, wrongBadge: 0,
      // 首页
      dashboard: null, todayTasks: [],
      dailyTasks: null, dailyTaskStats: { done_count: 0, total: 3, streak_days: 0 },
      reviewQueue: { items: [] },
      queueToday: 0, queueTodayNames: '', queueTomorrow: 0, queueDayAfter: 0, queueLater: 0,
      vocabTotal: 0, vocabLearned: 0,
      // 刷题中心
      practiceSub: 'generate', genDifficulty: '综合', genCount: 30,
      mathCategories: [], selectedCategories: [],
      engTypes: [], _engTypes: [], _chiTypes: [], selectedTypes: [], generating: false,
      grammarPoints: [], grammarCategory: '',
      grammarQuiz: [], grammarQuizIndex: 0, grammarSubmitted: false, grammarInput: '',
      grammarFeedbackOk: false, grammarCurrentAnswer: '', grammarCurrentExplanation: '',
      grammarResult: null,
      attempts: null, recentAttempts: [], statsAttempts: 0,
      attemptDetail: { show: false, id: 0, title: '', score: 0, correct: 0, total: 0, items: [] },
      // 背诵中心
      reciteSub: 'words',
      vocabToday: { new_words: [], review_words: [], stats: { total_words: 0, learned: 0, mastered: 0, due_today: 0, new_remaining: 0, new_today: 0, streak_days: 0 } },
      classicalToday: { new_texts: [], review_texts: [], stats: { total: 0, learned: 0, mastered: 0, due_today: 0, new_remaining: 0, streak_days: 0 } },
      classicalTexts: [],
      wordSession: { active: false, done: false, mode: 'new', words: [], i: 0, revealed: false, okCount: 0, results: [] },
      textSession: { active: false, done: false, mode: 'new', texts: [], i: 0, okCount: 0, failCount: 0, results: [] },
      textDetail: { show: false, id: 0, title: '', author: '', dynasty: '', grade: 0, text_type: '', content: '' },
      // 错题本
      wrongAnalysis: { total: 0, pending: 0, mastered: 0, mastery_rate: 0, by_cause: [], by_subject: [] },
      wrongScreen: 'list', wrongKind: 'all', wrongStatus: 'pending',
      wrongItems: [], curWrong: null,
      // AI 错题讲解（Sprint 2）：内联展示，状态挂在 quiz 题目项 / curWrong 上
      // 心情打卡（Sprint 2）
      moodTrend: null, moodNote: '', moodPicking: false,
      // 奖励闭环 + 成长周报（Sprint 3）
      rewards: null,
      allCoupons: [], pendingWishes: [],
      newCoupon: { title: '', kind: 'custom', reason: '', requiredDays: 0 },
      wishOverlay: { show: false, title: '', target: 5 },
      weeklyOverlay: { show: false }, weeklyLoading: false, weekly: null,
      shareImg: '', parentNote: '',
      // 家长功能（Sprint 6）：密码解锁 + 留言 + 学习数据 + 题数设置 + 成长记录
      parentPhase: '',           // unset / locked / reset / open（sessionStorage 记忆解锁）
      pwdForm: { pwd: '', pwd2: '', hintQ: '', hintA: '', unlock: '', resetA: '', resetPwd: '', old: '', new1: '', new2: '' },
      parentMsg: '', sentMsgs: [],
      parentMsgs: { unread: 0, messages: [] },
      examMin: { math_min: 5, chi_min: 5, eng_min: 5 },
      childStats: { week_attempts: 0, week_avg_score: 0, unmastered_wrong: 0, streak_days: 0, week_tasks_done: 0 },
      notices: null,
      rewardTimeline: [],
      // 申诉（AI 判题复核 + 孩子「我做对了」家长二次确认）
      pendingAppeals: [],
      submitWrongIds: {}, submitWrongNew: {},
      // 每日任务目标数量（家长设置）
      taskSettings: { items: [] },
      // Sprint 4：称号 / 挑战赛 / 学期目标 / 小老师
      titleInfo: null, titleBadges: [],
      chalOverlay: { show: false, stage: 'pick', kind: 'math', questions: [], i: 0, timeLeft: 60, input: '', correct: 0, total: 0, newBest: false },
      chalCombo: 0, chalBest: { math: { best: 0 }, word: { best: 0 } },
      goalOverlay: { show: false, kind: 'score', target: 90, deadline: '', subject: '数学' },
      goals: [],
      teachOverlay: { show: false, step: 1, card: null, answerText: '', result: '', hint: '' },
      teachDue: [], recheckOverlay: { show: false, card: null, answerText: '' },
      // 通用答题状态机
      quiz: { active: false, done: false, title: '', items: [], i: 0, fillText: '', correct: 0, wrongCount: 0, score: 0, source: null },
      // 爽感反馈：连击 / 飘字 / 宝箱 / 极速模式 / 自我超越
      combo: 0, maxCombo: 0,
      floatFx: { show: false, text: '', ok: true },
      chestReward: '', turbo: false, selfCompare: null,
      // 试卷中心
      papers: [],
      // 十万个为什么（Sprint 5）
      qaAsk: '', qaProvider: 'zhipu', qaLoading: false, qaAnswer: null,
      qaModels: [], qaModelsVip: false,
      qaHistory: [], qaHistType: 'all',
      // 统计
      vocabStats: {}, classicalStats: {}, grammarStats: {},
      // Toast
      toast: { show: false, msg: '' },
    };
  },

  computed: {
    greeting() {
      const h = new Date().getHours();
      return h < 6 ? '夜深了' : h < 12 ? '早上好' : h < 18 ? '下午好' : '晚上好';
    },
    vocabPct() {
      const s = this.vocabToday.stats || {};
      return s.total_words ? Math.round(s.learned / s.total_words * 100) : 0;
    },
    heroPct() {
      const vt = this.vocabTotal || 0;
      const vp = vt ? (this.vocabLearned || 0) / vt : 0;
      const cs = (this.classicalToday && this.classicalToday.stats) || {};
      const tp = cs.total ? (cs.learned || 0) / cs.total : 0;
      const wt = this.wrongAnalysis.total || 0;
      const wp = wt ? (this.wrongAnalysis.mastered || 0) / wt : 0;
      return Math.round((vp * 0.4 + tp * 0.3 + wp * 0.3) * 100);
    },
    quizPct() {
      return this.quiz.items.length ? Math.round(this.quiz.i / this.quiz.items.length * 100) : 0;
    },
    wordPct() {
      return this.wordSession.words.length ? Math.round(this.wordSession.i / this.wordSession.words.length * 100) : 0;
    },
    textPct() {
      return this.textSession.texts.length ? Math.round(this.textSession.i / this.textSession.texts.length * 100) : 0;
    },
    donutSegs() {
      const causes = this.wrongAnalysis.by_cause || [];
      const total = causes.reduce((s, c) => s + (c.pending || 0), 0);
      if (!total) return [];
      const C = 2 * Math.PI * 90;
      let acc = 0;
      return causes.filter(c => c.pending > 0).map(c => {
        const len = (c.pending / total) * C;
        const seg = { color: this.causeColor(c.code), len: len.toFixed(1), off: (-acc).toFixed(1) };
        acc += len;
        return seg;
      });
    },
    topCause() {
      const causes = (this.wrongAnalysis.by_cause || []).slice().sort((a, b) => (b.pending || 0) - (a.pending || 0));
      return causes.find(c => c.pending > 0) || null;
    },
    taskPct() {
      const s = this.dailyTaskStats;
      return s && s.total ? Math.round((s.done_count / s.total) * 100) : 0;
    },
    taskRemain() {
      const s = this.dailyTaskStats;
      return s ? Math.max(0, (s.total || 3) - (s.done_count || 0)) : 3;
    },
    starCount() {
      const s = this.quiz.score;
      if (!this.quiz.done) return 0;
      return s >= 90 ? 3 : s >= 70 ? 2 : s >= 50 ? 1 : 0;
    },
    causeOptions() {
      return [
        { code: 'careless', label: '粗心大意' }, { code: 'concept', label: '概念不清' },
        { code: 'method', label: '方法不会' }, { code: 'reading', label: '审题失误' },
      ];
    },
    attemptDeltaText() {
      const a = this.selfCompare && this.selfCompare.attempts;
      if (!a || a.delta_correct === null || a.delta_correct === undefined) return '';
      if (a.delta_correct > 0) return `比上次多对 ${a.delta_correct} 题，进步啦 🎉`;
      if (a.delta_correct === 0) return '和上次打平，稳住就是胜利';
      return `比上次少对 ${-a.delta_correct} 题，别灰心，下次追回来 💪`;
    },
    vocabDeltaText() {
      const v = this.selfCompare && this.selfCompare.vocab;
      if (!v) return '';
      if (v.delta > 0) return `今天比昨天多背 ${v.delta} 个单词 🔥`;
      if (v.delta < 0) return `昨天背了 ${v.yesterday} 个，今天再冲一冲！`;
      return v.today ? `今天已背 ${v.today} 个单词` : '';
    },
    classicalDeltaText() {
      const c = this.selfCompare && this.selfCompare.classical;
      if (!c) return '';
      if (c.delta > 0) return `古诗文比昨天多学 ${c.delta} 篇 📜`;
      if (c.delta < 0) return `昨天学了 ${c.yesterday} 篇，今天再加把劲`;
      return c.today ? `今天已学 ${c.today} 篇古诗文` : '';
    },
    moodOptions() {
      return [
        { code: 'great', face: '😄', label: '超开心' },
        { code: 'happy', face: '😊', label: '开心' },
        { code: 'ok', face: '😐', label: '一般' },
        { code: 'blue', face: '😔', label: '有点烦' },
        { code: 'sad', face: '😢', label: '很难过' },
      ];
    },
    moodTodayStr() {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    },
    curChalQ() {
      const qs = this.chalOverlay.questions || [];
      return qs[this.chalOverlay.i] || { q: '', options: [], answer: '' };
    },
  },

  methods: {
    /* ─────────── 通用 ─────────── */
    api(path, opts = {}) {
      return fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts))
        .then(async r => {
          const t = await r.text();
          let d = t;
          try { d = JSON.parse(t); } catch (e) { /* 非 JSON */ }
          if (!r.ok) throw new Error(typeof d === 'object' && d ? (d.detail || '请求失败') : String(d));
          return d;
        });
    },
    showToast(msg) {
      this.toast.msg = msg; this.toast.show = true;
      clearTimeout(this._tt);
      this._tt = setTimeout(() => { this.toast.show = false; }, 2400);
    },
    saveUser() {
      if (this.user) localStorage.setItem('zx_user', JSON.stringify({ user: this.user, grade: this.grade, subject: this.subject }));
    },

    /* ─────────── 登录 / 退出 ─────────── */
    login() {
      const name = this.username.trim();
      if (!name) return;
      this.api('/api/user/login', {
        method: 'POST',
        body: JSON.stringify({ user_id: name, grade: this.grade, subject: this.subject }),
      }).then(r => {
        this.user = name;
        this.streakDays = r.streak_days || 0;
        this.saveUser();
        this.showToast(`欢迎回来，${name}！`);
        this.refreshAll();
      }).catch(e => this.showToast(e.message));
    },
    logout() {
      localStorage.removeItem('zx_user');
      sessionStorage.removeItem('zx_parent_open');
      this.user = ''; this.username = ''; this.tab = 'home';
    },

    /* ─────────── 导航 ─────────── */
    goTab(t) {
      this.tab = t;
      if (t === 'home') { this.loadRewards(); this.loadRewardTimeline(); this.loadParentMsgs(); this.loadNotices(); }
      if (t === 'practice') { this.loadMathCategories(); if (this.subject === '英语') this.loadGrammarPoints(); }
      if (t === 'recite') { this.reciteSub === 'words' ? this.loadVocabToday() : this.loadClassicalToday(); this.loadClassicalTexts(); }
      if (t === 'wrong') { this.loadWrongItems(); this.loadAnalysis(); this.loadTeachDue(); }
      if (t === 'papers') this.loadPapers();
      if (t === 'qa') { this.loadQaModels(); this.loadQaHistory(); }
      if (t === 'stats') this.loadStats();
      if (t === 'settings') this.initParentPanel();
    },
    switchSubject(s) {
      this.subject = s;
      if (this.tab === 'practice') {
        if (s !== '英语' && this.practiceSub === 'grammar') this.practiceSub = 'generate';
        if (s === '英语') this.loadGrammarPoints();
      }
      if (this.tab === 'wrong') this.loadWrongItems();
      this.saveUser(); this.refreshAll();
    },
    onGradeChange() { this.saveUser(); this.refreshAll(); },
    onSubjectChange() {
      this.engTypes = this.subject === '语文' ? this._chiTypes : this._engTypes;
      this.selectedTypes = [];
      this.saveUser();
    },
    switchRecite(s) {
      this.reciteSub = s;
      if (s === 'words') this.loadVocabToday(); else this.loadClassicalToday();
      if (s === 'classical') this.loadClassicalTexts();
    },

    /* ─────────── 十万个为什么（Sprint 5） ─────────── */
    loadQaModels() {
      this.api(`/api/qa/models?user_id=${encodeURIComponent(this.user)}`)
        .then(d => {
          this.qaModels = d.models || [];
          this.qaModelsVip = !!d.vip;
          const cur = this.qaModels.find(m => m.key === this.qaProvider);
          if (!cur || !cur.available) {
            const first = (this.qaModels || []).find(m => m.available);
            this.qaProvider = first ? first.key : 'zhipu';
          }
        }).catch(() => { this.qaModels = []; });
    },
    qaModelLabel(key) {
      const m = (this.qaModels || []).find(x => x.key === key);
      return m ? m.label : key;
    },
    askQa() {
      const q = this.qaAsk.trim();
      if (!q || this.qaLoading) return;
      this.qaLoading = true;
      this.qaAnswer = null;
      this.api('/api/qa/ask', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, question: q, provider: this.qaProvider }),
      }).then(d => {
        this.qaAnswer = d;
        this.loadQaHistory();
      }).catch(e => {
        this.showToast(e.message);
      }).finally(() => { this.qaLoading = false; });
    },
    loadQaHistory() {
      if (!this.user) return;
      this.api(`/api/qa/history?user_id=${encodeURIComponent(this.user)}&q_type=${this.qaHistType}`)
        .then(d => { this.qaHistory = d || []; })
        .catch(() => { this.qaHistory = []; });
    },

    /* ─────────── 全局刷新 ─────────── */
    refreshAll() {
      if (!this.user) return;
      this.loadDailyTasks();
      this.loadDashboard();
      this.loadReviewQueue();
      this.loadVocabToday();
      this.loadVocabStats();
      this.loadClassicalToday();
      this.loadClassicalStats();
      this.loadGrammarStats();
      this.loadClassicalTexts();
      this.loadAnalysis();
      this.loadAttempts();
      this.loadPapers();
      this.loadMood();
      this.loadRewards();
      this.loadTitles();
      this.loadGoals();
      this.loadChalBest();
      this.loadTeachDue();
      this.loadParentMsgs();
      this.loadNotices();
      this.loadRewardTimeline();
    },

    /* ─────────── 首页 ─────────── */
    loadDashboard() {
      this.api(`/api/study/dashboard/today?user_id=${encodeURIComponent(this.user)}&grade=${this.grade}`)
        .then(d => {
          this.dashboard = d;
          this.totalTodo = d.total_todo || 0;
          const eng = d.subjects['英语'] || {}, chi = d.subjects['语文'] || {}, mth = d.subjects['数学'] || {};
          this.vocabTotal = (eng.vocab || {}).total || 0;
          this.vocabLearned = (eng.vocab || {}).learned || 0;
          const tasks = [];
          if (eng.vocab) {
            if (eng.vocab.new_words > 0) tasks.push({ key: 'word_new', ico: '🔤', icoCls: 't-blue', title: '背单词 · 新学', subject: '英语', detail: eng.vocab.new_words + ' 个新单词', done: false });
            if (eng.vocab.review_words > 0) tasks.push({ key: 'word_review', ico: '🔁', icoCls: 't-green', title: '背单词 · 复习', subject: '英语', detail: eng.vocab.review_words + ' 个到期复习', done: false });
          }
          if (eng.grammar && eng.grammar.total_exercises > 0) tasks.push({ key: 'grammar', ico: '📝', icoCls: 't-violet', title: '语法专项练习', subject: '英语', detail: eng.grammar.total_exercises + ' 道题库可选', done: false });
          if (chi.classical) {
            if (chi.classical.new_texts > 0) tasks.push({ key: 'text_new', ico: '📜', icoCls: 't-orange', title: '古诗文 · 新背', subject: '语文', detail: chi.classical.new_texts + ' 篇待背诵', done: false });
            if (chi.classical.review_texts > 0) tasks.push({ key: 'text_review', ico: '🔁', icoCls: 't-green', title: '古诗文 · 复习', subject: '语文', detail: chi.classical.review_texts + ' 篇到期复习', done: false });
          }
          const pendingWrong = this._pendingWrong(d);
          if (pendingWrong > 0) tasks.push({ key: 'wrong', ico: '📕', icoCls: 't-red', title: '错题攻坚', subject: '全部', detail: pendingWrong + ' 道待攻克', tag: '建议优先', tagCls: 'tag-red', done: false });
          if (!tasks.length) tasks.push({ key: 'practice', ico: '🧮', icoCls: 't-violet', title: '刷一套新试卷', subject: this.subject, detail: '生成试卷立即开始做题', done: false });
          this.todayTasks = tasks;
        }).catch(e => this.showToast(e.message));
    },
    /* ─────────── 每科必做：每日任务 ─────────── */
    loadDailyTasks() {
      this.api(`/api/tasks/daily?user_id=${encodeURIComponent(this.user)}`)
        .then(d => this._applyDailyTasks(d, true))
        .catch(() => {});
    },
    swapDailyTask(subject) {
      this.api('/api/tasks/daily/swap', { method: 'POST', body: JSON.stringify({ user_id: this.user, subject }) })
        .then(d => this._applyDailyTasks(d, false))
        .catch(e => this.showToast(e.message));
    },
    claimDailyTask(subject) {
      this.api('/api/tasks/daily/claim', { method: 'POST', body: JSON.stringify({ user_id: this.user, subject }) })
        .then(d => this._applyDailyTasks(d, true))
        .catch(e => this.showToast(e.message));
    },
    parentConfirmTask(subject) {
      this.api('/api/tasks/daily/claim', { method: 'POST', body: JSON.stringify({ user_id: this.user, subject }) })
        .then(() => { this.loadDailyTasks(); this.showToast('已确认完成 ✅'); })
        .catch(e => this.showToast(e.message));
    },
    _applyDailyTasks(d, celebrate) {
      const prev = this.dailyTaskStats ? this.dailyTaskStats.done_count : 0;
      this.dailyTasks = (d && d.tasks) || [];
      this.dailyTaskStats = { done_count: (d && d.done_count) || 0, total: (d && d.total) || 3, streak_days: (d && d.streak_days) || 0 };
      if (celebrate && this.dailyTaskStats.total && this.dailyTaskStats.done_count >= this.dailyTaskStats.total && prev < this.dailyTaskStats.total) {
        this.showToast('🎉 三科任务全部完成，今天全勤！');
        this.remindMoodCheckin();
      }
    },
    _pendingWrong(d) {
      const w = o => o ? (o.exam_pending || 0) + (o.study_pending || 0) : 0;
      const eng = d.subjects['英语'] || {}, chi = d.subjects['语文'] || {}, mth = d.subjects['数学'] || {};
      return w(eng.wrong) + w(chi.wrong) + w(mth.wrong);
    },
    loadReviewQueue() {
      this.api(`/api/study/review-queue?user_id=${encodeURIComponent(this.user)}&grade=${this.grade}`)
        .then(r => {
          this.reviewQueue = r;
          const today = (r.items || []).filter(i => i.overdue_days <= 0);
          this.queueToday = today.length;
          this.queueTodayNames = today.slice(0, 3).map(i => i.title).join('、') + (today.length > 3 ? ' 等' : '');
          const up = r.upcoming || {};
          this.queueTomorrow = up.t1 || 0; this.queueDayAfter = up.t2 || 0; this.queueLater = up.t3 || 0;
        }).catch(() => {});
    },
    startTask(t) {
      if (t.done) { this.showToast('该任务今天已完成，明天再来吧'); return; }
      if (t.key === 'word_new') this.startWordSession('new');
      else if (t.key === 'word_review') this.startWordSession('review');
      else if (t.key === 'text_new') this.startTextSession('new');
      else if (t.key === 'text_review') this.startTextSession('review');
      else if (t.key === 'grammar') { this.goTab('practice'); this.practiceSub = 'grammar'; this.loadGrammarPoints(); }
      else if (t.key === 'wrong') this.goTab('wrong');
      else { this.goTab('practice'); this.practiceSub = 'generate'; }
    },

    /* ─────────── 刷题中心 ─────────── */
    loadMathCategories() {
      this.api('/api/math/categories').then(cats => {
        this.mathCategories = (cats || []).map(c => c.name).filter(Boolean);
      }).catch(() => { this.mathCategories = []; });
    },
    loadEngTypes() {
      this._engTypes = [
        { code: 'word_translation', name: '单词翻译' }, { code: 'phrase_translation', name: '词组翻译' },
        { code: 'sentence_translation', name: '句子翻译' }, { code: 'phonetics', name: '语音辨析' },
        { code: 'grammar_choice', name: '语法选择' }, { code: 'situational', name: '情景交际' },
        { code: 'unscramble_sentence', name: '连词成句' }, { code: 'cloze', name: '选词填空' },
        { code: 'dictation', name: '单词听写' }, { code: 'choice', name: '单词选择' },
      ];
      this._chiTypes = [
        { code: 'pinyin_write', name: '看拼音写词语' }, { code: 'idiom_fill', name: '成语填空' },
        { code: 'poetry_fill', name: '古诗默写' }, { code: 'typo_correct', name: '改错字' },
        { code: 'sentence_rewrite', name: '句式变换' }, { code: 'word_classify', name: '词语归类' },
      ];
      this.engTypes = this.subject === '语文' ? this._chiTypes : this._engTypes;
    },
    toggleCategory(c) {
      const i = this.selectedCategories.indexOf(c);
      i >= 0 ? this.selectedCategories.splice(i, 1) : this.selectedCategories.push(c);
    },
    toggleType(t) {
      const i = this.selectedTypes.indexOf(t);
      i >= 0 ? this.selectedTypes.splice(i, 1) : this.selectedTypes.push(t);
    },
    generateExam() {
      const body = { subject: this.subject, grade: this.grade, difficulty: this.genDifficulty, user_id: this.user };
      if (this.subject === '数学') {
        body.math_count = this.genCount;
        body.math_categories = this.selectedCategories.length ? this.selectedCategories.slice() : null;
      } else {
        body.english_count = this.genCount;
        body.english_types = this.selectedTypes.length ? this.selectedTypes.slice() : null;
      }
      this.generating = true;
      fetch('/api/exam/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(async r => {
          const id = r.headers.get('x-exam-id');
          const t = await r.text();
          if (!r.ok) {
            let d = null; try { d = JSON.parse(t); } catch (e) {}
            let msg = '生成失败';
            if (d) {
              if (typeof d.detail === 'string') msg = d.detail;
              else if (Array.isArray(d.detail) && d.detail.length) msg = d.detail.map(x => (x && x.msg) ? x.msg : '参数错误').join('；');
              else if (d.message) msg = d.message;
            }
            throw new Error(msg);
          }
          if (!id) throw new Error('生成失败：未获取到试卷ID');
          return id;
        })
        .then(id => {
          this.generating = false;
          this.showToast('试卷生成成功，开始做题');
          this.loadPapers();
          this.startExamQuiz(id, `${this.subject}${this.grade}年级练习`);
        })
        .catch(e => { this.generating = false; this.showToast(e.message); });
    },
    loadAttempts() {
      this.api(`/api/exam/attempts/list?user_id=${encodeURIComponent(this.user)}&page_size=50&subject=${encodeURIComponent(this.subject)}`)
        .then(list => {
          list = list || [];
          this.attempts = list;
          this.recentAttempts = list.slice(0, 6);
          this.statsAttempts = list.length;
          const scored = list.filter(a => typeof a.score === 'number');
          this.avgScore = scored.length ? Math.round(scored.reduce((s, a) => s + a.score, 0) / scored.length) : 0;
        }).catch(() => { this.attempts = []; });
    },
    viewAttempt(a) {
      this.attemptDetail = { show: true, id: a.id, title: a.exam_title || '做题记录', score: a.score, correct: a.correct, total: a.total, items: [] };
      this.api(`/api/exam/attempts/${a.id}`)
        .then(d => {
          if (!d || !d.answers) { this.attemptDetail.show = false; this.showToast('记录详情加载失败'); return; }
          this.attemptDetail.items = d.answers.map(x => ({
            question: x.question, type_name: x.type_name || '', user_answer: x.user_answer || '',
            correct_answer: x.correct_answer || '', is_correct: !!x.is_correct,
          }));
        }).catch(e => { this.attemptDetail.show = false; this.showToast(e.message); });
    },

    /* ─────────── 语法练习 ─────────── */
    loadGrammarPoints() {
      const cat = this.grammarCategory ? '&category=' + encodeURIComponent(this.grammarCategory) : '';
      this.api(`/api/grammar/points?grade=${this.grade}${cat}`)
        .then(ps => { this.grammarPoints = ps || []; })
        .catch(e => this.showToast(e.message));
    },
    selectGrammarPoint(p) {
      this.api('/api/grammar/quiz', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, grade: this.grade, grammar_point_id: p.id, count: 10 }),
      }).then(r => {
        this.grammarQuiz = (r.questions || []).map(q => ({ ...q, answered: false, correct: false, selected: -1, userAnswer: '' }));
        this.grammarQuizIndex = 0; this.grammarSubmitted = false; this.grammarResult = null; this.grammarInput = '';
      }).catch(e => this.showToast(e.message));
    },
    typeLabel(t) {
      return ({
        choice: '选择题', fill: '填空题', transform: '句型转换', correct: '改错题',
        word_translation: '单词翻译', phrase_translation: '词组翻译', sentence_translation: '句子翻译',
        phonetics: '语音辨析', grammar_choice: '语法选择', situational: '情景交际',
        unscramble_sentence: '连词成句', cloze: '选词填空', dictation: '单词听写',
        pinyin_write: '看拼音写词语', idiom_fill: '成语填空', poetry_fill: '古诗默写',
        typo_correct: '改错字', sentence_rewrite: '句式变换', word_classify: '词语归类',
      })[t] || t || '';
    },
    optClass(opt, item) {
      if (!item.answered) return '';
      const idx = (item.options || []).indexOf(opt);
      const letter = 'ABCDEFGH'[idx];
      if (letter === String(item.answer || '').trim().toUpperCase()) return 'correct';
      if (item.selected === idx) return 'wrong';
      return '';
    },
    grammarAnswer(opt) {
      const it = this.grammarQuiz[this.grammarQuizIndex];
      if (it.answered) return;
      const idx = (it.options || []).indexOf(opt);
      it.selected = idx;
      const letter = 'ABCDEFGH'[idx];
      const ok = letter === String(it.answer || '').trim().toUpperCase();
      it.correct = ok; it.answered = true; it.userAnswer = letter;
      this.grammarSubmitted = true; this.grammarFeedbackOk = ok;
      this.grammarCurrentAnswer = this._readableAnswer(it);
      this.grammarCurrentExplanation = it.explanation || '';
    },
    grammarSubmit() {
      const it = this.grammarQuiz[this.grammarQuizIndex];
      if (it.answered) return;
      const ua = (this.grammarInput || '').trim();
      if (!ua) { this.showToast('请先输入答案'); return; }
      const ok = this._matchAnswer(ua, it.answer);
      it.correct = ok; it.answered = true; it.userAnswer = ua;
      this.grammarSubmitted = true; this.grammarFeedbackOk = ok;
      this.grammarCurrentAnswer = this._readableAnswer(it);
      this.grammarCurrentExplanation = it.explanation || '';
    },
    _readableAnswer(it) {
      const a = String(it.answer || '').trim().toUpperCase();
      if (it.options && it.options.length && a.length === 1) {
        const idx = 'ABCDEFGH'.indexOf(a);
        if (idx >= 0 && it.options[idx]) return it.options[idx];
      }
      return it.answer || '';
    },
    grammarNext() {
      if (this.grammarQuizIndex < this.grammarQuiz.length - 1) {
        this.grammarQuizIndex++; this.grammarSubmitted = false; this.grammarInput = '';
      } else {
        const total = this.grammarQuiz.length;
        const correct = this.grammarQuiz.filter(q => q.correct).length;
        this.grammarResult = { score: total ? Math.round(correct / total * 100) : 0, correct, total, wrong: total - correct };
        const wrongs = this.grammarQuiz.filter(q => !q.correct)
          .map(q => ({
            source_type: 'grammar', source_id: q.exercise_id, module_name: q.grammar_point_name || '语法练习',
            question: q.question, user_answer: q.userAnswer || '', correct_answer: q.answer,
            explanation: q.explanation || '', cause: '',
          }));
        if (wrongs.length) {
          this.api('/api/study/errors', { method: 'POST', body: JSON.stringify({ user_id: this.user, items: wrongs }) })
            .then(() => this.loadAnalysis()).catch(() => {});
        }
      }
    },
    grammarExit() {
      this.grammarQuiz = []; this.grammarResult = null; this.grammarSubmitted = false; this.grammarInput = '';
    },

    /* ─────────── 背诵中心 ─────────── */
    loadVocabToday() {
      this.api(`/api/vocab/today?user_id=${encodeURIComponent(this.user)}&grade=${this.grade}`)
        .then(r => {
          const stats = Object.assign({}, this.vocabToday.stats, r.stats || {});
          this.vocabToday = { new_words: r.new_words || [], review_words: r.review_words || [], stats };
        }).catch(() => {});
    },
    loadVocabStats() {
      this.api(`/api/vocab/stats?user_id=${encodeURIComponent(this.user)}&grade=${this.grade}`)
        .then(r => {
          this.vocabStats = r || {};
          const s = this.vocabToday.stats;
          s.streak_days = r.streak_days || s.streak_days || 0;
          s.new_today = r.new_today || 0;
          if (r.streak_days) this.streakDays = Math.max(this.streakDays, r.streak_days);
        }).catch(() => {});
    },
    loadClassicalToday() {
      this.api(`/api/classical/today?user_id=${encodeURIComponent(this.user)}&grade=${this.grade}`)
        .then(r => {
          this.classicalToday = {
            new_texts: r.new_texts || [], review_texts: r.review_texts || [],
            stats: Object.assign({}, this.classicalToday.stats, r.stats || {}),
          };
          if ((r.stats || {}).streak_days) this.streakDays = Math.max(this.streakDays, r.stats.streak_days);
        }).catch(() => {});
    },
    loadClassicalStats() {
      this.api(`/api/classical/stats?user_id=${encodeURIComponent(this.user)}&grade=${this.grade}`)
        .then(r => { this.classicalStats = r || {}; }).catch(() => {});
    },
    loadClassicalTexts() {
      this.api(`/api/classical/texts?grade=${this.grade}`)
        .then(ts => { this.classicalTexts = ts || []; }).catch(() => { this.classicalTexts = []; });
    },
    startWordSession(mode) {
      const words = mode === 'new' ? (this.vocabToday.new_words || []) : (this.vocabToday.review_words || []);
      if (!words.length) { this.showToast(mode === 'new' ? '今日新词已学完，明天再来吧' : '今日没有到期复习的单词'); return; }
      this.wordSession = { active: true, done: false, phase: 'card', mode, words, i: 0, revealed: false, okCount: 0, results: [] };
    },
    wordNext(ok) {
      const ws = this.wordSession;
      const w = ws.words[ws.i];
      ws.results.push({ word_id: w.word_id, correct: ok });
      if (ok) ws.okCount++;
      if (ws.i < ws.words.length - 1) { ws.i++; ws.revealed = false; }
      else { ws.phase = 'dictate'; this.startWordDictate(); }
    },
    /* 默写环节：翻完卡片后听写一遍，全对才算完成（错词重默直到全对） */
    startWordDictate() {
      const ws = this.wordSession;
      this.dtOk = {};
      const items = ws.words.map(w => ({
        qid: w.word_id, text_id: 0,
        question: `✍️ 听写：${w.pos ? w.pos + ' ' : ''}${w.meaning}`,
        sub: w.phonetic ? '🔉 ' + w.phonetic : '',
        placeholder: '请输入英文单词', options: [], answer: w.word, explanation: '',
      }));
      this.startQuiz({
        title: '✍️ 默写检测 · ' + (ws.mode === 'new' ? '新词听写' : '复习听写'),
        items, source: { mode: 'dictate', kind: 'word', mode2: ws.mode },
      });
    },
    startTextSession(mode) {
      const raw = mode === 'new' ? (this.classicalToday.new_texts || []) : (this.classicalToday.review_texts || []);
      if (!raw.length) { this.showToast(mode === 'new' ? '今日新篇已背完，明天再来吧' : '今日没有到期复习的篇目'); return; }
      this.textSession = {
        active: true, done: false, phase: 'card', mode,
        texts: raw.map(x => ({ ...x, dynasty: x.dynasty || '' })),
        i: 0, okCount: 0, failCount: 0, results: [],
      };
    },
    textNext(ok) {
      const ts = this.textSession;
      const t = ts.texts[ts.i];
      ts.results.push({ text_id: t.text_id, correct: ok });
      if (ok) ts.okCount++; else ts.failCount++;
      if (ts.i < ts.texts.length - 1) { ts.i++; }
      else { ts.phase = 'dictate'; this.startTextDictate(); }
    },
    /* 默写环节：翻完卡片后填空默写，全对才算完成（错句重默直到全对） */
    startTextDictate() {
      const ts = this.textSession;
      this.dtOk = {};
      const qs = [];
      const tasks = ts.texts.map(t =>
        this.api(`/api/classical/quiz?grade=${this.grade}&text_id=${t.text_id}&count=2`)
          .then(rows => { (rows || []).forEach(q => qs.push(q)); }).catch(() => {})
      );
      Promise.all(tasks).then(() => {
        if (!qs.length) { ts.active = false; this.showToast('默写题生成失败，请重试'); return; }
        const items = qs.map(q => ({
          qid: 0, text_id: q.text_id, question: q.question,
          sub: '📜 ' + (q.context || '默写'),
          placeholder: '默写内容', options: [], answer: q.answer, explanation: '',
        }));
        this.startQuiz({
          title: '✍️ 默写检测 · ' + (ts.mode === 'new' ? '新篇默写' : '复习默写'),
          items, source: { mode: 'dictate', kind: 'text', mode2: ts.mode },
        });
      });
    },
    openTextDetail(t) {
      this.textDetail = { show: true, id: t.id, title: t.title, author: t.author || '', dynasty: t.dynasty || '', grade: t.grade, text_type: t.text_type || 'poem', content: t.content };
    },
    startTextQuiz(t) {
      this.textDetail.show = false;
      this.api(`/api/classical/quiz?grade=${this.grade}&text_id=${t.id}&count=4`)
        .then(qs => {
          const items = (qs || []).map(q => ({
            qid: 0, text_id: q.text_id, question: q.question, sub: q.context || '',
            options: [], answer: q.answer, explanation: '',
          }));
          this.startQuiz({ title: `《${t.title}》默写练习`, items, source: { mode: 'classical', text_id: t.id, textTitle: t.title } });
        }).catch(e => this.showToast(e.message));
    },

    /* ─────────── 错题本 ─────────── */
    loadWrongItems() {
      const base = `user_id=${encodeURIComponent(this.user)}&subject=${encodeURIComponent(this.subject)}`;
      const examQ = `${base}&include_mastered=${this.wrongStatus === 'pending' ? 0 : 1}`;
      const studyQ = `${base}&only_pending=${this.wrongStatus === 'pending' ? 1 : 0}`;
      return Promise.all([this.api(`/api/exam/wrong/list?${examQ}`), this.api(`/api/study/errors?${studyQ}`)])
        .then(([examList, studyList]) => {
          const exam = (examList || []).map(w => ({
            key: 'exam-' + w.id, kind: 'exam', id: w.id, record_id: w.id, question_id: w.question_id,
            question: w.question, user_answer: '', correct_answer: w.answer, explanation: '',
            error_count: w.practice_count || 1, wrong_at: w.wrong_at || '',
            mastered: !!w.is_mastered, cause: w.cause || '',
            subject: w.subject || '', source: '试卷错题',
          }));
          const study = (studyList || []).map(e => ({
            key: 'study-' + e.id, kind: 'study', id: e.id, record_id: e.id, question_id: 0,
            question: e.question, user_answer: e.user_answer, correct_answer: e.correct_answer,
            explanation: e.explanation || '', error_count: e.error_count || 1, wrong_at: e.wrong_at || '',
            mastered: !!e.is_mastered, cause: e.cause || '',
            subject: e.source_type === 'grammar' ? '英语' : '语文', source: e.module_name || '学习错题',
          }));
          let items = [...exam, ...study];
          if (this.wrongKind === 'exam') items = items.filter(i => i.kind === 'exam');
          if (this.wrongKind === 'study') items = items.filter(i => i.kind === 'study');
          if (this.wrongStatus === 'pending') items = items.filter(i => !i.mastered);
          if (this.wrongStatus === 'mastered') items = items.filter(i => i.mastered);
          this.wrongItems = items;
        }).catch(e => this.showToast(e.message));
    },
    openWrongDetail(w) { this.curWrong = w; this.wrongScreen = 'detail'; },
    /* ─────────── AI 错题讲解（Sprint 2，内联展示） ─────────── */
    // 讲解文本三段式：按【错在哪】【怎么做】【再来一道】切分
    explainSectionsOf(t) {
      const segs = [];
      const rex = /【(错在哪|怎么做|再来一道)】([\s\S]*?)(?=【|$)/g;
      let m;
      while ((m = rex.exec(t || '')) !== null) segs.push({ title: m[1], body: m[2].trim() });
      return segs.length ? segs : [{ title: '', body: t || '' }];
    },
    // 统一带超时的讲解请求：25s 未返回自动解除锁定并提示，避免"点了没反应"
    explainFetch(path, payload) {
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('讲解生成超时，请稍后重试')), 25000);
        this.api(path, { method: 'POST', body: JSON.stringify(payload) })
          .then(d => { clearTimeout(timer); resolve(d); })
          .catch(e => { clearTimeout(timer); reject(e); });
      });
    },
    openExplain(w) {
      if (w.kind !== 'exam' || !w.question_id) { this.showToast('这道题暂不支持 AI 讲解'); return; }
      if (w.explaining) return; // 防重复点击
      w.explaining = true; w.aiText = ''; w.aiError = ''; w.aiDegraded = false;
      this.explainFetch('/api/ai/explain', { user_id: this.user, question_id: w.question_id })
        .then(d => {
          w.explaining = false;
          w.aiText = d.text || '';
          w.aiDegraded = !!d.degraded;
        }).catch(e => {
          w.explaining = false;
          w.aiError = e.message || '讲解生成失败，请稍后重试';
          this.showToast(w.aiError);
        });
    },
    /* 作答页「AI 讲解」：一键标记错题（错因=ai）并在题目下方内联展示讲解 */
    askQuizExplain() {
      const it = this.quiz.items[this.quiz.i];
      if (!it || !it.qid) { this.showToast('这道题暂不支持 AI 讲解'); return; }
      if (it.explaining) return; // 防重复点击
      it.explaining = true; it.aiText = ''; it.aiError = ''; it.aiDegraded = false;
      this.explainFetch('/api/ai/explain-mark', { user_id: this.user, question_id: it.qid })
        .then(d => {
          it.explaining = false;
          it.aiText = d.text || '';
          it.aiDegraded = !!d.degraded;
          if (d.marked) {
            it.cause = 'ai';
            this.showToast('已标记为做错了（AI 讲解），讲解后可以点「这次会了」');
          }
          // 供内联讲解下方「这次会了 / 变式重练」复用（record_id 来自服务端新标记）
          if (d.record_id && (!this.curWrong || this.curWrong.question_id !== it.qid)) {
            this.curWrong = { kind: 'exam', record_id: d.record_id, question_id: it.qid, question: d.question || it.question, mastered: false };
          }
        }).catch(e => {
          it.explaining = false;
          it.aiError = e.message || '讲解生成失败，请稍后重试';
          this.showToast(it.aiError);
        });
    },
    /* ─────────── 心情打卡（Sprint 2） ─────────── */
    moodFace(c) { const m = this.moodOptions.find(x => x.code === c); return m ? m.face : ''; },
    moodLabel(c) { const m = this.moodOptions.find(x => x.code === c); return m ? m.label : ''; },
    loadMood() {
      this.api(`/api/mood/trend?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.moodTrend = d || null; })
        .catch(() => { this.moodTrend = null; });
    },
    doMoodCheckin(mood) {
      this.api('/api/mood/checkin', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, mood, note: this.moodNote || '' }),
      }).then(() => {
        this.moodNote = ''; this.moodPicking = false;
        this.loadMood();
        this.showToast('心情已记录，谢谢你告诉我 🧡');
      }).catch(e => this.showToast(e.message));
    },
    resetMoodPick() { this.moodPicking = true; },
    remindMoodCheckin() {
      // 全勤后轻提醒打卡：30% 概率不打扰，每个会话最多一次
      try {
        if (sessionStorage.getItem('zx_mood_reminded')) return;
        if (Math.random() < 0.3) return;
        sessionStorage.setItem('zx_mood_reminded', '1');
        if (this.moodTrend && this.moodTrend.today_mood) return;
        this.showToast('🎉 今天全勤！回首页「今日心情」打个卡吧');
      } catch (e) { /* 隐私模式等异常忽略 */ }
    },
    /* ─────────── 奖励闭环 + 成长周报（Sprint 3） ─────────── */
    wishStatusLabel(s) {
      return { pending: '待家长确认', active: '进行中', pending_redeem: '达标待兑现', redeemed: '已兑现', archived: '已移除' }[s] || s;
    },
    couponIcon(k) {
      return { cartoon: '📺', snack: '🍪', sticker: '🌟', toy: '🧸', outing: '🎡', custom: '🎫' }[k] || '🎫';
    },
    loadRewards() {
      this.api(`/api/rewards/overview?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.rewards = d || { coupons: [], wish: null }; })
        .catch(() => { this.rewards = { coupons: [], wish: null }; });
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
    },
    /* ─────────── 孩子申诉（AI 判题复核 + 家长二次确认）─────────── */
    loadAppeals() {
      this.api(`/api/appeal/list?user_id=${encodeURIComponent(this.user)}&status=pending`)
        .then(d => { this.pendingAppeals = (d && d.appeals) || []; })
        .catch(() => { this.pendingAppeals = []; });
    },
    decideAppeal(a, ok) {
      this.api('/api/appeal/decide', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, appeal_id: a.id, action: ok ? 'approve' : 'reject' }),
      }).then(() => {
        this.showToast(ok ? '已确认孩子做对了，本题改判正确、得分已重算 ✅' : '已驳回申诉，维持原判');
        this.loadAppeals();
        this.loadChildStats();
      }).catch(e => this.showToast(e.message));
    },
    appealThis() {
      const it = this.quiz.items[this.quiz.i];
      if (!it || !it.answered || it.correct || it.appealed) return;
      const src = this.quiz.source;
      const mode = (src && src.mode === 'retry') ? 'retry' : 'exam';
      const payload = {
        user_id: this.user,
        source: mode,
        question_id: it.qid || null,
        question: it.question,
        user_answer: it.userAnswer || '',
        correct_answer: it.answer || '',
        subject: this.subject,
      };
      if (mode === 'retry' && it.extra) {
        payload.record_id = it.extra.record_id;
        payload.record_kind = it.extra.kind;
      } else if (this.submitWrongIds && this.submitWrongIds[it.qid]) {
        payload.wrong_record_id = this.submitWrongIds[it.qid];
        payload.wrong_new = !!this.submitWrongNew[it.qid];
      }
      this.api('/api/appeal/create', {
        method: 'POST',
        body: JSON.stringify(payload),
      }).then(() => {
        it.appealed = true;
        this.showToast('已提交申诉，等家长在「家长管理」里确认 ✋');
      }).catch(e => this.showToast(e.message));
    },
    /* ─────────── 家长功能（Sprint 6）：密码 + 留言 + 数据 + 题数 ─────────── */
    exitParentMode() {
      sessionStorage.removeItem('zx_parent_open');
      this.parentPhase = 'locked';
      this._resetPwdForm();
      this.loadRewards(); // 刷新孩子端数据（券状态等）
      this.showToast('已退出家长模式 🔒');
    },
    initParentPanel() {
      // 会话内已解锁过（sessionStorage），直接打开
      if (sessionStorage.getItem('zx_parent_open') === '1') { this.parentPhase = 'open'; this.loadParentPanel(); this.loadChildStats(); this.loadExamSettings(); this.loadSentMsgs(); this.loadDailyTasks(); return; }
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
        sessionStorage.setItem('zx_parent_open', '1');
        this.loadParentPanel(); this.loadChildStats(); this.loadExamSettings(); this.loadSentMsgs(); this.loadDailyTasks();
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
        sessionStorage.setItem('zx_parent_open', '1');
        this.loadParentPanel(); this.loadChildStats(); this.loadExamSettings(); this.loadSentMsgs(); this.loadDailyTasks();
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
    loadParentMsgs() {
      this.api(`/api/parent/messages?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.parentMsgs = d || { unread: 0, messages: [] }; })
        .catch(() => { this.parentMsgs = { unread: 0, messages: [] }; });
    },
    markMsgsRead() {
      this.api('/api/parent/messages/read', {
        method: 'POST', body: JSON.stringify({ user_id: this.user }),
      }).then(() => { this.loadParentMsgs(); this.loadNotices(); })
        .catch(() => {});
    },
    openMessages() {
      this.goTab('home');
      this.markMsgsRead();
      this.showToast('家长留言已打开 💌');
    },
    loadNotices() {
      this.api(`/api/parent/notices?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.notices = d || null; })
        .catch(() => { this.notices = null; });
    },
    loadRewardTimeline() {
      this.api(`/api/rewards/timeline?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.rewardTimeline = (d && d.items) || []; })
        .catch(() => { this.rewardTimeline = []; });
    },
    loadTaskSettings() {
      this.api(`/api/tasks/settings?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.taskSettings = d || { items: [] }; })
        .catch(() => { this.taskSettings = { items: [] }; });
    },
    saveTaskSettings() {
      // 每次保存提交全部 6 项，保证"改回默认值"也能生效
      const changed = {};
      for (const it of this.taskSettings.items || []) {
        const v = Number(it.target);
        if (!Number.isInteger(v) || v < 1 || v > 50) return this.showToast(`「${it.title}」的数量需为 1-50 的整数`);
        changed[it.code] = v;
      }
      this.api('/api/tasks/settings', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, settings: changed }),
      }).then(d => {
        this.taskSettings = d || { items: [] };
        this.loadDailyTasks(); // 立即刷新今日任务，家长能马上看到效果
        this.showToast('每日任务数量已保存 ✅');
      }).catch(e => this.showToast(e.message));
    },
    createCoupon() {
      const title = (this.newCoupon.title || '').trim();
      if (!title) return this.showToast('先写下兑换券内容');
      const requiredDays = Math.max(0, Math.min(30, Number(this.newCoupon.requiredDays) || 0));
      this.api('/api/rewards/coupon', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, title, kind: this.newCoupon.kind, reason: this.newCoupon.reason || '', required_days: requiredDays }),
      }).then(() => {
        this.newCoupon.title = ''; this.newCoupon.reason = ''; this.newCoupon.requiredDays = 0;
        this.loadParentPanel(); this.loadRewards();
        this.showToast(requiredDays > 0 ? `已添加：三科全勤 ${requiredDays} 天可得 🎫` : '兑换券已添加 🎫');
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
    startWish() { this.wishOverlay.title = ''; this.wishOverlay.show = true; },
    submitWish() {
      const title = (this.wishOverlay.title || '').trim();
      if (!title) return this.showToast('写下你的心愿吧');
      this.api('/api/rewards/wish', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, title, target: Number(this.wishOverlay.target) || 5 }),
      }).then(() => {
        this.wishOverlay.show = false;
        this.loadRewards(); this.loadParentPanel();
        this.showToast('心愿已许下，等家长确认 ✨');
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
    archiveWish(w) {
      this.api(`/api/rewards/wish/${w.id}/archive`, {
        method: 'POST', body: JSON.stringify({ user_id: this.user }),
      }).then(() => {
        this.loadParentPanel(); this.loadRewards();
        this.showToast('心愿已移除');
      }).catch(e => this.showToast(e.message));
    },
    openWeekly() {
      this.weeklyOverlay.show = true;
      this.weeklyLoading = true;
      this.weekly = null; this.shareImg = '';
      this.api('/api/ai/report', {
        method: 'POST', body: JSON.stringify({ user_id: this.user }),
      }).then(d => {
        this.weekly = d;
        // 缓存命中时家长寄语可能后写入，动态补拉最新寄语
        if (d && d.already_exists) {
          this.api(`/api/rewards/parent-note?user_id=${encodeURIComponent(this.user)}`)
            .then(n => { if (n && n.note !== undefined) this.weekly.parent_note = n.note; })
            .catch(() => {});
        }
      }).catch(e => {
        this.showToast(e.message || '周报生成失败，稍后再试');
      }).finally(() => { this.weeklyLoading = false; });
    },
    shareWeekly() {
      if (!window.html2canvas) return this.showToast('分享组件未加载，请刷新后重试');
      const el = document.querySelector('.share-target');
      if (!el) return;
      window.html2canvas(el, { scale: 2, backgroundColor: '#fff', useCORS: true })
        .then(canvas => { this.shareImg = canvas.toDataURL('image/png'); })
        .catch(() => this.showToast('生成图片失败，可直接截图分享'));
    },
    saveParentNote() {
      this.api('/api/rewards/parent-note', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, note: this.parentNote || '' }),
      }).then(() => {
        this.showToast('悄悄话已保存 💌');
      }).catch(e => this.showToast(e.message));
    },
    /* ─────────── 称号系统（Sprint 4） ─────────── */
    loadTitles() {
      this.api(`/api/user/titles?user_id=${encodeURIComponent(this.user)}`)
        .then(d => {
          this.titleInfo = { name: d.main.name, icon: d.main.icon, next: d.next };
          this.titleBadges = d.badges || [];
          try {
            const prev = localStorage.getItem('zx_title');
            if (prev && prev !== d.main.name) this.showToast(`🎉 称号升级：${d.main.icon} ${d.main.name}！`);
            localStorage.setItem('zx_title', d.main.name);
          } catch (e) { /* ignore */ }
        }).catch(() => {});
    },
    /* ─────────── 60 秒挑战赛（Sprint 4） ─────────── */
    loadChalBest() {
      this.api(`/api/challenge/records?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.chalBest = d || { math: { best: 0 }, word: { best: 0 } }; })
        .catch(() => {});
    },
    openChal() {
      this.chalOverlay.show = true;
      this.chalOverlay.stage = 'pick';
      this.loadChalBest();
    },
    closeChal() {
      if (this._chalTimer) { clearInterval(this._chalTimer); this._chalTimer = null; }
      this.chalOverlay.show = false;
    },
    startChallenge(kind) {
      this.api(`/api/challenge/questions?user_id=${encodeURIComponent(this.user)}&kind=${kind}&grade=${this.grade}&count=25`)
        .then(d => {
          const qs = (d.questions || []).slice(0, 25);
          if (!qs.length) { this.showToast('题库暂时为空，换个类别试试'); return; }
          this.chalOverlay.kind = kind;
          this.chalOverlay.questions = qs;
          this.chalOverlay.i = 0; this.chalOverlay.timeLeft = 60;
          this.chalOverlay.input = ''; this.chalOverlay.correct = 0;
          this.chalOverlay.total = 0; this.chalOverlay.newBest = false;
          this.chalCombo = 0;
          this.chalOverlay.stage = 'run';
          if (this._chalTimer) clearInterval(this._chalTimer);
          this._chalTimer = setInterval(() => {
            this.chalOverlay.timeLeft--;
            if (this.chalOverlay.timeLeft <= 0) this.endChallenge();
          }, 1000);
        }).catch(e => this.showToast(e.message));
    },
    chalAnswer(val) {
      if (this.chalOverlay.stage !== 'run') return;
      const q = this.curChalQ;
      const ua = this.chalOverlay.kind === 'word'
        ? String(val || '').trim() : String(this.chalOverlay.input || '').trim();
      if (!ua && this.chalOverlay.kind === 'math') return;
      const okAns = String(q.answer || '').trim();
      if (ua === okAns || (this.chalOverlay.kind === 'math' && parseInt(ua, 10) === parseInt(okAns, 10))) {
        this.chalOverlay.correct++;
        this.chalCombo++;
        if (this.chalCombo >= 3) this.showFloat(`🔥 连击 x${this.chalCombo}`, true);
      } else {
        this.chalCombo = 0;
      }
      this.chalOverlay.total++;
      this.chalOverlay.i++;
      this.chalOverlay.input = '';
      if (this.chalOverlay.i >= this.chalOverlay.questions.length) this.endChallenge();
    },
    endChallenge() {
      if (this._chalTimer) { clearInterval(this._chalTimer); this._chalTimer = null; }
      const kind = this.chalOverlay.kind;
      const prevBest = (this.chalBest[kind] || {}).best || 0;
      this.chalOverlay.newBest = this.chalOverlay.correct > prevBest;
      this.api('/api/challenge/record', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, kind, correct: this.chalOverlay.correct, total: this.chalOverlay.total }),
      }).then(d => {
        this.chalBest[kind] = d;
        this.chalOverlay.stage = 'done';
        this.loadTitles();
      }).catch(() => { this.chalOverlay.stage = 'done'; });
    },
    /* ─────────── 学期目标（Sprint 4） ─────────── */
    loadGoals() {
      this.api(`/api/goals?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.goals = (d && d.goals) || []; })
        .catch(() => { this.goals = []; });
    },
    submitGoal() {
      const target = Number(this.goalOverlay.target) || 0;
      if (target <= 0) return this.showToast('写下目标值（正整数）');
      if (this.goalOverlay.kind === 'score' && !(this.goalOverlay.subject || '').trim()) return this.showToast('写下学科，如：数学');
      this.api('/api/goals', {
        method: 'POST',
        body: JSON.stringify({
          user_id: this.user, kind: this.goalOverlay.kind, target,
          deadline: this.goalOverlay.deadline || '', subject: this.goalOverlay.subject,
        }),
      }).then(() => {
        this.loadGoals();
        this.showToast('目标已立下，冲鸭 🎯');
      }).catch(e => this.showToast(e.message));
    },
    doneGoal(g) {
      this.api(`/api/goals/${g.id}/done`, { method: 'POST', body: JSON.stringify({ user_id: this.user }) })
        .then(() => { this.loadGoals(); this.showToast('目标达成，太棒了 🏆'); })
        .catch(e => this.showToast(e.message));
    },
    archiveGoal(g) {
      this.api(`/api/goals/${g.id}/archive`, { method: 'POST', body: JSON.stringify({ user_id: this.user }) })
        .then(() => { this.loadGoals(); })
        .catch(e => this.showToast(e.message));
    },
    /* ─────────── 小老师模式（Sprint 4） ─────────── */
    openTeach(w) {
      this.api('/api/teach/create', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, kind: w.kind, record_id: w.id }),
      }).then(card => {
        this.teachOverlay = { show: true, step: 1, card, answerText: '', result: '', hint: '' };
      }).catch(e => this.showToast(e.message));
    },
    closeTeach() {
      this.teachOverlay.show = false;
      this.loadTeachDue();
      this.loadTitles();
    },
    submitTeachAnswer() {
      const text = (this.teachOverlay.answerText || '').trim();
      if (!text) return this.showToast('家长先写下答案吧');
      this.api('/api/teach/answer', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, card_id: this.teachOverlay.card.id, answer_text: text }),
      }).then(card => {
        this.teachOverlay.card = card;
        this.teachOverlay.step = 3;
      }).catch(e => this.showToast(e.message));
    },
    gradeTeach(ok) {
      this.api('/api/teach/grade', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, card_id: this.teachOverlay.card.id, is_correct: ok }),
      }).then(card => {
        this.teachOverlay.card = card;
        if (ok) {
          this.teachOverlay.result = '讲得真棒！🌟';
          this.teachOverlay.hint = '7 天后系统会帮你复习验证这道题，看看真记住了没';
          this.teachOverlay.step = 4;
        } else {
          this.teachOverlay.step = 1;
          this.teachOverlay.answerText = '';
          this.showToast('家长还没明白，再讲一遍吧 💪');
        }
      }).catch(e => this.showToast(e.message));
    },
    loadTeachDue() {
      this.api(`/api/teach/due?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.teachDue = (d && d.items) || []; })
        .catch(() => { this.teachDue = []; });
    },
    openRecheck() {
      if (!this.teachDue.length) return;
      this.recheckOverlay = { show: true, card: this.teachDue[0], answerText: '' };
    },
    submitRecheck() {
      const text = (this.recheckOverlay.answerText || '').trim();
      if (!text) return this.showToast('写出你的答案');
      const card = this.recheckOverlay.card;
      const isCorrect = String(text).replace(/\s+/g, '') === String(card.answer || '').replace(/\s+/g, '');
      this.api('/api/teach/recheck', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, card_id: card.id, is_correct: isCorrect }),
      }).then(() => {
        this.recheckOverlay.show = false;
        this.loadTeachDue();
        this.loadTitles();
        this.showToast(isCorrect ? '还记得！真的学会啦 🎉' : '有点忘了，去错题本再讲一遍吧 📕');
      }).catch(e => this.showToast(e.message));
    },
    /* ─────────── AI 即时鼓励语（Sprint 4） ─────────── */
    askEncourage(ctx) {
      if (!this.user) return;
      this.api('/api/ai/encourage', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, context: ctx }),
      }).then(d => {
        if (d && d.text) this.showFloat('💬 ' + d.text, false, 3000);
      }).catch(() => {});
    },
    causeLabel(c) {
      return { careless: '粗心大意', concept: '概念不清', method: '方法不会', reading: '审题失误', ai: 'AI 讲解' }[c] || '';
    },
    submitCause(c) {
      if (!this.curWrong) return;
      this.api('/api/study/cause', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, kind: this.curWrong.kind, record_id: this.curWrong.record_id, cause: c }),
      }).then(() => {
        this.curWrong.cause = c;
        this.showToast('错因已记录，将针对性推送变式练习');
        this.loadAnalysis();
      }).catch(e => this.showToast(e.message));
    },
    /* 「标记已掌握」= 掌握检测：先做 3 道同类型题，全部答对才真正标记已掌握，
       防止"假掌握"。答对结果由 /api/study/practice-submit 按 record 分组整组判定 */
    markWrongMastered(w) {
      this.showToast('先做 3 道同类型题，全部答对才算掌握');
      this.startWrongRetry(w, { mastery: true });
    },
    loadAnalysis() {
      this.api(`/api/study/errors/analysis?user_id=${encodeURIComponent(this.user)}&subject=${encodeURIComponent(this.subject)}`)
        .then(r => {
          this.wrongAnalysis = r;
          this.masteredTotal = r.mastered || 0;
          this.wrongBadge = r.pending || 0;
        }).catch(() => {});
    },
    causeColor(c) {
      return { careless: '#F5A623', concept: '#4E7CF6', method: '#8B7CF6', reading: '#F2604C', ai: '#34C77B' }[c] || '#93A1BD';
    },
    subjColor(s) {
      return { '数学': '#F5A623', '英语': '#4E7CF6', '语文': '#34C77B' }[s] || '#93A1BD';
    },
    subjPct(s) {
      const arr = this.wrongAnalysis.by_subject || [];
      const max = Math.max(1, ...arr.map(x => x.count || 0));
      return Math.round((s.count || 0) / max * 100);
    },
    causePct(c) {
      const arr = this.wrongAnalysis.by_cause || [];
      const max = Math.max(1, ...arr.map(x => x.pending || 0));
      return Math.round((c.pending || 0) / max * 100);
    },
    startWrongRetry(w, opts = {}) {
      this.api('/api/study/retry', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, kind: w.kind, record_id: w.record_id, count: 3 }),
      }).then(r => {
        const items = (r.questions || []).map(q => ({
          qid: q.qid, question: q.question,
          sub: (q.type_name || r.module_name || '') + (opts.mastery ? ' · 全对才掌握' : ''),
          options: q.options || [], answer: q.answer, explanation: q.explanation || '',
          extra: { kind: w.kind, record_id: w.record_id }, text_id: q.text_id || 0,
        }));
        this.startQuiz({
          title: opts.mastery ? '✅ 掌握检测 · 3 题全对才标记已掌握' : '🎯 变式重练 · ' + (r.module_name || '同类题'),
          items, source: { mode: 'retry', retry: { kind: w.kind, record_id: w.record_id }, mastery: !!opts.mastery },
        });
      }).catch(e => this.showToast(e.message));
    },
    /* 错题攻坚页「练习错题」：从错题本（当前学科，未掌握）抽 5 道错题，
       每道错题配 3 道同类型新题，整组全对才算修正 */
    startWrongPractice() {
      this.api('/api/exam/wrong/practice-quiz', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, subject: this.subject, count: 5 }),
      }).then(r => {
        const groups = r.groups || [];
        if (!groups.length) { this.showToast('暂无错题可练习，先去做题积累错题吧'); return; }
        const items = [];
        groups.forEach(g => {
          (g.questions || []).forEach(q => {
            items.push({
              qid: q.qid, question: q.question,
              sub: (g.type_name ? '🎯 ' + g.type_name + ' · 全组全对才算修正' : '🎯 错题修正'),
              options: q.options || [], answer: q.answer, explanation: q.explanation || '',
              extra: { kind: 'exam', record_id: g.record_id }, text_id: 0,
            });
          });
        });
        this.startQuiz({
          title: `🎯 错题修正 · ${this.subject}（${groups.length} 组 × 3 题）`,
          items, source: { mode: 'retry', retry: { kind: 'exam', record_id: 0 } },
        });
      }).catch(e => this.showToast(e.message));
    },
    async retryTopCause() {
      const code = this.topCause.code;
      const q = `user_id=${encodeURIComponent(this.user)}&subject=${encodeURIComponent(this.subject)}`;
      try {
        const [examList, studyList] = await Promise.all([
          this.api(`/api/exam/wrong/list?${q}`), this.api(`/api/study/errors?${q}`),
        ]);
        const pool = (examList || []).map(w => ({ kind: 'exam', record_id: w.id, cause: w.cause || '', mastered: !!w.is_mastered }))
          .concat((studyList || []).map(e => ({ kind: 'study', record_id: e.id, cause: e.cause || '', mastered: !!e.is_mastered })));
        const hit = pool.find(i => !i.mastered && i.cause === code) || pool.find(i => !i.mastered);
        if (!hit) { this.showToast('没有可练习的错题，先去错题本标注错因吧'); return; }
        this.startWrongRetry({ kind: hit.kind, record_id: hit.record_id });
      } catch (e) { this.showToast(e.message); }
    },

    /* ─────────── 试卷中心 ─────────── */
    loadPapers() {
      this.api(`/api/exam/records?subject=${encodeURIComponent(this.subject)}`)
        .then(ps => {
          this.papers = ps || [];
        }).catch(() => { this.papers = []; });
    },
    previewPaper(p) { this.startExamQuiz(p.id, p.title); },
    downloadPaper(p) { window.open(`/api/exam/download/${p.id}`, '_blank'); },

    /* ─────────── 统计 ─────────── */
    loadStats() {
      this.loadVocabStats(); this.loadClassicalStats(); this.loadGrammarStats(); this.loadAttempts();
      this.loadMood();
      this.api(`/api/study/self-compare?user_id=${encodeURIComponent(this.user)}&subject=${encodeURIComponent(this.subject)}`)
        .then(d => { this.selfCompare = d || null; }).catch(() => { this.selfCompare = null; });
    },
    loadGrammarStats() {
      this.api(`/api/grammar/stats?grade=${this.grade}`)
        .then(r => { this.grammarStats = r || {}; }).catch(() => {});
    },
    statPct(a, b) { return b ? Math.round((a || 0) / b * 100) : 0; },

    /* ─────────── 通用答题状态机 ─────────── */
    startQuiz({ title, items, source }) {
      this.quiz = {
        active: true, done: false, title,
        items: items.map(it => ({ ...it, answered: false, correct: false, selected: -1, userAnswer: '', cause: '' })),
        i: 0, fillText: '', correct: 0, wrongCount: 0, score: 0, source,
      };
      this.combo = 0; this.maxCombo = 0; this.chestReward = '';
    },
    qOptClass(item, oi) {
      if (!item.answered) return '';
      const letter = 'ABCDEFGH'[oi];
      if (letter === String(item.answer || '').trim().toUpperCase()) return 'correct';
      if (item.selected === oi) return 'wrong';
      return '';
    },
    pickOption(oi) {
      const it = this.quiz.items[this.quiz.i];
      if (it.answered) return;
      it.selected = oi;
      const letter = 'ABCDEFGH'[oi];
      it.correct = letter === String(it.answer || '').trim().toUpperCase();
      it.userAnswer = letter;
      this._afterAnswer(it);
    },
    submitFill() {
      const it = this.quiz.items[this.quiz.i];
      if (it.answered) return;
      const ua = (this.quiz.fillText || '').trim();
      if (!ua) { this.showToast('请先输入答案'); return; }
      it.userAnswer = ua;
      it.correct = this._matchAnswer(ua, it.answer);
      this._afterAnswer(it);
    },
    _afterAnswer(it) {
      it.answered = true;
      if (it.correct) {
        this.quiz.correct++;
        this.combo++;
        this.maxCombo = Math.max(this.maxCombo, this.combo);
        this.showFloat(this.combo >= 2 ? `🔥 连击 x${this.combo}` : '✔ 答对了！', true);
      } else {
        const broken = this.combo >= 3;
        this.quiz.wrongCount++;
        this.combo = 0;
        this.showFloat('差一点！', false);
        // AI 即时鼓励：连击中断或答错时给一句暖心话（3 次/分钟限频，失败自动降级）
        this.askEncourage(broken ? 'combo_broken' : 'wrong_answer');
      }
      if (it.correct && this.quiz.source && this.quiz.source.mode === 'retry' && it.extra
          && this.quiz.source.retry && this.quiz.source.retry.record_id) {
        // 变式重练（单题连对累计）：逐题回写
        this.api('/api/study/practice-submit', {
          method: 'POST',
          body: JSON.stringify({ user_id: this.user, results: [{ kind: it.extra.kind, record_id: it.extra.record_id, correct: true }] }),
        }).then(() => this.loadAnalysis()).catch(() => {});
      }
    },
    showFloat(text, ok, ms = 700) {
      this.floatFx = { show: true, text, ok };
      clearTimeout(this._ft);
      this._ft = setTimeout(() => { this.floatFx.show = false; }, ms);
    },
    pickCause(c) {
      const it = this.quiz.items[this.quiz.i];
      if (!it || !it.answered || it.correct || it.cause) return;
      it.cause = c;
      this.showToast('错因已记录，将针对性推送变式练习 ✨');
    },
    toggleTurbo() {
      this.turbo = !this.turbo;
      localStorage.setItem('zx_turbo', this.turbo ? '1' : '0');
      this.showToast(this.turbo ? '极速模式已开启（动画加速）' : '极速模式已关闭');
    },
    quizNext() {
      // AI 讲解生成中禁止进入下一题（防止讲解被跳过/重复点击）
      const it = this.quiz.items[this.quiz.i];
      if (it && it.explaining) return;
      if (this.quiz.i < this.quiz.items.length - 1) { this.quiz.i++; this.quiz.fillText = ''; }
      else this.finishQuiz();
    },
    finishQuiz() {
      // 防重复提交：done 已为 true 说明本次已提交过（双击"查看结果"/重复点击），直接忽略
      if (this.quiz.done) return;
      const total = this.quiz.items.length;
      this.quiz.score = total ? Math.round(this.quiz.correct / total * 100) : 0;
      this.quiz.done = true;
      const rewards = [
        '✨ 获得 20 学习金币', '📖 掉落知识卡：连击纪录刷新了！',
        '🏅 获得徽章碎片 x1', '💪 勇气值 +10，明天继续挑战！',
        '🎈 好运气球 +1，集满 7 个有惊喜',
      ];
      this.chestReward = rewards[Math.floor(Math.random() * rewards.length)];
      const src = this.quiz.source;
      if (!src) return;
      if (src.mode === 'exam') {
        this.api('/api/exam/submit-answers', {
          method: 'POST',
          body: JSON.stringify({
            user_id: this.user, exam_id: src.exam_id, duration_sec: Math.round((Date.now() - src.startedAt) / 1000),
            answers: this.quiz.items.map(it => ({ question_id: it.qid, user_answer: it.userAnswer || '' })),
          }),
        }).then(r => {
          this.loadAttempts();
          // 提交后按服务端结果（含 AI 复核改判）同步题目状态与得分
          this.submitWrongIds = (r && r.wrong_ids) || {};
          this.submitWrongNew = (r && r.wrong_new_ids) || {};
          if (r && r.results) {
            r.results.forEach(rr => {
              const it = this.quiz.items.find(x => x.qid === rr.question_id);
              if (it) it.correct = rr.is_correct;
            });
            this.quiz.correct = r.correct;
            this.quiz.wrongCount = r.wrong;
            this.quiz.score = r.score;
          }
          if (r && r.ai_approved && r.ai_approved.length) {
            this.showToast(`🤖 AI 复核：${r.ai_approved.length} 题判定为正确 ✓`);
          }
          // 正确率不足 60%：任务不推进，明确告诉孩子/家长为什么任务还没完成
          if (typeof r.score === 'number' && r.score < 60) {
            this.showToast(`正确率 ${r.score}%，要 60% 以上才算完成今日任务哦，再练一套吧！`);
          }
          // 答题中自评的错因：提交后批量落库
          const causes = this.quiz.items.filter(it => !it.correct && it.cause && r.wrong_ids && r.wrong_ids[it.qid])
            .map(it => ({ question_id: it.qid, cause: it.cause }));
          causes.forEach(c => this.api('/api/study/cause-by-question', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, question_id: c.question_id, cause: c.cause }),
          }).catch(() => {}));
          // 提交完成后再刷新每日任务：避免与提交并发读到旧进度，
          // 导致"任务已完成"提示延迟到下次刷新（如切换学科）才弹出
          this.loadDailyTasks();
        }).catch(e => this.showToast(e.message));
      } else if (src.mode === 'retry') {
        this.api('/api/study/practice-submit', {
          method: 'POST',
          body: JSON.stringify({
            user_id: this.user,
            results: this.quiz.items.map(it => ({
              kind: it.extra.kind, record_id: it.extra.record_id, correct: it.correct,
              question: it.question, user_answer: it.userAnswer || '',
              correct_answer: it.answer || '', subject: this.subject,
            })),
          }),
        }).then(r => {
          // AI 复核判对的题：同步前端题目状态（得分/提示保持一致）
          if (r && r.ai_approved && r.ai_approved.length) {
            r.ai_approved.forEach(idx => {
              const it = this.quiz.items[idx];
              if (it && !it.correct) { it.correct = true; it.appealed = false; }
            });
            this.showToast(`🤖 AI 复核：${r.ai_approved.length} 题判定为正确 ✓`);
          }
          const answered = this.quiz.items.filter(it => it.answered);
          const allOk = answered.length > 0 && answered.every(it => it.correct);
          const masteredIds = ((r && r.details) || []).filter(d => d.status === 'mastered').map(d => d.record_id);
          // 掌握检测/错题修正：整组全对 → 已掌握（后端按 record 分组判定）
          if (src.mastery || this.quiz.items.length >= 3) {
            this.showToast(allOk ? '🎉 全部答对，已标记掌握！' : '有答错的题，暂未掌握，加油再来！');
          } else {
            this.showToast(allOk ? '全部答对 🎉' : '再练练，下次全对就能掌握啦');
          }
          this.loadAnalysis();
          this.loadDailyTasks();
          this.loadWrongItems().then(() => {
            // 同步详情页当前错题的最新掌握状态
            if (this.curWrong && this.curWrong.record_id) {
              const fresh = this.wrongItems.find(x => x.kind === this.curWrong.kind && x.record_id === this.curWrong.record_id);
              if (fresh) Object.assign(this.curWrong, fresh);
              else if (masteredIds.includes(this.curWrong.record_id)) this.curWrong.mastered = true;
            }
          });
        }).catch(e => this.showToast(e.message));
      } else if (src.mode === 'classical') {
        const wrongs = this.quiz.items.filter(it => !it.correct && it.userAnswer)
          .map(it => ({
            source_type: 'classical', source_id: it.text_id || src.text_id, module_name: '古诗文默写',
            question: it.question, user_answer: it.userAnswer, correct_answer: it.answer,
            explanation: it.sub || '',
          }));
        const p = wrongs.length
          ? this.api('/api/study/errors', { method: 'POST', body: JSON.stringify({ user_id: this.user, items: wrongs }) })
          : Promise.resolve();
        // 提交完成后再刷新每日任务：与答题提交竞态同理，避免
        // "任务已完成"提示延迟到下次刷新（如切换学科）才弹出
        p.then(() => { this.loadAnalysis(); this.loadDailyTasks(); }).catch(() => {});
      } else if (src.mode === 'dictate') {
        // 默写检测：全对才算通过；未全对 → 只重默错的部分，直到全对才落库
        const wrongs = this.quiz.items.filter(it => !it.correct);
        this.quiz.items.forEach(it => { if (it.correct) this.dtOk[it.qid] = it.userAnswer; });
        if (wrongs.length) {
          this.showToast(`还有 ${wrongs.length} 处没默写对，再默一遍！`);
          this.startQuiz({
            title: this.quiz.title,
            items: wrongs.map(it => ({
              qid: it.qid, text_id: it.text_id, question: it.question, sub: it.sub,
              placeholder: it.placeholder, options: [], answer: it.answer, explanation: '',
            })),
            source: src,
          });
          return;
        }
        // 全部默写正确 → 提交后端（后端再核验，全对才真正记录进度）
        if (src.kind === 'word') {
          const ws = this.wordSession;
          const results = (ws.words || []).map(w => ({ word_id: w.word_id, answer: this.dtOk[w.word_id] || w.word }));
          this.api('/api/vocab/dictate', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, mode: src.mode2, results }),
          }).then(r => {
            this.quiz.active = false;
            if (r && r.passed) { ws.done = true; this.refreshAll(); }
            else { ws.active = false; this.showToast('有个别拼写仍需核对，再学一遍吧'); this.refreshAll(); }
          }).catch(e => { this.quiz.active = false; ws.active = false; this.showToast(e.message); });
        } else {
          const ts = this.textSession;
          const textIds = (ts.texts || []).map(t => t.text_id);
          this.api('/api/classical/dictate', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, mode: src.mode2, text_ids: textIds }),
          }).then(r => {
            this.quiz.active = false;
            if (r && r.passed) { ts.done = true; this.refreshAll(); }
            else { ts.active = false; this.showToast('默写未通过，本次不计入进度'); this.refreshAll(); }
          }).catch(e => { this.quiz.active = false; ts.active = false; this.showToast(e.message); });
        }
        return;
      }
      this.refreshAll();
    },
    closeQuiz() {
      const src = this.quiz.source;
      if (src && src.mode === 'dictate' && !this.quiz.done) {
        // 默写中途退出：学习未完成默写，不记录任何进度
        if (src.kind === 'word') this.wordSession.active = false;
        else this.textSession.active = false;
        this.showToast('未完成默写，本次学习不记录进度，加油再来！');
      } else if (src && src.mode === 'retry' && !this.quiz.done) {
        const answered = this.quiz.items.filter(it => it.answered);
        if (answered.length) {
          this.api('/api/study/practice-submit', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, results: answered.map(it => ({ kind: it.extra.kind, record_id: it.extra.record_id, correct: it.correct })) }),
          }).then(() => { this.loadAnalysis(); this.loadDailyTasks(); this.loadWrongItems(); }).catch(() => {});
        }
      } else if (src && src.mode === 'exam' && !this.quiz.done) {
        // 中途退出：全部题目提交，未作答的记为错误，保证一定生成完整做题记录
        this.api('/api/exam/submit-answers', {
          method: 'POST',
          body: JSON.stringify({
            user_id: this.user, exam_id: src.exam_id,
            duration_sec: Math.round((Date.now() - (src.startedAt || Date.now())) / 1000),
            answers: this.quiz.items.map(it => ({ question_id: it.qid, user_answer: it.answered ? (it.userAnswer || '') : '' })),
          }),
        }).then(r => {
          this.loadAttempts();
          this.loadDailyTasks();
          // 中途退出也算"直接提交"：正确率不足 60% 时同样提示任务不会完成
          if (typeof r.score === 'number' && r.score < 60) {
            this.showToast(`正确率 ${r.score}%，要 60% 以上才算完成今日任务哦，再练一套吧！`);
          } else {
            this.showToast('已保存：未作答题目记为错误');
          }
        }).catch(e => this.showToast('保存失败：' + (e.message || '')));
      }
      this.quiz.active = false;
      this.refreshAll();
    },
    quizAgain() {
      const src = this.quiz.source;
      if (!src) return;
      if (src.mode === 'exam') this.startExamQuiz(src.exam_id, src.title);
      else if (src.mode === 'retry') {
        if (src.retry && src.retry.record_id) this.startWrongRetry({ kind: src.retry.kind, record_id: src.retry.record_id });
        else this.startWrongPractice();
      }
      else if (src.mode === 'classical') this.startTextQuiz({ id: src.text_id, title: src.textTitle });
    },
    closeQuizGo(tab) {
      this.quiz.active = false;
      this.refreshAll();
      this.goTab(tab);
    },
    startExamQuiz(examId, title) {
      this.api(`/api/exam/${examId}/questions`)
        .then(qs => {
          const items = (qs || []).map(q => ({
            qid: q.id, question: q.question, sub: q.type_name || '',
            options: this._parseOpts(q.options_json), answer: q.answer, explanation: '',
          }));
          this.startQuiz({ title: title || '在线做题', items, source: { mode: 'exam', exam_id: examId, startedAt: Date.now() } });
        }).catch(e => this.showToast(e.message));
    },
    _parseOpts(s) {
      if (!s) return [];
      try { const d = JSON.parse(s); return Array.isArray(d) ? d : []; } catch (e) { return []; }
    },
    /* 容错判题（与后端 app/services/answer_check.py 完全一致）：
       孩子写简便方法过程（如 2*(999+1)=2*1000=2000）也算对 */
    _cleanSeg(seg) {
      let x = String(seg).replace(/[^0-9+\-*/().%]+$/g, '');   // 剥单位："2000元"→"2000"
      if (!x) return null;
      while (x.endsWith('(') || (x.endsWith(')') && !x.includes('('))) {  // 不成对括号
        x = x.slice(0, -1).replace(/[^0-9+\-*/().%]+$/g, '');
        if (!x) return null;
      }
      if (x.endsWith('%')) x = x.slice(0, -1) + '/100';         // "50%" → 50/100
      return x;
    },
    /* 安全求值简单算术表达式（+ - * / 括号、小数）；非法/除零 → null */
    _mathEval(expr) {
      const s = this._cleanSeg(expr);
      if (!s || /[^0-9+\-*/().]/.test(s) || s.includes('%')) return null;
      let i = 0; const n = s.length;
      const peek = () => (i < n ? s[i] : '');
      const num = () => {
        const m = /^\d+(?:\.\d+)?/.exec(s.slice(i));
        if (!m) return null;
        i += m[0].length;
        return parseFloat(m[0]);
      };
      const exprP = () => {
        const c = peek();
        if (c === '(') { i++; const v = exprFull(); if (v === null || peek() !== ')') return null; i++; return v; }
        if (c === '+') { i++; return exprP(); }
        if (c === '-') { i++; const v = exprP(); return v === null ? null : -v; }
        return num();
      };
      const term = () => {
        let v = exprP();
        if (v === null) return null;
        while (peek() === '*' || peek() === '/') {
          const op = peek(); i++;
          const r = exprP();
          if (r === null || (op === '/' && r === 0)) return null;
          v = op === '*' ? v * r : v / r;
        }
        return v;
      };
      const exprFull = () => {
        let v = term();
        if (v === null) return null;
        while (peek() === '+' || peek() === '-') {
          const op = peek(); i++;
          const r = term();
          if (r === null) return null;
          v = op === '+' ? v + r : v - r;
        }
        return v;
      };
      const v = exprFull();
      return v !== null && i === n ? v : null;
    },
    /* 答案的最终结果值：'=' 分段取最后一段求值（用户陈述的结果），不可求值时取第一个可求值段 */
    _resultValue(s) {
      const segs = s.split('=');
      const last = this._mathEval(segs[segs.length - 1]);
      if (last !== null) return last;
      for (const seg of segs) { const v = this._mathEval(seg); if (v !== null) return v; }
      return null;
    },
    _matchAnswer(ua, ans) {
      const stripAnnot = s => {   // 仅剥含非数学字符的末尾括号注释（共N个/原式=…），算式括号保留
        for (;;) {
          const m = /\([^()]*\)$/.exec(s);
          if (!m) return s;
          const inner = m[0].slice(1, -1);
          if (/^[0-9+\-*/().%]*$/.test(inner)) return s;   // 纯算式（(999+1)、(45)）→ 停止
          const t = s.slice(0, m.index);
          if (!t) return s;
          s = t;
        }
      };
      const norm = (s, keepSep) => {
        let x = String(s || '').trim().toLowerCase()
          .replace(/\s+/g, '')
          .replace(/[０-９]/g, d => String.fromCharCode(d.charCodeAt(0) - 0xFEE0))
          .replace(/[ａ-ｚ]/g, d => String.fromCharCode(d.charCodeAt(0) - 0xFEE0))
          .replace(/[Ａ-Ｚ]/g, d => String.fromCharCode(d.charCodeAt(0) - 0xFEE0))
          .replace(/（/g, '(').replace(/）/g, ')')
          .replace(/＝/g, '=').replace(/，/g, ',').replace(/。/g, '.')
          .replace(/×/g, '*').replace(/＊/g, '*').replace(/·/g, '*')
          .replace(/÷/g, '/').replace(/＋/g, '+').replace(/－/g, '-')
          .replace(/、/g, ',')   // 顿号当分隔符（与后端 answer_check 一致）
          .replace(/[。！？；：、,.!?;:…]+$/g, '');
        x = stripAnnot(x);
        if (!keepSep) x = x.replace(/,/g, '');
        return x;
      };
      const u = norm(ua), a = norm(ans);
      if (!a) return false;
      if (u === a) return true;
      if (!/\d/.test(a)) return false;   // 无数字（单词/古诗文/句子）→ 严格
      const uRes = this._resultValue(u), aRes = this._resultValue(a);
      if (uRes !== null && aRes !== null && Math.abs(uRes - aRes) < 1e-9) return true;
      // token 从保留分隔符的规范化串提取："90、120、150" 与 "90,120,150" 均为 3 个 token
      const nums = s => (String(s).match(/-?\d+\.?\d*/g) || []);
      const un = nums(norm(ua, true)), an = nums(norm(ans, true));
      if (an.length === 1 && un.length && Math.abs(parseFloat(un[un.length - 1]) - parseFloat(an[0])) < 1e-9) return true;
      // 数字 token 数量一致 → 排序后逐一比对（忽略书写顺序）
      if (un.length && un.length === an.length) {
        const us = un.map(parseFloat).sort((m, n) => m - n);
        const as = an.map(parseFloat).sort((m, n) => m - n);
        if (us.every((x, i) => Math.abs(x - as[i]) < 1e-9)) return true;
      }
      return false;
    },
  },

  mounted() {
    this.loadMathCategories();
    this.loadEngTypes();
    this.turbo = localStorage.getItem('zx_turbo') === '1';
    const saved = JSON.parse(localStorage.getItem('zx_user') || 'null');
    if (saved && saved.user) {
      this.user = saved.user;
      this.username = saved.user;
      this.grade = saved.grade || 6;
      this.subject = saved.subject || '英语';
      this.engTypes = this.subject === '语文' ? this._chiTypes : this._engTypes;
      this.refreshAll();
    }
  },
}).mount('#app');
