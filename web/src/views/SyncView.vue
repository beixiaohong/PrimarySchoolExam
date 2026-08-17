<template>
  <div class="sync-view">
    <h2 class="page-title">📚 同步学</h2>

    <div class="card">
      <div class="tabs">
        <button v-for="s in subjects" :key="s" class="tab" :class="{on: subject===s}" @click="switchSubject(s)">{{ s }}</button>
      </div>
      <div class="grade-row">
        <label>年级：</label>
        <select v-model="grade" @change="onGradeChange">
          <option v-for="g in gradeOptions" :key="g" :value="g">{{ g }}年级</option>
        </select>
        <label class="next"><input type="checkbox" v-model="includeNext" @change="loadOverview"> 包含下学期预习单元</label>
      </div>
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
              {{ subject==='英语' ? (p.word+' '+p.meaning) : subject==='语文' ? p.title : subject==='数学' ? p.name : (p.question || p.name) }}
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
                <input v-model="fillAns[i]" class="fi" placeholder="输入答案" @compositionstart="composing = true" @compositionend="composing = false" @keydown.enter="!composing && judgeFill(i, it)">
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
  // 同步学组件：按学科/年级浏览课本单元，含单元要点、同步练习、单元小测（10 题过关制）
  data() {
    let user = '', grade = 6
    try { const z = JSON.parse(localStorage.getItem('zx_user') || '{}'); user = z.user || ''; grade = z.grade || 6 } catch (e) {}
    return {
      user, grade,
      composing: false, // IME 输入法组词状态（防 Enter 确认候选词时误触发提交）
      // subjects 复用全局 subjectOptions：初中(grade>=7) 显示九科，小学显示语数英
      subjects: [], subject: '英语', // 默认英语
      gradeOptions: [1, 2, 3, 4, 5, 6, 7, 8, 9],
      includeNext: false, // 是否纳入下学期预习单元
      units: [], loading: false, active: null, points: [], // units=单元总览；active=当前展开单元；points=要点
      practice: [], picked: {}, fillAns: {}, fillBack: {}, // 同步练习：选项选中态/填空答案/判分结果
      quiz: { questions: [], token: '' }, quizPicked: {}, quizFill: {}, quizResult: null, // 单元小测：token 防重复提交
    }
  },
  computed: {
    // 学科 tab：复用全局九科分类（初中六科仅在 grade>=7 时出现）
    subjectTabs() { return (this.$root.subjectOptions && this.$root.subjectOptions()) || ['语文', '数学', '英语'] },
  },
  mounted() {
    this.subjects = this.subjectTabs
    this.loadOverview()
  },
  methods: {
    // 年级变化：刷新学科 tab（初中才显示六科）并重新拉取总览
    onGradeChange() {
      this.subjects = this.subjectTabs
      if (this.subjects.indexOf(this.subject) < 0) this.subject = '英语'
      this.active = null
      this.loadOverview()
    },
    // 切换学科：收起当前单元并重新拉取总览
    switchSubject(s) { this.subject = s; this.active = null; this.loadOverview() },
    // 单元状态 → 标签配色（已过关/进行中/其它）
    statusClass(s) {
      return s === '已过关' ? 'tag-green' : s === '进行中' ? 'tag-orange' : 'tag-gray'
    },
    // 拉取单元总览列表
    async loadOverview() {
      this.loading = true
      try {
        const r = await api(`/api/sync/overview?user_id=${encodeURIComponent(this.user)}&subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&include_next=${this.includeNext}`)
        this.units = r.units || []
      } finally { this.loading = false }
    },
    // 展开单元：清空练习/小测态，并加载该单元要点
    async selectUnit(u) {
      this.active = u; this.practice = []; this.quiz = { questions: [], token: '' }; this.quizResult = null
      this.picked = {}; this.fillAns = {}; this.fillBack = {}
      const r = await api(`/api/sync/unit-points?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&unit=${encodeURIComponent(u.unit)}`)
      this.points = r.points || []
    },
    // 生成同步练习（选择题+填空题）
    async startPractice() {
      if (!this.active) return
      const r = await api(`/api/sync/unit-practice?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&unit=${encodeURIComponent(this.active.unit)}`)
      this.practice = r.items || []
      this.picked = {}; this.fillAns = {}; this.fillBack = {}
    },
    // 选择题作答（仅首次点击有效，答后锁定）
    pick(i, j, it) {
      if (this.picked[i] !== undefined) return
      this.picked[i] = j
    },
    // 填空题判分（仅首次有效），小写归一化比较
    judgeFill(i, it) {
      if (this.fillBack[i] !== undefined) return
      const ua = (this.fillAns[i] || '').trim().toLowerCase()
      const ca = (it.answer || '').trim().toLowerCase()
      this.fillBack = Object.assign({}, this.fillBack, { [i]: ua === ca })
    },
    // 生成单元小测（返回题目与本次 token，token 随交卷回传用于校验）
    async startQuiz() {
      if (!this.active) return
      const r = await api(`/api/sync/unit-quiz/generate?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&unit=${encodeURIComponent(this.active.unit)}`)
      this.quiz = { questions: r.questions || [], token: r.token || '' }
      this.quizPicked = {}; this.quizFill = {}; this.quizResult = null
    },
    // 交卷：汇总各题用户作答（选择/填空），带 token 提交；回填结果并刷新总览（更新过关状态/小测次数）
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
.grade-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; color: #666; font-size: 13px; }
.grade-row select { padding: 4px 8px; border: 1px solid #e0e0e0; border-radius: 8px; }
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
