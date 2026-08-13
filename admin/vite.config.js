import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 管理后台独立工程：构建产物 admin/dist 由后端（app/main.py）托管在 /admin。
// base 必须设为 /admin/，这样构建出的资源路径为 /admin/assets/...，与后端挂载一致。
export default defineConfig({
  base: '/admin/',
  plugins: [vue()],
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
