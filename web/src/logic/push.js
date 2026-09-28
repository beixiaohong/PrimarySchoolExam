// 消息推送（OneSignal Web Push）前端逻辑
//
// 职责：登录后初始化 SDK、绑定 external_id（= 本系统 user_id）、上报订阅 ID、
//       维护用户的逐场景偏好，登出时解绑。
//
// 三条设计约束（都是踩过的坑，改动前务必先读）：
// 1. **SDK 懒加载**：只有后端 `/api/push/config` 返回 enabled=true 才去加载
//    OneSignal 的外部脚本。通道未配置时零第三方请求 —— 否则控制台持续报错，
//    用户以为功能坏了，其实只是后台没填密钥。
// 2. **登录后才 login()**：游客状态绝不调用 OneSignal.login()，
//    否则订阅会被绑到空/错误的 external_id，之后该设备收不到任何定向推送。
// 3. **失败全静默**：推送是增量能力，任何一步失败都不得影响登录、答题等主流程，
//    所以这里所有请求与 SDK 调用都包了 try/catch，只提示不抛出。
//
// 字段与 `logic/gaoxiang.js` 等保持一致的三字典导出：pushData() / pushComputed / pushMethods。

// OneSignal Web SDK v16（页面脚本）。Service Worker 由后端根路径
// `/OneSignalSDKWorker.js` 托管（见 web/public/OneSignalSDKWorker.js 与 app/main.py）。
const OS_SDK_SRC = 'https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js';

// 设置页的场景开关清单：field 与后端 push_prefs 的列名、/api/push/prefs 的入参一一对应。
// 只在前端维护一份展示文案，开关的**实际生效**在后端（services/push.py 的 _PREF_FIELD），
// 前端关掉只是不发请求，不构成安全边界。
const PUSH_EVENT_FIELDS = [
  { field: 'enable_study', label: '学习提醒', desc: '作业未完成、打卡断签、错题到复习时间' },
  { field: 'enable_im', label: '私信提醒', desc: '对方发来消息、而你当前不在线时' },
  { field: 'enable_announce', label: '公告通知', desc: '老师与管理员发布的公告、站内信' },
  { field: 'enable_exam', label: '考试与成绩', desc: '交卷出分、成绩单生成' },
];

function _detectBrowser() {
  const ua = (navigator.userAgent || '').toLowerCase();
  if (ua.indexOf('micromessenger') > -1) return 'WeChat';
  if (ua.indexOf('edg/') > -1) return 'Edge';
  if (ua.indexOf('firefox') > -1) return 'Firefox';
  if (ua.indexOf('chrome') > -1) return 'Chrome';
  if (ua.indexOf('safari') > -1) return 'Safari';
  return 'Other';
}

function _detectDevice() {
  const ua = navigator.userAgent || '';
  if (/iPad|Tablet/i.test(ua)) return 'Tablet';
  if (/Mobile|Android|iPhone/i.test(ua)) return 'Mobile';
  return 'Desktop';
}

export function pushData() {
  return {
    pushRaw: null,          // /api/push/config 原始响应（enabled / app_id / events）
    pushPrefs: {
      // 逐场景偏好；后端无记录时也是这套默认值（缺行 = 全开）
      enable_study: true, enable_im: true, enable_announce: true, enable_exam: true,
      quiet_start: '', quiet_end: '',
    },
    pushPermission: '',     // 浏览器通知权限：default / granted / denied
    pushOptedIn: false,     // 本设备是否已订阅
    pushLoading: false,     // 设备开关操作进行中
    pushTesting: false,     // 测试推送进行中
    pushQuietForm: { start: '', end: '' },   // 免打扰时段编辑态
    pushEventFields: PUSH_EVENT_FIELDS,
    pushDevices: 0,         // 本账号已登记的有效订阅设备数
    // SDK 是否已完成初始化（= 状态已可判定）。未就绪时界面必须显示「检查中…」，
    // **不能**显示成「未开启」—— 那是把「还不知道」说成了「没有」（见 pushDeviceState）。
    pushReady: false,
    // OneSignal 脚本未能加载（被浏览器跟踪防护 / 广告拦截拦掉）。
    // 之前这种情况是**彻底静默**的：SDK 不出现 → 不弹授权提示 → 用户以为功能坏了。
    // 见 pushDeviceState 与 _pushLoadSdk 的超时兜底。
    pushSdkError: '',
  };
}

export const pushComputed = {
  // 通道是否可用：后端已填 OneSignal 密钥且 PUSH_ENABLED 未关闭
  pushEnabled() {
    return !!(this.pushRaw && this.pushRaw.enabled);
  },
  // 本设备推送的**当前状态**（唯一真相源：界面上的色点 / 文字 / 开关位置都由它驱动）
  //
  // 起因：原先只有一个按钮，且按钮上写的是**状态词**（「已开启」/「已关闭」），
  // 但按钮本身是**动作** —— 点「已开启」其实是把它关掉。用户反馈「不知道当前是开的
  // 还是关的」，正是因为状态与动作挤在同一个元素上，只靠主色/灰底这点细微差别区分。
  // 现在拆成三重表达：文字（已开启 / 未开启 / 已被浏览器阻止 / 脚本被拦截 / 检查中…）
  //   + 色点（绿=开、灰=关、红=被阻止、橙=脚本被拦）+ 真实开关（位置即状态）。
  //
  // ⚠️ 未就绪时必须说「检查中…」而不是「未开启」—— 这与 09-28 那类误判同源：
  //    把「未知」当成了「零」。状态没读回来之前，任何结论都是错的。
  pushDeviceState() {
    if (!this.pushRaw) {
      return { tone: 'muted', title: '检查中…', hint: '正在读取本设备的推送状态' };
    }
    if (!this.pushEnabled) {
      return { tone: 'muted', title: '未开通', hint: '管理后台尚未配置推送密钥' };
    }
    // 脚本压根没加载成功：常见于 Edge「严格」跟踪防护、Firefox「严格」、uBlock/AdGuard
    // 等把 onesignal.com 当广告追踪器拦掉（它在 disconnect.me 列表里属 Advertising 类）。
    if (this.pushSdkError) {
      return { tone: 'warn', title: '脚本被拦截', hint: '浏览器把推送脚本拦掉了，请放行本网站后刷新页面' };
    }
    if (!this.pushReady) {
      return { tone: 'muted', title: '检查中…', hint: '正在初始化推送服务，稍候片刻' };
    }
    if (this.pushPermission === 'denied') {
      return { tone: 'danger', title: '已被浏览器阻止', hint: '点地址栏的锁图标，把「通知」改为「允许」后刷新页面' };
    }
    if (this.pushOptedIn) {
      const extra = this.pushDevices > 1 ? '（本账号共 ' + this.pushDevices + ' 台设备已开启）' : '';
      return { tone: 'ok', title: '已开启', hint: '这台设备会收到提醒' + extra };
    }
    if (this.pushPermission === 'default') {
      return { tone: 'muted', title: '未开启', hint: '打开右侧开关后，浏览器会询问是否允许通知' };
    }
    return { tone: 'muted', title: '未开启', hint: '这台设备不会收到任何推送' };
  },
};

export const pushMethods = {
  /* ─────────── 初始化 ─────────── */

  // 登录成功后调用（onLoginOk / 恢复会话处）。幂等：重复调用只跑一次。
  pushInit() {
    if (!this.user) return;                       // 游客不初始化（约束 2）
    if (this._osInited || this._osBooting) return;
    this._osBooting = true;
    this.api('/api/push/config')
      .then(cfg => {
        this.pushRaw = cfg || {};
        if (cfg && cfg.prefs) {
          this.pushPrefs = Object.assign({}, this.pushPrefs, cfg.prefs);
          this.pushQuietForm = { start: cfg.prefs.quiet_start || '', end: cfg.prefs.quiet_end || '' };
        }
        if (!cfg || !cfg.enabled || !cfg.app_id) return null;   // 约束 1：不加载 SDK
        return this._pushLoadSdk().then(OS => this._pushBoot(OS, cfg));
      })
      .catch(() => { /* 静默：推送不可用不影响登录 */ })
      .finally(() => { this._osBooting = false; });
  },

  // 动态注入 OneSignal 页面脚本（只注入一次）
  //
  // ⚠️ 必须带超时兜底：脚本被跟踪防护 / 广告拦截拦掉时，`onerror` **不保证触发**
  // （请求可能在浏览器内部就被丢弃）。没有超时的话这个 Promise 会永远 pending，
  // 界面停在「未开启」，用户和我们都拿不到任何线索 —— 线上真实踩过。
  _pushLoadSdk() {
    if (window.OneSignal && window.OneSignal.User) return Promise.resolve(window.OneSignal);
    if (this._osPromise) return this._osPromise;
    const self = this;
    this._osPromise = new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(function () {
        if (settled) return;
        settled = true;
        self._osPromise = null;                 // 允许下一次登录重试
        self.pushSdkError = 'SCRIPT_BLOCKED';
        reject(new Error('OneSignal SDK 加载超时（脚本可能被浏览器拦截）'));
      }, 10000);
      window.OneSignalDeferred = window.OneSignalDeferred || [];
      // v16 的 SDK 通过 OneSignalDeferred 队列回调交付实例
      window.OneSignalDeferred.push(function (OneSignal) {
        clearTimeout(timer);
        if (settled) return;                    // 已判失败：不翻转界面状态
        settled = true;
        self.pushSdkError = '';
        resolve(OneSignal);
      });
      const s = document.createElement('script');
      s.src = OS_SDK_SRC;
      s.defer = true;
      s.onerror = () => {
        clearTimeout(timer);
        if (settled) return;
        settled = true;
        this._osPromise = null;
        this.pushSdkError = 'SCRIPT_BLOCKED';
        reject(new Error('OneSignal SDK 加载失败'));
      };
      document.head.appendChild(s);
    });
    return this._osPromise;
  },

  // 初始化 SDK + 绑定 external_id + 登记订阅
  _pushBoot(OneSignal, cfg) {
    const self = this;
    const host = (location.hostname || '');
    return OneSignal.init({
      appId: cfg.app_id,
      safari_web_id: cfg.safari_web_id || undefined,
      // Service Worker 由后端根路径托管（必须显式指定：默认路径可用，
      // 但写明后即使 OneSignal 改了默认值也能生效）
      serviceWorkerPath: '/OneSignalSDKWorker.js',
      // 本地开发（http://127.0.0.1）也允许订阅，否则没法在本地验证链路
      allowLocalhostAsSecureOrigin: host === 'localhost' || host === '127.0.0.1',
      notifyButton: { enable: false },   // 不用 OneSignal 自带的铃铛，界面统一由本站控制
    }).then(function () {
      self._os = OneSignal;
      self._osInited = true;
      self._pushBindEvents(OneSignal);
      // external_id = 本系统 user_id：后端按它定向推送
      return OneSignal.login(self.user);
    }).then(function () {
      self._pushSyncState();
      // 状态已经读回来了，界面才允许下结论（此前一律显示「检查中…」）
      self.pushReady = true;
      const sid = self._pushSubscriptionId();
      // 已订阅过（同一浏览器回头客）：刷新一次上报，顺带更新 last_seen 与 UA
      if (sid && self.pushOptedIn) self._pushReport(sid);
      // 我的订阅设备数（仅用于界面展示）
      self.api('/api/push/status')
        .then(d => { self.pushDevices = (d && d.subscribed_devices) || 0; })
        .catch(() => {});
    });
  },

  // 订阅状态变化 / 权限变化时同步到界面与后端
  _pushBindEvents(OneSignal) {
    const self = this;
    try {
      // 用户可能在浏览器层面手动改权限、或换设备，这里统一跟随 SDK 的真实状态
      OneSignal.User.PushSubscription.addEventListener('change', function (event) {
        const cur = (event && event.current) || {};
        self.pushOptedIn = !!cur.optedIn;
        if (cur.id && cur.optedIn) self._pushReport(cur.id);
      });
      OneSignal.Notifications.addEventListener('permissionChange', function (p) {
        self.pushPermission = p;
      });
    } catch (e) { /* 老版本 SDK 无此事件：忽略 */ }
  },

  // 读 SDK 当前状态到界面
  _pushSyncState() {
    try {
      const OS = this._os;
      this.pushPermission = (OS.Notifications && OS.Notifications.permission) || '';
      this.pushOptedIn = !!(OS.User && OS.User.PushSubscription && OS.User.PushSubscription.optedIn);
    } catch (e) { /* 忽略 */ }
  },

  _pushSubscriptionId() {
    try {
      return (this._os && this._os.User && this._os.User.PushSubscription
        && this._os.User.PushSubscription.id) || '';
    } catch (e) { return ''; }
  },

  // 上报订阅（后端按 subscription_id 幂等 upsert）
  _pushReport(subscriptionId) {
    if (!subscriptionId) return Promise.resolve();
    return this.api('/api/push/subscribe', {
      method: 'POST',
      body: JSON.stringify({
        subscription_id: subscriptionId,
        platform: 'web',
        device_type: _detectDevice(),
        browser: _detectBrowser(),
        user_agent: (navigator.userAgent || '').slice(0, 250),
        opted_in: true,
      }),
    }).catch(() => {});
  },

  /* ─────────── 用户操作 ─────────── */

  // 本设备推送开关
  pushToggleDevice() {
    if (this.pushLoading) return;
    if (!this._osInited || !this._os) {
      // 区分「还在加载」与「已经确定加载不上」：后者要给出可执行的下一步，
      // 否则用户只会反复点开关、反复刷新，永远不知道是浏览器把脚本拦了。
      this.showToast(this.pushSdkError
        ? '推送脚本被浏览器拦截：请关闭跟踪防护/广告拦截后刷新页面'
        : '推送服务未就绪，请刷新页面后重试');
      return;
    }
    const self = this;
    this.pushLoading = true;
    const OS = this._os;
    const P = OS.User.PushSubscription;
    let task;
    if (this.pushOptedIn) {
      task = P.optOut().then(function () {
        self.pushOptedIn = false;
        // 后端也解绑：SDK 侧解绑失败时，至少后端不会再拿这个订阅发消息
        return self.api('/api/push/unsubscribe', {
          method: 'POST',
          body: JSON.stringify({ subscription_id: self._pushSubscriptionId() }),
        }).catch(function () {});
      }).then(function () { self.showToast('已关闭本设备的推送'); });
    } else {
      // 先申请浏览器权限：denied 状态下无法再弹窗，只能引导用户去浏览器设置改
      task = Promise.resolve()
        .then(function () {
          if (OS.Notifications.permission === 'default') return OS.Notifications.requestPermission();
          return null;
        })
        .then(function () {
          self._pushSyncState();
          if (OS.Notifications.permission === 'denied') {
            self.showToast('浏览器已阻止通知：请点地址栏左侧的锁图标，把「通知」改为允许');
            return null;
          }
          return P.optIn().then(function () {
            self._pushSyncState();
            const sid = self._pushSubscriptionId();
            return self._pushReport(sid);
          }).then(function () {
            self.showToast('已开启推送，将收到学习提醒');
            return self.api('/api/push/status').then(function (d) {
              self.pushDevices = (d && d.subscribed_devices) || 0;
            }).catch(function () {});
          });
        });
    }
    task.catch(function () { self.showToast('操作失败，请稍后重试'); })
      .finally(function () { self.pushLoading = false; });
  },

  // 场景开关（乐观更新 + 失败回滚）
  pushSavePref(field, value) {
    const patch = {};
    patch[field] = value;
    const backup = Object.assign({}, this.pushPrefs);
    this.pushPrefs = Object.assign({}, this.pushPrefs, patch);
    this.api('/api/push/prefs', { method: 'PUT', body: JSON.stringify(patch) })
      .then(d => { if (d) this.pushPrefs = Object.assign({}, this.pushPrefs, d); })
      .catch(() => {
        this.pushPrefs = backup;              // 回滚，避免界面显示与后端不一致
        this.showToast('保存失败，请稍后重试');
      });
  },

  // 免打扰时段
  pushSaveQuiet() {
    const start = (this.pushQuietForm.start || '').trim();
    const end = (this.pushQuietForm.end || '').trim();
    if ((start && !end) || (!start && end)) {
      this.showToast('免打扰时段需要同时填写开始与结束，或都留空');
      return;
    }
    this.api('/api/push/prefs', {
      method: 'PUT', body: JSON.stringify({ quiet_start: start, quiet_end: end }),
    }).then(d => {
      if (d) {
        this.pushPrefs = Object.assign({}, this.pushPrefs, d);
        this.pushQuietForm = { start: d.quiet_start || '', end: d.quiet_end || '' };
      }
      this.showToast(start ? '免打扰时段已保存' : '免打扰已关闭');
    }).catch(() => this.showToast('保存失败，请稍后重试'));
  },

  // 测试推送（端到端验证）
  pushSendTest() {
    if (this.pushTesting) return;
    this.pushTesting = true;
    this.api('/api/push/test', { method: 'POST', body: JSON.stringify({}) })
      .then(d => this.showToast((d && d.message) || '已发送'))
      .catch(e => this.showToast((e && e.message) || '发送失败，请稍后重试'))
      .finally(() => { this.pushTesting = false; });
  },

  // 登出：解绑浏览器侧 + 后端侧（公共电脑上必须做，否则下一位使用者会看到你的通知）
  pushTeardown() {
    try {
      if (this._osInited && this._os) {
        if (this._os.User && this._os.User.PushSubscription) this._os.User.PushSubscription.optOut();
        if (this._os.logout) this._os.logout();     // 解除 external_id 绑定
      }
    } catch (e) { /* 忽略 */ }
    this.api('/api/push/unsubscribe', { method: 'POST', body: JSON.stringify({}) })
      .catch(() => {});
    this.pushOptedIn = false;
    this.pushDevices = 0;
    // 保留 pushRaw（通道配置与账号无关）与偏好缓存，下次登录会重新拉取覆盖
    this._osInited = false;
    this.pushReady = false;   // 下次登录要重新判定状态，期间界面显示「检查中…」
  },
};
