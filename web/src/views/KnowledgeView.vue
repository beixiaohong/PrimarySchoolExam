<template>
  <div class="kp-view">
    <h2 class="page-title">📚 知识点卡 · 讲解→例子→自测</h2>

    <div class="card">
      <div class="tabs">
        <button v-for="s in subjects" :key="s" class="tab" :class="{on: subject===s}" @click="switchSubject(s)">{{ s }}</button>
      </div>
      <div class="grade-row">
        <label>年级：</label>
        <select v-model="grade" @change="onGradeChange">
          <option v-for="g in gradeOptions" :key="g" :value="g">{{ g }}年级</option>
        </select>
        <label>单元：</label>
        <select v-model="unit" @change="loadList">
          <option value="">全部单元</option>
          <option v-for="u in units" :key="u" :value="u">{{ u }}</option>
        </select>
        <span class="progress">已学 {{ studiedCount }}/{{ list.length }} · 连击 🔥{{ combo }}</span>
      </div>
    </div>

    <div v-if="loading" class="card empty">加载中…</div>
    <div v-else-if="!list.length" class="card empty">该学科/年级暂无知识点（线上库执行过知识点 SQL 后才会有数据）</div>
    <div v-else class="kps">
      <div v-for="kp in list" :key="kp.id" class="card kp" :class="{open: active===kp.id, done: studied[kp.id]}">
        <div class="k-head" @click="selectKP(kp)">
          <div class="k-head-main">
            <div class="k-title">{{ kp.title }} <span v-if="studied[kp.id]" class="ok-badge">✓已学</span></div>
            <div class="k-meta">{{ kp.unit }} · 难度 {{ '★'.repeat(kp.difficulty) }}</div>
            <div class="k-sum">{{ kp.summary }}</div>
          </div>
          <span class="arrow">{{ active===kp.id ? '▾' : '▸' }}</span>
        </div>

        <div v-if="active===kp.id && details[kp.id]" class="k-body">
          <div class="sub-title">📖 讲解</div>
          <div class="k-content">{{ details[kp.id].content || '（暂无详细讲解，先看一句话要点）' }}</div>

          <div v-if="details[kp.id].examples && details[kp.id].examples.length" class="sub-title">💡 例子</div>
          <ul v-if="details[kp.id].examples && details[kp.id].examples.length" class="ex-list">
            <li v-for="(ex, i) in details[kp.id].examples" :key="i">{{ ex }}</li>
          </ul>

          <div class="sub-title">✍️ 挖空自测（填回挖空处，检验是否真懂）</div>
          <button v-if="!cloze[kp.id]" class="btn btn-ghost" @click="startCloze(kp)" :disabled="loadingCloze">开始自测</button>
          <div v-else class="cloze">
            <div v-for="(it, i) in cloze[kp.id]" :key="i" class="c-item">
              <div class="c-q">{{ i+1 }}. {{ it.sentence }}</div>
              <div class="fill">
                <input v-model="answers[kp.id][i]" class="fi" placeholder="填入挖空处" @keydown.enter="checkCloze(kp)">
                <span v-if="feedback[kp.id] && feedback[kp.id][i]!==undefined" class="fb" :class="feedback[kp.id][i]?'ok':'bad'">
                  {{ feedback[kp.id][i] ? '✓' : '✗ 答案：'+it.answer }}
                </span>
              </div>
            </div>
            <button class="btn btn-primary" @click="checkCloze(kp)">检查</button>
          </div>

          <button class="btn btn-master" @click="markMaster(kp)">我学会了 +3🪙</button>
        </div>
      </div>
    </div>

    <div v-if="toast.show" class="toast">🪙 +{{ toast.coins_gained }}　{{ toast.text }}</div>
  </div>
</template>

<script>
import { api } from '../api/http.js'
export default {
  name: 'KnowledgeView',
  // 知识点卡：把 knowledge_points 死数据变成「讲解→例子→挖空自测」互动卡，
  // 自测全对/标记掌握发 +3 金币，制造即时正反馈，解决"知识点枯燥没用上"的问题。
  data() {
    let user = '', grade = 6
    try { const z = JSON.parse(localStorage.getItem('zx_user') || '{}'); user = z.user || ''; grade = z.grade || 6 } catch (e) {}
    return {
      user, grade,
      subjects: [], subject: '数学',
      gradeOptions: [1, 2, 3, 4, 5, 6, 7, 8, 9],
      units: [], unit: '',
      list: [], loading: false, loadingCloze: false, active: null,
      details: {}, cloze: {}, answers: {}, feedback: {},
      studied: {}, combo: 0, studiedCount: 0,
      toast: { show: false, text: '', coins_gained: 0 },
    }
  },
  computed: {
    // 学科 tab：复用全局九科分类（初中 grade>=7 显示九科，小学显示语数英）
    subjectTabs() { return (this.$root.subjectOptions && this.$root.subjectOptions()) || ['语文', '数学', '英语'] },
  },
  mounted() {
    this.subjects = this.subjectTabs
    if (this.grade >= 7 && this.subjects.indexOf(this.subject) < 0) this.subject = '语文'
    this.loadUnits(); this.loadList()
  },
  methods: {
    switchSubject(s) { this.subject = s; this.unit = ''; this.active = null; this.loadUnits(); this.loadList() },
    onGradeChange() {
      this.subjects = this.subjectTabs
      if (this.subjects.indexOf(this.subject) < 0) this.subject = this.subjects[0] || '语文'
      this.unit = ''; this.active = null; this.loadUnits(); this.loadList()
    },
    async loadUnits() {
      try {
        const r = await api(`/api/knowledge/units?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}`)
        this.units = r || []
      } catch (e) { this.units = [] }
    },
    async loadList() {
      this.loading = true
      this.active = null
      try {
        const r = await api(`/api/knowledge?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&unit=${encodeURIComponent(this.unit)}`)
        this.list = r || []
      } finally { this.loading = false }
    },
    async selectKP(kp) {
      // 再点一次收起
      if (this.active === kp.id) { this.active = null; return }
      this.active = kp.id
      if (!this.details[kp.id]) {
        const r = await api(`/api/knowledge/${kp.id}`)
        this.details = Object.assign({}, this.details, { [kp.id]: r })
      }
    },
    async startCloze(kp) {
      this.loadingCloze = true
      try {
        const r = await api(`/api/knowledge/${kp.id}/cloze`)
        const items = r.items || []
        this.cloze = Object.assign({}, this.cloze, { [kp.id]: items })
        this.answers = Object.assign({}, this.answers, { [kp.id]: items.map(() => '') })
        this.feedback = Object.assign({}, this.feedback, { [kp.id]: items.map(() => undefined) })
      } catch (e) { alert(e.message || '该知识点暂无可用于自测的文本') } finally { this.loadingCloze = false }
    },
    checkCloze(kp) {
      const items = this.cloze[kp.id] || []
      if (!items.length) return
      const ans = this.answers[kp.id] || []
      const fb = items.map((it, i) => (ans[i] || '').trim().toLowerCase() === it.answer.trim().toLowerCase())
      this.feedback = Object.assign({}, this.feedback, { [kp.id]: fb })
      if (fb.every(Boolean)) this.grantMaster(kp, true)
    },
    markMaster(kp) { this.grantMaster(kp, true) },
    async grantMaster(kp, allCorrect) {
      if (this.studied[kp.id]) { this.showToast('这个知识点已经学过啦，复习一下～', 0); return }
      try {
        const r = await api(`/api/knowledge/${kp.id}/master`, {
          method: 'POST', body: JSON.stringify({ user_id: this.user, all_correct: allCorrect }),
        })
        if (r.granted > 0) {
          this.studied = Object.assign({}, this.studied, { [kp.id]: true })
          this.studiedCount = Object.keys(this.studied).length
          this.combo += 1
          this.showToast(r.message, r.granted)
        } else {
          this.showToast(r.message, 0)
        }
      } catch (e) { alert(e.message || '操作失败') }
    },
    showToast(text, gained) {
      this.toast = { show: true, text, coins_gained: gained }
      setTimeout(() => { this.toast = { show: false, text: '', coins_gained: 0 } }, 2200)
    },
  },
}
</script>

<style scoped>
.kp-view { padding: 8px; }
.page-title { font-size: 20px; margin: 6px 0; }
.card { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.tab { flex: 1; min-width: 56px; padding: 8px; border: 1px solid #e0e0e0; background: #fff; border-radius: 8px; cursor: pointer; font-size: 13px; }
.tab.on { background: #4c8bf5; color: #fff; border-color: #4c8bf5; }
.grade-row { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 10px; color: #666; font-size: 13px; }
.grade-row select { padding: 4px 8px; border: 1px solid #e0e0e0; border-radius: 8px; }
.progress { margin-left: auto; color: #4c8bf5; font-weight: 600; }
.kps { display: flex; flex-direction: column; gap: 12px; }
.kp { cursor: pointer; transition: box-shadow .15s; }
.kp.open { box-shadow: 0 4px 16px rgba(76,139,245,.12); }
.kp.done { border-left: 4px solid #1aa260; }
.k-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.k-head-main { flex: 1; }
.k-title { font-weight: 600; font-size: 15px; }
.ok-badge { background: #e6f9ed; color: #1aa260; font-size: 11px; padding: 1px 6px; border-radius: 10px; margin-left: 4px; }
.k-meta { color: #999; font-size: 12px; margin-top: 2px; }
.k-sum { color: #555; font-size: 13px; margin-top: 4px; }
.arrow { color: #bbb; font-size: 18px; }
.k-body { margin-top: 12px; border-top: 1px dashed #eee; padding-top: 10px; cursor: default; }
.sub-title { font-weight: 600; margin: 12px 0 6px; }
.k-content { color: #333; font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
.ex-list { margin: 0; padding-left: 18px; color: #555; font-size: 13px; line-height: 1.7; }
.cloze { margin-top: 8px; }
.c-item { padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.c-q { margin-bottom: 6px; line-height: 1.6; }
.fill { display: flex; gap: 8px; align-items: center; }
.fi { flex: 1; padding: 6px 10px; border: 1px solid #e0e0e0; border-radius: 8px; }
.fb { font-size: 13px; margin-left: 6px; }
.fb.ok { color: #1aa260; } .fb.bad { color: #e74c3c; }
.btn { border: none; border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 14px; margin-top: 8px; }
.btn-primary { background: #4c8bf5; color: #fff; }
.btn-ghost { background: #eef3ff; color: #4c8bf5; }
.btn-master { background: linear-gradient(135deg,#ffd86b,#ff9f43); color: #7a4b00; font-weight: 600; }
.btn:disabled { opacity: .6; cursor: default; }
.toast {
  position: fixed; left: 50%; bottom: 80px; transform: translateX(-50%);
  background: #2d2d2d; color: #fff; padding: 10px 18px; border-radius: 22px;
  font-size: 14px; z-index: 999; box-shadow: 0 6px 20px rgba(0,0,0,.25);
  animation: pop .25s ease;
}
@keyframes pop { from { transform: translateX(-50%) scale(.8); opacity: 0; } to { transform: translateX(-50%) scale(1); opacity: 1; } }
.empty { color: #aaa; text-align: center; padding: 12px; }
</style>
