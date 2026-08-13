import { createRouter, createWebHashHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Dashboard from '../views/Dashboard.vue'
import Users from '../views/Users.vue'
import UserDetail from '../views/UserDetail.vue'
import Analytics from '../views/Analytics.vue'

const routes = [
  { path: '/login', name: 'login', component: Login, meta: { public: true } },
  { path: '/', name: 'dashboard', component: Dashboard },
  { path: '/users', name: 'users', component: Users },
  { path: '/users/:userId', name: 'user-detail', component: UserDetail },
  { path: '/analytics', name: 'analytics', component: Analytics },
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
