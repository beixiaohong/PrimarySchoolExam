// 小说站路由：hash 模式（后端只托管 /novel 一个入口，hash 路由免去 nginx 兜底配置）
import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import ShelfView from './views/ShelfView.vue'
import BookView from './views/BookView.vue'
import ReaderView from './views/ReaderView.vue'

export default createRouter({
  // 基础路径 /novel/ —— 站点部署在 https://<host>/novel/ 下
  history: createWebHashHistory('/novel/'),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/shelf', name: 'shelf', component: ShelfView },
    { path: '/book/:id', name: 'book', component: BookView },
    { path: '/read/:id', name: 'read', component: ReaderView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  // 切换页面回到顶部（阅读器内部自己维护滚动位置，不在此处理）
  scrollBehavior() {
    return { top: 0 }
  },
})
