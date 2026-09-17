// 前端 Vite 构建配置（web 工程）
// 职责：dev 用 5173 端口并代理 /api 到后端 8000；build 输出到 dist/ 由 FastAPI 同源托管。
//
// 多页入口：index.html=学生学习端（/），novel.html=小说站（/novel，独立 Vue 应用）。
// 两者共用 /assets（content hash 命名，可安全缓存），互不共享组件与状态。
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const page = (name) => fileURLToPath(new URL(`./${name}`, import.meta.url))

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
    rollupOptions: {
      input: {
        main: page('index.html'),
        novel: page('novel.html'),
      },
    },
  },
})
