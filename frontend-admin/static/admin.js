/* 智学学堂管理后台：Vue 3 + Element Plus + ECharts（CDN 单文件 SPA） */
const { createApp, reactive, ref, computed, nextTick } = Vue;

const app = createApp({
  setup() { return {}; },
  data() {
    return {
      token: localStorage.getItem('zx_admin_token') || '',
      adminName: localStorage.getItem('zx_admin_name') || '',
      loginForm: { username: '', password: '' },
      loginLoading: false,
      view: 'dashboard',
      // 仪表盘
      dash: { total_users: 0, vip_count: 0, ai_usage_7d: 0, diamond_spend_7d: 0, diamond_grant_7d: 0,
              registration_trend: [], active_trend: [] },
      dashLoading: false,
      regChart: null, dauChart: null,
      // 用户管理
      users: [], userTotal: 0, userPage: 1, userPageSize: 20,
      userKeyword: '', usersLoading: false,
      showAccount: false,
      accountForm: { user_id: '', action: 'reset_password', value: '' },
      showAsset: false,
      assetForm: { user_id: '', asset: 'diamond', amount: 0, reason: '', cur: {} },
      // 三方配置
      configGroups: [], configLoading: false,
      showConfig: false, configForm: { key: '', value: '', masked: '' },
      // 操作日志
      logs: [], logTotal: 0, logPage: 1, logPageSize: 20, logsLoading: false,
      // 内容校对（多 AI 审核队列）
      reviews: [], reviewTotal: 0, reviewPage: 1, reviewPageSize: 20, reviewsLoading: false,
      reviewStatus: 'conflict', reviewsRunning: false,
      // 改密
      showChangePwd: false, pwdForm: { old: '', new1: '', new2: '' },
    };
  },
  computed: {
    viewTitle() {
      return { dashboard: '仪表盘', users: '用户管理', config: '三方 API 配置', reviews: '内容校对', logs: '操作日志' }[this.view] || '';
    },
  },
  methods: {
    msg(text, type = 'success') { ElementPlus.ElMessage[type](text); },

    async api(path, options = {}) {
      const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
      if (this.token) headers['Authorization'] = 'Bearer ' + this.token;
      const res = await fetch('/api/admin' + path, { ...options, headers });
      if (res.status === 401) { this.logout(); throw new Error('登录已失效'); }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `请求失败(${res.status})`);
      return data;
    },

    // ── 登录/退出 ──
    async doLogin() {
      if (!this.loginForm.username || !this.loginForm.password) return this.msg('请输入账号和密码', 'warning');
      this.loginLoading = true;
      try {
        const d = await this.api('/login', { method: 'POST', body: JSON.stringify(this.loginForm) });
        this.token = d.token; this.adminName = d.username;
        localStorage.setItem('zx_admin_token', d.token);
        localStorage.setItem('zx_admin_name', d.username);
        this.goView('dashboard');
      } catch (e) { this.msg(e.message, 'error'); }
      finally { this.loginLoading = false; }
    },
    logout() {
      this.token = ''; this.adminName = '';
      localStorage.removeItem('zx_admin_token');
      localStorage.removeItem('zx_admin_name');
    },

    goView(v) {
      this.view = v;
      if (v === 'dashboard') this.loadDashboard();
      if (v === 'users') this.loadUsers(1);
      if (v === 'config') this.loadConfig();
      if (v === 'reviews') this.loadReviews(1);
      if (v === 'logs') this.loadLogs(1);
    },

    // ── 仪表盘 ──
    async loadDashboard() {
      this.dashLoading = true;
      try {
        this.dash = await this.api('/dashboard');
        await nextTick();
        this.renderCharts();
      } catch (e) { this.msg(e.message, 'error'); }
      finally { this.dashLoading = false; }
    },
    // v-if 切换会移除图表 DOM，缓存实例仍存活但绑定在已脱离的节点上，需检测并重建
    _chart(inst, el) {
      if (inst && (inst.isDisposed() || inst.getDom() !== el)) { inst.dispose(); inst = null; }
      return inst || echarts.init(el);
    },
    renderCharts() {
      if (this.$refs.regChart) {
        this.regChart = this._chart(this.regChart, this.$refs.regChart);
        this.regChart.setOption({
          title: { text: '注册趋势（近30天）', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' }, grid: { left: 40, right: 16, top: 44, bottom: 26 },
          xAxis: { type: 'category', data: this.dash.registration_trend.map(p => p.date.slice(5)) },
          yAxis: { type: 'value', minInterval: 1 },
          series: [{ type: 'line', smooth: true, areaStyle: { opacity: .15 },
                     data: this.dash.registration_trend.map(p => p.count) }],
        });
      }
      if (this.$refs.dauChart) {
        this.dauChart = this._chart(this.dauChart, this.$refs.dauChart);
        this.dauChart.setOption({
          title: { text: '日活（近7天）', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' }, grid: { left: 40, right: 16, top: 44, bottom: 26 },
          xAxis: { type: 'category', data: this.dash.active_trend.map(p => p.date.slice(5)) },
          yAxis: { type: 'value', minInterval: 1 },
          series: [{ type: 'bar', barWidth: 22, data: this.dash.active_trend.map(p => p.count) }],
        });
      }
    },

    // ── 用户管理 ──
    async loadUsers(page) {
      this.userPage = page || 1;
      this.usersLoading = true;
      try {
        const d = await this.api(`/users?keyword=${encodeURIComponent(this.userKeyword)}&page=${this.userPage}&page_size=${this.userPageSize}`);
        this.users = d.items; this.userTotal = d.total;
      } catch (e) { this.msg(e.message, 'error'); }
      finally { this.usersLoading = false; }
    },
    openAccount(row) {
      this.accountForm = { user_id: row.user_id, action: 'reset_password', value: '' };
      this.showAccount = true;
    },
    async submitAccount() {
      try {
        const d = await this.api('/users/account', { method: 'POST', body: JSON.stringify(this.accountForm) });
        this.msg(d.detail); this.showAccount = false; this.loadUsers(this.userPage);
      } catch (e) { this.msg(e.message, 'error'); }
    },
    openAsset(row) {
      this.assetForm = { user_id: row.user_id, asset: 'diamond', amount: 0, reason: '',
                         cur: { diamonds: row.diamonds, coins: row.coins, makeup_cards: row.makeup_cards } };
      this.showAsset = true;
    },
    async submitAsset() {
      if (!this.assetForm.amount) return this.msg('数量不能为 0', 'warning');
      if (!this.assetForm.reason.trim()) return this.msg('调整理由必填', 'warning');
      try {
        const d = await this.api('/assets/adjust', {
          method: 'POST',
          body: JSON.stringify({ user_id: this.assetForm.user_id, asset: this.assetForm.asset,
                                 amount: this.assetForm.amount, reason: this.assetForm.reason }),
        });
        this.msg(d.detail); this.showAsset = false; this.loadUsers(this.userPage);
      } catch (e) { this.msg(e.message, 'error'); }
    },
    async toggleVip(row) {
      const action = row.is_vip ? 'remove' : 'add';
      try {
        await this.api('/vip', { method: 'POST', body: JSON.stringify({ user_id: row.user_id, action }) });
        this.msg(action === 'add' ? '已开通 VIP' : '已取消 VIP');
        this.loadUsers(this.userPage);
      } catch (e) { this.msg(e.message, 'error'); }
    },

    // ── 三方配置 ──
    async loadConfig() {
      this.configLoading = true;
      try {
        const d = await this.api('/config');
        this.configGroups = d.groups;
      } catch (e) { this.msg(e.message, 'error'); }
      finally { this.configLoading = false; }
    },
    openConfig(row) {
      this.configForm = { key: row.key, value: '', masked: row.value };
      this.showConfig = true;
    },
    async submitConfig() {
      try {
        await this.api('/config', { method: 'POST', body: JSON.stringify(this.configForm) });
        this.msg('配置已保存，60 秒内生效'); this.showConfig = false; this.loadConfig();
      } catch (e) { this.msg(e.message, 'error'); }
    },

    // ── 操作日志 ──
    async loadLogs(page) {
      this.logPage = page || 1;
      this.logsLoading = true;
      try {
        const d = await this.api(`/logs?page=${this.logPage}&page_size=${this.logPageSize}`);
        this.logs = d.items; this.logTotal = d.total;
      } catch (e) { this.msg(e.message, 'error'); }
      finally { this.logsLoading = false; }
    },

    // ── 内容校对（多 AI 审核队列）──
    async loadReviews(page) {
      this.reviewPage = page || 1;
      this.reviewsLoading = true;
      try {
        const d = await this.api(`/reviews?status=${encodeURIComponent(this.reviewStatus)}&page=${this.reviewPage}&page_size=${this.reviewPageSize}`);
        this.reviews = d.items; this.reviewTotal = d.total;
      } catch (e) { this.msg(e.message, 'error'); }
      finally { this.reviewsLoading = false; }
    },
    async runReviews() {
      this.reviewsRunning = true;
      try {
        const d = await this.api('/reviews/run', { method: 'POST', body: JSON.stringify({ limit: 50 }) });
        this.msg(`校对 ${d.reviewed} 条（通过 ${d.approved}，分歧 ${d.conflict}）`);
        this.loadReviews(this.reviewPage);
      } catch (e) { this.msg(e.message, 'error'); }
      finally { this.reviewsRunning = false; }
    },
    async resolveReview(row, verdict) {
      try {
        await this.api('/reviews/resolve', {
          method: 'POST',
          body: JSON.stringify({ content_type: row.content_type, content_id: row.content_id, verdict }),
        });
        this.msg(verdict === 'approved' ? '已采纳（approved）' : '已驳回（rejected）');
        this.loadReviews(this.reviewPage);
      } catch (e) { this.msg(e.message, 'error'); }
    },

    // ── 改密 ──
    async submitChangePwd() {
      if (this.pwdForm.new1 !== this.pwdForm.new2) return this.msg('两次输入的新密码不一致', 'warning');
      try {
        await this.api('/change-password', {
          method: 'POST',
          body: JSON.stringify({ old_password: this.pwdForm.old, new_password: this.pwdForm.new1 }),
        });
        this.msg('密码已修改，请重新登录'); this.showChangePwd = false; this.logout();
      } catch (e) { this.msg(e.message, 'error'); }
    },
  },
  mounted() {
    if (this.token) this.goView('dashboard');
    window.addEventListener('resize', () => {
      this.regChart && this.regChart.resize();
      this.dauChart && this.dauChart.resize();
    });
  },
});
app.use(ElementPlus, { locale: window.ElementPlusLocaleZhCn });
app.mount('#admin');
