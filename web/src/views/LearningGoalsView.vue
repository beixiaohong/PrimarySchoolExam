<template>
  <div class="lg">
    <!-- 内部四 Tab 导航：页内横向 pill（对齐全局 .pill 风格），不另起竖栏、不底部固定 -->
    <nav class="lg-nav">
      <button v-for="t in tabs" :key="t.key" class="lg-nav-item" :class="{active: sub===t.key}" @click="sub=t.key">
        <span class="lg-nav-ico" v-html="t.icon"></span>
        <span class="lg-nav-label">{{ t.label }}</span>
      </button>
    </nav>

    <main class="lg-main">
      <!-- 读取失败：明确提示 + 重试，不白屏 -->
      <div v-if="loadError" class="lg-box lg-error">
        <p>😢 数据读取失败：{{ loadError }}</p>
        <button class="btn btn-primary" @click="refresh">重试</button>
      </div>

      <!-- ============ 今日 ============ -->
      <section v-else-if="sub==='today'" class="lg-sec">
        <div class="lg-sec-head">
          <h2>今日目标</h2>
          <button class="btn btn-primary" @click="openNew">
            <span v-html="icons.plus"></span> 新建目标
          </button>
        </div>

        <div v-if="goals.length===0" class="lg-box lg-empty">
          <p>还没有学习目标。定一个「有终点、有总量」的目标，比如背完 2000 个单词、读完一本 440 页的书。</p>
          <div class="row">
            <button class="btn btn-primary" @click="openNew">＋ 新建目标</button>
            <button class="btn btn-ghost" @click="seedExamples">载入示例目标</button>
          </div>
        </div>

        <div v-else class="lg-cards">
          <article v-for="g in goals" :key="g.id" class="lg-card"
                   :class="['card-'+g.card_kind, {pinned:g.pinned}]" :style="cardStyle(g)">
            <!-- 逾期 / 休息日 横幅 -->
            <div v-if="g.card_kind==='overdue'" class="banner banner-red">
              <span v-html="icons.warn"></span>
              已逾期 <b>{{ g.overdue_days }}</b> 天 · 截止日 {{ g.deadline }}
              <div class="banner-actions">
                <button class="btn btn-sm btn-primary" @click="openCheckin(g)">立即打卡</button>
                <button class="btn btn-sm btn-ghost" @click="openEdit(g)">调整计划</button>
              </div>
            </div>
            <div v-else-if="g.card_kind==='rest'" class="banner banner-amber">
              <span v-html="icons.rest"></span>
              本周还有 1 次休息日，昨日未打卡<b>不中断</b>连续天数；今日建议量已含昨日未完成部分。
            </div>
            <div v-else-if="g.card_kind==='broken'" class="banner banner-red">
              <span v-html="icons.warn"></span>
              本周休息日已用于其他漏打，昨日未打卡会使连续中断；今日建议量已滚入昨日。
            </div>

            <div class="lg-card-top">
              <div>
                <div class="lg-card-name">{{ g.name }}</div>
                <div class="lg-card-meta">{{ g.current }}/{{ g.total }} {{ g.unit }} · 剩 {{ g.days_left>=0?g.days_left:'—' }} 天</div>
              </div>
              <div class="lg-card-pct" :style="{color: theme(g.color).p}">{{ g.pct }}%</div>
            </div>

            <div class="lg-bar"><div class="lg-bar-fill" :style="{width:g.pct+'%', background: theme(g.color).p}"></div></div>

            <div class="lg-stats">
              <div class="st"><span class="st-n" :style="{color: theme(g.color).p}">{{ g.streak }}</span><span class="st-l">连续天</span></div>
              <div class="st">
                <span class="st-n">{{ g.est.has_est ? g.est.est_date : '暂无推算' }}</span>
                <span class="st-l">{{ g.est.has_est ? (g.est.delta_days<=0?'预计提前':'预计拖后') : '预计完成' }}</span>
              </div>
              <div class="st" v-if="g.est.has_est">
                <span class="st-n" :style="{color: g.est.delta_days<=0?'#16a34a':'#ef4444'}">{{ g.est.delta_days<=0?'提前':'拖后' }} {{ Math.abs(g.est.delta_days) }}天</span>
                <span class="st-l">对比截止日</span>
              </div>
            </div>

            <!-- 用户预案 -->
            <div v-if="g.obstacle" class="lg-plan">
              <div class="lg-plan-row"><span class="lg-plan-tag tag-amber" v-html="icons.block"></span><b>障碍</b>：{{ g.obstacle }}</div>
              <div v-if="g.counter" class="lg-plan-row"><span class="lg-plan-tag tag-green" v-html="icons.light"></span><b>对策</b>：{{ g.counter }}</div>
            </div>

            <div class="lg-card-actions">
              <button class="btn btn-primary" @click="openCheckin(g)">打卡</button>
              <button class="btn btn-ghost" @click="openEdit(g)">编辑</button>
              <button class="btn btn-ghost danger" @click="askDelete(g)">删除</button>
            </div>

            <!-- 删除二次确认 -->
            <div v-if="delTarget===g.id" class="lg-confirm">
              确定删除「{{ g.name }}」？此操作不可恢复。
              <button class="btn btn-sm danger" @click="doDelete(g)">确认删除</button>
              <button class="btn btn-sm btn-ghost" @click="delTarget=null">取消</button>
            </div>
          </article>
        </div>

        <div v-if="goals.length" class="lg-bottom-new">
          <button class="btn btn-primary btn-block" @click="openNew">
            <span v-html="icons.plus"></span> 新建目标
          </button>
        </div>
      </section>

      <!-- ============ 看板 ============ -->
      <section v-else-if="sub==='board'" class="lg-sec">
        <div class="lg-sec-head"><h2>看板</h2></div>
        <div v-if="goals.length===0" class="lg-box lg-empty"><p>暂无目标，先去「今日」新建一个吧。</p></div>
        <div v-else class="lg-board">
          <article v-for="g in goals" :key="g.id" class="lg-board-card" :style="cardStyle(g)">
            <div class="lg-board-head">
              <svg class="ring" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" :stroke="theme(g.color).s" stroke-width="12" fill="none"/>
                <circle cx="60" cy="60" r="52" :stroke="theme(g.color).p" stroke-width="12" fill="none"
                        stroke-linecap="round" :stroke-dasharray="2*Math.PI*52"
                        :stroke-dashoffset="2*Math.PI*52*(1-g.pct/100)" transform="rotate(-90 60 60)"/>
                <text x="60" y="58" text-anchor="middle" class="ring-pct">{{ g.pct }}%</text>
                <text x="60" y="76" text-anchor="middle" class="ring-sub">{{ g.current }}/{{ g.total }}</text>
              </svg>
              <div class="lg-board-name">{{ g.name }}</div>
            </div>
            <div class="lg-stats three">
              <div class="st"><span class="st-n" :style="{color:theme(g.color).p}">{{ g.current }}/{{ g.total }}</span><span class="st-l">完成量</span></div>
              <div class="st"><span class="st-n">{{ g.streak }}</span><span class="st-l">连续天</span></div>
              <div class="st">
                <span class="st-n">{{ g.est.has_est ? g.est.est_date : '暂无推算' }}</span>
                <span class="st-l">预计完成</span>
              </div>
            </div>
            <div v-if="g.obstacle" class="lg-plan mini">
              <div class="lg-plan-row"><span class="lg-plan-tag tag-amber" v-html="icons.block"></span>{{ g.obstacle }}</div>
              <div v-if="g.counter" class="lg-plan-row"><span class="lg-plan-tag tag-green" v-html="icons.light"></span>{{ g.counter }}</div>
            </div>
            <div class="lg-recents">
              <div class="lg-recents-title">最近记录</div>
              <div v-if="!g.recent.length" class="lg-recents-empty">暂无打卡</div>
              <div v-for="r in g.recent" :key="r.id" class="lg-recent">
                <span class="lg-recent-date">{{ r.date }}<i v-if="r.is_backfill" class="badge-back">补</i></span>
                <span class="lg-recent-amt">+{{ r.amount }} {{ g.unit }}</span>
                <span v-if="r.minutes!=null" class="lg-recent-min">· {{ r.minutes }} 分钟</span>
                <button class="lg-recent-del" :title="icons.del" @click="delRecord(r)">×</button>
              </div>
            </div>
          </article>
        </div>

        <!-- 近 14 天投入分钟 分目标堆叠柱状图 -->
        <div v-if="minutesData && minutesData.goals.length" class="lg-box lg-chart">
          <div class="sub-title">近 14 天投入分钟（按目标堆叠）</div>
          <svg class="bars" :viewBox="'0 0 '+(minutesData.dates.length*26+8)+' 200'" preserveAspectRatio="none">
            <line x1="4" :y1="170" :x2="minutesData.dates.length*26+4" y2="170" stroke="#e3e6ef" stroke-width="1"/>
            <g v-for="(d,i) in minutesData.dates" :key="d">
              <rect v-for="(seg,gi) in stackFor(d)" :key="gi"
                    :x="i*26+6" :y="seg.y" :width="14" :height="seg.h" :fill="theme(minutesData.goals[gi].color).p" rx="2"/>
              <text :x="i*26+13" y="186" text-anchor="middle" class="bar-date">{{ d.slice(5) }}</text>
            </g>
          </svg>
          <div class="lg-legend">
            <span v-for="gg in minutesData.goals" :key="gg.id" class="lg-legend-item">
              <i :style="{background:theme(gg.color).p}"></i>{{ gg.name }}
            </span>
          </div>
        </div>
      </section>

      <!-- ============ 周报 ============ -->
      <section v-else-if="sub==='weekly'" class="lg-sec">
        <div class="lg-sec-head">
          <h2>周报</h2>
          <div class="row">
            <button class="btn btn-sm btn-ghost" @click="shiftWeek(-7)">← 上周</button>
            <button class="btn btn-sm btn-ghost" @click="shiftWeek(7)" v-if="!isThisWeek">本周</button>
            <button class="btn btn-sm btn-ghost" @click="shiftWeek(7)" v-if="isThisWeek">下周</button>
          </div>
        </div>
        <div v-if="weekLoadError" class="lg-box lg-error">
          <p>周报读取失败：{{ weekLoadError }}</p><button class="btn btn-primary" @click="loadWeekly()">重试</button>
        </div>
        <div v-else class="lg-box">
          <div class="lg-week-range">本周：{{ weekly.week_start }} ~ {{ weekEnd }}</div>
          <div class="lg-week-cmp">
            <div class="cmp">
              <div class="cmp-n">{{ weekly.this_week.amount }}</div><div class="cmp-l">本周完成量</div>
            </div>
            <div class="cmp">
              <div class="cmp-n">{{ weekly.this_week.days }}</div><div class="cmp-l">打卡天数</div>
            </div>
            <div class="cmp">
              <div class="cmp-n">{{ weekly.this_week.minutes }}</div><div class="cmp-l">投入分钟</div>
            </div>
            <div class="cmp">
              <div class="cmp-n" :style="{color: cmpColor}">{{ cmpText }}</div><div class="cmp-l">环比上周</div>
            </div>
          </div>

          <div class="lg-four">
            <div class="four-col">
              <div class="four-h tag-green">保持</div>
              <textarea v-model="wv.keep" class="ta" rows="3" placeholder="上周做得好的，继续坚持…"></textarea>
            </div>
            <div class="four-col">
              <div class="four-h tag-amber">问题</div>
              <textarea v-model="wv.problem" class="ta" rows="3" placeholder="上周卡住的地方…"></textarea>
            </div>
            <div class="four-col">
              <div class="four-h tag-blue">尝试</div>
              <textarea v-model="wv.try_plan" class="ta" rows="3" placeholder="本周想试的新方法…"></textarea>
            </div>
            <div class="four-col">
              <div class="four-h tag-purple">下周预案</div>
              <textarea v-model="wv.next_plan" class="ta" rows="3" placeholder="下周计划…"></textarea>
            </div>
          </div>
          <div class="row between">
            <button class="btn btn-primary" :disabled="savingWeek" @click="saveWeek">{{ savingWeek?'保存中…':'保存周报' }}</button>
            <button class="btn btn-ghost" @click="genWeekText">一键生成周报文本</button>
          </div>
          <div v-if="weekText" class="lg-weektext">
            <div class="sub-title">周报文本（可复制）</div>
            <pre>{{ weekText }}</pre>
            <button class="btn btn-sm btn-ghost" @click="copyText(weekText)">复制</button>
          </div>
        </div>
      </section>

      <!-- ============ 我的 ============ -->
      <section v-else-if="sub==='mine'" class="lg-sec">
        <div class="lg-sec-head"><h2>我的</h2></div>
        <div class="lg-box">
          <div class="lg-sync">
            <span class="dot" :class="online?'on':'off'"></span>
            在线同步：<b>{{ online?'已连接':'离线' }}</b>
            <span class="lg-sync-time" v-if="lastSync">· 最近同步 {{ lastSync }}</span>
          </div>
          <button class="btn btn-ghost" :disabled="loadError" @click="refresh">手动重新同步</button>

          <hr class="lg-hr"/>
          <div class="sub-title">清空示例 / 全部数据</div>
          <p class="lg-tip">输入「清空」并确认后，将删除你全部目标、打卡记录与周报，且不可恢复。</p>
          <div class="row">
            <input v-model="clearInput" class="inp" placeholder="请输入 清空" />
            <button class="btn danger" :disabled="clearInput!=='清空'" @click="clearAll">清空全部</button>
          </div>

          <hr class="lg-hr"/>
          <div class="sub-title">添加到手机主屏幕</div>
          <ol class="lg-steps">
            <li>打开本页面，点浏览器右上角「分享 / 菜单」按钮</li>
            <li>选择「添加到主屏幕 / Add to Home Screen」</li>
            <li>命名「学习目标」并确认，以后从桌面图标直达</li>
          </ol>
        </div>
      </section>
    </main>

    <!-- 新建 / 编辑 弹层 -->
    <div v-if="showForm" class="mask" @click.self="closeForm">
      <div class="sheet">
        <div class="sheet-h">{{ editing?'编辑目标':'新建目标' }}</div>
        <label class="fld">名称<input v-model="form.name" class="inp" :placeholder="'如：背完 2000 个单词'" maxlength="40"/></label>
        <div class="row">
          <label class="fld grow">单位<input v-model="form.unit" class="inp" placeholder="个/页/节" maxlength="6"/></label>
          <label class="fld grow">总量<input v-model="form.total" class="inp" type="number" min="1"/></label>
        </div>
        <label class="fld">截止日<input v-model="form.deadline" class="inp" type="date"/></label>
        <label class="fld">配色
          <div class="color-pick">
            <button v-for="c in colorKeys" :key="c" class="color-dot" :class="{sel:form.color===c}"
                    :style="{background:theme(c).p}" @click="form.color=c"></button>
          </div>
        </label>
        <label class="fld">最容易拦住我的障碍（选填）
          <textarea v-model="form.obstacle" class="ta" rows="2" placeholder="如：早上起不来"></textarea>
        </label>
        <label class="fld">如果它出现，我就……（选填）
          <textarea v-model="form.counter" class="ta" rows="2" placeholder="如：把任务拆成碎片时间完成"></textarea>
        </label>
        <div class="row between">
          <button class="btn btn-ghost" @click="closeForm">取消</button>
          <button class="btn btn-primary" :disabled="savingForm" @click="saveForm">{{ savingForm?'保存中…':'保存' }}</button>
        </div>
        <div v-if="formErr" class="err">{{ formErr }}</div>
      </div>
    </div>

    <!-- 打卡 弹层 -->
    <div v-if="showCheckin" class="mask" @click.self="closeCheckin">
      <div class="sheet">
        <div class="sheet-h">打卡 · {{ ckGoal.name }}</div>
        <div class="lg-suggest" v-if="ckGoal.daily_suggestion!=null">
          今日建议量：<b>{{ fmt(ckGoal.daily_suggestion) }}</b> {{ ckGoal.unit }}（已预填，可修改）
        </div>
        <label class="fld">完成量（{{ ckGoal.unit }}）
          <input v-model="ck.amount" class="inp" type="number" min="0" step="0.1"/>
        </label>
        <label class="fld">投入分钟（选填）
          <input v-model="ck.minutes" class="inp" type="number" min="0" placeholder="不填则不计入分钟图"/>
        </label>
        <label class="fld">日期
          <input v-model="ck.date" class="inp" type="date" :max="todayStr" :min="minBackDate"/>
          <span v-if="ck.date && ck.date<todayStr" class="badge-back">补记</span>
        </label>
        <div class="row between">
          <button class="btn btn-ghost" @click="closeCheckin">取消</button>
          <button class="btn btn-primary" :disabled="savingCk" @click="saveCheckin">{{ savingCk?'提交中…':'提交打卡' }}</button>
        </div>
        <div v-if="ckErr" class="err">{{ ckErr }}</div>
      </div>
    </div>

    <!-- 全局 toast -->
    <div v-if="toast.show" class="lg-toast" :class="toast.type">{{ toast.msg }}</div>
    <!-- 彩带 -->
    <div v-if="confettiOn" class="confetti">
      <i v-for="n in 36" :key="n" class="cf" :style="confettiStyle(n)"></i>
    </div>
  </div>
</template>

<script>
import { api } from '../api/http.js'
// 目标配色对齐全站设计 Token：purple→全局 --violet，blue→--primary，
// green→--success，amber→--warning，red→--danger，teal 保留作点缀色
const THEMES = {
  purple: { p: '#8B7CF6', s: '#F0EEFE' },
  blue:   { p: '#4E7CF6', s: '#EAF0FE' },
  green:  { p: '#34C77B', s: '#E6F9F0' },
  amber:  { p: '#F5A623', s: '#FEF4E5' },
  red:    { p: '#F2604C', s: '#FEEBEA' },
  teal:   { p: '#14B8A6', s: '#D8F6F1' },
}
const SVG = {
  target: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/></svg>',
  board:  '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 3v18"/></svg>',
  weekly: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V5M4 19h16M9 15l3-4 3 3 4-6"/></svg>',
  mine:   '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6"/></svg>',
  plus:   '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M12 5v14M5 12h14"/></svg>',
  warn:   '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/></svg>',
  rest:   '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9"/><path d="M12 3v9l6 3"/></svg>',
  block:  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/></svg>',
  light:  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10c1 1 1 2 1 3h6c0-1 0-2 1-3a6 6 0 0 0-4-10z"/></svg>',
}
export default {
  name: 'LearningGoalsView',
  data() {
    let user = ''
    try { const z = JSON.parse(localStorage.getItem('zx_user') || '{}'); user = z.user || '' } catch (e) {}
    return {
      user,
      sub: 'today',
      tabs: [
        { key: 'today', label: '今日', icon: SVG.target },
        { key: 'board', label: '看板', icon: SVG.board },
        { key: 'weekly', label: '周报', icon: SVG.weekly },
        { key: 'mine', label: '我的', icon: SVG.mine },
      ],
      icons: SVG,
      colorKeys: Object.keys(THEMES),
      goals: [], serverDate: '', hasExamples: false,
      loadError: '', online: true, lastSync: '',
      showForm: false, editing: null, form: this.blankForm(), formErr: '', savingForm: false,
      showCheckin: false, ckGoal: {}, ck: { amount: '', minutes: '', date: '' }, ckErr: '', savingCk: false,
      delTarget: null,
      minutesData: null,
      weekly: { week_start: '', this_week: { amount: 0, days: 0, minutes: 0 }, last_week: { amount: 0, days: 0, minutes: 0 }, review: null },
      wv: { keep: '', problem: '', try_plan: '', next_plan: '' },
      weekOffset: 0, weekLoadError: '', savingWeek: false, weekText: '',
      clearInput: '',
      toast: { show: false, msg: '', type: '' }, _tt: null,
      confettiOn: false,
    }
  },
  computed: {
    todayStr() { return this.serverDate || new Date().toISOString().slice(0, 10) },
    minBackDate() {
      const t = new Date(this.todayStr); t.setDate(t.getDate() - 6)
      return t.toISOString().slice(0, 10)
    },
    isThisWeek() { return this.weekOffset === 0 },
    weekEnd() {
      if (!this.weekly.week_start) return ''
      const d = new Date(this.weekly.week_start); d.setDate(d.getDate() + 6)
      return d.toISOString().slice(0, 10)
    },
    cmpText() {
      const d = this.weekly.this_week.amount - this.weekly.last_week.amount
      if (this.weekly.last_week.amount === 0) return d > 0 ? '新增' : '—'
      return (d >= 0 ? '+' : '') + d
    },
    cmpColor() { return this.cmpText.startsWith('+') || this.cmpText === '新增' ? '#16a34a' : (this.cmpText === '—' ? '#94a3b8' : '#ef4444') },
  },
  mounted() { this.refresh() },
  methods: {
    blankForm() { return { name: '', unit: '个', total: '', deadline: '', color: 'purple', obstacle: '', counter: '' } },
    theme(c) { return THEMES[c] || THEMES.purple },
    cardStyle(g) { return { borderColor: this.theme(g.color).s, background: 'linear-gradient(180deg,#ffffff,' + this.theme(g.color).s + '55)' } },
    fmt(n) { if (n == null) return ''; const x = Math.round(n * 10) / 10; return Number.isInteger(x) ? String(x) : String(x) },
    toastMsg(m, type = '') { this.toast = { show: true, msg: m, type }; clearTimeout(this._tt); this._tt = setTimeout(() => { this.toast.show = false }, 2400) },

    async refresh() {
      this.loadError = ''
      try {
        const r = await api('/api/learning-goals')
        this.goals = r.goals || []
        this.serverDate = r.server_date || this.todayStr
        this.hasExamples = r.has_examples
        this.online = true
        this.lastSync = new Date().toLocaleString('zh-CN')
        if (this.goals.length === 0 && !localStorage.getItem('lg_cleared')) {
          await this.seedExamples(true)
        }
        if (this.sub === 'board') this.loadMinutes()
        if (this.sub === 'weekly') this.loadWeekly()
      } catch (e) {
        this.loadError = e.message || '网络错误'
        this.online = false
      }
    },

    async seedExamples(silent) {
      try {
        await api('/api/learning-goals/seed-examples', { method: 'POST' })
        localStorage.removeItem('lg_cleared')
        await this.refresh()
        if (!silent) this.toastMsg('已载入示例目标')
      } catch (e) { if (!silent) this.toastMsg('载入失败：' + (e.message || ''), 'err') }
    },

    openNew() { this.editing = null; this.form = this.blankForm(); this.formErr = ''; this.showForm = true },
    openEdit(g) { this.editing = g.id; this.form = { name: g.name, unit: g.unit, total: g.total, deadline: g.deadline || '', color: g.color, obstacle: g.obstacle, counter: g.counter }; this.formErr = ''; this.showForm = true },
    closeForm() { this.showForm = false; this.editing = null },

    async saveForm() {
      this.formErr = ''
      if (!this.form.name.trim()) { this.formErr = '请填写目标名称'; return }
      if (!this.form.total || Number(this.form.total) <= 0) { this.formErr = '总量需大于 0'; return }
      this.savingForm = true
      try {
        if (this.editing) {
          await api('/api/learning-goals/' + this.editing, { method: 'PUT', body: JSON.stringify(this.form) })
        } else {
          await api('/api/learning-goals', { method: 'POST', body: JSON.stringify(this.form) })
        }
        this.closeForm(); this.toastMsg('已保存'); await this.refresh()
        if (this.sub === 'board') this.loadMinutes()
      } catch (e) { this.formErr = e.message || '保存失败' }
      finally { this.savingForm = false }
    },

    askDelete(g) { this.delTarget = this.delTarget === g.id ? null : g.id },
    async doDelete(g) {
      try {
        await api('/api/learning-goals/' + g.id, { method: 'DELETE' })
        this.delTarget = null; this.toastMsg('已删除'); await this.refresh()
        if (this.sub === 'board') this.loadMinutes()
      } catch (e) { this.toastMsg('删除失败：' + (e.message || ''), 'err') }
    },

    openCheckin(g) {
      this.ckGoal = g
      this.ck = { amount: g.daily_suggestion != null ? String(this.fmt(g.daily_suggestion)) : '', minutes: '', date: this.todayStr }
      this.ckErr = ''; this.savingCk = false; this.showCheckin = true
    },
    closeCheckin() { this.showCheckin = false },
    async saveCheckin() {
      const amt = Number(this.ck.amount)
      if (!amt || amt <= 0) { this.ckErr = '完成量需大于 0'; return }
      this.savingCk = true; this.ckErr = ''
      const body = { amount: amt, date: this.ck.date || this.todayStr }
      if (this.ck.minutes !== '' && this.ck.minutes != null) body.minutes = Number(this.ck.minutes)
      try {
        const r = await api('/api/learning-goals/' + this.ckGoal.id + '/checkin', { method: 'POST', body: JSON.stringify(body) })
        this.closeCheckin(); await this.refresh()
        if (this.sub === 'board') this.loadMinutes()
        if (r.just_achieved) this.fireConfetti()
        else this.toastMsg('打卡成功 +' + this.fmt(amt) + ' ' + this.ckGoal.unit)
      } catch (e) { this.ckErr = e.message || '打卡失败' }
      finally { this.savingCk = false }
    },
    async delRecord(r) {
      try {
        await api('/api/learning-goals/checkins/' + r.id, { method: 'DELETE' })
        this.toastMsg('已删除记录'); await this.refresh()
        if (this.sub === 'board') this.loadMinutes()
      } catch (e) { this.toastMsg('删除失败：' + (e.message || ''), 'err') }
    },

    async loadMinutes() {
      try {
        const r = await api('/api/learning-goals/minutes?days=14')
        this.minutesData = r
      } catch (e) { /* 图表非阻断 */ }
    },
    stackFor(date) {
      if (!this.minutesData) return []
      const row = this.minutesData.series[date] || {}
      const maxMin = this.maxMinutes
      let yBase = 170
      const segs = []
      this.minutesData.goals.forEach((gg, gi) => {
        const v = row[gg.id]
        if (!v) return
        const h = maxMin > 0 ? Math.max(2, Math.round(v / maxMin * 150)) : 0
        segs.push({ y: yBase - h, h }); yBase -= h
      })
      return segs
    },
    get maxMinutes() {
      if (!this.minutesData) return 0
      let m = 0
      Object.values(this.minutesData.series).forEach(row => { Object.values(row).forEach(v => { if (v > m) m = v }) })
      return m
    },

    async loadWeekly() {
      this.weekLoadError = ''
      try {
        let ws = ''
        if (this.weekOffset !== 0) {
          const d = new Date(this.todayStr); d.setDate(d.getDate() - d.getDay() + 1 + this.weekOffset); ws = d.toISOString().slice(0, 10)
        }
        const r = await api('/api/learning-goals/weekly' + (ws ? '?week=' + ws : ''))
        this.weekly = r
        this.wv = { keep: (r.review && r.review.keep) || '', problem: (r.review && r.review.problem) || '', try_plan: (r.review && r.review.try_plan) || '', next_plan: (r.review && r.review.next_plan) || '' }
      } catch (e) { this.weekLoadError = e.message || '读取失败' }
    },
    shiftWeek(d) { this.weekOffset += d; this.loadWeekly() },
    async saveWeek() {
      this.savingWeek = true
      try {
        await api('/api/learning-goals/weekly', { method: 'POST', body: JSON.stringify(Object.assign({ week_start: this.weekly.week_start }, this.wv)) })
        this.toastMsg('周报已保存'); await this.loadWeekly()
      } catch (e) { this.toastMsg('保存失败：' + (e.message || ''), 'err') }
      finally { this.savingWeek = false }
    },
    genWeekText() {
      const w = this.weekly, v = this.wv
      const cmp = w.last_week.amount > 0 ? (w.this_week.amount - w.last_week.amount >= 0 ? '比上周多 ' + (w.this_week.amount - w.last_week.amount) : '比上周少 ' + (w.last_week.amount - w.this_week.amount)) : '上周无记录'
      this.weekText = `【学习目标周报】${w.week_start} ~ ${this.weekEnd}\n本周完成量：${w.this_week.amount}　打卡 ${w.this_week.days} 天　投入 ${w.this_week.minutes} 分钟（${cmp}）\n保持：${v.keep || '—'}\n问题：${v.problem || '—'}\n尝试：${v.try_plan || '—'}\n下周预案：${v.next_plan || '—'}`
    },
    copyText(t) { try { navigator.clipboard.writeText(t); this.toastMsg('已复制') } catch (e) { this.toastMsg('复制失败') } },

    async clearAll() {
      if (this.clearInput !== '清空') return
      if (!confirm('确定清空全部学习目标、打卡与周报？此操作不可恢复。')) return
      try {
        await api('/api/learning-goals/clear', { method: 'POST', body: JSON.stringify({ confirm: '清空' }) })
        localStorage.setItem('lg_cleared', '1'); this.clearInput = ''
        this.toastMsg('已清空'); await this.refresh()
      } catch (e) { this.toastMsg('清空失败：' + (e.message || ''), 'err') }
    },

    fireConfetti() {
      this.confettiOn = true; this.toastMsg('🎉 目标达成！', '')
      setTimeout(() => { this.confettiOn = false }, 2600)
    },
    confettiStyle(n) {
      const colors = ['#8B7CF6', '#34C77B', '#F5A623', '#4E7CF6', '#F2604C', '#14B8A6']
      return { left: (n * 2.7) % 100 + '%', background: colors[n % colors.length], animationDelay: (n % 12) * 0.06 + 's', transform: 'rotate(' + (n * 37 % 360) + 'deg)' }
    },
  },
  watch: {
    sub(v) { if (v === 'board' && !this.minutesData) this.loadMinutes(); if (v === 'weekly') this.loadWeekly() },
  },
}
</script>

<style scoped>
.lg { display: flex; flex-direction: column; min-height: 60vh; gap: 14px; }
/* 页内四 Tab：横向 pill，对齐全局 .pill 风格；不另起竖栏、不底部固定，避免与全局 TabBar 叠加 */
.lg-nav { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px; background: var(--bg); border-radius: 20px; }
.lg-nav-item { display: inline-flex; align-items: center; gap: 8px; padding: 9px 18px; border: none;
  background: var(--card); border-radius: 20px; color: var(--text-2); font-size: 14px; font-weight: 500;
  cursor: pointer; box-shadow: var(--shadow); transition: .15s; }
.lg-nav-item .lg-nav-ico { color: var(--text-2); display: inline-flex; }
.lg-nav-item.active { background: var(--primary); color: #fff; box-shadow: 0 6px 14px rgba(78,124,246,.3); }
.lg-nav-item.active .lg-nav-ico { color: #fff; }
.lg-main { flex: 1; min-width: 0; }
.lg-sec-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.lg-sec-head h2 { font-size: 20px; margin: 0; color: var(--text); }
.lg-box { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 14px; box-shadow: var(--shadow); }
.lg-empty { color: var(--text-2); line-height: 1.7; }
.row { display: flex; gap: 10px; align-items: center; } .row.between { justify-content: space-between; }
.btn { border: none; border-radius: var(--radius-sm); padding: 9px 16px; font-size: 14px; cursor: pointer; font-weight: 600; }
.btn-primary { background: var(--primary); color: #fff; box-shadow: 0 6px 16px rgba(78,124,246,.28); }
.btn-primary:hover { background: var(--primary-dark); }
.btn-ghost { background: var(--bg); color: var(--text-2); }
.btn-ghost:hover { background: #E9EDF6; color: var(--text); }
.btn-block { width: 100%; }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn.danger, .btn-ghost.danger { color: var(--danger); }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.lg-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.lg-card { border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 14px 12px; background: var(--card); box-shadow: var(--shadow); position: relative; }
.lg-card.pinned { box-shadow: 0 0 0 2px rgba(78,124,246,.18); }
.lg-card.card-rest { border-color: rgba(245,166,35,.4); }
.lg-card.card-overdue { border-color: rgba(242,96,76,.4); }
.banner { border-radius: var(--radius-sm); padding: 9px 11px; font-size: 13px; line-height: 1.55; margin-bottom: 10px; }
.banner-red { background: var(--danger-light); color: var(--danger); } .banner-amber { background: var(--warning-light); color: var(--warning); }
.banner-actions { margin-top: 8px; display: flex; gap: 8px; }
.lg-card-top { display: flex; justify-content: space-between; align-items: flex-start; }
.lg-card-name { font-size: 16px; font-weight: 700; color: var(--text); }
.lg-card-meta { font-size: 12px; color: var(--text-2); margin-top: 3px; }
.lg-card-pct { font-size: 22px; font-weight: 800; }
.lg-bar { height: 8px; background: #eef0f6; border-radius: 6px; margin: 10px 0; overflow: hidden; }
.lg-bar-fill { height: 100%; border-radius: 6px; transition: width .4s; }
.lg-stats { display: flex; gap: 8px; margin: 8px 0; }
.lg-stats.three { gap: 4px; }
.st { flex: 1; background: var(--bg); border-radius: 9px; padding: 8px 4px; text-align: center; }
.st-n { display: block; font-size: 14px; font-weight: 700; color: var(--text); }
.st-l { display: block; font-size: 11px; color: var(--text-2); margin-top: 2px; }
.lg-plan { background: #fbfbfe; border: 1px dashed #e6e8f2; border-radius: 10px; padding: 8px 10px; margin: 8px 0; font-size: 13px; color: var(--text-2); }
.lg-plan.mini { font-size: 12px; padding: 6px 8px; }
.lg-plan-row { display: flex; gap: 6px; align-items: flex-start; line-height: 1.5; }
.lg-plan-tag { display: inline-flex; width: 18px; height: 18px; border-radius: 50%; align-items: center; justify-content: center; color: #fff; flex-shrink: 0; }
.tag-amber { background: var(--warning); } .tag-green { background: var(--success); } .tag-blue { background: var(--primary); } .tag-purple { background: var(--violet); }
.lg-card-actions { display: flex; gap: 8px; margin-top: 10px; }
.lg-confirm { margin-top: 10px; font-size: 13px; color: var(--danger); background: var(--danger-light); border-radius: 9px; padding: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.lg-bottom-new { margin-top: 16px; }
.lg-board { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.lg-board-card { border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; background: var(--card); box-shadow: var(--shadow); }
.lg-board-head { display: flex; align-items: center; gap: 12px; }
.ring { width: 84px; height: 84px; flex-shrink: 0; } .ring-pct { font-size: 20px; font-weight: 800; fill: var(--text); } .ring-sub { font-size: 11px; fill: var(--text-2); }
.lg-recents { margin-top: 10px; }
.lg-recents-title { font-size: 12px; color: var(--text-2); margin-bottom: 4px; }
.lg-recents-empty { font-size: 12px; color: var(--text-3); }
.lg-recent { display: flex; align-items: center; gap: 6px; font-size: 13px; padding: 4px 0; border-top: 1px dashed #f0f1f6; }
.lg-recent-date { color: var(--text-2); } .lg-recent-amt { font-weight: 700; color: var(--text); }
.lg-recent-min { color: var(--text-3); } .lg-recent-del { margin-left: auto; border: none; background: transparent; color: #c0c4d0; font-size: 18px; cursor: pointer; line-height: 1; }
.badge-back { background: var(--warning); color: #fff; border-radius: 4px; font-size: 10px; padding: 1px 4px; font-style: normal; margin-left: 4px; }
.lg-chart { margin-top: 14px; }
.bars { width: 100%; height: 200px; }
.bar-date { font-size: 8px; fill: var(--text-3); }
.lg-legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 6px; font-size: 12px; color: var(--text-2); }
.lg-legend-item i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: middle; }
.lg-week-range { font-size: 13px; color: var(--text-2); margin-bottom: 10px; }
.lg-week-cmp { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
.cmp { background: var(--bg); border-radius: 10px; padding: 10px; text-align: center; }
.cmp-n { font-size: 18px; font-weight: 800; color: var(--text); } .cmp-l { font-size: 11px; color: var(--text-2); margin-top: 2px; }
.lg-four { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 12px; }
.four-col { background: #fafbff; border: 1px solid #eef0f6; border-radius: 10px; padding: 10px; }
.four-h { font-size: 13px; font-weight: 700; padding: 2px 8px; border-radius: 6px; display: inline-block; margin-bottom: 6px; color: #fff; }
.ta { width: 100%; border: 1px solid var(--border); border-radius: 9px; padding: 8px; font-size: 14px; font-family: inherit; resize: vertical; box-sizing: border-box; }
.ta:focus, .inp:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(78,124,246,.12); }
.lg-weektext pre { white-space: pre-wrap; background: var(--bg); border-radius: 9px; padding: 10px; font-size: 13px; color: var(--text); }
.lg-sync { font-size: 14px; color: var(--text-2); margin-bottom: 8px; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
.dot.on { background: var(--success); } .dot.off { background: #c0c4d0; }
.lg-sync-time { color: var(--text-2); font-size: 12px; }
.lg-hr { border: none; border-top: 1px solid #eef0f6; margin: 14px 0; }
.lg-tip { font-size: 12px; color: var(--text-2); margin: 4px 0 8px; }
.lg-steps { margin: 6px 0 0; padding-left: 18px; color: var(--text-2); font-size: 13px; line-height: 1.8; }
.sub-title { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 8px; }
.inp { border: 1px solid var(--border); border-radius: 9px; padding: 8px 10px; font-size: 14px; width: 100%; box-sizing: border-box; }
.fld { display: block; font-size: 13px; color: var(--text-2); margin: 10px 0; }
.fld.grow { flex: 1; }
.color-pick { display: flex; gap: 8px; margin-top: 6px; }
.color-dot { width: 26px; height: 26px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px var(--border); cursor: pointer; }
.color-dot.sel { box-shadow: 0 0 0 2px var(--primary); }
.mask { position: fixed; inset: 0; background: rgba(31,36,64,.4); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 16px; }
.sheet { background: var(--card); border-radius: var(--radius); padding: 18px; width: 100%; max-width: 420px; box-shadow: var(--shadow-lg); }
.sheet-h { font-size: 17px; font-weight: 800; color: var(--text); margin-bottom: 6px; }
.lg-suggest { background: var(--primary-light); color: var(--primary); border-radius: 9px; padding: 8px 10px; font-size: 13px; margin-bottom: 6px; }
.err { color: var(--danger); font-size: 13px; margin-top: 8px; }
.lg-error { text-align: center; color: var(--danger); }
.lg-toast { position: fixed; left: 50%; bottom: 80px; transform: translateX(-50%); background: var(--text); color: #fff; padding: 10px 18px; border-radius: 10px; font-size: 14px; z-index: 80; box-shadow: var(--shadow-lg); }
.lg-toast.err { background: var(--danger); }
.confetti { position: fixed; inset: 0; pointer-events: none; z-index: 90; overflow: hidden; }
.cf { position: absolute; top: -20px; width: 9px; height: 14px; border-radius: 2px; animation: fall 2.4s linear forwards; }
@keyframes fall { to { transform: translateY(105vh) rotate(540deg); opacity: .9; } }
/* 移动端：四 Tab 同屏横向 pills，列布局收敛，不再底部固定（消除与全局 TabBar 叠加） */
@media (max-width: 640px) {
  .lg-nav { gap: 6px; }
  .lg-nav-item { padding: 8px 14px; font-size: 13px; }
  .lg-cards, .lg-board { grid-template-columns: 1fr; }
  .lg-week-cmp { grid-template-columns: repeat(2, 1fr); }
  .lg-four { grid-template-columns: 1fr; }
}
</style>
