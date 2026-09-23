// 单词背诵 + 古文默写（Word/Text 视图）
// 从 appOptions.js 机械抽取，沿用三字典范式，由主文件展开运算符合并。
export function reciteData() {
  return {
      wordSession: { active: false, done: false, mode: 'new', words: [], i: 0, revealed: false, okCount: 0, results: [] },
      textSession: { active: false, done: false, mode: 'new', texts: [], i: 0, okCount: 0, failCount: 0, results: [] },
      textDetail: { show: false, id: 0, title: '', author: '', dynasty: '', grade: 0, text_type: '', content: '' },
  };
}

export const reciteComputed = {
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
};

export const reciteMethods = {
    startWordSession(mode) {
      const words = mode === 'new' ? (this.vocabToday.new_words || []) : (this.vocabToday.review_words || []);
      if (!words.length) { this.showToast(mode === 'new' ? '词库已全部学完，太棒了！' : '今日没有到期复习的单词'); return; }
      this.wordSession = { active: true, done: false, phase: 'card', mode, words, i: 0, revealed: false, okCount: 0, results: [], comprehensiveIds: null };
      if (mode === 'review') {
        // 复习模式：提示本批数量与积压总量，跳过卡片直接检测
        const dueTotal = (this.vocabToday.stats || {}).due_today || words.length;
        if (dueTotal > words.length) {
          this.showToast(`本批 ${words.length} 个（共 ${dueTotal} 个到期），完成后可继续下一批`);
        }
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
          const batchInfo = ws.mode === 'review' ? `（本批 ${ws.words.length} 个）` : '';
          this.startQuiz({
            title: '✍️ 背诵检测 · ' + (ws.mode === 'new' ? '新词' : '复习') + batchInfo,
            items, source: { mode: 'dictate', kind: 'word', mode2: ws.mode },
          });
        }).catch(e => { ws.active = false; this.showToast(e.message); });
    },

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

};
