// appOptions：App.vue 的业务逻辑 mixin（选项对象，被 App.vue 展开合并）。
// 集中承载登录/认证、首页任务（强制+可选+补签 makeup_pending）、复习队列（艾宾浩斯）、
// 刷题/背诵/错题、家长面板（X-Parent-Pwd 密码头、补签确认、申诉）、挑战赛、宠物/成长树等全部 data 与 methods。
// 注意：仅补充注释，未改动任何逻辑/字段；Vue 模板在 App.vue 内。
const appOptions = {
  data() {
    return {
      // 登录
      user: '', userName: '', token: '', username: '', grade: 6, subject: '英语', showGradeModal: false,
      promotedInfo: null,   // 升年级引导弹窗（登录响应 promoted）
      // 学习同步（家长面板）：预习/课堂同步/小升初衔接 + 教学进度
      studyFlags: { include_next: false, sync_mode: false, xsc_bridge: false },
      teachBooks: [], teachProgressItems: [], teachProgress: { book_id: 0, chapter: '' },
      // 认证（P2：注册/登录/重置/绑定）
      authMode: 'login', loginPwd: '', authInfo: {},
      regTarget: '', regCode: '', regPwd: '', regNickname: '',
      rstTarget: '', rstCode: '', rstPwd: '',
      bindTarget: '', bindCode: '', authCooldown: 0, _authTimer: null,
      // 天气（P3：首页卡片 + 城市配置）
      weather: null, cityInput: '',
      // 导航
      tab: 'home',
      // 全局统计
      streakDays: 0, totalTodo: 0, avgScore: 0,
      masteredTotal: 0, wrongBadge: 0, diamonds: 0,
      // 钻石充值（手动充值：扫码付款 + 客服核对账户后发放）
      rechargeOpen: false, rechargeCfg: null, rechargePkg: 0, rechargeCopied: false, rechargeQrOpen: false,
      // 首页
      dashboard: null, todayTasks: [],
      rejudging: false,          // AI 重判进行中（当前做题题）
      recheckingId: null,        // 家长申诉列表中正在 AI 复核的申诉 id
      dailyTasks: null, dailyTaskStats: { done_count: 0, total: 3, streak_days: 0 }, makeupCards: 0,
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
      // 完成确认（孩子提交任务完成 → 家长确认/拒绝）：首页展示 + 家长操作
      taskConfirms: [],
      taskConfirmsTotal: 0,                       // 历史总条数（用于「查看全部 N 条」）
      taskReject: { id: null, reason: '' },       // 家长拒绝时展开的输入框
      taskSubmitTip: { show: false },             // 孩子完成任务后弹出的「发截图给家长」提示
      showAllConfirms: false,                     // 首页「完成确认」是否展开全部历史
      showAllAppeals: false,                      // 首页「错题申诉结果」是否展开全部历史
      showAllRewards: false,                      // 首页「成长奖励记录」是否展开全部历史
      homeSub: 'today',                           // 首页子视图：today(今日) / reward(奖励激励) / family(家园互动)

      // 错题本
      wrongAnalysis: { total: 0, pending: 0, mastered: 0, mastery_rate: 0, by_cause: [], by_subject: [] },
      wrongScreen: 'list', wrongKind: 'all', wrongStatus: 'pending',
      wrongItems: [], curWrong: null, showAllWrong: false,
      // AI 错题讲解（Sprint 2）：内联展示，状态挂在 quiz 题目项 / curWrong 上
      // 心情打卡（Sprint 2）
      moodTrend: null, moodNote: '', moodPicking: false,
      // 奖励闭环 + 成长周报（Sprint 3）
      rewards: null,
      allCoupons: [], pendingWishes: [],
      newCoupon: { title: '', kind: 'custom', reason: '', requiredDays: 0, requiredWithinDays: 0 },
      wishOverlay: { show: false, title: '', target: 5, wish_type: 'task_count', daily_target: 3 },
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
      showAllPending: false,    // 待处理申诉是否展开全部（避免一次渲染过多卡顿）
      decidedAppeals: [],       // 已裁决（判对/判错），首页「家长反馈」区展示
      decidedAppealsTotal: 0,   // 已裁决历史总条数
      appealExpanded: {},       // {id: true} 点击展开查看完整题目
      appealNotes: {},          // {id: '备注'} 家长判题时填写的备注
      pendingMakeups: [],
      submitWrongIds: {}, submitWrongNew: {},
      // 每日任务设置
      taskSettings: { items: [] },
      taskDialog: { show: false, defaults: [], extra: [], optional: [], disabled: [] },
      parentCustomTasks: [],
      customTaskForm: { title: '', subject: '数学', task_type: 'optional', target: 1 },
      // Sprint 4：称号 / 挑战赛 / 学期目标 / 小老师
      titleInfo: null, titleBadges: [],
      chalOverlay: { show: false, stage: 'pick', kind: 'math', questions: [], i: 0, timeLeft: 60, input: '', correct: 0, total: 0, newBest: false },
      chalCombo: 0, chalBest: { math: { best: 0 }, word: { best: 0 } },
      goalOverlay: { show: false, kind: 'score', target: 90, deadline: '', subject: '数学' },
      goals: [],
      teachOverlay: { show: false, cards: [], idx: 0, step: 1, card: null, answerText: '', result: '', hint: '' },
      teachDue: [], recheckOverlay: { show: false, card: null, answerText: '' },
      // 通用答题状态机
      quiz: { active: false, done: false, title: '', items: [], i: 0, fillText: '', correct: 0, wrongCount: 0, score: 0, source: null },
      // 爽感反馈：连击 / 飘字 / 宝箱 / 极速模式 / 自我超越
      combo: 0, maxCombo: 0,
      floatFx: { show: false, text: '', ok: true },
      chestReward: '', turbo: false, selfCompare: null,
      newStarRecord: false,   // 首获五星 → 「新纪录！」（结算页展示）
      // 明日复习队列（PRD 3.3：重做仍错 → 明天再来一次）
      tomorrowQueue: { count: 0, items: [] },
      // 试卷中心
      papers: [],
      // 十万个为什么（Sprint 5 + 多轮对话）
      qaAsk: '', qaProvider: 'zhipu', qaLoading: false, qaAnswer: null,
      qaModels: [], qaModelsVip: false,
      qaHistory: [], qaHistType: 'all',
      qaMessages: [], qaSessionId: '', qaSessions: [],
      // 宠物家园（P2-1 金币宠物）
      petProfile: null, petLedger: [], petRules: [], petMsg: '', petBusy: false, petLeveledUp: false,
      // 成长树（P2-2 创意 7）
      treeData: null,
      treeStages: [
        { name: '小种子', emoji: '🌱' }, { name: '小幼苗', emoji: '🌿' }, { name: '小树苗', emoji: '🪴' },
        { name: '青葱小树', emoji: '🌳' }, { name: '茁壮大树', emoji: '🌳' }, { name: '枝繁叶茂', emoji: '🌳' },
        { name: '开花啦', emoji: '🌸' }, { name: '硕果累累', emoji: '🍎' }, { name: '森林之王', emoji: '🌟' },
      ],
      // 成就徽章（P2-3 创意 8）
      badgeData: null, badgeNew: [],
      // 知识卡图鉴（P2-4 创意 13）
      cardData: null, drawCards: [], drawAllCollected: false, cardDrawing: false,
      // 听写磨耳朵（P2-5 创意 25）
      dictMode: 'word',
      dictSession: { active: false, done: false, items: [], i: 0, current: null, answer: '', revealed: false, lastOk: false, correct: 0, rewarded: false },
      // 番茄专注钟（P2-6 创意 22）
      focusTimer: { total: 25, left: 25 * 60, running: false, paused: false },
      focusDone: false, focusMsg: '', focusToday: null, focusStats: null, _focusTicker: null,
      // AI 趣味出题（AI-2 创意 24）
      aiQuizThemes: { adventure: '冒险岛探险', space: '太空旅行', dino: '恐龙世界', food: '美食厨房', magic: '魔法学院' },
      aiQuizThemeEmoji: { adventure: '🗺️', space: '🚀', dino: '🦕', food: '🍔', magic: '🔮' },
      aiQuiz: { subject: '数学', grade: 6, theme: 'adventure', loading: false, themeName: '', quiz: null, answers: {}, inputs: {}, graded: null, score: null, rewardGranted: 0 },
      aiQuizPlayed: Number(localStorage.getItem('zx_aiquiz_played') || 0),
      // AI 学习助手（AI-5）
      assistantProfile: null, assistantMsgs: [], assistantDraft: '', assistantLoading: false,
      // 统计
      vocabStats: {}, classicalStats: {}, grammarStats: {},
      // Toast
      toast: { show: false, msg: '' },
    };
  },

  computed: {
    isAccountCredential() {
      // 登录统一为邮箱 + 密码
      const a = (this.username || '').trim();
      return /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/.test(a);
    },
    subjectOptions() {
      // 九科：初中（grade>=7）额外显示物理/化学/生物/道德与法治/历史/地理
      const base = ['数学', '语文', '英语'];
      return this.grade >= 7 ? base.concat(['物理', '化学', '生物', '道德与法治', '历史', '地理']) : base;
    },
    teachUnitOptions() {
      const b = (this.teachBooks || []).find(x => x.book_id === this.teachProgress.book_id);
      return b ? b.units : [];
    },
    teachProgressText() {
      const it = (this.teachProgressItems || []).find(x => x.subject === '英语');
      if (!it || (!it.book_name && !it.chapter)) return '';
      return [it.book_name, it.chapter].filter(Boolean).join(' · ');
    },
    greeting() {
      const h = new Date().getHours();
      return h < 6 ? '夜深了' : h < 12 ? '早上好' : h < 18 ? '下午好' : '晚上好';
    },
    focusTimeText() {
      const s = this.focusTimer.left % 60;
      const m = Math.floor(this.focusTimer.left / 60);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    },
    focusRingStyle() {
      const total = this.focusTimer.total * 60 || 1;
      const pct = Math.min(100, Math.round((total - this.focusTimer.left) / total * 100));
      return `background: conic-gradient(#ff512f ${pct}%, #ffe3e3 ${pct}% 100%)`;
    },
    aiQuizAnswered() {
      const q = this.aiQuiz;
      if (!q.quiz) return 0;
      let n = 0;
      q.quiz.forEach((item, i) => {
        if (item.options && item.options.length) { if (q.answers[i]) n++; }
        else if (q.inputs[i] && String(q.inputs[i]).trim()) n++;
      });
      return n;
    },
    assistantChips() {
      return ['今天该学什么？', '帮我分析我的错题', '夸夸我这周表现', '我进步了吗？'];
    },
    assistantChipCount() {
      return this.assistantProfile ? (this.assistantProfile.profile || '').split('；').filter(Boolean).length : 0;
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
    curWord() {
      return (this.wordSession && this.wordSession.words && this.wordSession.words[this.wordSession.i]) || {};
    },
    curText() {
      return (this.textSession && this.textSession.texts && this.textSession.texts[this.textSession.i]) || {};
    },
    textLines() {
      // 与后端 _pinyin_lines 逐行对齐（均过滤空行）
      return (this.curText.content || '').split('\n').map(s => s.trim()).filter(s => s);
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
      return s >= 90 ? 5 : s >= 70 ? 4 : s >= 50 ? 3 : s >= 30 ? 2 : 1;
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
    mandatoryTasks() {
      return (this.dailyTasks || []).filter(t => t.mandatory);
    },
    optionalTasks() {
      return (this.dailyTasks || []).filter(t => !t.mandatory);
    },
    allTaskOptions() {
      // 所有任务选项（用于任务设置弹窗；背诵/学单词仅供强制任务下拉，不可作为可选任务）
      return [
        { code: 'math_exam', title: '完成 1 套数学练习', subject: '数学' },
        { code: 'chi_classical', title: '背诵古诗文', subject: '语文' },
        { code: 'eng_vocab', title: '学单词', subject: '英语' },
        { code: 'math_fix', title: '订正错题', subject: '数学' },
        { code: 'math_teach', title: '给家长讲题', subject: '数学' },
        { code: 'math_challenge', title: '数学60秒挑战赛', subject: '数学' },
        { code: 'math_sync', title: '学习平板同步练习', subject: '数学' },
        { code: 'chi_exam', title: '完成 1 套语文练习', subject: '语文' },
        { code: 'chi_read', title: '朗读课文', subject: '语文' },
        { code: 'chi_dictation', title: '默写古诗', subject: '语文' },
        { code: 'chi_sync', title: '学习平板同步练习', subject: '语文' },
        { code: 'eng_exam', title: '完成 1 套英语练习', subject: '英语' },
        { code: 'eng_dictation', title: '听写单词', subject: '英语' },
        { code: 'eng_challenge', title: '英语60秒挑战赛', subject: '英语' },
        { code: 'eng_sync', title: '学习平板同步练习', subject: '英语' },
      ];
    },
  },

  methods: {
    /* ─────────── 通用 ─────────── */
    api(path, opts = {}) {
      // 家长解锁期间自动携带家长密码头（服务端敏感接口校验 X-Parent-Pwd）
      const headers = { 'Content-Type': 'application/json' };
      try {
        const pp = sessionStorage.getItem('zx_parent_pwd');
        if (pp) headers['X-Parent-Pwd'] = pp;
        // 登录会话 token：后端业务接口要求 Bearer 鉴权
        const tk = localStorage.getItem('zx_token');
        if (tk) headers['Authorization'] = 'Bearer ' + tk;
      } catch (e) { /* 隐私模式等异常忽略 */ }
      return fetch(path, Object.assign({ headers }, opts))
        .then(async r => {
          // 401：登录态失效，清除本地会话并回到登录页
          if (r.status === 401) {
            const hadSession = !!localStorage.getItem('zx_user');
            try { localStorage.removeItem('zx_user'); localStorage.removeItem('zx_token'); sessionStorage.removeItem('zx_parent_pwd'); } catch (e) {}
            // 业务接口 401：清会话 + 延迟跳登录页（仅首次有 session 时跳）。
            // 先 throw 让调用方 .catch() 有机会弹 toast 告知用户；
            // 延迟 1.8s 再跳转，保证用户能看到提示（而非按钮突然无反应、页面莫名刷新）。
            const msg = '登录已过期，请重新登录';
            if (path.indexOf('/api/auth/') === -1 && hadSession) {
              this.showToast(msg);
              setTimeout(() => { location.href = '/'; }, 1800);
            }
            throw new Error(msg);
          }
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
      if (this.user) {
        localStorage.setItem('zx_user', JSON.stringify({ user: this.user, grade: this.grade, subject: this.subject, nickname: this.userName, token: this.token }));
        if (this.token) localStorage.setItem('zx_token', this.token);
      }
    },

    /* ─────────── 登录 / 注册 / 退出 ─────────── */
    login() {
      const account = this.username.trim();
      if (!account) { this.showToast('请输入邮箱'); return; }
      if (!this.isAccountCredential) { this.showToast('请输入有效的邮箱'); return; }
      if (!this.loginPwd) { this.showToast('请输入密码'); return; }
      this.api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ account, password: this.loginPwd }),
      }).then(r => this.onLoginOk(r)).catch(e => this.showToast(e.message));
    },
    onLoginOk(r) {
      this.user = r.user_id;
      this.userName = r.nickname || r.user_id;
      this.token = r.token || '';
      this.streakDays = r.streak_days || 0;
      this.grade = r.grade || 6;
      this.subject = r.subject || '英语';
      this.saveUser();
      this.showToast(`欢迎回来，${this.userName}！`);
      this.loadAuthInfo();
      this.loadWeather();
      // 升年级引导：9月1日自动升级后登录弹窗
      if (r.promoted) {
        this.promotedInfo = { prev_grade: r.prev_grade || (r.new_grade || r.grade) - 1, new_grade: r.new_grade || r.grade };
      }
      if (r.is_new || !r.grade) {
        this.showGradeModal = true;
      } else {
        this.refreshAll();
      }
    },
    closePromoted() {
      this.promotedInfo = null;
    },
    register() {
      const target = this.regTarget.trim();
      if (!/^[\w.+-]+@[\w-]+(\.[\w-]+)+$/.test(target)) { this.showToast('请输入有效的邮箱'); return; }
      if (this.regCode.trim().length < 6 || !this.regPwd) return;
      this.api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          target, code: this.regCode.trim(), password: this.regPwd,
          nickname: this.regNickname.trim() || null,
        }),
      }).then(r => { this.regCode = ''; this.regPwd = ''; this.onLoginOk(r); })
        .catch(e => this.showToast(e.message));
    },
    sendAuthCode(purpose, target) {
      const t = (target || '').trim();
      if (!t || this.authCooldown > 0) return;
      this.api('/api/auth/send-code', {
        method: 'POST',
        body: JSON.stringify({ target: t, purpose }),
      }).then(() => {
        this.showToast('验证码已发送，请注意查收');
        this.startAuthCooldown();
      }).catch(e => this.showToast(e.message));
    },
    startAuthCooldown() {
      this.authCooldown = 60;
      clearInterval(this._authTimer);
      this._authTimer = setInterval(() => {
        if (--this.authCooldown <= 0) clearInterval(this._authTimer);
      }, 1000);
    },
    resetPassword() {
      const target = this.rstTarget.trim();
      if (!target || this.rstCode.trim().length < 6 || !this.rstPwd) return;
      this.api('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ target, code: this.rstCode.trim(), new_password: this.rstPwd }),
      }).then(() => {
        this.showToast('密码已重置，请用新密码登录');
        this.username = target; this.rstTarget = ''; this.rstCode = ''; this.rstPwd = '';
        this.authMode = 'login';
      }).catch(e => this.showToast(e.message));
    },
    bindAccount() {
      const target = this.bindTarget.trim();
      if (!this.user || !target || this.bindCode.trim().length < 6) return;
      this.api('/api/auth/bind', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, target, code: this.bindCode.trim() }),
      }).then(() => {
        this.showToast('绑定成功 🎉');
        this.bindTarget = ''; this.bindCode = '';
        this.loadAuthInfo();
      }).catch(e => this.showToast(e.message));
    },
    loadAuthInfo() {
      if (!this.user) return;
      this.api(`/api/auth/me?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.authInfo = d || {}; if (d && d.nickname) this.userName = d.nickname; })
        .catch(() => { this.authInfo = {}; });
    },
    loadWeather() {
      // 首页天气卡：优先用户配置城市，后端回退 IP 定位/默认城市
      this.api(`/api/weather/current?user_id=${encodeURIComponent(this.user || '')}`)
        .then(d => { this.weather = d; if (d && d.city) this.cityInput = d.city; })
        .catch(() => { this.weather = null; });
    },
    saveCity() {
      const city = (this.cityInput || '').trim();
      if (!city) { this.showToast('请输入城市'); return; }
      this.api('/api/weather/city', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, city }),
      }).then(() => {
        this.showToast(`城市已保存：${city}`);
        this.weather = null;
        this.loadWeather();
      }).catch(e => this.showToast(e.message));
    },
    wxDayLabel(fxDate) {
      // 预报日期转「今天/明天/周几」
      if (!fxDate) return '';
      const d = new Date(fxDate + 'T00:00:00');
      const diff = Math.round((d - new Date(new Date().toDateString())) / 86400000);
      if (diff === 0) return '今天';
      if (diff === 1) return '明天';
      return '周' + '日一二三四五六'[d.getDay()];
    },
    logout() {
      localStorage.removeItem('zx_user');
      localStorage.removeItem('zx_token');
      sessionStorage.removeItem('zx_parent_pwd');
      this.user = ''; this.username = ''; this.tab = 'home'; this.showGradeModal = false;
      this.loginPwd = ''; this.authInfo = {}; this.authMode = 'login';
    },

    /* ─────────── 导航 ─────────── */
    goTab(t) {
      this.tab = t;
      if (t === 'home') { this.loadRewards(); this.loadRewardTimeline(); this.loadParentMsgs(); this.loadNotices(); }
      if (t === 'practice') { this.loadMathCategories(); if (this.subject === '英语') this.loadGrammarPoints(); }
      if (t === 'recite') { this.reciteSub === 'words' ? this.loadVocabToday() : this.loadClassicalToday(); this.loadClassicalTexts(); }
      if (t === 'wrong') { this.loadWrongItems(); this.loadAnalysis(); this.loadTeachDue(); }
      if (t === 'papers') this.loadPapers();
      if (t === 'qa') { this.loadQaModels(); this.loadQaHistory(); this.loadQaSessions(); }
      if (t === 'pet') { this.petLeveledUp = false; this.loadPet(); this.loadPetLedger(); this.loadPetRules(); }
      if (t === 'tree') this.loadTree();
      if (t === 'badges') { this.badgeNew = []; this.loadBadges(true); }
      if (t === 'cards') this.loadCards();
      if (t === 'focus') this.loadFocus();
      if (t === 'aiquiz') {
        if (!this.aiQuiz.quiz) { this.aiQuiz.subject = this.subject; this.aiQuiz.grade = this.grade; }
      }
      if (t === 'assistant') this.loadAssistantProfile();
      if (t === 'stats') this.loadStats();
      if (t === 'settings') this.initParentPanel();
    },
    switchSubject(s) {
      this.subject = s;
      if (this.tab === 'practice') {
        if (s !== '英语' && this.practiceSub === 'grammar') this.practiceSub = 'generate';
        if (s === '英语') this.loadGrammarPoints();
        this.loadAttempts();
      }
      if (this.tab === 'wrong') { this.loadWrongItems(); this.loadAnalysis(); }
      this.saveUser();
    },
    onGradeChange() {
      this._normalizeSubjectForGrade();
      this.saveUser();
      this.api('/api/user/grade', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, grade: this.grade }),
      }).then(() => this.refreshAll()).catch(() => {});
    },
    selectInitialGrade() {
      this.showGradeModal = false;
      this._normalizeSubjectForGrade();
      this.api('/api/user/grade', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, grade: this.grade }),
      }).then(() => { this.saveUser(); this.refreshAll(); }).catch(() => { this.refreshAll(); });
    },
    _normalizeSubjectForGrade() {
      // 降回小学年级时，初中专属学科回退为英语
      if (this.grade < 7 && ['物理', '化学', '生物', '道德与法治', '历史', '地理'].indexOf(this.subject) >= 0) {
        this.subject = '英语';
      }
    },
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
    genSessionId() {
      return 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    },
    newQaSession() {
      this.qaSessionId = '';
      this.qaMessages = [];
      this.qaAsk = '';
    },
    loadQaSessions() {
      if (!this.user) return;
      this.api(`/api/qa/sessions?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.qaSessions = (d && d.items) || []; })
        .catch(() => { this.qaSessions = []; });
    },
    openQaSession(sid) {
      if (this.qaLoading) return;
      this.api(`/api/qa/session?user_id=${encodeURIComponent(this.user)}&session_id=${encodeURIComponent(sid)}`)
        .then(d => {
          this.qaSessionId = sid;
          this.qaMessages = ((d && d.items) || []).map(r => ({
            role: 'user', text: r.question,
          }, {
            role: 'ai', text: r.answer, provider: r.provider, model: r.model, degraded: !!r.degraded,
          })).flat();
          this.$nextTick(this.scrollQaChat);
        })
        .catch(() => {});
    },
    scrollQaChat() {
      const el = document.querySelector('.qa-chat');
      if (el) el.scrollTop = el.scrollHeight;
    },
    askQa() {
      const q = this.qaAsk.trim();
      if (!q || this.qaLoading) return;
      if (!this.qaSessionId) this.qaSessionId = this.genSessionId();
      this.qaLoading = true;
      this.qaMessages.push({ role: 'user', text: q });
      this.qaAsk = '';
      this.$nextTick(this.scrollQaChat);
      this.api('/api/qa/ask', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, question: q, provider: this.qaProvider, session_id: this.qaSessionId }),
      }).then(d => {
        this.qaMessages.push({
          role: 'ai', text: d.answer, provider: d.provider, model: d.model,
          cached: !!d.cached, degraded: !!d.degraded, session_id: d.session_id || '',
        });
        if (!d.cached && d.session_id) this.qaSessionId = d.session_id;
        this.$nextTick(this.scrollQaChat);
        this.loadQaSessions();
        this.loadQaHistory();
      }).catch(e => {
        this.qaMessages.push({ role: 'ai', text: '（发送失败）' + e.message, degraded: true });
      }).finally(() => { this.qaLoading = false; });
    },
    loadQaHistory() {
      if (!this.user) return;
      this.api(`/api/qa/history?user_id=${encodeURIComponent(this.user)}&q_type=${this.qaHistType}`)
        .then(d => { this.qaHistory = d || []; })
        .catch(() => { this.qaHistory = []; });
    },

    /* ─────────── 宠物家园（P2-1 金币宠物） ─────────── */
    loadPet() {
      if (!this.user) return;
      this.api(`/api/pet?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.petProfile = d; })
        .catch(() => { this.petProfile = null; });
    },
    loadDiamonds() {
      if (!this.user) return;
      this.api(`/api/diamond/balance?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.diamonds = d.balance || 0; })
        .catch(() => { this.diamonds = 0; });
    },
    // 打开钻石购买弹窗并加载充值配置（收款二维码/客服/汇率）
    openRecharge() {
      this.rechargeOpen = true;
      this.rechargeQrOpen = false;
      if (!this.rechargeCfg) {
        this.api('/api/diamond/recharge/config')
          .then(c => { this.rechargeCfg = c || null; })
          .catch(() => { this.rechargeCfg = null; });
      }
    },
    closeRecharge() { this.rechargeOpen = false; this.rechargeCopied = false; this.rechargeQrOpen = false; },
    // 选择充值套餐（点击即展示对应收款二维码）
    selectRechargePkg(n) { this.rechargePkg = n; this.rechargeCopied = false; },
    // 展开 / 收起「收款 / 客服二维码」（默认收起，仅显示客服微信号；点击展开）
    toggleRechargeQr() { this.rechargeQrOpen = !this.rechargeQrOpen; },
    copyRechargeAccount() {
      const acc = this.user || '';
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(acc).then(() => { this.rechargeCopied = true; });
          return;
        }
      } catch (e) { /* 忽略，走降级 */ }
      try {
        const ta = document.createElement('textarea');
        ta.value = acc; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
        this.rechargeCopied = true;
      } catch (e) { this.rechargeCopied = false; }
    },
    loadPetLedger() {
      if (!this.user) return;
      this.api(`/api/pet/ledger?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.petLedger = d || []; })
        .catch(() => { this.petLedger = []; });
    },
    loadPetRules() {
      if (this.petRules.length) return;
      this.api('/api/pet/rules')
        .then(d => { this.petRules = (d && d.items) || []; })
        .catch(() => {});
    },
    petFeed() {
      if (this.petBusy) return;
      this.petBusy = true;
      this.petMsg = '';
      this.api('/api/pet/feed', { method: 'POST', body: JSON.stringify({ user_id: this.user }) })
        .then(d => {
          const leveled = !!d.leveled;
          this.petProfile = d;
          if (leveled) {
            this.petLeveledUp = true;
            this.petMsg = '🎉 升级啦！宠物长成新的样子了！';
            this.showToast(`🎉 宠物升级到 Lv.${d.level}！`);
          } else {
            this.petMsg = '🍎 嗷呜～真好吃！经验 +5';
          }
          this.loadPetLedger();
        })
        .catch(e => { this.petMsg = e.message; })
        .finally(() => { this.petBusy = false; });
    },
    petPat() {
      if (this.petBusy) return;
      this.petBusy = true;
      this.petMsg = '';
      this.api('/api/pet/pat', { method: 'POST', body: JSON.stringify({ user_id: this.user }) })
        .then(d => {
          this.petProfile = d;
          this.petMsg = d.leveled ? '🎉 升级啦！宠物长成新的样子了！' : '🤗 好舒服～经验 +1';
          if (d.leveled) { this.petLeveledUp = true; this.showToast(`🎉 宠物升级到 Lv.${d.level}！`); }
        })
        .catch(e => { this.petMsg = e.message; })
        .finally(() => { this.petBusy = false; });
    },
    petEmoji(level) {
      if (level >= 9) return '🦚';
      if (level >= 7) return '🦜';
      if (level >= 5) return '🐥';
      if (level >= 3) return '🐤';
      return '🥚';
    },
    petName(level) {
      if (level >= 9) return '🦚 凤凰奇奇';
      if (level >= 7) return '🦜 鹦鹉小七';
      if (level >= 5) return '🐥 大黄鸭';
      if (level >= 3) return '🐤 小黄鸡';
      return '🥚 宠物蛋';
    },
    petDesc(level) {
      if (level >= 9) return '传说中的凤凰，闪闪发光，同学都会羡慕你！';
      if (level >= 7) return '学会说人话了，会跟着你朗读课文！';
      if (level >= 5) return '长出翅膀了，越来越精神！';
      if (level >= 3) return '破壳啦！一只毛茸茸的小家伙';
      return '还是一颗蛋，努力赚金币喂它，很快就会孵出来！';
    },
    petExpPct(p) {
      if (!p || !p.exp_next) return 100;
      return Math.min(100, Math.round(p.exp / p.exp_next * 100));
    },

    /* ─────────── 成长树（P2-2 创意 7） ─────────── */
    loadTree() {
      if (!this.user) return;
      this.api(`/api/tree?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.treeData = d; })
        .catch(() => { this.treeData = null; });
    },
    treeStageName(idx) {
      const s = this.treeStages[idx];
      return s ? s.name : '';
    },

    /* ─────────── 成就徽章（P2-3 创意 8） ─────────── */
    loadBadges(announce) {
      if (!this.user) return;
      this.api(`/api/badges?user_id=${encodeURIComponent(this.user)}`)
        .then(d => {
          const prevNew = this.badgeNew;
          this.badgeData = d;
          if (d.newly && d.newly.length) {
            this.badgeNew = (d.items || []).filter(b => (d.newly || []).includes(b.code));
            if (announce && this.badgeNew.length) {
              this.showToast(`🎉 获得新徽章：${this.badgeNew.map(b => b.name).join('、')}！`);
            }
          } else if (prevNew.length) {
            this.badgeNew = prevNew;
          }
        })
        .catch(() => { this.badgeData = null; });
    },

    /* ─────────── 知识卡图鉴（P2-4 创意 13） ─────────── */
    loadCards() {
      if (!this.user) return;
      this.api(`/api/cards?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.cardData = d; })
        .catch(() => { this.cardData = null; });
    },
    cardDraw() {
      if (this.cardDrawing || !this.user) return;
      this.cardDrawing = true;
      this.drawCards = [];
      this.api(`/api/cards/draw?user_id=${encodeURIComponent(this.user)}`)
        .then(d => {
          this.drawAllCollected = !!d.all_collected;
          this.drawCards = d.cards || [];
          if (this.drawCards.length) this.showToast('🎴 抽到 3 张知识卡！');
        })
        .catch(e => this.showToast(e.message))
        .finally(() => { this.cardDrawing = false; });
    },

    /* ─────────── 听写磨耳朵（P2-5 创意 25） ─────────── */
    dictSwitchMode(m) {
      if (this.dictSession.active) return;
      this.dictMode = m;
    },
    dictStart() {
      const isWord = this.dictMode === 'word';
      const url = isWord
        ? `/api/dictation/words?user_id=${encodeURIComponent(this.user)}&count=10`
        : `/api/dictation/texts?user_id=${encodeURIComponent(this.user)}&count=5&grade=${this.grade}`;
      this.api(url).then(d => {
        const items = (d.items || []).map(it => isWord
          ? { answer: it.word, meaning: `${it.pos || ''} ${it.meaning || ''}`.trim(), extra: it.word }
          : { answer: it.sentence, meaning: it.title, extra: it.full });
        if (!items.length) { this.showToast('题库是空的，先学一点再来听写吧'); return; }
        this.dictSession = { active: true, done: false, items, i: 0, current: items[0], answer: '', revealed: false, lastOk: false, correct: 0, rewarded: false };
        this.$nextTick(() => setTimeout(() => this.dictSpeak(items[0]), 350));
      }).catch(e => this.showToast(e.message));
    },
    speakText(text, lang, rate) {
      if (!text) return;
      try {
        if (!('speechSynthesis' in window)) return;
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.lang = lang;
        u.rate = rate;
        u.pitch = 1;
        window.speechSynthesis.speak(u);
      } catch (e) { /* 静默失败，不阻断操作 */ }
    },
    wordSpeak() {
      const ws = this.wordSession;
      if (!ws.words || !ws.words.length) return;
      const w = ws.words[ws.i];
      if (w) this.speakText(w.word, 'en-US', 0.8);
    },
    textSpeak() {
      const ts = this.textSession;
      if (!ts.texts || !ts.texts.length) return;
      const t = ts.texts[ts.i];
      if (t) this.speakText(t.title + '，' + (t.author || '') + '，' + t.content, 'zh-CN', 0.85);
    },
    dictSpeak(item) {
      if (!item) return;
      try {
        if (!('speechSynthesis' in window)) { this.showToast('当前浏览器不支持语音朗读'); return; }
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(item.extra || item.answer);
        u.lang = this.dictMode === 'word' ? 'en-US' : 'zh-CN';
        u.rate = this.dictMode === 'word' ? 0.8 : 0.9;
        u.pitch = 1;
        window.speechSynthesis.speak(u);
      } catch (e) { this.showToast('语音播放失败，请检查浏览器设置'); }
    },
    dictCheck() {
      const s = this.dictSession;
      if (!s.current) return;
      const ans = (s.answer || '').trim().toLowerCase().replace(/[，。！？；、\s]/g, '');
      const correct = (s.current.answer || '').trim().toLowerCase().replace(/[，。！？；、\s]/g, '');
      s.lastOk = ans === correct;
      if (s.lastOk) s.correct += 1;
      s.revealed = true;
    },
    dictReplay() { this.dictSpeak(this.dictSession.current); },
    dictNext() {
      const s = this.dictSession;
      if (s.i >= s.items.length - 1) {
        s.active = false;
        s.done = true;
        if (s.correct === s.items.length && !s.rewarded) {
          s.rewarded = true;
          this.api('/api/dictation/reward', { method: 'POST', body: JSON.stringify({ user_id: this.user, correct: s.correct, total: s.items.length }) })
            .then(d => { if (d.granted) { this.loadPet(); this.showToast(`🪙 听写全对 +${d.granted} 金币！`); } })
            .catch(() => {});
        }
        return;
      }
      s.i += 1;
      s.current = s.items[s.i];
      s.answer = '';
      s.revealed = false;
      this.$nextTick(() => setTimeout(() => this.dictSpeak(s.current), 250));
    },

    /* ─────────── 番茄专注钟（P2-6 创意 22） ─────────── */
    focusSet(m) { this.focusTimer.total = m; this.focusTimer.left = m * 60; },
    focusStart() {
      this.focusDone = false;
      this.focusMsg = '';
      this.focusTimer.running = true;
      this.focusTimer.paused = false;
      this._startFocusTicker();
      this.showToast(`⏰ 开始专注 ${this.focusTimer.total} 分钟，加油！`);
    },
    _startFocusTicker() {
      if (this._focusTicker) clearInterval(this._focusTicker);
      this._focusTicker = setInterval(() => {
        if (!this.focusTimer.running) return;
        this.focusTimer.left -= 1;
        if (this.focusTimer.left <= 0) {
          this.focusTimer.left = 0;
          this.focusFinish();
        }
      }, 1000);
    },
    focusPause() { this.focusTimer.running = false; this.focusTimer.paused = true; this.focusMsg = '⏸ 已暂停，休息一下眼睛吧'; },
    focusResume() { this.focusTimer.running = true; this.focusTimer.paused = false; this.focusMsg = ''; },
    focusReset() {
      if (this._focusTicker) clearInterval(this._focusTicker);
      this.focusTimer.running = false;
      this.focusTimer.paused = false;
      this.focusDone = false;
      this.focusMsg = '';
      this.focusTimer.left = this.focusTimer.total * 60;
    },
    focusFinish() {
      if (this._focusTicker) clearInterval(this._focusTicker);
      this.focusTimer.running = false;
      this.focusDone = true;
      this.focusMsg = '🎉 专注完成！';
      this.api('/api/focus/complete', { method: 'POST', body: JSON.stringify({ user_id: this.user, minutes: this.focusTimer.total }) })
        .then(d => {
          if (d.granted) {
            this.focusMsg = `🎉 专注完成！金币 +${d.granted}`;
            this.loadPet();
          } else if (d.limited) {
            this.focusMsg = '🎉 专注完成！（今天专注次数已满，金币不再增加啦）';
          }
          this.loadFocus();
        })
        .catch(e => this.showToast(e.message));
    },
    loadFocus() {
      if (!this.user) return;
      this.api(`/api/focus/today?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.focusToday = d; })
        .catch(() => {});
      this.api(`/api/focus/stats?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.focusStats = d; })
        .catch(() => {});
    },

    /* ─────────── AI 趣味出题（AI-2） ─────────── */
    aiQuizGenerate() {
      if (!this.user) return this.showToast('请先登录');
      const q = this.aiQuiz;
      q.loading = true; q.quiz = null; q.graded = null; q.score = null; q.rewardGranted = 0; q.themeName = '';
      this.api('/api/ai-quiz/generate', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, subject: q.subject, grade: q.grade, theme: q.theme, count: 5 }),
      }).then(d => {
        q.loading = false;
        if (!d.questions || !d.questions.length) { this.showToast(d.detail || 'AI 生成失败了，稍后再试试'); return; }
        q.themeName = d.theme;
        q.quiz = d.questions;
        q.answers = {}; q.inputs = {};
      }).catch(e => { q.loading = false; this.showToast(e.message); });
    },
    aiQuizPick(i, letter) { this.aiQuiz.answers[i] = letter; },
    aiQuizUserAnswer(i) {
      const q = this.aiQuiz.quiz[i];
      return (q.options && q.options.length) ? (this.aiQuiz.answers[i] || '未作答') : (this.aiQuiz.inputs[i] || '未作答');
    },
    aiQuizGrade() {
      const q = this.aiQuiz;
      if (!q.quiz) return;
      let correct = 0;
      const detail = [];
      q.quiz.forEach((item, i) => {
        const userAns = (item.options && item.options.length) ? (q.answers[i] || '') : (q.inputs[i] || '');
        const ok = String(userAns).trim().toLowerCase() === String(item.answer).trim().toLowerCase();
        if (ok) correct++;
        detail.push(ok);
        if (!ok) {
          // 答错 → 回写错题本
          this.api('/api/ai-quiz/wrong', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, question: item.question, user_answer: userAns, correct_answer: item.answer, explanation: item.explanation }),
          }).catch(() => {});
        }
      });
      q.graded = true;
      q.score = { correct, total: q.quiz.length, detail };
      this.aiQuizPlayed++;
      localStorage.setItem('zx_aiquiz_played', String(this.aiQuizPlayed));
      if (correct === q.quiz.length) {
        this.api('/api/ai-quiz/reward', {
          method: 'POST',
          body: JSON.stringify({ user_id: this.user, correct, total: q.quiz.length }),
        }).then(d => {
          q.rewardGranted = (d && d.granted) || 0;
          if (q.rewardGranted) { this.loadPet(); this.showToast(`🎉 全对！金币 +${q.rewardGranted}`); }
        }).catch(() => {});
      } else {
        this.loadWrongItems();
      }
    },
    aiQuizReset() {
      const q = this.aiQuiz;
      q.quiz = null; q.graded = null; q.score = null; q.answers = {}; q.inputs = {};
      q.rewardGranted = 0; q.themeName = ''; q.subject = this.subject; q.grade = this.grade;
    },

    /* ─────────── AI 学习助手（AI-5） ─────────── */
    loadAssistantProfile() {
      if (!this.user) return;
      this.api(`/api/assistant/profile?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.assistantProfile = d; })
        .catch(() => {});
    },
    assistantAsk(q) {
      this.assistantDraft = q;
      this.assistantSend();
    },
    assistantSend() {
      const text = (this.assistantDraft || '').trim();
      if (!text || this.assistantLoading || !this.user) return;
      this.assistantMsgs.push({ role: 'me', text });
      this.assistantDraft = '';
      this.assistantLoading = true;
      this.$nextTick(() => this._scrollChat());
      const history = this.assistantMsgs.slice(-8, -1).map(m => ({ role: m.role === 'me' ? 'user' : 'assistant', content: m.text }));
      this.api('/api/assistant/chat', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, message: text, history }),
      }).then(d => {
        this.assistantMsgs.push({ role: 'ai', text: d.text || '（AI 老师没说出话来，再问一次吧）' });
        this.assistantLoading = false;
        this.$nextTick(() => this._scrollChat());
      }).catch(e => {
        this.assistantMsgs.push({ role: 'ai', text: e.message || '网络出错了，稍后再试试' });
        this.assistantLoading = false;
        this.$nextTick(() => this._scrollChat());
      });
    },
    _scrollChat() {
      const box = this.$refs.chatBox;
      if (box) box.scrollTop = box.scrollHeight;
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
      this.loadTomorrowQueue();
      this.loadPet();
      this.loadDiamonds();
      this.loadTree();
      this.loadBadges(false);
      this.loadCards();
      this.loadFocus();
      this.loadTaskConfirms();
      this.loadDecidedAppeals();
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
    claimDailyTask(subject, taskId) {
      const body = { user_id: this.user };
      if (taskId) body.task_id = taskId;
      else body.subject = subject;
      this.api('/api/tasks/daily/claim', { method: 'POST', body: JSON.stringify(body) })
        .then(d => this._applyDailyTasks(d, true))
        .catch(e => this.showToast(e.message));
    },
    childSubmitTask(taskId) {
      this.api('/api/tasks/daily/child_submit', { method: 'POST', body: JSON.stringify({ user_id: this.user, task_id: taskId }) })
        .then(d => { this._applyDailyTasks(d, false); this.showToast('已提交，等家长确认 ✋'); })
        .catch(e => this.showToast(e.message));
    },
    makeupCompleteTask(taskId) {
      if (this.makeupCards <= 0) return this.showToast('没有可用的补签卡');
      if (!confirm('使用 1 张补签卡完成该任务？提交后需家长确认才生效')) return;
      // 孩子发起：立即扣卡并进入「待家长确认」，任务暂不完成
      this.api('/api/tasks/daily/makeup_complete', { method: 'POST', body: JSON.stringify({ user_id: this.user, task_id: taskId }) })
        .then(d => { this._applyDailyTasks(d, true); this.showToast('补签卡已使用，待家长确认后生效 ⏳'); })
        .catch(e => this.showToast(e.message));
    },
    /* ─────────── 补签卡待确认（孩子发起 → 家长确认/拒绝）───────────
       调用关系：
         makeupCompleteTask 孩子用补签卡发起 → 服务端扣卡并把任务置为 makeup_pending（待家长确认）
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
    _applyDailyTasks(d, celebrate) {
      const prev = this.dailyTaskStats ? this.dailyTaskStats.done_count : 0;
      this.dailyTasks = (d && d.tasks) || [];
      this.dailyTaskStats = { done_count: (d && d.mandatory_done) || 0, total: (d && d.mandatory_total) || 3, streak_days: (d && d.streak_days) || 0 };
      this.makeupCards = (d && d.makeup_cards) || 0;
      if (celebrate && this.dailyTaskStats.total && this.dailyTaskStats.done_count >= this.dailyTaskStats.total && prev < this.dailyTaskStats.total) {
        this.showToast('🎉 强制任务全完成，今天全勤！');
        this.remindMoodCheckin();
      }
      // 可选任务全完成 → 提示获得补签卡
      if (celebrate && d && d.optional_done === d.optional_total && d.optional_total > 0) {
        this.showToast('🎫 可选任务全完成，获得补签卡×1！');
      }
      if (celebrate && this.dailyTaskStats.done_count > prev) this.loadPet();
    },
    _pendingWrong(d) {
      const w = o => o ? (o.exam_pending || 0) + (o.study_pending || 0) : 0;
      const eng = d.subjects['英语'] || {}, chi = d.subjects['语文'] || {}, mth = d.subjects['数学'] || {};
      return w(eng.wrong) + w(chi.wrong) + w(mth.wrong);
    },
    // 复习队列：按艾宾浩斯遗忘曲线自动排程到期复习（单词/古诗文），
    // 拉取后拆分「今天到期 / 明天 / 后天 / 3 天后」四个时间节点供首页时间轴展示
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
    loadTomorrowQueue() {
      this.api(`/api/study/tomorrow-queue?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.tomorrowQueue = d || { count: 0, items: [] }; })
        .catch(() => { this.tomorrowQueue = { count: 0, items: [] }; });
    },
    startTask(t) {
      if (t.done) { this.showToast('该任务今天已完成，明天再来吧'); return; }
      // 背诵类任务先跳转到「背诵中心」对应子页，再启动背诵/听写会话（点击任务即跳转对应界面）
      if (t.key === 'word_new') { this.goTab('recite'); this.reciteSub = 'words'; this.startWordSession('new'); }
      else if (t.key === 'word_review') { this.goTab('recite'); this.reciteSub = 'words'; this.startWordSession('review'); }
      else if (t.key === 'text_new') { this.goTab('recite'); this.reciteSub = 'classical'; this.startTextSession('new'); }
      else if (t.key === 'text_review') { this.goTab('recite'); this.reciteSub = 'classical'; this.startTextSession('review'); }
      else if (t.key === 'grammar') { this.goTab('practice'); this.practiceSub = 'grammar'; this.loadGrammarPoints(); }
      else if (t.key === 'wrong') this.goTab('wrong');
      else { this.goTab('practice'); this.practiceSub = 'generate'; }
    },

    /* 首页每日任务卡片「去做 →」：按 task_code 跳转到对应界面 */
    gotoTaskCode(t) {
      const code = (t && t.task_code) || '';
      // code → [一级tab, 二级sub]；无映射的（如讲题/自定义）提示手动完成
      const map = {
        math_exam: ['practice', 'generate'], chi_exam: ['practice', 'generate'], eng_exam: ['practice', 'generate'],
        chi_classical: ['recite', 'classical'], eng_vocab: ['recite', 'words'],
        math_fix: ['wrong'], chi_dictation: ['dict'], eng_dictation: ['dict'],
        chi_read: ['reading'], math_challenge: ['practice'],
        math_sync: ['sync'], chi_sync: ['sync'], eng_sync: ['sync'],
      };
      const m = map[code];
      if (!m) { this.showToast('完成本题后点「我完成了 ✓」即可'); return; }
      const [tab, sub] = m;
      this.goTab(tab);
      if (sub) {
        if (tab === 'recite') this.reciteSub = sub;
        else if (tab === 'practice') this.practiceSub = sub;
        else if (tab === 'dict') this.dictSub = sub;
      }
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
        { code: 'sentence_translation', name: '句子翻译' },
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
      // 难度与题型由后端按最近成绩自动决定，前端不再提交
      const body = { subject: this.subject, grade: this.grade, user_id: this.user };
      if (this.subject === '数学') {
        body.math_count = this.genCount;
      } else {
        body.english_count = this.genCount;
      }
      this.generating = true;
      // 必须携带登录 token：/api/exam/generate 挂在 require_self 鉴权依赖下，
      // 裸 fetch 不带头会直接返回 401「未登录」（这是点击生成题目提示没登录的根因）。
      const headers = { 'Content-Type': 'application/json' };
      try {
        const tk = localStorage.getItem('zx_token');
        if (tk) headers['Authorization'] = 'Bearer ' + tk;
        const pp = sessionStorage.getItem('zx_parent_pwd');
        if (pp) headers['X-Parent-Pwd'] = pp;
      } catch (e) {}
      fetch('/api/exam/generate', { method: 'POST', headers, body: JSON.stringify(body) })
        .then(async r => {
          // 401：登录态失效，与 api() 一致清会话+跳登录页，不抛错避免重复弹 toast
          if (r.status === 401) {
            const hadSession = !!localStorage.getItem('zx_user');
            try { localStorage.removeItem('zx_user'); localStorage.removeItem('zx_token'); sessionStorage.removeItem('zx_parent_pwd'); } catch (e) {}
            if (hadSession) location.href = '/';
            return;
          }
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
          if (id === undefined) return; // 401 分支已处理（return undefined），跳过后续
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
        grammar_choice: '语法选择', situational: '情景交际',
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
      if (!words.length) { this.showToast(mode === 'new' ? '词库已全部学完，太棒了！' : '今日没有到期复习的单词'); return; }
      this.wordSession = { active: true, done: false, phase: 'card', mode, words, i: 0, revealed: false, okCount: 0, results: [], comprehensiveIds: null };
      if (mode === 'review') {
        // 复习模式：跳过「逐词卡片(词面)+逐词测一测」，直接进合并检测（直接出题，不展示原文/词面）
        this.wordSession.phase = 'dictate';
        this.$nextTick(() => this.startWordDictate());
        return;
      }
      this.$nextTick(() => setTimeout(() => this.wordSpeak(), 350));
    },
    wordNext(ok) {
      const ws = this.wordSession;
      const w = ws.words[ws.i];
      ws.results.push({ word_id: w.word_id, correct: ok });
      if (ok) ws.okCount++;
      if (ws.i < ws.words.length - 1) { ws.i++; ws.revealed = false; this.$nextTick(() => setTimeout(() => this.wordSpeak(), 200)); }
      else { ws.phase = 'dictate'; this.startWordDictate(); }
    },
    /* 检测环节：翻完卡片后混合题检测（默写+理解型），任一题错整轮重学 */
    _quizItemsFromSession(items) {
      // 后端 session-quiz 题目 → 通用 quiz 项；选择题答案转字母供本地判分
      // error_id>0 表示这是混入的「错题本」题目，提交时需走专项连击回写
      return (items || []).map(q => {
        if ((q.options || []).length) {
          const ansIdx = q.options.indexOf(q.answer);
          return {
            qid: q.word_id || 0, text_id: q.text_id || 0, error_id: q.error_id || 0,
            question: q.question, sub: '🌟 ' + (q.context || ''),
            options: q.options, answer: 'ABCDEFGH'[Math.max(ansIdx, 0)],
            _answerText: q.answer, explanation: '',
          };
        }
        return {
          qid: q.word_id || 0, text_id: q.text_id || 0, error_id: q.error_id || 0,
          question: q.question, sub: q.context || '',
          placeholder: q.word_id ? '请输入英文单词' : '默写内容',
          options: [], answer: q.answer, explanation: '',
        };
      });
    },
    /* 背诵检测混入的错题本题目：按 error_id 整组提交，batch=true 表示「整组=1次尝试」，
       后端连续 3 次全对（每次4题）即移除错题本，任一错则连击清零重计。 */
    _submitErrorBatch(errorItems, subject) {
      if (!errorItems || !errorItems.length) return Promise.resolve();
      const results = errorItems.map(it => ({
        kind: 'study', record_id: it.error_id,
        correct: !!it.correct, qid: it.qid || 0,
        question: it.question || '', user_answer: it.userAnswer || '',
        correct_answer: it._answerText || it.answer || '',
        subject: subject || '', batch: true,
      }));
      return this.api('/api/study/practice-submit', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, results }),
      }).then(() => { this.loadWrongItems(); }).catch(() => {});
    },
    startWordDictate() {
      const ws = this.wordSession;
      this.dtOk = {};
      const ids = ws.words.map(w => w.word_id).join(',');
      this.api(`/api/vocab/session-quiz?user_id=${encodeURIComponent(this.user)}&word_ids=${ids}&mode=${ws.mode}&grade=${this.grade}&mix_errors=1`)
        .then(r => {
          const items = this._quizItemsFromSession(r.items);
          if (!items.length) { ws.active = false; this.showToast('检测题生成失败，请重试'); return; }
          this.startQuiz({
            title: '✍️ 背诵检测 · ' + (ws.mode === 'new' ? '新词' : '复习'),
            items, source: { mode: 'dictate', kind: 'word', mode2: ws.mode },
          });
        }).catch(e => { ws.active = false; this.showToast(e.message); });
    },
    /* 逐词「测一测」：学完一个词立即做 1 道客观题（默写填空），
       用客观提取替代「学会了/没记住」的二进制自报，提升记忆效率。
       每词只出 1 题（后端 per_word=1，强制默写填空题，任何复习阶段均直接检验拼写记忆）。 */
    wordTest(idx) {
      const ws = this.wordSession;
      const i = (idx != null) ? idx : ws.i;
      const w = ws.words[i];
      if (!w) return;
      this.dtOk = this.dtOk || {};
      this.api(`/api/vocab/session-quiz?user_id=${encodeURIComponent(this.user)}&word_ids=${w.word_id}&mode=${ws.mode}&grade=${this.grade}&mix_errors=0&per_word=1`)
        .then(r => {
          const items = this._quizItemsFromSession(r.items);
          if (!items.length) { this.showToast('练习题生成失败，请重试'); return; }
          this.startQuiz({
            title: '✍️ 测一测 · ' + (ws.mode === 'new' ? '新词' : '复习') + `（第 ${i + 1}/${ws.words.length} 个）`,
            items, source: { mode: 'dictate', kind: 'word', mode2: ws.mode, perItem: true, index: i },
          });
        }).catch(e => this.showToast(e.message));
    },
    startTextSession(mode) {
      const raw = mode === 'new' ? (this.classicalToday.new_texts || []) : (this.classicalToday.review_texts || []);
      if (!raw.length) { this.showToast(mode === 'new' ? '篇目库已全部背完，太棒了！' : '今日没有到期复习的篇目'); return; }
      this.textSession = {
        active: true, done: false, phase: 'card', mode,
        texts: raw.map(x => ({ ...x, dynasty: x.dynasty || '' })),
        i: 0, okCount: 0, failCount: 0, results: [], comprehensiveIds: null,
      };
      if (mode === 'review') {
        // 复习模式：跳过「逐篇卡片(原文)+逐篇测一测」，直接进合并检测（每首3题，N首共3N题，不展示原文）
        this.textSession.phase = 'dictate';
        this.$nextTick(() => this.startTextDictate());
        return;
      }
      this.$nextTick(() => setTimeout(() => this.textSpeak(), 350));
    },
    textNext(ok) {
      const ts = this.textSession;
      const t = ts.texts[ts.i];
      ts.results.push({ text_id: t.text_id, correct: ok });
      if (ok) ts.okCount++; else ts.failCount++;
      if (ts.i < ts.texts.length - 1) { ts.i++; this.$nextTick(() => setTimeout(() => this.textSpeak(), 200)); }
      else { ts.phase = 'dictate'; this.startTextDictate(); }
    },
    /* 检测环节：翻完卡片后混合题检测（默写+理解型），任一题错整轮重学 */
    startTextDictate() {
      const ts = this.textSession;
      this.dtOk = {};
      const ids = ts.texts.map(t => t.text_id).join(',');
      this.api(`/api/classical/session-quiz?user_id=${encodeURIComponent(this.user)}&text_ids=${ids}&mode=${ts.mode}&mix_errors=1`)
        .then(r => {
          const items = this._quizItemsFromSession(r.items);
          if (!items.length) { ts.active = false; this.showToast('检测题生成失败，请重试'); return; }
          this.startQuiz({
            title: '✍️ 背诵检测 · ' + (ts.mode === 'new' ? '新篇' : '复习'),
            items, source: { mode: 'dictate', kind: 'text', mode2: ts.mode },
          });
        }).catch(e => { ts.active = false; this.showToast(e.message); });
    },
    /* 逐篇「测一测」：学完一篇立即做客观题（填空/理解），用客观提取替代「背熟了」自报。 */
    textTest(idx) {
      const ts = this.textSession;
      const i = (idx != null) ? idx : ts.i;
      const t = ts.texts[i];
      if (!t) return;
      this.dtOk = this.dtOk || {};
      this.api(`/api/classical/session-quiz?user_id=${encodeURIComponent(this.user)}&text_ids=${t.text_id}&mode=${ts.mode}&mix_errors=1`)
        .then(r => {
          const items = this._quizItemsFromSession(r.items);
          if (!items.length) { this.showToast('练习题生成失败，请重试'); return; }
          this.startQuiz({
            title: '✍️ 测一测 · ' + (ts.mode === 'new' ? '新篇' : '复习') + `（《${t.title}》）`,
            items, source: { mode: 'dictate', kind: 'text', mode2: ts.mode, perItem: true, index: i },
          });
        }).catch(e => this.showToast(e.message));
    },
    /* 综合测试：本轮全部学完后，对所有条目做一次统一测试；出错只重测出错项，直至全对 */
    startWordComprehensive() {
      const ws = this.wordSession;
      const reIds = (ws.comprehensiveIds && ws.comprehensiveIds.length) ? ws.comprehensiveIds : null;
      const ids = reIds ? reIds.join(',') : ws.words.map(w => w.word_id).join(',');
      this.api(`/api/vocab/session-quiz?user_id=${encodeURIComponent(this.user)}&word_ids=${ids}&mode=${ws.mode}&grade=${this.grade}&mix_errors=0&per_word=1`)
        .then(r => {
          const items = this._quizItemsFromSession(r.items);
          if (!items.length) { ws.done = true; this.refreshAll(); this.showToast('🎉 本轮全部背对，背诵任务完成！'); return; }
          this.startQuiz({
            title: (reIds ? '🔁 综合补测 · 仅错题' : '📝 综合测试 · 本轮全部') + (ws.mode === 'new' ? '（新词）' : '（复习）'),
            items, source: { mode: 'dictate', kind: 'word', mode2: ws.mode, comprehensive: true },
          });
        }).catch(e => this.showToast(e.message));
    },
    startTextComprehensive() {
      const ts = this.textSession;
      const reIds = (ts.comprehensiveIds && ts.comprehensiveIds.length) ? ts.comprehensiveIds : null;
      const ids = reIds ? reIds.join(',') : ts.texts.map(t => t.text_id).join(',');
      this.api(`/api/classical/session-quiz?user_id=${encodeURIComponent(this.user)}&text_ids=${ids}&mode=${ts.mode}&mix_errors=0`)
        .then(r => {
          const items = this._quizItemsFromSession(r.items);
          if (!items.length) { ts.done = true; this.refreshAll(); this.showToast('🎉 本轮全部背对，背诵任务完成！'); return; }
          this.startQuiz({
            title: (reIds ? '🔁 综合补测 · 仅错题' : '📝 综合测试 · 本轮全部') + (ts.mode === 'new' ? '（新篇）' : '（复习）'),
            items, source: { mode: 'dictate', kind: 'text', mode2: ts.mode, comprehensive: true },
          });
        }).catch(e => this.showToast(e.message));
    },
    /* 综合测试结束：统计本轮正确情况，全对→任务完成；有错→仅重测出错项（循环） */
    _finishComprehensive() {
      const src = this.quiz.source;
      const items = this.quiz.items;
      const normal = items.filter(it => !(it.error_id && it.error_id > 0));
      if (src.kind === 'text') {
        const ts = this.textSession;
        const wrong = [];
        ts.texts.forEach(t => {
          if (normal.some(it => (it.text_id || src.text_id) === t.text_id && !it.correct)) wrong.push(t.text_id);
        });
        if (!wrong.length) {
          // 综合测试（含错题重测）全部通过 → 才标记本轮全部篇目为已背诵
          const passedIds = ts.texts.map(t => t.text_id);
          this.api('/api/classical/dictate', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, mode: src.mode2, passed_ids: passedIds }),
          }).then(() => {
            ts.done = true; this.refreshAll();
            this.showToast(`🎉 本轮 ${ts.texts.length} 篇全部背对，已掌握！`);
            this.submitReciteCompletion(src);
          }).catch(e => this.showToast(e.message));
        } else { ts.comprehensiveIds = wrong; this.startTextComprehensive(); }
      } else {
        const ws = this.wordSession;
        const wrong = [];
        ws.words.forEach(w => {
          if (normal.some(it => it.qid === w.word_id && !it.correct)) wrong.push(w.word_id);
        });
        if (!wrong.length) {
          // 综合测试（含错题重测）全部通过 → 才标记本轮全部单词为已掌握
          const results = ws.words.map(w => ({ word_id: w.word_id, answer: w.word }));
          this.api('/api/vocab/dictate', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, mode: src.mode2, results }),
          }).then(r => {
            const saved = (r && r.saved) || [];
            ws.done = true; this.refreshAll();
            this.showToast(`🎉 本轮 ${ws.words.length} 个单词全部背对，已掌握 ${saved.length} 个！`);
            this.submitReciteCompletion(src);
          }).catch(e => this.showToast(e.message));
        } else { ws.comprehensiveIds = wrong; this.startWordComprehensive(); }
      }
    },
    /* 孩子完成一轮背诵 → 提交「完成确认」并弹出提示：发截图给家长确认 */
    submitReciteCompletion(src) {
      const isText = src.kind === 'text';
      const sess = isText ? this.textSession : this.wordSession;
      const modeLabel = sess.mode === 'new' ? '新学' : '复习';
      const n = (isText ? sess.texts : sess.words).length;
      const summary = isText ? `${modeLabel}古诗文 ${n} 篇` : `${modeLabel}单词 ${n} 个`;
      this.createTaskConfirm({
        task_type: isText ? 'recite_text' : 'recite_word',
        title: '背诵任务完成',
        summary,
      });
      // 弹窗提示：把完成截图通过微信等方式发给家长确认
      this.taskSubmitTip = { show: true };
    },
    loadTaskConfirms() {
      if (!this.user) return;
      this.api(`/api/task-confirm/list?user_id=${encodeURIComponent(this.user)}`)
        .then(r => {
          this.taskConfirms = (r && r.items) || [];
          this.taskConfirmsTotal = (r && typeof r.total === 'number') ? r.total : this.taskConfirms.length;
        })
        .catch(() => { this.taskConfirms = []; this.taskConfirmsTotal = 0; });
    },
    createTaskConfirm(payload) {
      if (!this.user) return;
      this.api('/api/task-confirm/create', {
        method: 'POST',
        body: JSON.stringify(Object.assign({ user_id: this.user }, payload)),
      }).then(() => { this.loadTaskConfirms(); }).catch(() => {});
    },
    openReject(id) {
      this.taskReject = { id, reason: '' };
    },
    cancelReject() {
      this.taskReject = { id: null, reason: '' };
    },
    /* 家长确认/拒绝（家长模式开启时调用，api 自动携带 X-Parent-Pwd） */
    resolveTaskConfirm(id, action) {
      if (!this.user) return;
      const reason = (this.taskReject && this.taskReject.id === id) ? this.taskReject.reason : '';
      this.api('/api/task-confirm/resolve', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, id, action, reject_reason: reason }),
      }).then(() => {
        if (action === 'reject') this.cancelReject();
        this.loadTaskConfirms();
        this.showToast(action === 'approve' ? '已通过，太棒了！✅' : '已拒绝并记录理由');
      }).catch(e => this.showToast(e.message || '操作失败'));
    },
    openTextDetail(t) {
      this.textDetail = { show: true, id: t.id, title: t.title, author: t.author || '', dynasty: t.dynasty || '', grade: t.grade, text_type: t.text_type || 'poem', content: t.content };
    },
    startTextQuiz(t) {
      this.textDetail.show = false;
      this.api(`/api/classical/quiz?grade=${this.grade}&text_id=${t.id}&count=3`)
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
            question: w.question, user_answer: w.user_answer || '', correct_answer: w.answer, explanation: '',
            error_count: w.practice_count || 1, wrong_at: w.wrong_at || '',
            mastered: !!w.is_mastered, cause: w.cause || '',
            is_unanswered: !!w.is_unanswered,
            subject: w.subject || '', source: '试卷错题',
          }));
          const study = (studyList || []).map(e => ({
            key: 'study-' + e.id, kind: 'study', id: e.id, record_id: e.id, question_id: 0,
            question: e.question, user_answer: e.user_answer, correct_answer: e.correct_answer,
            explanation: e.explanation || '', error_count: e.error_count || 1, wrong_at: e.wrong_at || '',
            mastered: !!e.is_mastered, cause: e.cause || '',
            is_unanswered: false,
            subject: (e.source_type === 'grammar' || e.source_type === 'vocab') ? '英语' : '语文', source: e.module_name || '学习错题',
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
      if (!w.cause) { this.showToast('请先选择错因，才能使用讲解功能'); return; }
      if (w.explaining) return; // 防重复点击
      w.explaining = true; w.aiText = ''; w.aiError = ''; w.aiDegraded = false;
      this.explainFetch('/api/ai/explain', { user_id: this.user, question_id: w.question_id })
        .then(d => {
          w.explaining = false;
          w.aiText = d.text || '';
          w.aiDegraded = !!d.degraded;
          if (d.diamond_cost) this.loadDiamonds();
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
          if (d.diamond_cost) this.loadDiamonds();
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
    _displayTaskTitle(ts) {
      if (!ts) return '';
      // 替换标题中最后一个数字为 N（避免误改"60秒"等固定值）
      const title = ts.title || '';
      if (!title || ts.target === ts.default) return title;
      const parts = title.split(/(\d+)/);
      for (let i = parts.length - 2; i >= 0; i--) {
        if (/^\d+$/.test(parts[i])) { parts[i] = 'N'; break; }
      }
      return parts.join('');
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
      this.loadPendingMakeup();
      this.loadTeachPanel();
    },
    /* ─────────── 孩子申诉（AI 判题复核 + 家长二次确认）─────────── */
    loadAppeals() {
      this.api(`/api/appeal/list?user_id=${encodeURIComponent(this.user)}&status=pending`)
        .then(d => { this.pendingAppeals = (d && d.appeals) || []; })
        .catch(() => { this.pendingAppeals = []; });
    },
    loadDecidedAppeals() {
      // 已裁决申诉（家长判对/判错），用于首页「家长反馈」区展示结果
      this.api(`/api/appeal/list?user_id=${encodeURIComponent(this.user)}&status=history`)
        .then(d => {
          this.decidedAppeals = (d && d.appeals) || [];
          this.decidedAppealsTotal = (d && typeof d.total === 'number') ? d.total : this.decidedAppeals.length;
        })
        .catch(() => { this.decidedAppeals = []; this.decidedAppealsTotal = 0; });
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
        }).then(() => {
          // 立即本地移除该条，避免列表刷新前二次点击「已处理过」报错
          const idx = this.pendingAppeals.findIndex(x => x.id === a.id);
          if (idx >= 0) this.pendingAppeals.splice(idx, 1);
          delete this.appealNotes[a.id];
          this.showToast(ok ? '已确认孩子做对了，本题改判正确、得分已重算 ✅' : '已驳回申诉，维持原判');
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
    /* ─────────── AI 重判（题目判错后用 AI 复核，可纠正错误参考答案）─────────── */
    aiRejudge(payload) {
      // 通用：调用 /api/ai/rejudge，返回 {correct, stored_wrong, correct_answer, reason, fixed, credited}
      return this.api('/api/ai/rejudge', {
        method: 'POST',
        body: JSON.stringify(Object.assign({ user_id: this.user }, payload)),
      });
    },
    async aiRejudgeCurrent() {
      const it = this.quiz.items[this.quiz.i];
      if (!it || !it.answered || it.correct) return;
      this.rejudging = true;
      // 兜底：15s 内 AI 调用未返回，强制解除禁用
      const guard = setTimeout(() => { this.rejudging = false; }, 15000);
      let d = null;
      try {
        d = await this.aiRejudge({
          question_id: it.qid || null,
          question: it.question,
          answer: it.answer || '',
          user_answer: it.userAnswer || '',
          subject: this.subject,
        });
      } catch (e) { this.showToast(e.message); }
      this.rejudging = false;
      if (!d) return;
      if (d.correct) {
        it.correct = true;
        it.appealed = true;
        let msg = '🤖 AI 复核：你的答案正确，已加分 ✅';
        if (d.fixed) msg += '（参考答案有误，已自动修正为 ' + d.correct_answer + '）';
        else if (d.correct_answer) msg += '（正确答案：' + d.correct_answer + '）';
        this.showToast(msg);
        this.loadAnalysis(); this.loadDailyTasks(); this.loadWrongItems();
      } else {
        this.showToast('🤖 AI 复核：' + (d.reason || '认为作答不正确，维持原判'));
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
      } else {
        this.showToast('🤖 AI 复核：' + (d.reason || '认为作答不正确'));
      }
    },
    async aiRejudgeWrong(w) {
      if (!w || w.is_unanswered) return;
      this.rejudging = true;
      // 兜底：15s 内 AI 调用未返回（模型慢/异常），强制解除禁用，避免按钮卡死
      const guard = setTimeout(() => { this.rejudging = false; }, 15000);
      let d = null;
      try {
        d = await this.aiRejudge({
          question_id: w.question_id || null,
          question: w.question,
          answer: w.correct_answer || '',
          user_answer: w.user_answer || '',
          subject: w.subject || this.subject,
        });
      } catch (e) { this.showToast(e.message); }
      clearTimeout(guard);
      this.rejudging = false;
      if (!d) return;
      if (d.correct) {
        let msg = '🤖 AI 复核：你的答案正确，已加分 ✅';
        if (d.fixed) msg += '（参考答案有误，已自动修正为 ' + d.correct_answer + '）';
        else if (d.correct_answer) msg += '（正确答案：' + d.correct_answer + '）';
        this.showToast(msg);
        this.loadWrongItems(); this.loadDailyTasks(); this.loadAnalysis();
      } else {
        this.showToast('🤖 AI 复核：' + (d.reason || '认为作答不正确，维持原判'));
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
        sessionStorage.setItem('zx_parent_pwd', pwd);
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
      // 每科默认强制任务：固定保留不可删，仅可调数量
      const defaults = ['math', 'chi', 'eng'].map(key => {
        const code = DEFAULTS[key];
        const def = this.allTaskOptions.find(o => o.code === code)
          || { code, title: code, subject: revMap[key] };
        const item = items.find(i => i.code === code);
        return { subject: revMap[key], code, def, target: item ? item.target : (key === 'eng' ? 5 : 1) };
      });
      // 回显家长追加的强制任务（后端 settings.mandatory 存 {学科: [追加codes]}）
      const extra = [];
      if (this.taskSettings.mandatory) {
        for (const [subj, codes] of Object.entries(this.taskSettings.mandatory)) {
          const key = subjMap[subj];
          if (!key) continue;
          for (const code of (Array.isArray(codes) ? codes : [codes])) {
            if (!code || code === DEFAULTS[key]) continue;
            const item = items.find(i => i.code === code);
            extra.push({ subject: key, code, target: item ? item.target : 1 });
          }
        }
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
      this.taskDialog = { show: true, defaults, extra, optional, disabled, subOpts };
      this.loadParentCustomTasks();
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
      const { defaults, extra, optional, disabled } = this.taskDialog;
      // 背诵类固定「全量完成」语义，不可作为可选/追加任务，但默认强制行的数量仍回传供回显
      const UNCONFIGURABLE = ['chi_classical', 'eng_vocab'];
      // 处理所有任务的目标数量
      for (const it of this.taskSettings.items || []) {
        if (UNCONFIGURABLE.includes(it.code)) continue;
        targets[it.code] = it.target;
        enabled[it.code] = !disabled.includes(it.code);
      }
      // 默认强制任务的目标数量（含背诵类回显数量）
      for (const d of defaults) {
        targets[d.code] = d.target || 1;
      }
      // 追加的强制任务：目标数 + 按学科归组为 {学科: [追加codes]}
      const subjMap = { math: '数学', chi: '语文', eng: '英语' };
      const mandatoryOut = { '数学': [], '语文': [], '英语': [] };
      for (const ex of extra) {
        if (!ex.code) continue;
        if (UNCONFIGURABLE.includes(ex.code)) continue;
        targets[ex.code] = ex.target || 1;
        enabled[ex.code] = true;
        const subj = subjMap[ex.subject];
        if (subj && !mandatoryOut[subj].includes(ex.code)) mandatoryOut[subj].push(ex.code);
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
    startWish() { this.wishOverlay.title = ''; this.wishOverlay.target = 5; this.wishOverlay.wish_type = 'task_count'; this.wishOverlay.daily_target = 3; this.wishOverlay.deadline = ''; this.wishOverlay.show = true; },
    submitWish() {
      const title = (this.wishOverlay.title || '').trim();
      if (!title) return this.showToast('写下你的心愿吧');
      const payload = { user_id: this.user, title, target: Number(this.wishOverlay.target) || 5, wish_type: this.wishOverlay.wish_type, daily_target: Number(this.wishOverlay.daily_target) || 3, deadline: this.wishOverlay.deadline || '' };
      this.api('/api/rewards/wish', {
        method: 'POST',
        body: JSON.stringify(payload),
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
    /* ─────────── 小老师模式（Sprint 4 + PRD 17：1-3 道错题） ─────────── */
    loadTeachCards() {
      return this.api(`/api/teach/active?user_id=${encodeURIComponent(this.user)}`)
        .then(d => {
          const items = (d && d.items) || [];
          if (!items.length) return null;
          this.teachOverlay = { show: true, cards: items, idx: 0, step: 1, card: items[0], answerText: '', result: '', hint: '' };
          return this.teachOverlay;
        });
    },
    openTeach(w) {
      if (!w.cause) { this.showToast('请先选择错因，才能出题给家长'); return; }
      this.api('/api/teach/create', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, kind: w.kind, record_id: w.id }),
      }).then(() => this.loadTeachCards())
        .catch(e => this.showToast(e.message));
    },
    nextTeach() {
      const idx = this.teachOverlay.idx + 1;
      if (idx >= this.teachOverlay.cards.length) return this.closeTeach();
      this.teachOverlay.idx = idx;
      this.teachOverlay.card = this.teachOverlay.cards[idx];
      this.teachOverlay.step = 1;
      this.teachOverlay.answerText = '';
      this.teachOverlay.result = '';
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
        this.teachOverlay.cards[this.teachOverlay.idx] = card;
        this.teachOverlay.step = 3;
      }).catch(e => this.showToast(e.message));
    },
    gradeTeach(ok) {
      this.api('/api/teach/grade', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, card_id: this.teachOverlay.card.id, is_correct: ok }),
      }).then(card => {
        this.teachOverlay.card = card;
        this.teachOverlay.cards[this.teachOverlay.idx] = card;
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
    /* 未答题作答：先做再判断对错 */
    answerUnanswered() {
      if (!this.curWrong || !this.curWrong.is_unanswered) return;
      const ans = (this.curWrong._answerInput || '').trim();
      if (!ans) { this.showToast('请先输入答案'); return; }
      this.api('/api/exam/wrong/answer-unanswered', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, record_id: this.curWrong.record_id, user_answer: ans }),
      }).then(r => {
        this.showToast(r.message || (r.correct ? '答对了！' : '答错了'));
        if (r.correct) {
          this.curWrong.mastered = true;
          this.curWrong.is_unanswered = false;
        } else {
          this.curWrong.is_unanswered = false;
          this.curWrong.correct_answer = r.correct_answer || this.curWrong.correct_answer;
        }
        this.loadWrongItems();
        this.loadAnalysis();
      }).catch(e => this.showToast(e.message));
    },
    /* 「标记已掌握」= 掌握检测：先做 3 道同类型题，全部答对才真正标记已掌握，
       防止"假掌握"。答对结果由 /api/study/practice-submit 按 record 分组整组判定 */
    markWrongMastered(w) {
      if (!w.cause) { this.showToast('请先选择错因，才能检测掌握'); return; }
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
      if (!w.cause) { this.showToast('请先选择错因，才能进行重练'); return; }
      this.api('/api/study/retry', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, kind: w.kind, record_id: w.record_id, count: 3 }),
      }).then(r => {
        const items = (r.questions || []).map(q => ({
          qid: q.qid, question: q.question,
          sub: (q.type_name || r.module_name || '') + (opts.mastery ? ' · 全对才掌握' : ''),
          options: q.options || [], answer: q.answer, explanation: q.explanation || '',
          // exam/grammar 题后端不下发答案，逐题判分走 /api/study/check-answer
          check_kind: (r.sub_kind === 'exam' || r.sub_kind === 'grammar') ? r.sub_kind : '',
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
              check_kind: 'exam',  // 后端不下发答案，逐题判分走 /api/study/check-answer
              extra: { kind: 'exam', record_id: g.record_id }, text_id: 0,
            });
          });
        });
        this.startQuiz({
          title: `🎯 错题修正 · ${this.subject}（${groups.length} 组同类题）`,
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
      // 后端判分题（无 answer）不高亮正确选项，避免看答案背题
      if (item.answer != null && letter === String(item.answer || '').trim().toUpperCase()) return 'correct';
      if (item.selected === oi) return 'wrong';
      return '';
    },
    async _serverCheck(it, userAnswer) {
      // 防刷：答案不下发前端，作答后由后端判对错
      try {
        const r = await this.api('/api/study/check-answer', {
          method: 'POST',
          body: JSON.stringify({ user_id: this.user, kind: it.check_kind, qid: it.qid, user_answer: userAnswer }),
        });
        return !!r.correct;
      } catch (e) { return false; }
    },
    async pickOption(oi) {
      const it = this.quiz.items[this.quiz.i];
      if (it.answered || it.checking) return;
      it.selected = oi;
      const letter = 'ABCDEFGH'[oi];
      it.userAnswer = letter;
      if (it.answer == null && it.check_kind) {
        it.checking = true;
        it.correct = await this._serverCheck(it, letter);
        it.checking = false;
      } else {
        it.correct = letter === String(it.answer || '').trim().toUpperCase();
      }
      this._afterAnswer(it);
    },
    async submitFill() {
      const it = this.quiz.items[this.quiz.i];
      if (it.answered || it.checking) return;
      const ua = (this.quiz.fillText || '').trim();
      if (!ua) { this.showToast('请先输入答案'); return; }
      it.userAnswer = ua;
      if (it.answer == null && it.check_kind) {
        it.checking = true;
        it.correct = await this._serverCheck(it, ua);
        it.checking = false;
      } else {
        it.correct = this._matchAnswer(ua, it.answer);
      }
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
        }).then(r => {
          if (r && r.details && r.details.some(d => d.status === 'mastered')) this.showFloat('📈 进步 +1', true, 900);
          this.loadAnalysis();
        }).catch(() => {});
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
      // 首获五星 → 「新纪录！」（每个用户独立记录，首次达到 90 分时展示）
      if (this.quiz.score >= 90) {
        const k = 'zx_five_' + (this.user || 'guest');
        this.newStarRecord = !localStorage.getItem(k);
        if (this.newStarRecord) localStorage.setItem(k, '1');
      } else {
        this.newStarRecord = false;
      }
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
              qid: it.qid || 0,  // 后端按题目 id 重判，不信任前端 correct
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
            if (allOk) {
              this.showToast('🎉 全部答对，已标记掌握！');
              if (masteredIds.length) this.showFloat('📈 进步 +1', true, 900);   // PRD 3.3 进步动效
            } else {
              this.showToast('有答错的题，明天再来一次！已记入明日复习队列 🌙');
              this.loadTomorrowQueue();
            }
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
        // 背诵检测：逐题判分——做对即时保存进度，做错进入错题本，不再「整轮从头重来」。
        // 本轮混入的错题本题目（error_id>0）按「每批4题=1次尝试」回写连击，连续3次全对移除。
        const items = this.quiz.items;
        const errorQuizItems = items.filter(it => it.error_id && it.error_id > 0);   // 混入的错题本题目
        const normalItems = items.filter(it => !(it.error_id && it.error_id > 0));   // 本轮正常背诵题目

        const afterRecite = () => {
          this.quiz.active = false;
          if (src.comprehensive) { this._finishComprehensive(); return; }
          // 逐条测试闸门：当前条目有错 → 重测同一题；全对 → 才进入下一个
          const items = this.quiz.items;
          const normal = items.filter(it => !(it.error_id && it.error_id > 0));
          if (src.kind === 'text') {
            const ts = this.textSession;
            const t = ts.texts[src.index];
            const curWrong = normal.some(it => (it.text_id || src.text_id) === t.text_id && !it.correct);
            if (src.perItem && src.index < ts.texts.length - 1) {
              if (curWrong) { this.showToast('这一篇还没背熟，再测一次 ✊'); this.textTest(src.index); }
              else { ts.i = src.index + 1; ts.phase = 'card'; this.$nextTick(() => setTimeout(() => this.textSpeak(), 250)); }
            } else if (src.perItem && src.index === ts.texts.length - 1) {
              if (curWrong) { this.showToast('这一篇还没背熟，再测一次 ✊'); this.textTest(src.index); }
              else { ts.phase = 'comprehensive'; this.startTextComprehensive(); }
            } else { ts.done = true; this.refreshAll(); }
          } else {
            const ws = this.wordSession;
            const w = ws.words[src.index];
            const curWrong = normal.some(it => it.qid === w.word_id && !it.correct);
            if (src.perItem && src.index < ws.words.length - 1) {
              if (curWrong) { this.showToast('这个单词还没记住，再测一次 ✊'); this.wordTest(src.index); }
              else { ws.i = src.index + 1; ws.phase = 'card'; ws.revealed = false; this.$nextTick(() => setTimeout(() => this.wordSpeak(), 250)); }
            } else if (src.perItem && src.index === ws.words.length - 1) {
              if (curWrong) { this.showToast('这个单词还没记住，再测一次 ✊'); this.wordTest(src.index); }
              else { ws.phase = 'comprehensive'; this.startWordComprehensive(); }
            } else { ws.done = true; this.refreshAll(); }
          }
        };

        if (src.kind === 'word') {
          // 逐词测一测 / 综合测试：绝不在这一步标记掌握，避免「测 1 个词却标记全部 20 个」。
          // 逐词仅作过关闸门（对→下一词，错→重测）；综合测试由 _finishComprehensive 统一判定并落库。
          if (src.perItem || src.comprehensive) { afterRecite(); return; }
          const ws = this.wordSession;
          // 每个单词的默写答案（取填空题作答）
          const ansMap = {};
          normalItems.forEach(it => { if (!it.options || !it.options.length) ansMap[it.qid] = it.userAnswer; });
          // 按词判定：任一子题错 → 该词错（进错题本）；全对 → 即时保存
          const wordWrong = {};
          normalItems.forEach(it => { if (!it.correct) wordWrong[it.qid] = true; });
          const correctWords = (ws.words || []).filter(w => !wordWrong[w.word_id]);
          const results = correctWords.map(w => ({
            word_id: w.word_id,
            answer: (ansMap[w.word_id] != null && ansMap[w.word_id] !== '') ? ansMap[w.word_id] : w.word,
          }));
          const studyErrors = Object.keys(wordWrong).map(wid => {
            const w = (ws.words || []).find(x => x.word_id === Number(wid)) || {};
            const it = normalItems.find(i => i.qid === Number(wid) && !i.correct);
            return {
              source_type: 'vocab', source_id: Number(wid), module_name: '单词背诵',
              question: (it && it.question) || ('默写：' + (w.word || '')),
              user_answer: (it && it.userAnswer) || '', correct_answer: w.word || '',
              explanation: (it && it.sub) || '',
            };
          });
          const pErr = studyErrors.length
            ? this.api('/api/study/errors', { method: 'POST', body: JSON.stringify({ user_id: this.user, items: studyErrors }) })
            : Promise.resolve();
          pErr.then(() => this.api('/api/vocab/dictate', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, mode: src.mode2, results }),
          })).then(r => {
            const saved = (r && r.saved) || [];
            return this._submitErrorBatch(errorQuizItems, '英语').then(() => {
              this.loadAnalysis();
              const okN = saved.length, badN = studyErrors.length;
              this.showToast(okN ? `已掌握 ${okN} 个单词` + (badN ? `，${badN} 个待巩固（已加入错题本）` : '，太棒了！') : '本次需巩固，已加入错题本');
              afterRecite();
            });
          }).catch(e => { this.quiz.active = false; ws.active = false; this.showToast(e.message); });
        } else {
          // 逐篇测一测 / 综合测试：同单词逻辑，仅作闸门或统一落库，不在每篇即时标记掌握
          if (src.perItem || src.comprehensive) { afterRecite(); return; }
          const ts = this.textSession;
          // 按篇目判定：所有子题全对才算通过
          const textOk = {};
          normalItems.forEach(it => {
            const tid = it.text_id || src.text_id;
            if (!(tid in textOk)) textOk[tid] = true;
            if (!it.correct) textOk[tid] = false;
          });
          const passedIds = Object.keys(textOk).filter(k => textOk[k]).map(Number);
          const wrongTextIds = Object.keys(textOk).filter(k => !textOk[k]).map(Number);
          const studyErrors = wrongTextIds.map(tid => {
            const t = (ts.texts || []).find(x => x.text_id === tid) || {};
            const it = normalItems.find(i => (i.text_id === tid) && !i.correct);
            return {
              source_type: 'classical', source_id: tid, module_name: '古诗文背诵',
              question: (it && it.question) || ('默写：《' + (t.title || '') + '》'),
              user_answer: (it && it.userAnswer) || '', correct_answer: (it && it.answer) || '',
              explanation: (it && it.sub) || '',
            };
          });
          const pErr = studyErrors.length
            ? this.api('/api/study/errors', { method: 'POST', body: JSON.stringify({ user_id: this.user, items: studyErrors }) })
            : Promise.resolve();
          // AI 复审：将判错的篇目送给 AI 二次确认（繁体/通假字/语序差异等边界情况）
          const wrongItems = studyErrors.map(se => ({
            text_id: se.source_id, question: se.question,
            user_answer: se.user_answer, answer: se.correct_answer, subject: '语文',
          }));
          pErr.then(() => this.api('/api/classical/dictate', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, mode: src.mode2, passed_ids: passedIds, wrong_items: wrongItems }),
          })).then(r => {
            const saved = (r && r.saved) || [];
            const flipped = (r && r.ai_flipped) || [];
            return this._submitErrorBatch(errorQuizItems, '语文').then(() => {
              this.loadAnalysis();
              const okN = saved.length, badN = studyErrors.length - flipped.length;
              if (flipped.length) this.showToast(`🤖 AI 复核：${flipped.length} 篇判定为正确 ✓`);
              this.showToast(okN ? `已背诵 ${okN} 篇` + (badN > 0 ? `，${badN} 篇待巩固（已加入错题本）` : '，太棒了！') : '本次需巩固，已加入错题本');
              afterRecite();
            });
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
          // 去除填空占位符与间隔符号（非答案内容）：全角/半角下划线（题干空白）、
          // 省略号/两点leader、各类间隔点。古诗文/单词填空题若孩子把题干里的「＿」一并
          // 写进答案（或混入下划线/间隔点），会出现「内容一模一样却判错」。
          .replace(/[＿_…‥•・˙‧]/g, '')
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
    this.loadEngTypes();
    this.turbo = localStorage.getItem('zx_turbo') === '1';
    const saved = JSON.parse(localStorage.getItem('zx_user') || 'null');
    if (saved && saved.user) {
      this.user = saved.user;
      this.username = saved.user;
      this.userName = saved.nickname || saved.user;
      this.token = saved.token || '';
      this.grade = saved.grade || 6;
      this.subject = saved.subject || '英语';
      this.engTypes = this.subject === '语文' ? this._chiTypes : this._engTypes;
      this.loadMathCategories();   // 仅在已登录后加载（接口需登录 token）
      this.refreshAll();
      this.loadAuthInfo();
      this.loadWeather();
    }
  },
}

export default appOptions
