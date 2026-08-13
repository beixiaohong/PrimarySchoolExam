<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="always">
      <h2>智学学堂 · 管理后台</h2>
      <el-form @submit.prevent="doLogin" label-width="60px">
        <el-form-item label="账号">
          <el-input v-model="username" placeholder="管理员账号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password
                    @keyup.enter="doLogin" placeholder="密码" />
        </el-form-item>
        <el-button type="primary" :loading="loading" @click="doLogin" style="width: 100%">登录</el-button>
      </el-form>
      <p v-if="err" class="err">{{ err }}</p>
      <p class="tip">默认账号 admin / admin123456，请上线后尽快修改密码</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const username = ref('')
const password = ref('')
const loading = ref(false)
const err = ref('')
const router = useRouter()

async function doLogin() {
  err.value = ''
  loading.value = true
  try {
    const { data } = await api.post('/api/admin/login', {
      username: username.value,
      password: password.value,
    })
    localStorage.setItem('admin_token', data.token)
    localStorage.setItem('admin_username', data.username)
    router.push('/')
  } catch (e) {
    err.value = (e.response && e.response.data && e.response.data.detail) || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #1f2d3d; }
.login-card { width: 360px; }
.login-card h2 { margin: 0 0 20px; text-align: center; font-size: 20px; }
.err { color: #f56c6c; font-size: 13px; margin: 10px 0 0; }
.tip { color: #909399; font-size: 12px; margin: 14px 0 0; text-align: center; }
</style>
