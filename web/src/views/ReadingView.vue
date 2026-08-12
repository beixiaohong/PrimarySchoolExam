<template>
  <div class="reading-view">
    <h2 class="page-title">📖 阅读专项</h2>

    <div class="card">
      <div class="tabs">
        <button v-for="s in subjects" :key="s" class="tab" :class="{on: subject===s}" @click="switchSubject(s)">{{ s }}</button>
      </div>
      <div class="row">
        <label class="lbl">年级</label>
        <select v-model="grade" class="sel" @change="passage=null;result=null">
          <option v-for="g in gradeOptions" :key="g" :value="g">{{ g }} 年级</option>
        </select>
        <button class="btn btn-primary" :disabled="loading" @click="loadPassage">🎲 抽一篇</button>
      </div>
    </div>

    <div v-if="loading" class="card empty">加载中…</div>

    <div v-else-if="passage" class="card passage">
      <div class="p-title">{{ passage.title }}</div>
      <div class="p-meta">{{ passage.subject }} · {{ passage.grade }} 年级</div>
      <div class="p-text">{{ passage.passage }}</div>

      <div v-for="(q, i) in passage.questions" :key="i" class="q-item">
        <div class="q-q"><b>{{ i+1 }}.</b> {{ q.question }}
          <span class="q-score">（{{ q.score }} 分）</span>
        </div>

        <!-- 客观选择题 -->
        <div v-if="q.type==='choice'" class="opts">
          <button v-for="(o, j) in q.options" :key="j" class="opt"
                  :class="optClass(i, j, q)"
                  @click="choose(i, j)" :disabled="!!result">{{ o }}</button>
        </div>

        <!-- 主观简答 -->
        <div v-else class="fill">
          <textarea v-model="shortAns[i]" class="ta" rows="3" placeholder="写下你的回答…"
                    :disabled="!!result"></textarea>
        </div>

        <!-- 交卷后的逐题解析 -->
        <div v-if="result" class="fb" :class="detailOf(i).correct?'ok':'bad'">
          <span v-if="q.type==='choice'">
            {{ detailOf(i).correct ? '✓ 正确' : '✗ 正确答案：' + detailOf(i).correct_answer }}
          </span>
          <span v-else>
            得分 {{ detailOf(i).earned }}/{{ detailOf(i).max }}
            <span v-if="detailOf(i).comment" class="cmt">｜{{ detailOf(i).comment }}</span>
          </span>
          <div class="exp">参考答案：{{ detailOf(i).explanation }}</div>
        </div>
      </div>

      <button v-if="!result" class="btn btn-primary submit" @click="submit">交卷判分</button>
      <div v-else class="result" :class="result.total_score>=result.max_score*0.6?'ok':'bad'">
        本次得分 <b>{{ result.total_score }}</b> / {{ result.max_score }}
      </div>
    </div>

    <div v-else class="card empty">选择学科与年级，点击「抽一篇」开始阅读训练</div>
  </div>
</template>

<script>
import { api } from '../api/http.js'
export default {
  name: 'ReadingView',
  data() {
    let user = '', grade = 7
    try {
      const z = JSON.parse(localStorage.getItem('zx_user') || '{}')
      user = z.user || ''
      grade = z.grade && z.grade >= 7 ? z.grade : 7
    } catch (e) {}
    return {
      user, subjects: ['语文', '英语'], subject: '英语', grade,
      passage: null, loading: false,
      picked: {}, shortAns: {}, result: null,
    }
  },
  computed: {
    gradeOptions() {
      return this.subject === '英语' ? [7, 8, 9] : [5, 6, 7, 8, 9]
    },
  },
  methods: {
    switchSubject(s) {
      this.subject = s
      this.passage = null; this.result = null; this.picked = {}; this.shortAns = {}
      // 切换到该学科支持的年级范围
      if (this.subject === '英语' && this.grade < 7) this.grade = 7
    },
    async loadPassage() {
      this.loading = true; this.result = null; this.picked = {}; this.shortAns = {}
      try {
        const r = await api(`/api/reading/passages?subject=${encodeURIComponent(this.subject)}&grade=${this.grade}&limit=1`)
        const list = r.passages || []
        this.passage = list.length ? list[0] : null
        if (!this.passage) alert('该年级暂无阅读篇目，换个年级试试')
      } catch (e) {
        alert(e.message || '抽题失败')
      } finally { this.loading = false }
    },
    choose(i, j) {
      if (this.result) return
      this.picked = Object.assign({}, this.picked, { [i]: j })
    },
    optClass(i, j, q) {
      if (!this.result) return this.picked[i] === j ? 'opt-sel' : ''
      const d = this.detailOf(i)
      const correctText = q.options[j]
      if (correctText === d.correct_answer) return 'opt-ok'
      if (this.picked[i] === j) return 'opt-bad'
      return ''
    },
    detailOf(i) {
      if (!this.result) return {}
      return this.result.detail[i] || {}
    },
    async submit() {
      if (!this.passage) return
      const answers = this.passage.questions.map((q, i) => {
        let ua = ''
        if (q.type === 'choice') {
          const j = this.picked[i]
          ua = (j !== undefined && q.options[j] !== undefined) ? q.options[j] : ''
        } else {
          ua = this.shortAns[i] || ''
        }
        return { qid: i, user_answer: ua }
      })
      try {
        const r = await api('/api/reading/submit', { method: 'POST',
          body: JSON.stringify({ user_id: this.user, passage_id: this.passage.id, answers }) })
        this.result = r
      } catch (e) { alert(e.message || '交卷失败') }
    },
  },
}
</script>

<style scoped>
.reading-view { padding: 8px; }
.page-title { font-size: 20px; margin: 6px 0; }
.card { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.tabs { display: flex; gap: 8px; }
.tab { flex: 1; padding: 8px; border: 1px solid #e0e0e0; background: #fff; border-radius: 8px; cursor: pointer; }
.tab.on { background: #4c8bf5; color: #fff; border-color: #4c8bf5; }
.row { display: flex; gap: 10px; align-items: center; margin-top: 12px; }
.lbl { color: #666; font-size: 14px; }
.sel { padding: 7px 10px; border: 1px solid #e0e0e0; border-radius: 8px; }
.btn { border: none; border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 14px; }
.btn-primary { background: #4c8bf5; color: #fff; }
.btn-primary:disabled { opacity: .6; }
.passage { margin-top: 4px; }
.p-title { font-size: 17px; font-weight: 700; }
.p-meta { color: #999; font-size: 12px; margin: 2px 0 8px; }
.p-text { line-height: 1.9; background: #fafbff; border-radius: 8px; padding: 10px; white-space: pre-wrap; }
.q-item { padding: 10px 0; border-bottom: 1px solid #f3f3f3; }
.q-q { margin-bottom: 6px; }
.q-score { color: #aaa; font-size: 12px; font-weight: 400; }
.opts { display: flex; flex-wrap: wrap; gap: 6px; }
.opt { padding: 6px 12px; border: 1px solid #e0e0e0; background: #fff; border-radius: 8px; cursor: pointer; font-size: 13px; }
.opt-sel { background: #eaf2ff; border-color: #4c8bf5; }
.opt-ok { background: #e6f9ed; border-color: #1aa260; color: #1aa260; }
.opt-bad { background: #fdecec; border-color: #e74c3c; color: #e74c3c; }
.fill { margin-top: 4px; }
.ta { width: 100%; padding: 8px 10px; border: 1px solid #e0e0e0; border-radius: 8px; resize: vertical; font-family: inherit; }
.fb { margin-top: 6px; font-size: 13px; padding: 6px 8px; border-radius: 6px; }
.fb.ok { background: #e6f9ed; color: #1aa260; }
.fb.bad { background: #fff3e0; color: #e08e0b; }
.cmt { color: #555; }
.exp { color: #888; font-size: 12px; margin-top: 2px; }
.submit { margin-top: 10px; width: 100%; }
.result { margin-top: 12px; padding: 12px; border-radius: 10px; text-align: center; font-size: 16px; }
.result.ok { background: #e6f9ed; color: #1aa260; }
.result.bad { background: #fff3e0; color: #e08e0b; }
.empty { color: #aaa; text-align: center; padding: 18px; }
</style>
