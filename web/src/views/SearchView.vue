<template>
  <div class="search-view">
    <h2 class="page-title">🔍 搜题智能解答</h2>
    <p class="page-tip">把课内作业、试卷上的题粘贴进来，AI 帮你讲解（文字录入；拍照搜题下期开放）。</p>

    <div class="card">
      <div class="row">
        <select v-model="subject" class="sel">
          <option value="">不指定学科</option>
          <option>语文</option><option>数学</option><option>英语</option>
        </select>
        <button class="btn btn-photo" disabled title="敬请期待">📷 拍照（敬请期待）</button>
      </div>
      <textarea v-model="question" class="ta" rows="4" maxlength="500"
                placeholder="请输入或粘贴题干（最多 500 字）"></textarea>
      <div class="row between">
        <span class="cnt">{{ question.length }}/500</span>
        <button class="btn btn-primary" :disabled="!question.trim() || loading" @click="ask">
          {{ loading ? '解答中…' : '求解' }}
        </button>
      </div>
      <div v-if="askError" class="err">{{ askError }}</div>
    </div>

    <!-- 求解结果展示区 -->
    <div v-if="result" class="card answer-card">
      <div class="tag" :class="result.hit ? 'tag-green' : 'tag-blue'">
        {{ result.hit ? '题库命中' : 'AI 解答' }}<span v-if="result.cached"> · 缓存秒回</span>
      </div>

      <div v-if="result.hit" class="block">
        <div class="q">{{ result.question }}</div>
        <div class="a"><b>参考答案：</b>{{ result.answer }}</div>
        <div v-if="result.explanation" class="exp"><b>解析：</b>{{ result.explanation }}</div>
      </div>
      <div v-else class="block ai-text">{{ result.ai_text }}</div>

      <div class="row between mt">
        <span class="cost">消耗钻石：{{ result.diamond_cost ?? 0 }}</span>
        <button class="btn btn-ghost" @click="addWrong">＋ 加入错题本</button>
      </div>
    </div>

    <!-- 搜题历史区 -->
    <div class="card">
      <div class="sub-title">📚 我的搜题历史</div>
      <div v-if="!history.length" class="empty">暂无搜题记录</div>
      <ul class="hist">
        <li v-for="(h, i) in history" :key="i" @click="reuse(h)">
          <span class="h-q">{{ h.question }}</span>
          <span class="h-time">{{ h.created_at }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
import { api } from '../api/http.js'
export default {
  name: 'SearchView',
  // 搜题组件：粘贴题干 → 调接口求解（题库命中或 AI 生成），可加入错题本并查看历史
  data() {
    let user = ''
    try { const z = JSON.parse(localStorage.getItem('zx_user') || '{}'); user = z.user || '' } catch (e) {}
    return {
      user,            // 当前登录用户（来自 localStorage 的 zx_user）
      subject: '',     // 选填学科，不指定则留空
      question: '',    // 题干输入
      result: null,    // 求解结果（含命中标记 / AI 文本 / 费用）
      loading: false,  // 求解中
      askError: '',    // 求解失败提示
      history: [],     // 历史搜题列表
    }
  },
  mounted() { this.loadHistory() },
  methods: {
    // 提交求解：组装请求体（可选学科），命中/未命中均回填 result 并刷新历史
    async ask() {
      this.loading = true; this.askError = ''
      try {
        const body = { user_id: this.user, question_text: this.question.trim() }
        if (this.subject) body.subject = this.subject
        const r = await api('/api/search/ask', { method: 'POST', body: JSON.stringify(body) })
        this.result = r
        this.loadHistory()
      } catch (e) { this.askError = e.message || '求解失败' }
      finally { this.loading = false }
    },
    // 把当前结果加入错题本：命中题取答案，AI 题取 ai_text
    async addWrong() {
      if (!this.result) return
      const answer = this.result.hit ? (this.result.answer || '') : (this.result.ai_text || '')
      try {
        await api('/api/search/to-wrong', { method: 'POST',
          body: JSON.stringify({ user_id: this.user, question: this.question.trim(),
                                 answer, subject: this.subject }) })
        alert('已加入错题本')
      } catch (e) { alert(e.message || '加入失败') }
    },
    // 拉取最近 50 条搜题历史（容错为空）
    async loadHistory() {
      try {
        const r = await api(`/api/search/history?user_id=${encodeURIComponent(this.user)}`)
        this.history = (r.history || []).slice(0, 50)
      } catch (e) { this.history = [] }
    },
    // 点击历史项回填题干/学科并回到顶部，方便重问
    reuse(h) { this.question = h.question; if (h.subject) this.subject = h.subject; window.scrollTo(0, 0) }
  }
}
</script>

<style scoped>
.search-view { padding: 8px; }
.page-title { font-size: 20px; margin: 6px 0; }
.page-tip { color: #888; font-size: 13px; margin: 0 0 10px; }
.card { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.row { display: flex; gap: 8px; align-items: center; }
.row.between { justify-content: space-between; }
.sel { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid #e0e0e0; }
.btn { border: none; border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 14px; }
.btn-primary { background: #4c8bf5; color: #fff; }
.btn-ghost { background: #eef3ff; color: #4c8bf5; }
.btn-photo { background: #f0f0f0; color: #999; }
.ta { width: 100%; border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px; margin: 10px 0; resize: vertical; font-size: 14px; box-sizing: border-box; }
.cnt { color: #aaa; font-size: 12px; }
.err { color: #e74c3c; font-size: 13px; margin-top: 8px; }
.tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; margin-bottom: 8px; }
.tag-green { background: #e6f9ed; color: #1aa260; }
.tag-blue { background: #eaf2ff; color: #4c8bf5; }
.block { font-size: 15px; line-height: 1.7; }
.q { font-weight: 600; margin-bottom: 6px; }
.exp { color: #666; margin-top: 6px; }
.ai-text { white-space: pre-wrap; }
.mt { margin-top: 10px; }
.cost { color: #999; font-size: 13px; }
.sub-title { font-weight: 600; margin-bottom: 8px; }
.empty { color: #aaa; text-align: center; padding: 12px; }
.hist { list-style: none; padding: 0; margin: 0; }
.hist li { display: flex; justify-content: space-between; padding: 8px 4px; border-bottom: 1px solid #f2f2f2; cursor: pointer; }
.h-q { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h-time { color: #bbb; font-size: 12px; margin-left: 8px; }
</style>
