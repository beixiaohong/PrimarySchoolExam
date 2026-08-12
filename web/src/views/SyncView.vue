<template>
  <div class="sync-view">
    <h2 class="page-title">📚 同步学</h2>

    <div class="card">
      <div class="tabs">
        <button v-for="s in subjects" :key="s" class="tab" :class="{on: subject===s}" @click="switchSubject(s)">{{ s }}</button>
      </div>
      <label class="next"><input type="checkbox" v-model="includeNext" @change="loadOverview"> 包含下学期预习单元</label>
    </div>

    <div v-if="loading" class="card empty">加载中…</div>
    <div v-else class="units">
      <div v-for="u in units" :key="u.unit" class="card unit"
           :class="{open: active && active.unit===u.unit}">
        <div class="u-head" @click="selectUnit(u)">
          <div>
            <div class="u-name">{{ u.unit_label }}</div>
            <div class="u-meta">最佳 {{ u.quiz_best }} 分 · 小测 {{ u.total_quizzes }} 次</div>
          </div>
          <span class="tag" :class="statusClass(u.status)">{{ u.status }}</span>
        </div>

        <div v-if="active && active.unit===u.unit" class="u-body">
          <!-- 要点 -->
          <div class="sub-title">📌 本单元要点（{{ points.length }}）</div>
          <div class="points">
            <span v-for="(p, i) in points" :key="i" class="pt">
              {{ subject==='英语' ? (p.word+' '+p.meaning) : subject==='语文' ? p.title : p.name }}
            </span>
          </div>

          <!-- 同步练习 -->
          <div class="sub-title">✏️ 同步练习</div>
          <button class="btn btn-ghost" @click="startPractice">生成练习</button>
          <div v-if="practice.length" class="practice">
            <div v-for="(it, i) in practice" :key="i" class="p-item">
              <div class="p-q">{{ i+1 }}. {{ it.question }}</div>
              <div v-if="it.kind==='choice'" class="opts">
                <button v-for="(o, j) in it.options" :key="j" class="opt"
                        :class="picked[i]===j ? (o===it.answer?'opt-ok':'opt-bad') : ''"
                        @click="pick(i, j, it)">{{ o }}</button>
              </div>
              <div v-else class="fill">
                <input v-model="fillAns[i]" class="fi" placeholder="输入答案" @keyup.enter="judgeFill(i, it)">
                <button class="btn btn-mini" @click="judgeFill(i, it)">判分</button>
                <span v-if="fillBack[i]!==undefined" class="fb" :class="fillBack[i]?'ok':'bad'">
                  {{ fillBack[i] ? '✓' : '✗ 正确答案：'+it.answer }}
                </span>
              </div>
            </div>
          </div>

          <!-- 单元小测 -->
          <div class="sub-title">📝 单元小测</div>
          <button class="btn btn-primary" @click="startQuiz">开始小测（10 题）</button>
          <div v-if="quiz.questions.length" class="quiz">
            <div v-for="(q, i) in quiz.questions" :key="i" class="p-item">
              <div class="p-q">{{ i+1 }}. {{ q.question }}</div>
              <div v-if="q.kind==='choice'" class="opts">
                <button v-for="(o, j) in q.options" :key="j" class="opt"
                        :class="quizPicked[i]===j?'opt-sel':''" @click="quizPicked[i]=j">{{ o }}</button>
              </div>
              <div v-else class="fill">
                <input v-model="quizFill[i]" class="fi" placeholder="输入答案">
              </div>
            </div>
            <button class="btn btn-primary" @click="submitQuiz">交卷</button>
          </div>
          <div v-if="quizResult" class="quiz-result" :class="quizResult.passed?'ok':'bad'">
            得分 {{ quizResult.score }}（对 {{ quizResult.correct }}/{{ quizResult.total }}）
            {{ quizResult.passed ? '🎉 已过关' : '继续加油' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { api } from '../api/http.js'
export default {
  name: 'SyncView',
  data() {
    let user = '', grade = 6
    try { const z = JSON.parse(localStorage.getItem('zx_user') || '{}'); user = z.user || ''; grade = z.grade || 6 } catch (e) {}
    return {
      user, grade, subjects: ['语文', '数学', '英语'], subject: '英语', includeNext: false,
      units: [], loading: false, active: null, points: [],
      practice: [], picked: {}, fillAns: {}, fillBack: {},
      quiz: { questions: [], token: '' }, quizPicked: {}, quizFill: {}, quizResult: null,
    }
  },
  mounted() { this.loadOverview() },
  methods: {
    switchSubject(s) { this.subject = s; this.active = null; this.loadOverview() },
    statusClass(s) {
      return s === '已过关' ? 'tag-green' : s === '进行中' ? 'tag-orange' : 'tag-gray'
    },
    async loadOverview() {
      this.loading = true
      try {
        const r = await api(`/api/sync/overview?user_id=${encodeURIComponent(this.user)}&subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&include_next=${this.includeNext}`)
        this.units = r.units || []
      } finally { this.loading = false }
    },
    async selectUnit(u) {
      this.active = u; this.practice = []; this.quiz = { questions: [], token: '' }; this.quizResult = null
      this.picked = {}; this.fillAns = {}; this.fillBack = {}
      const r = await api(`/api/sync/unit-points?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&unit=${encodeURIComponent(u.unit)}`)
      this.points = r.points || []
    },
    async startPractice() {
      if (!this.active) return
      const r = await api(`/api/sync/unit-practice?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&unit=${encodeURIComponent(this.active.unit)}`)
      this.practice = r.items || []
      this.picked = {}; this.fillAns = {}; this.fillBack = {}
    },
    pick(i, j, it) {
      if (this.picked[i] !== undefined) return
      this.picked[i] = j
    },
    judgeFill(i, it) {
      if (this.fillBack[i] !== undefined) return
      const ua = (this.fillAns[i] || '').trim().toLowerCase()
      const ca = (it.answer || '').trim().toLowerCase()
      this.fillBack = Object.assign({}, this.fillBack, { [i]: ua === ca })
    },
    async startQuiz() {
      if (!this.active) return
      const r = await api(`/api/sync/unit-quiz/generate?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&unit=${encodeURIComponent(this.active.unit)}`)
      this.quiz = { questions: r.questions || [], token: r.token || '' }
      this.quizPicked = {}; this.quizFill = {}; this.quizResult = null
    },
    async submitQuiz() {
      const answers = this.quiz.questions.map((q, i) => {
        let ua = ''
        if (q.kind === 'choice') {
          const j = this.quizPicked[i]
          ua = (j !== undefined && q.options[j] !== undefined) ? q.options[j] : ''
        } else { ua = this.quizFill[i] || '' }
        return { qid: i, user_answer: ua }
      })
      try {
        const r = await api('/api/sync/unit-quiz', { method: 'POST',
          body: JSON.stringify({ user_id: this.user, subject: this.subject, grade: this.grade,
                                 unit: this.active.unit, token: this.quiz.token, answers }) })
        this.quizResult = r
        this.loadOverview()
      } catch (e) { alert(e.message || '交卷失败') }
    }
  }
}
</script>

<style scoped>
.sync-view { padding: 8px; }
.page-title { font-size: 20px; margin: 6px 0; }
.card { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.tabs { display: flex; gap: 8px; }
.tab { flex: 1; padding: 8px; border: 1px solid #e0e0e0; background: #fff; border-radius: 8px; cursor: pointer; }
.tab.on { background: #4c8bf5; color: #fff; border-color: #4c8bf5; }
.next { display: block; margin-top: 10px; color: #666; font-size: 13px; }
.unit { cursor: pointer; }
.u-head { display: flex; justify-content: space-between; align-items: center; }
.u-name { font-weight: 600; }
.u-meta { color: #999; font-size: 12px; margin-top: 2px; }
.tag { padding: 2px 10px; border-radius: 20px; font-size: 12px; }
.tag-green { background: #e6f9ed; color: #1aa260; }
.tag-orange { background: #fff3e0; color: #e08e0b; }
.tag-gray { background: #f0f0f0; color: #999; }
.u-body { margin-top: 12px; border-top: 1px dashed #eee; padding-top: 10px; }
.sub-title { font-weight: 600; margin: 12px 0 6px; }
.points { display: flex; flex-wrap: wrap; gap: 6px; }
.pt { background: #f4f7ff; color: #4c6bbf; padding: 3px 8px; border-radius: 6px; font-size: 12px; }
.practice, .quiz { margin-top: 8px; }
.p-item { padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.p-q { margin-bottom: 6px; }
.opts { display: flex; flex-wrap: wrap; gap: 6px; }
.opt { padding: 6px 12px; border: 1px solid #e0e0e0; background: #fff; border-radius: 8px; cursor: pointer; font-size: 13px; }
.opt-ok { background: #e6f9ed; border-color: #1aa260; color: #1aa260; }
.opt-bad { background: #fdecec; border-color: #e74c3c; color: #e74c3c; }
.opt-sel { background: #eaf2ff; border-color: #4c8bf5; }
.fill { display: flex; gap: 8px; align-items: center; }
.fi { flex: 1; padding: 6px 10px; border: 1px solid #e0e0e0; border-radius: 8px; }
.btn { border: none; border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 14px; }
.btn-primary { background: #4c8bf5; color: #fff; }
.btn-ghost { background: #eef3ff; color: #4c8bf5; }
.btn-mini { background: #eee; padding: 4px 10px; font-size: 13px; }
.fb { font-size: 13px; margin-left: 6px; }
.fb.ok { color: #1aa260; } .fb.bad { color: #e74c3c; }
.quiz-result { margin-top: 10px; padding: 10px; border-radius: 8px; font-weight: 600; }
.quiz-result.ok { background: #e6f9ed; color: #1aa260; }
.quiz-result.bad { background: #fff3e0; color: #e08e0b; }
.empty { color: #aaa; text-align: center; padding: 12px; }
</style>
