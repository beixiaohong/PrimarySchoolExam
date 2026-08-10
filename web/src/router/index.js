import { createRouter, createWebHashHistory } from 'vue-router'

// 单体渲染：App.vue 内以 v-if 切换各 tab，路由仅负责 URL ↔ tab 同步（深链/刷新保持当前页）。
// 匹配到的组件为空渲染，实际内容由 App.vue 承载。
const Blank = { render: () => null }

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/:tab', component: Blank },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})
