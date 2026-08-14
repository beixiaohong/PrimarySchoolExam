import { createRouter, createWebHashHistory } from 'vue-router'

// 路由级懒加载：每个视图拆成独立 chunk，避免首屏一次性打包全部视图。
// 关键点：Dashboard / Analytics 用到了 echarts，拆出去后主包体积与编译期内存都下降，
// 且 echarts 仅在访问对应页面时才加载（rollup 会把共用的 echarts/core 抽到共享 chunk）。
const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue') },
  { path: '/users', name: 'users', component: () => import('../views/Users.vue') },
  { path: '/users/:userId', name: 'user-detail', component: () => import('../views/UserDetail.vue') },
  { path: '/analytics', name: 'analytics', component: () => import('../views/Analytics.vue') },
  { path: '/datacenter', name: 'datacenter', component: () => import('../views/DataCenter.vue') },
  { path: '/manage', name: 'manage', component: () => import('../views/Manage.vue') },
  { path: '/announcements', name: 'announcements', component: () => import('../views/Announcements.vue') },
]

// hash 模式：客户端路由形如 /admin#/users，避免服务端 SPA 回退冲突。
const router = createRouter({
  history: createWebHashHistory('/admin/'),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('admin_token')
  if (!to.meta.public && !token) {
    return { path: '/login' }
  }
  if (to.path === '/login' && token) {
    return { path: '/' }
  }
})

export default router
