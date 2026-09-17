<template>
  <div class="nv-reader" :class="'nv-theme-' + theme">
    <!-- 顶部工具条 -->
    <div class="nv-reader-bar">
      <span style="cursor:pointer" @click="goBook">← {{ bookTitle || '返回' }}</span>
      <div class="nv-tools">
        <button @click="fontSize = Math.max(14, fontSize - 1)">A-</button>
        <button @click="fontSize = Math.min(26, fontSize + 1)">A+</button>
        <button @click="cycleTheme">{{ themeText }}</button>
      </div>
    </div>

    <div class="nv-reader-body">
      <!-- 起始不为第 1 段时给出提示（从目录/进度跳进来的场景） -->
      <div class="nv-muted" style="text-align:center;padding:6px 0 14px" v-if="startFrom > 1">
        已从第 {{ startFrom }} {{ unitText }}开始
        <a style="color:var(--nv-main);cursor:pointer" @click="restart">（从头阅读）</a>
      </div>

      <template v-for="s in segs" :key="s.idx">
        <h3 class="nv-seg-title" v-if="s.title">{{ s.title }}</h3>
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

onMounted(async () => {
  await loadMeta()
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
