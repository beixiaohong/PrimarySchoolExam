import { createRouter, createWebHashHistory } from 'vue-router'

// 单体渲染：App.vue 内以 v-if 切换各 tab，路由仅负责 URL ↔ tab 同步（深链/刷新保持当前页）。
// 匹配到的组件为空渲染，实际内容由 App.vue 承载。
// Blank 为占位空组件：命中路由时不渲染任何 DOM，避免重复渲染内容
const Blank = { render: () => null }

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/:tab', component: Blank }, // 任意 /xxx 解析为对应 tab，内容仍由 App.vue 渲染
    { path: '/:pathMatch(.*)*', redirect: '/home' }, // 未匹配路径兜底回首页
  ],
})
