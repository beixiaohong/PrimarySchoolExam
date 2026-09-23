// logic/auth.js：登录 / 注册 / 重置密码 / 绑定账号 等认证相关（认证态表单 + 认证 methods）。
//
// 由来：从 3000+ 行的 appOptions.js 中抽出「认证」这一块，导出 authData()（认证表单状态）
// 与 authMethods（登录 / 注册 / 重置 / 绑定 / 退出凭证 / 拉取个人信息），由 appOptions.js 用展开运算符合并：
//   data()    { return { ...parentData(), ...ledgerData(), ...imData(), ...authData(), ...其余 } }
//   methods:  { ...parentMethods, ...ledgerMethods, ...imMethods, ...authMethods, ...其余 }
// 展开后 this 仍绑定同一个 App 实例（App.vue provide appCtx=this），所有 appCtx.xxx / this.xxx
// 调用点零改动。刻意不用 Vue mixin 数组——App.vue 是手工展开 appOptions，混入 mixin 数组会改变合并语义。
// 收尾强制校验：authMethods 的键集合与 appOptions.methods 剩余键集合交集为空。
//
// 边界：
//   - 身份 / 年级等基础字段（user/userName/token/username/grade/subject/showGradeModal/promotedInfo）
//     是全局共享的，保留在 appOptions.js 主 data 中，本文件只含「认证态表单」字段。
//   - loadWeather/saveCity/wxDayLabel 属天气（P3），logout 属通用生命周期，均留在 appOptions.js。
//   - onLoginOk 调用的 loadWeather/refreshAll/saveUser 仍在 appOptions.js，合并后 this 可正常解析。

// ─────────── 认证表单 data（由 appOptions.data 用 ...authData() 合并）───────────
export function authData() {
  return {
    authMode: 'login', loginPwd: '', authInfo: {},
    regTarget: '', regCode: '', regPwd: '', regNickname: '',
    rstTarget: '', rstCode: '', rstPwd: '',
    bindTarget: '', bindCode: '', authCooldown: 0, _authTimer: null,
  };
}

// ─────────── 认证 methods（由 appOptions.methods 用 ...authMethods 合并）───────────
export const authMethods = {
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
};
