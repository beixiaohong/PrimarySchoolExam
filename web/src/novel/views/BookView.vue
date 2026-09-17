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

onMounted(load)
</script>
