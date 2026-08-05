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
      attempts: null, attemptSubject: '', recentAttempts: [], statsAttempts: 0,
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
      wrongScreen: 'list', wrongKind: 'all', wrongStatus: 'pending', wrongSubject: '',
      wrongItems: [], curWrong: null,
      // 通用答题状态机
      quiz: { active: false, done: false, title: '', items: [], i: 0, fillText: '', correct: 0, wrongCount: 0, score: 0, source: null },
      // 试卷中心
      papers: [], paperSubject: '',
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
      this.user = ''; this.username = ''; this.tab = 'home';
    },

    /* ─────────── 导航 ─────────── */
    goTab(t) {
      this.tab = t;
      if (t === 'practice') { this.loadMathCategories(); if (this.subject === '英语') this.loadGrammarPoints(); }
      if (t === 'recite') { this.reciteSub === 'words' ? this.loadVocabToday() : this.loadClassicalToday(); this.loadClassicalTexts(); }
      if (t === 'wrong') { this.loadWrongItems(); this.loadAnalysis(); }
      if (t === 'papers') this.loadPapers();
      if (t === 'stats') this.loadStats();
    },
    switchSubject(s) {
      this.subject = s;
      if (this.tab === 'practice') {
        if (s !== '英语' && this.practiceSub === 'grammar') this.practiceSub = 'generate';
        if (s === '英语') this.loadGrammarPoints();
      }
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

    /* ─────────── 全局刷新 ─────────── */
    refreshAll() {
      if (!this.user) return;
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
      const body = { subject: this.subject, grade: this.grade, difficulty: this.genDifficulty };
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
          if (!r.ok) { let d = t; try { d = JSON.parse(t); } catch (e) {} throw new Error(typeof d === 'object' && d ? (d.detail || '生成失败') : '生成失败'); }
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
      this.api(`/api/exam/attempts/list?user_id=${encodeURIComponent(this.user)}&page_size=50${this.attemptSubject ? '&subject=' + encodeURIComponent(this.attemptSubject) : ''}`)
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
      this.wordSession = { active: true, done: false, mode, words, i: 0, revealed: false, okCount: 0, results: [] };
    },
    wordNext(ok) {
      const ws = this.wordSession;
      const w = ws.words[ws.i];
      ws.results.push({ word_id: w.word_id, correct: ok });
      if (ok) ws.okCount++;
      if (ws.i < ws.words.length - 1) { ws.i++; ws.revealed = false; }
      else {
        ws.done = true;
        if (ws.mode === 'new') {
          this.api('/api/vocab/learn', { method: 'POST', body: JSON.stringify({ user_id: this.user, word_ids: ws.words.map(x => x.word_id) }) })
            .then(() => this.refreshAll()).catch(e => this.showToast(e.message));
        } else {
          this.api('/api/vocab/review', { method: 'POST', body: JSON.stringify({ user_id: this.user, results: ws.results }) })
            .then(() => this.refreshAll()).catch(e => this.showToast(e.message));
        }
      }
    },
    startTextSession(mode) {
      const raw = mode === 'new' ? (this.classicalToday.new_texts || []) : (this.classicalToday.review_texts || []);
      if (!raw.length) { this.showToast(mode === 'new' ? '今日新篇已背完，明天再来吧' : '今日没有到期复习的篇目'); return; }
      this.textSession = {
        active: true, done: false, mode,
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
      else {
        ts.done = true;
        if (ts.mode === 'new') {
          this.api('/api/classical/learn', { method: 'POST', body: JSON.stringify({ user_id: this.user, text_ids: ts.texts.map(x => x.text_id) }) })
            .then(() => this.refreshAll()).catch(e => this.showToast(e.message));
        } else {
          this.api('/api/classical/review', { method: 'POST', body: JSON.stringify({ user_id: this.user, results: ts.results }) })
            .then(() => this.refreshAll()).catch(e => this.showToast(e.message));
        }
      }
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
      const q = `user_id=${encodeURIComponent(this.user)}`;
      Promise.all([this.api(`/api/exam/wrong/list?${q}`), this.api(`/api/study/errors?${q}`)])
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
          if (this.wrongSubject) items = items.filter(i => i.subject === this.wrongSubject);
          this.wrongItems = items;
        }).catch(e => this.showToast(e.message));
    },
    openWrongDetail(w) { this.curWrong = w; this.wrongScreen = 'detail'; },
    causeLabel(c) {
      return { careless: '粗心大意', concept: '概念不清', method: '方法不会', reading: '审题失误' }[c] || '';
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
    markWrongMastered(w) {
      if (w.kind === 'study') {
        this.api('/api/study/errors/master', { method: 'POST', body: JSON.stringify({ user_id: this.user, error_id: w.id }) })
          .then(() => { w.mastered = true; this.showToast('已标记掌握 🎉'); this.loadAnalysis(); this.loadWrongItems(); })
          .catch(e => this.showToast(e.message));
      } else {
        this.api('/api/exam/wrong/batch-master', { method: 'POST', body: JSON.stringify({ user_id: this.user, question_ids: [w.question_id] }) })
          .then(() => { w.mastered = true; this.showToast('已标记掌握 🎉'); this.loadAnalysis(); this.loadWrongItems(); })
          .catch(e => this.showToast(e.message));
      }
    },
    loadAnalysis() {
      this.api(`/api/study/errors/analysis?user_id=${encodeURIComponent(this.user)}`)
        .then(r => {
          this.wrongAnalysis = r;
          this.masteredTotal = r.mastered || 0;
          this.wrongBadge = r.pending || 0;
        }).catch(() => {});
    },
    causeColor(c) {
      return { careless: '#F5A623', concept: '#4E7CF6', method: '#8B7CF6', reading: '#F2604C' }[c] || '#93A1BD';
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
    startWrongRetry(w) {
      this.api('/api/study/retry', {
        method: 'POST',
        body: JSON.stringify({ user_id: this.user, kind: w.kind, record_id: w.record_id, count: 3 }),
      }).then(r => {
        const items = (r.questions || []).map(q => ({
          qid: q.qid, question: q.question, sub: q.type_name || r.module_name || '',
          options: q.options || [], answer: q.answer, explanation: q.explanation || '',
          extra: { kind: w.kind, record_id: w.record_id }, text_id: q.text_id || 0,
        }));
        this.startQuiz({
          title: '🎯 变式重练 · ' + (r.module_name || '同类题'),
          items, source: { mode: 'retry', retry: { kind: w.kind, record_id: w.record_id } },
        });
      }).catch(e => this.showToast(e.message));
    },
    async retryTopCause() {
      const code = this.topCause.code;
      const q = `user_id=${encodeURIComponent(this.user)}`;
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
      this.api('/api/exam/records')
        .then(ps => {
          ps = ps || [];
          this.papers = this.paperSubject ? ps.filter(p => p.subject === this.paperSubject) : ps;
        }).catch(() => { this.papers = []; });
    },
    previewPaper(p) { this.startExamQuiz(p.id, p.title); },
    downloadPaper(p) { window.open(`/api/exam/download/${p.id}`, '_blank'); },

    /* ─────────── 统计 ─────────── */
    loadStats() { this.loadVocabStats(); this.loadClassicalStats(); this.loadGrammarStats(); this.loadAttempts(); },
    loadGrammarStats() {
      this.api(`/api/grammar/stats?grade=${this.grade}`)
        .then(r => { this.grammarStats = r || {}; }).catch(() => {});
    },
    statPct(a, b) { return b ? Math.round((a || 0) / b * 100) : 0; },

    /* ─────────── 通用答题状态机 ─────────── */
    startQuiz({ title, items, source }) {
      this.quiz = {
        active: true, done: false, title,
        items: items.map(it => ({ ...it, answered: false, correct: false, selected: -1, userAnswer: '' })),
        i: 0, fillText: '', correct: 0, wrongCount: 0, score: 0, source,
      };
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
      if (it.correct) this.quiz.correct++; else this.quiz.wrongCount++;
      if (it.correct && this.quiz.source && this.quiz.source.mode === 'retry' && it.extra) {
        this.api('/api/study/practice-submit', {
          method: 'POST',
          body: JSON.stringify({ user_id: this.user, results: [{ kind: it.extra.kind, record_id: it.extra.record_id, correct: true }] }),
        }).then(() => this.loadAnalysis()).catch(() => {});
      }
    },
    quizNext() {
      if (this.quiz.i < this.quiz.items.length - 1) { this.quiz.i++; this.quiz.fillText = ''; }
      else this.finishQuiz();
    },
    finishQuiz() {
      const total = this.quiz.items.length;
      this.quiz.score = total ? Math.round(this.quiz.correct / total * 100) : 0;
      this.quiz.done = true;
      const src = this.quiz.source;
      if (!src) return;
      if (src.mode === 'exam') {
        this.api('/api/exam/submit-answers', {
          method: 'POST',
          body: JSON.stringify({
            user_id: this.user, exam_id: src.exam_id, duration_sec: Math.round((Date.now() - src.startedAt) / 1000),
            answers: this.quiz.items.map(it => ({ question_id: it.qid, user_answer: it.userAnswer || '' })),
          }),
        }).then(() => this.loadAttempts()).catch(e => this.showToast(e.message));
      } else if (src.mode === 'retry') {
        this.api('/api/study/practice-submit', {
          method: 'POST',
          body: JSON.stringify({
            user_id: this.user,
            results: this.quiz.items.map(it => ({ kind: it.extra.kind, record_id: it.extra.record_id, correct: it.correct })),
          }),
        }).then(() => this.loadAnalysis()).catch(e => this.showToast(e.message));
      } else if (src.mode === 'classical') {
        const wrongs = this.quiz.items.filter(it => !it.correct && it.userAnswer)
          .map(it => ({
            source_type: 'classical', source_id: it.text_id || src.text_id, module_name: '古诗文默写',
            question: it.question, user_answer: it.userAnswer, correct_answer: it.answer,
            explanation: it.sub || '',
          }));
        if (wrongs.length) {
          this.api('/api/study/errors', { method: 'POST', body: JSON.stringify({ user_id: this.user, items: wrongs }) })
            .then(() => this.loadAnalysis()).catch(() => {});
        }
      }
      this.refreshAll();
    },
    closeQuiz() {
      const src = this.quiz.source;
      if (src && src.mode === 'retry') {
        const answered = this.quiz.items.filter(it => it.answered);
        if (answered.length) {
          this.api('/api/study/practice-submit', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.user, results: answered.map(it => ({ kind: it.extra.kind, record_id: it.extra.record_id, correct: it.correct })) }),
          }).then(() => this.loadAnalysis()).catch(() => {});
        }
      } else if (src && src.mode === 'exam' && !this.quiz.done) {
        // 中途退出：把已答部分提交保存，避免"做完没有记录"
        const answered = this.quiz.items.filter(it => it.answered);
        if (answered.length) {
          this.api('/api/exam/submit-answers', {
            method: 'POST',
            body: JSON.stringify({
              user_id: this.user, exam_id: src.exam_id,
              duration_sec: Math.round((Date.now() - (src.startedAt || Date.now())) / 1000),
              answers: answered.map(it => ({ question_id: it.qid, user_answer: it.userAnswer || '' })),
            }),
          }).then(() => { this.loadAttempts(); this.showToast('已保存当前答题进度'); }).catch(() => {});
        }
      }
      this.quiz.active = false;
      this.refreshAll();
    },
    quizAgain() {
      const src = this.quiz.source;
      if (!src) return;
      if (src.mode === 'exam') this.startExamQuiz(src.exam_id, src.title);
      else if (src.mode === 'retry') this.startWrongRetry({ kind: src.retry.kind, record_id: src.retry.record_id });
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
    _matchAnswer(ua, ans) {
      const norm = s => String(s || '').trim().toLowerCase().replace(/\s+/g, '');
      const stripP = s => s.replace(/[，。！？；：、,.!?;:]+$/g, '');
      const u = stripP(norm(ua)), a = stripP(norm(ans));
      if (!a) return false;
      if (u === a) return true;
      const nums = s => (String(s).match(/-?\d+\.?\d*/g) || []);
      const un = nums(ua), an = nums(ans);
      if (an.length === 1 && un.length === 1) return Math.abs(parseFloat(un[0]) - parseFloat(an[0])) < 1e-9;
      return false;
    },
  },

  mounted() {
    this.loadMathCategories();
    this.loadEngTypes();
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
