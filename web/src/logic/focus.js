// focus.js：番茄专注钟（P2-6 创意 22）业务逻辑，从 appOptions.js 抽出（Tier2 上帝文件拆分）。
// 由来：appOptions.js 按视图切分，一次一个视图。本文件承载「专注钟」这一块，
// 由 appOptions.js 用展开运算符合并：...focusData() / ...focusComputed / ...focusMethods。
// 展开后 this 仍绑定同一个 App 实例（App.vue provide appCtx=this），FocusView 经 inject('appCtx') 访问。
// 依赖通用方法 api/showToast/loadPet（保留在 appOptions.js，合并后 this 可解析）。
// 收尾强制校验：focus* 键与 appOptions/parent/ledger/im/auth 零冲突（前缀 focus/focusXxx 唯一）。

export function focusData() {
  return {
    focusTimer: { total: 25, left: 25 * 60, running: false, paused: false },
    focusDone: false, focusMsg: '', focusToday: null, focusStats: null, _focusTicker: null,
  };
}

export const focusComputed = {
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
};

export const focusMethods = {
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
};
