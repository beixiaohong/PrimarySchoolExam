// checkin.js：每日签到 + 连续奖励（新功能 A，2026Q4）的 data / computed / methods，从 appOptions.js 机械抽出。
// 仅依赖通用 api/showToast/loadDiamonds（通用方法保留在主文件）；与其他 logic/* 经展开运算符合并后
// this 仍绑定同一实例。后端契约见 app/domains/engagement/routers/checkin.py：
//   GET  /api/checkin/status  -> {signed_today, streak, month_calendar, next_reward_day, ladder, base_reward, diamonds}
//   POST /api/checkin         -> {signed_today, already_signed, streak, reward, bonus, next_reward_day, diamonds}
// 复用 daily_tasks（task_code='checkin'）+ diamond.grant，零新表；连续天数独立计算，不与全勤 streak 耦合。

export function checkinData() {
  return {
    checkin: null,                       // GET /api/checkin/status 的响应对象（首页按钮/月历/阶梯的数据源）
    checkinLoading: false,              // 签到 POST 进行中（防连点）
    checkinOverlay: { show: false, reward: 0, bonus: 0, streak: 0, already: false }, // 签到结果弹窗
  };
}

export const checkinComputed = {
  // 今日是否已签到
  checkinSignedToday() {
    return !!(this.checkin && this.checkin.signed_today);
  },
  // 当前连续签到天数
  checkinStreak() {
    return (this.checkin && this.checkin.streak) || 0;
  },
  // 下一个阶梯里程碑（{day, bonus}）或 null（已解锁全部）
  checkinNextReward() {
    const c = this.checkin;
    if (!c || !c.next_reward_day) return null;
    const hit = (c.ladder || []).find(x => x.day === c.next_reward_day);
    return hit ? hit : { day: c.next_reward_day, bonus: 0 };
  },
  // 本月签到日历（[{day, signed}]）
  checkinCalendar() {
    const c = this.checkin;
    return (c && c.month_calendar) || [];
  },
};

export const checkinMethods = {
  /* ─────────── 每日签到（新功能 A） ─────────── */
  loadCheckin() {
    if (!this.user) return;
    this.api(`/api/checkin/status?user_id=${encodeURIComponent(this.user)}`)
      .then(d => { this.checkin = d; })
      .catch(() => { this.checkin = null; });
  },
  doCheckin() {
    if (this.checkinLoading) return;                 // 防连点
    if (this.checkinSignedToday) { this.openCheckinOverlay(true); return; }
    this.checkinLoading = true;
    this.api('/api/checkin', {
      method: 'POST',
      body: JSON.stringify({ user_id: this.user }),
    })
      .then(d => {
        this.checkin = d;                            // 刷新状态（含最新 streak/月历/余额）
        this.loadDiamonds();                         // 同步顶部钻石数
        this.openCheckinOverlay(false, d);
        const rw = d.reward || 0;
        if (rw > 0) this.showToast(`🎉 签到成功，获得 ${rw} 钻石！`);
      })
      .catch(e => this.showToast(e.message))
      .finally(() => { this.checkinLoading = false; });
  },
  openCheckinOverlay(already, d) {
    const src = d || this.checkin || {};
    this.checkinOverlay = {
      show: true,
      reward: src.reward || 0,
      bonus: src.bonus || 0,
      streak: src.streak || 0,
      already: !!already,
    };
  },
  closeCheckinOverlay() {
    this.checkinOverlay.show = false;
  },
};
