// dict.js：听写磨耳朵（DictView）的 data 与 methods，从 appOptions.js 机械抽出。
// 仅依赖通用 api/showToast/loadPet（留在主文件）；与其他 logic/* 经展开运算符合并后 this 仍绑定同一实例。
// 共享语音方法 speakText/wordSpeak/textSpeak 与 loadQuizCandidates(quiz) 仍留在 appOptions.js。

export function dictData() {
  return {
    dictMode: 'word',
    dictSession: { active: false, done: false, items: [], i: 0, current: null, answer: '', revealed: false, lastOk: false, correct: 0, rewarded: false, candidateChars: [] },
  };
}

export const dictMethods = {
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
        this.dictSession = { active: true, done: false, items, i: 0, current: items[0], answer: '', revealed: false, lastOk: false, correct: 0, rewarded: false, candidateChars: [] };
        if (!isWord) this.loadDictCandidates(items[0].answer);
        this.$nextTick(() => setTimeout(() => this.dictSpeak(items[0]), 350));
      }).catch(e => this.showToast(e.message));
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
    loadDictCandidates(answer) {
      // 2026-08-19：背诵/默写已改为输入法输入（AntiCheatInput text 模式），
      // 不再需要「点选字池」防作弊方案（用户反馈候选字太难找字）。
      // 保留空实现以免调用点报错；candidateChars 不再填充。
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
      if (this.dictMode !== 'word') this.loadDictCandidates(s.current.answer);
      this.$nextTick(() => setTimeout(() => this.dictSpeak(s.current), 250));
    },
};
