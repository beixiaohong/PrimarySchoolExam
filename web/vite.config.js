// 前端 Vite 构建配置（web 工程）
// 职责：dev 用 5173 端口并代理 /api 到后端 8000；build 输出到 dist/ 由 FastAPI 同源托管。
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// dev 阶段 /api 代理到后端 8000；build 产物部署时由后端直接托管
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
