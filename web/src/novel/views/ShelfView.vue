<template>
  <div>
    <h3 class="nv-title">我的书架</h3>

    <div class="nv-books" v-if="books.length">
      <div class="nv-book" v-for="b in books" :key="b.id" @click="open(b)">
        <div class="nv-cover">
          <img v-if="b.cover_url" :src="b.cover_url" :alt="b.title" />
          <span v-else>{{ b.title }}</span>
        </div>
        <div class="nv-book-b">
          <div class="nv-book-t">{{ b.title }}</div>
          <div class="nv-book-m">{{ b.author || '佚名' }}</div>
        </div>
      </div>
    </div>

    <div class="nv-empty" v-if="!loading && !books.length">
      <div v-if="!login">登录后才能使用书架</div>
      <div v-else>书架还是空的，去书城挑一本吧</div>
      <div style="margin-top:14px"><router-link to="/" class="nv-btn primary">去书城</router-link></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, isLogin } from '../api'

const router = useRouter()
const books = ref([])
const loading = ref(true)
const login = isLogin()

async function load() {
  loading.value = true
  try { books.value = await api.shelf() } catch (e) { books.value = [] } finally { loading.value = false }
}

function open(b) { router.push(`/book/${b.id}`) }

onMounted(load)
</script>
