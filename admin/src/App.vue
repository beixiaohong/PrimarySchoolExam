<template>
  <div class="admin-root">
    <template v-if="isLogin">
      <router-view />
    </template>
    <template v-else>
      <aside class="side">
        <div class="logo">智学学堂<small>管理后台</small></div>
        <el-menu :default-active="activeMenu" router class="side-menu">
          <el-menu-item index="/">仪表盘</el-menu-item>
          <el-menu-item index="/users">用户管理</el-menu-item>
          <el-menu-item index="/analytics">运营分析</el-menu-item>
        </el-menu>
        <div class="side-foot">
          <span class="uname">{{ username }}</span>
          <el-button text type="primary" size="small" @click="logout">退出</el-button>
        </div>
      </aside>
      <main class="main">
        <router-view />
      </main>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const isLogin = computed(() => route.name === 'login')
const username = computed(() => localStorage.getItem('admin_username') || '')
const activeMenu = computed(() => route.path === '/' ? '/' : (route.path.startsWith('/users') ? '/users' : route.path))

function logout() {
  localStorage.removeItem('admin_token')
  localStorage.removeItem('admin_username')
  router.push('/login')
}
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f4f6fb; }
.admin-root { display: flex; min-height: 100vh; }
.side { width: 200px; background: #1f2d3d; color: #fff; display: flex; flex-direction: column; }
.logo { padding: 20px 16px; font-size: 18px; font-weight: 700; line-height: 1.3; border-bottom: 1px solid #324056; }
.logo small { display: block; font-size: 12px; font-weight: 400; color: #9fb0c3; margin-top: 2px; }
.side-menu { flex: 1; border-right: none; background: transparent; }
.side-menu .el-menu-item { color: #cdd9e5; }
.side-menu .el-menu-item.is-active { background: #2d4059; color: #fff; }
.side-foot { padding: 12px 16px; border-top: 1px solid #324056; font-size: 13px; display: flex; align-items: center; justify-content: space-between; }
.side-foot .uname { color: #9fb0c3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.main { flex: 1; padding: 20px 24px; overflow: auto; }
.main h2 { margin: 0 0 16px; font-size: 20px; }
</style>
