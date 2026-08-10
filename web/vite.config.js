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
