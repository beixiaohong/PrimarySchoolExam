<template>
  <div class="nv-reader" :class="'nv-theme-' + theme">
    <!-- 顶部工具条 -->
    <div class="nv-reader-bar">
      <span style="cursor:pointer" @click="goBook">← {{ bookTitle || '返回' }}</span>
      <div class="nv-tools">
        <button @click="fontSize = Math.max(14, fontSize - 1)">A-</button>
        <button @click="fontSize = Math.min(26, fontSize + 1)">A+</button>
        <button @click="cycleTheme">{{ themeText }}</button>
        <button @click="showBookmarks = !showBookmarks">🔖 书签</button>
      </div>
    </div>

    <!-- 书签面板（登录用户可用；未登录提示登录） -->
    <div class="nv-bookmarks" v-if="showBookmarks">
      <div class="nv-bm-head">
        <strong>书签</strong>
        <span class="nv-bm-close" @click="showBookmarks = false">✕</span>
      </div>
      <template v-if="!isLogin()">
        <div class="nv-muted">登录后可添加书签并跨设备同步。</div>
      </template>
      <template v-else>
        <div class="nv-bm-add">
          <input v-model="bookmarkNote" class="nv-bm-input" placeholder="便签（可选）" />
          <button class="nv-btn nv-btn-sm" @click="addBookmark">
            🔖 第 {{ currentIdx }}{{ unitText }} 加书签
          </button>
        </div>
        <div class="nv-bm-list" v-if="bookmarks.length">
          <div class="nv-bm-item" v-for="b in bookmarks" :key="b.id">
            <div class="nv-bm-info">
              <span class="nv-bm-idx">#{{ b.chapter_idx }}{{ unitText }}</span>
              <span class="nv-bm-note" v-if="b.note">{{ b.note }}</span>
            </div>
            <div class="nv-bm-ops">
              <button class="nv-link" @click="jumpTo(b.chapter_idx)">跳转</button>
              <button class="nv-link nv-danger" @click="removeBookmark(b.id)">删除</button>
            </div>
          </div>
        </div>
        <div class="nv-muted" v-else>还没有书签，读到精彩处点上方按钮收藏吧。</div>
      </template>
    </div>

    <div class="nv-reader-body">
      <!-- 起始不为第 1 段时给出提示（从目录/进度跳进来的场景） -->
      <div class="nv-muted" style="text-align:center;padding:6px 0 14px" v-if="startFrom > 1">
        已从第 {{ startFrom }} {{ unitText }}开始
        <a style="color:var(--nv-main);cursor:pointer" @click="restart">（从头阅读）</a>
      </div>

      <template v-for="s in segs" :key="s.idx">
        <h3 class="nv-seg-title" v-if="s.title">
          {{ s.title }}
          <span v-if="bookmarkSet.has(s.idx)" class="nv-bm-flag" title="已加书签">🔖</span>
        </h3>
        <div class="nv-seg-text" :style="{ fontSize: fontSize + 'px' }">{{ s.content }}</div>
      </template>

      <div class="nv-loading" v-if="loading">加载中…</div>
      <div class="nv-end" v-else-if="!hasMore && segs.length">— 全文完 —</div>
      <div class="nv-end" v-else-if="!loading && !segs.length">暂无内容</div>

      <!-- 哨兵：进入视口即触发下一段加载；同时给一个手动按钮兜底 -->
      <div class="nv-sentinel" ref="sentinel"></div>
      <div style="text-align:center;padding-bottom:30px" v-if="hasMore && !loading">
        <button class="nv-btn" @click="loadMore">加载下一段</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, isLogin } from '../api'

const route = useRoute()
const router = useRouter()
const id = computed(() => route.params.id)
const startFrom = ref(parseInt(route.query.from, 10) || 1)

const book = ref(null)
const bookTitle = ref('')
const segs = ref([])
const nextIdx = ref(startFrom.value)
const total = ref(0)
const loading = ref(false)
const hasMore = ref(true)
const sentinel = ref(null)
let io = null

// 阅读偏好（记忆到 localStorage）
const fontSize = ref(parseInt(localStorage.getItem('nv_font') || '17', 10))
const theme = ref(localStorage.getItem('nv_theme') || 'paper')
const THEMES = ['paper', 'white', 'night']
const themeText = computed(() => ({ paper: '纸黄', white: '纯白', night: '夜间' })[theme.value])
const unitText = computed(() => (book.value && book.value.chapter_mode === 'stream' ? '段' : '章'))

function cycleTheme() {
  const i = THEMES.indexOf(theme.value)
  theme.value = THEMES[(i + 1) % THEMES.length]
}

async function loadMeta() {
  try {
    book.value = await api.detail(id.value)
    bookTitle.value = book.value.title
  } catch (e) { book.value = null }
}

async function loadMore() {
  if (loading.value || nextIdx.value === null) return
  loading.value = true
  try {
    // 一次拉 1 段：下滑到哪里读到哪里，首屏快、流量省
    const d = await api.read(id.value, nextIdx.value, 1)
    segs.value.push(...(d.items || []))
    nextIdx.value = d.next
    total.value = d.total || 0
    hasMore.value = !!d.has_more
    await nextTick()
    ensureObserver()
    saveProgress()
  } catch (e) {
    hasMore.value = false
  } finally {
    loading.value = false
  }
}

let lastSaved = 0
function saveProgress() {
  if (!isLogin() || !segs.value.length) return
  const idx = segs.value[segs.value.length - 1].idx
  if (idx === lastSaved) return
  lastSaved = idx
  api.saveProgress(id.value, idx).catch(() => { /* 进度丢失不影响阅读 */ })
}

function restart() {
  segs.value = []
  nextIdx.value = 1
  hasMore.value = true
  startFrom.value = 1
  window.scrollTo(0, 0)
  loadMore()
}

function goBook() { router.push(`/book/${id.value}`) }

function ensureObserver() {
  if (io) io.disconnect()
  if (!sentinel.value) return
  io = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) loadMore()
  }, { rootMargin: '500px' })
  io.observe(sentinel.value)
}

// ───────────────── 书签（需登录） ─────────────────
const showBookmarks = ref(false)
const bookmarks = ref([])
const bookmarkNote = ref('')
const currentIdx = computed(() => segs.value.length ? segs.value[segs.value.length - 1].idx : 1)
// 已加书签的章/段号集合，用于在正文中渲染 🔖 标记
const bookmarkSet = computed(() => new Set((bookmarks.value || []).map((b) => b.chapter_idx)))

async function loadBookmarks() {
  if (!isLogin()) { bookmarks.value = []; return }
  try {
    bookmarks.value = await api.bookmarks(id.value)
  } catch (e) { bookmarks.value = [] }
}

async function addBookmark() {
  if (!isLogin()) { alert('请先登录后再添加书签'); return }
  try {
    await api.addBookmark(id.value, currentIdx.value, bookmarkNote.value.trim())
    bookmarkNote.value = ''
    await loadBookmarks()
  } catch (e) { alert('添加失败：' + e.message) }
}

async function removeBookmark(bid) {
  try {
    await api.deleteBookmark(id.value, bid)
    await loadBookmarks()
  } catch (e) { alert('删除失败：' + e.message) }
}

function jumpTo(idx) {
  // 从指定章/段重新加载（清空已读段落并定位）
  segs.value = []
  nextIdx.value = idx
  hasMore.value = true
  startFrom.value = idx
  window.scrollTo(0, 0)
  loadMore()
}

onMounted(async () => {
  await loadMeta()
  await loadBookmarks()
  window.scrollTo(0, 0)
  await loadMore()
})

// 偏好持久化
onUnmounted(() => {
  if (io) io.disconnect()
  localStorage.setItem('nv_font', String(fontSize.value))
  localStorage.setItem('nv_theme', theme.value)
})
</script>
