<template>
  <div class="nv-app">
    <!-- 顶部条：阅读页沉浸式，隐去站点头由 ReaderView 自带工具条接管 -->
    <header class="nv-header" v-if="!isReader">
      <div class="nv-brand">智学小说</div>
      <a class="nv-back" href="/">← 返回主站</a>
    </header>

    <main class="nv-main" :class="{ 'nv-main-full': isReader }">
      <router-view />
    </main>

    <nav class="nv-tabbar" v-if="!isReader">
      <router-link to="/" :class="{ active: route.name === 'home' }">
        <span class="ico">📚</span>书城
      </router-link>
      <router-link to="/shelf" :class="{ active: route.name === 'shelf' }">
        <span class="ico">🔖</span>书架
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
// 阅读页全屏：去掉主站头尾，阅读器自带返回/工具栏
const isReader = computed(() => route.name === 'read')
</script>

<style>
/* 阅读页去掉主容器留白与最大宽度限制，交给阅读器自己控制 */
.nv-main-full { max-width: none; padding: 0; }
</style>
