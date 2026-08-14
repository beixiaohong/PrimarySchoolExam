import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 管理后台独立工程：构建产物 admin/dist 由后端（app/main.py）托管在 /admin。
// base 必须设为 /admin/，这样构建出的资源路径为 /admin/assets/...，与后端挂载一致。
export default defineConfig({
  base: '/admin/',
  plugins: [vue()],
  server: {
    // 本地 npm run dev 时，把 /api 代理到后端（默认 127.0.0.1:8000），
    // 否则前端 baseURL 同源模式下登录等请求会打到 vite 自身而失败。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
