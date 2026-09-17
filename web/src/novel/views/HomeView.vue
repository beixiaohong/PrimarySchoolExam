<template>
  <div>
    <div class="nv-search">
      <input v-model="keyword" placeholder="搜索书名或作者" @keyup.enter="reload" />
      <button class="nv-btn primary" @click="reload">搜索</button>
    </div>

    <div class="nv-chips">
      <span class="nv-chip" :class="{ active: !category }" @click="pick('')">全部</span>
      <span class="nv-chip" :class="{ active: category === c.category }"
            v-for="c in categories" :key="c.category" @click="pick(c.category)">
        {{ c.category }}（{{ c.count }}）
      </span>
    </div>

    <div class="nv-books">
      <div class="nv-book" v-for="b in books" :key="b.id" @click="open(b)">
        <div class="nv-cover">
          <img v-if="b.cover_url" :src="b.cover_url" :alt="b.title" />
          <span v-else>{{ b.title }}</span>
        </div>
        <div class="nv-book-b">
          <div class="nv-book-t">{{ b.title }}</div>
          <div class="nv-book-m">{{ b.author || '佚名' }} · {{ fmtWords(b.word_count) }}字</div>
        </div>
      </div>
    </div>

    <div class="nv-empty" v-if="!loading && !books.length">暂无小说，请到后台上传 TXT</div>
    <div class="nv-loading" v-if="loading">加载中…</div>
    <div class="nv-end" v-else-if="!hasMore && books.length">— 已经到底了 —</div>
    <div class="nv-sentinel" ref="sentinel"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const categories = ref([])
const books = ref([])
const keyword = ref('')
const category = ref('')
const page = ref(1)
const PAGE_SIZE = 20
const total = ref(0)
const loading = ref(false)
const hasMore = ref(true)
const sentinel = ref(null)
let io = null

const fmtWords = (n) => (n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n || 0))

async function loadCats() {
  try { categories.value = await api.categories() } catch (e) { categories.value = [] }
}

async function loadMore() {
  if (loading.value || !hasMore.value) return
  loading.value = true
  try {
    const data = await api.list({
      category: category.value, keyword: keyword.value,
      page: page.value, page_size: PAGE_SIZE,
    })
    books.value.push(...(data.items || []))
    total.value = data.total || 0
    hasMore.value = books.value.length < total.value
    page.value += 1
    await nextTick()
    ensureObserver()
  } catch (e) {
    hasMore.value = false
  } finally {
    loading.value = false
  }
}

function pick(c) {
  if (category.value === c) return
  category.value = c
  reload()
}

function reload() {
  books.value = []
  page.value = 1
  hasMore.value = true
  loadMore()
}

function open(b) {
  router.push(`/book/${b.id}`)
}

// 无限滚动：哨兵进入视口即加载下一页
function ensureObserver() {
  if (io) io.disconnect()
  if (!sentinel.value) return
  io = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) loadMore()
  }, { rootMargin: '400px' })
  io.observe(sentinel.value)
}

onMounted(async () => {
  await loadCats()
  await loadMore()
})
onUnmounted(() => { if (io) io.disconnect() })
</script>
