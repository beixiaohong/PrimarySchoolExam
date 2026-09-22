<template>
  <div v-if="book">
    <div class="nv-card">
      <div class="nv-detail-top">
        <div class="nv-detail-cover">
          <img v-if="book.cover_url" :src="book.cover_url" :alt="book.title" />
          <span v-else>{{ book.title }}</span>
        </div>
        <div style="flex:1;min-width:0">
          <h2 class="nv-detail-h">{{ book.title }}</h2>
          <div class="nv-detail-m">
            {{ book.author || '佚名' }} · {{ book.category || '未分类' }} ·
            {{ statusText }} · {{ fmtWords(book.word_count) }}字
          </div>
          <div class="nv-detail-m">
            共 {{ book.chapter_count }} {{ unitText }} · {{ book.view_count || 0 }} 次阅读
          </div>
          <div class="nv-actions">
            <button class="nv-btn primary" @click="readFromStart">
              {{ book.chapter_idx > 0 ? '继续阅读' : '开始阅读' }}
            </button>
            <button class="nv-btn" @click="toggleShelf">
              {{ book.in_shelf ? '移出书架' : '加入书架' }}
            </button>
            <button class="nv-btn" @click="shareBook">🔗 分享</button>
          </div>
        </div>
      </div>
      <div class="nv-detail-i" v-if="book.intro">{{ book.intro }}</div>
      <div class="nv-detail-m" style="margin-top:10px">
        阅读方式：{{ book.chapter_mode === 'chapter' ? '已自动分章（可看目录）' : '未识别章节，下滑流式加载' }}
      </div>
    </div>

    <!-- 目录：仅分章模式展示（stream 模式全是空标题，展示无意义） -->
    <div class="nv-card" v-if="book.chapter_mode === 'chapter'">
      <h3 class="nv-title">目录（{{ chapters.length }}/{{ total }}）</h3>
      <div class="nv-chapter-list">
        <div class="nv-chapter" v-for="c in chapters" :key="c.id" @click="readAt(c.idx)">
          {{ c.title || ('第 ' + c.idx + ' 章') }}
        </div>
      </div>
      <div style="margin-top:12px;text-align:center" v-if="chapters.length < total">
        <button class="nv-btn" @click="loadMoreChapters">加载更多目录</button>
      </div>
    </div>

    <!-- 读者评论（社区 UGC）：公开列表 + 登录发布/删除 -->
    <div class="nv-card">
      <h3 class="nv-title">读者评论（{{ commentTotal }}）</h3>
      <div class="nv-comment-box" v-if="isLogin()">
        <textarea v-model="commentText" class="nv-comment-input" rows="3"
                  maxlength="500" placeholder="说说你的读后感（1-500 字，文明发言）"></textarea>
        <div class="nv-comment-bar">
          <span class="nv-comment-count">{{ commentText.length }}/500</span>
          <button class="nv-btn primary" :disabled="posting" @click="postComment">发布评论</button>
        </div>
      </div>
      <div class="nv-comment-tip" v-else>登录主站后可在本书发表评论</div>

      <div class="nv-comment-list" v-if="comments.length">
        <div class="nv-comment" v-for="c in comments" :key="c.id">
          <div class="nv-comment-head">
            <span class="nv-comment-user">{{ maskUser(c.user_id) }}</span>
            <span class="nv-comment-time" v-if="c.chapter_idx > 0">读到第{{ c.chapter_idx }}章</span>
            <span class="nv-comment-time" v-else>全书短评</span>
            <button v-if="isLogin() && c.user_id === myUser" class="nv-comment-del"
                    @click="removeComment(c)">删除</button>
          </div>
          <div class="nv-comment-text">{{ c.content }}</div>
        </div>
        <div style="margin-top:12px;text-align:center" v-if="comments.length < commentTotal">
          <button class="nv-btn" @click="loadMoreComments">加载更多评论</button>
        </div>
      </div>
      <div class="nv-comment-empty" v-else>还没有评论，来做第一个吧～</div>
    </div>
  </div>

  <div class="nv-empty" v-else-if="!loading">小说不存在或已下架</div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, isLogin } from '../api'

const route = useRoute()
const router = useRouter()
const id = computed(() => route.params.id)

const book = ref(null)
const chapters = ref([])
const total = ref(0)
const loading = ref(true)

// ── 社区：评论 ──
const comments = ref([])
const commentTotal = ref(0)
const commentText = ref('')
const posting = ref(false)
const commentPage = ref(1)
const myUser = computed(() => {
  try {
    const raw = localStorage.getItem('zx_user')
    const d = raw ? JSON.parse(raw) : null
    return d && d.user ? String(d.user) : ''
  } catch (e) { return '' }
})

function maskUser(uid) {
  const u = String(uid || '')
  if (u.length <= 2) return u || '匿名读者'
  return u.slice(0, 1) + '***' + u.slice(-1)
}

const fmtWords = (n) => (n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n || 0))
const unitText = computed(() => (book.value && book.value.chapter_mode === 'stream' ? '段' : '章'))
const statusText = computed(() => {
  const s = book.value && book.value.status
  return s === 'finished' ? '完本' : (s === 'draft' ? '草稿' : '连载')
})

async function load() {
  loading.value = true
  try {
    book.value = await api.detail(id.value)
    if (book.value.chapter_mode === 'chapter') await loadChapters()
  } catch (e) {
    book.value = null
  } finally {
    loading.value = false
  }
}

async function loadChapters() {
  const d = await api.chapters(id.value, { offset: chapters.value.length, limit: 100 })
  chapters.value.push(...(d.items || []))
  total.value = d.total || 0
}

function loadMoreChapters() { loadChapters() }

function readFromStart() {
  const from = (book.value && book.value.chapter_idx) || 1
  router.push(`/read/${id.value}?from=${from}`)
}
function readAt(idx) { router.push(`/read/${id.value}?from=${idx}`) }

async function toggleShelf() {
  if (!isLogin()) { alert('请先登录主站后再使用书架'); return }
  const next = !book.value.in_shelf
  try {
    await api.toggleShelf(id.value, next)
    book.value.in_shelf = next
  } catch (e) { alert(e.message || '操作失败') }
}

async function loadComments() {
  commentPage.value = 1
  try {
    const d = await api.comments(id.value, { page: 1, page_size: 20 })
    comments.value = d.items || []
    commentTotal.value = d.total || 0
  } catch (e) { comments.value = []; commentTotal.value = 0 }
}

async function loadMoreComments() {
  const next = commentPage.value + 1
  try {
    const d = await api.comments(id.value, { page: next, page_size: 20 })
    comments.value.push(...(d.items || []))
    commentPage.value = next
  } catch (e) { /* 忽略翻页错误 */ }
}

async function postComment() {
  const text = commentText.value.trim()
  if (!text) { alert('评论内容不能为空'); return }
  if (!isLogin()) { alert('请先登录主站后再发表评论'); return }
  posting.value = true
  try {
    const c = await api.addComment(id.value, text, 0)
    comments.value.unshift(c)
    commentTotal.value += 1
    commentText.value = ''
  } catch (e) { alert(e.message || '发布失败') }
  finally { posting.value = false }
}

async function removeComment(c) {
  if (!confirm('确定删除这条评论？')) return
  try {
    await api.deleteComment(id.value, c.id)
    comments.value = comments.value.filter(x => x.id !== c.id)
    commentTotal.value = Math.max(0, commentTotal.value - 1)
  } catch (e) { alert(e.message || '删除失败') }
}

function shareBook() {
  const link = `${location.origin}/novel#/book/${id.value}`
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(
      () => alert('分享链接已复制：' + link),
      () => prompt('复制下面的分享链接：', link),
    )
  } else {
    prompt('复制下面的分享链接：', link)
  }
}

onMounted(() => { load(); loadComments() })
</script>
