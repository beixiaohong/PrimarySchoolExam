<template>
  <div class="sc">
    <!-- 顶部：连续打卡 + 累计统计 -->
    <div class="sc-hero" v-if="!loadError">
      <div class="sc-streak">
        <div class="sc-streak-num">🔥 {{ data.streak }}</div>
        <div class="sc-streak-label">连续学习天数</div>
      </div>
      <div class="sc-stats">
        <div class="sc-stat"><b>{{ data.total_days }}</b><span>累计打卡天</span></div>
        <div class="sc-stat"><b>{{ data.total_tasks_done }}</b><span>完成任务数</span></div>
        <div class="sc-stat"><b>{{ Math.round(data.total_focus_minutes) }}</b><span>专注分钟</span></div>
      </div>
    </div>

    <!-- 加载/错误 -->
    <div v-if="loadError" class="sc-box sc-error">
      <p>😢 日历读取失败：{{ loadError }}</p>
      <button class="btn btn-primary" @click="refresh">重试</button>
    </div>

    <!-- 热力月历：按月堆叠 -->
    <div v-else class="sc-months">
      <div class="sc-month" v-for="m in months" :key="m.key">
        <div class="sc-month-head">{{ m.label }}</div>
        <div class="sc-weekdays">
          <span v-for="w in weekLabels" :key="w" class="sc-wd">{{ w }}</span>
        </div>
        <div class="sc-grid">
          <div v-for="(c, i) in m.cells" :key="i"
               class="sc-cell"
               :class="'lv' + c.level"
               :title="cellTitle(c)">
            <template v-if="c.day">
              <span class="sc-d">{{ c.day }}</span>
              <span v-if="c.mood" class="sc-mood">{{ moodEmoji(c.mood) }}</span>
            </template>
          </div>
        </div>
      </div>
      <div class="sc-legend">
        <span>少</span>
        <i class="sc-cell lv0"></i><i class="sc-cell lv1"></i><i class="sc-cell lv2"></i><i class="sc-cell lv3"></i><i class="sc-cell lv4"></i>
        <span>多</span>
      </div>
    </div>
  </div>
</template>

<script>
import { api } from '../api/http.js'

// 学习日历：自包含视图（对齐 LearningGoalsView 模式，不依赖 appCtx 巨型 mixin）。
// 数据来自 /api/calendar（聚合 daily_tasks / focus_sessions / mood_checkins）。
export default {
  name: 'StudyCalendarView',
  data() {
    let user = ''
    try { const z = JSON.parse(localStorage.getItem('zx_user') || '{}'); user = z.user || '' } catch (e) {}
    return {
      user,
      data: { days: [], streak: 0, total_days: 0, total_focus_minutes: 0, total_tasks_done: 0 },
      loadError: '',
      weekLabels: ['一', '二', '三', '四', '五', '六', '日'],
      weekNames: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
    }
  },
  computed: {
    // 把返回的天列表按月份分组，生成对齐周一的月历网格
    months() {
      const map = {}
      for (const d of (this.data.days || [])) {
        const [y, m] = d.date.split('-')
        const key = y + '-' + m
        if (!map[key]) map[key] = { key, label: y + '年' + Number(m) + '月', items: [] }
        map[key].items.push(d)
      }
      return Object.keys(map).sort().map(k => {
        const grp = map[k]
        const cells = []
        // 每月 1 号星期几（0=周日 → 转成 周一为 0）
        const [y, m] = k.split('-')
        const first = new Date(Number(y), Number(m) - 1, 1).getDay()
        const lead = (first + 6) % 7
        for (let i = 0; i < lead; i++) cells.push({ blank: true, level: 0 })
        for (const it of grp.items) {
          const day = Number(it.date.split('-')[2])
          cells.push({
            day,
            date: it.date,
            level: this.levelOf(it),
            tasks_done: it.tasks_done,
            focus_minutes: it.focus_minutes,
            mood: it.mood,
            checked_in: it.checked_in,
          })
        }
        return { key: grp.key, label: grp.label, cells }
      })
    },
  },
  mounted() { this.refresh() },
  methods: {
    // 热力等级：任务完成 + 专注分钟折算
    levelOf(it) {
      const score = (it.tasks_done || 0) + Math.floor((it.focus_minutes || 0) / 30)
      if (!it.checked_in) return 0
      if (score <= 0) return 1
      if (score <= 2) return 2
      if (score <= 5) return 3
      return 4
    },
    moodEmoji(m) {
      return ({ great: '😄', happy: '🙂', ok: '😐', blue: '😟', sad: '😢' })[m] || ''
    },
    cellTitle(c) {
      if (!c.day) return ''
      let t = c.date
      if (c.checked_in) t += '\n✅ 已打卡'
      if (c.tasks_done) t += '\n完成任务 ' + c.tasks_done + ' 个'
      if (c.focus_minutes) t += '\n专注 ' + c.focus_minutes + ' 分钟'
      if (c.mood) t += '\n心情 ' + c.mood
      if (!c.checked_in) t += '\n未学习'
      return t
    },
    async refresh() {
      this.loadError = ''
      try {
        const r = await api('/api/calendar?user_id=' + encodeURIComponent(this.user || '') + '&days=90')
        this.data = Object.assign({ days: [], streak: 0, total_days: 0, total_focus_minutes: 0, total_tasks_done: 0 }, r)
      } catch (e) {
        this.loadError = e.message || '网络错误'
      }
    },
  },
}
</script>

<style scoped>
.sc { display: flex; flex-direction: column; gap: 14px; padding-top: 4px; }
.sc-hero { display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  background: linear-gradient(135deg,#4E7CF6,#8B7CF6); border-radius: 16px; padding: 18px 20px; color: #fff; box-shadow: 0 8px 20px rgba(78,124,246,.25); }
.sc-streak-num { font-size: 30px; font-weight: 800; line-height: 1.1; }
.sc-streak-label { font-size: 13px; opacity: .9; }
.sc-stats { display: flex; gap: 22px; margin-left: auto; }
.sc-stat { text-align: center; }
.sc-stat b { display: block; font-size: 20px; font-weight: 800; }
.sc-stat span { font-size: 12px; opacity: .85; }

.sc-box { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow); }
.sc-error { text-align: center; color: var(--danger); }

.sc-months { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.sc-month { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; box-shadow: var(--shadow); }
.sc-month-head { font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 10px; }
.sc-weekdays { display: grid; grid-template-columns: repeat(7,1fr); gap: 4px; margin-bottom: 4px; }
.sc-wd { text-align: center; font-size: 11px; color: var(--text-3); }
.sc-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 4px; }
.sc-cell { aspect-ratio: 1 / 1; border-radius: 7px; display: flex; align-items: center; justify-content: center;
  position: relative; font-size: 12px; color: var(--text-2); background: #eef0f6; }
.sc-cell.lv0 { background: #eef0f6; }
.sc-cell.lv1 { background: #d7e6ff; }
.sc-cell.lv2 { background: #aecbff; }
.sc-cell.lv3 { background: #7ea6ff; color: #fff; }
.sc-cell.lv4 { background: #4E7CF6; color: #fff; }
.sc-d { font-weight: 600; }
.sc-mood { position: absolute; right: 2px; bottom: 1px; font-size: 10px; }

.sc-legend { display: flex; align-items: center; gap: 5px; justify-content: flex-end; margin-top: 10px; font-size: 12px; color: var(--text-2); }
.sc-legend i { width: 14px; height: 14px; border-radius: 4px; display: inline-block; }
.sc-legend .lv0, .sc-legend .lv1, .sc-legend .lv2, .sc-legend .lv3, .sc-legend .lv4 { background: #eef0f6; }
.sc-legend .lv1 { background: #d7e6ff; } .sc-legend .lv2 { background: #aecbff; } .sc-legend .lv3 { background: #7ea6ff; } .sc-legend .lv4 { background: #4E7CF6; }
</style>
