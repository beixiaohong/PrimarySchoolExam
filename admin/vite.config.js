import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// 管理后台独立工程：构建产物 admin/dist 由后端（app/main.py）托管在 /admin。
// base 必须设为 /admin/，这样构建出的资源路径为 /admin/assets/...，与后端挂载一致。
//
// 性能优化：element-plus 改为按需自动导入（只打包模板里用到的组件），
// 不再 app.use(ElementPlus) 全量注册，避免 vite build 时把整个 UI 库拉进 rollup 打包，
// 否则小内存服务器编译时 CPU 跑满、内存暴涨。
// importStyle: false → 样式统一由 main.js 里的 element-plus/dist/index.css 提供，
// 避免组件级样式重复注入。
export default defineConfig({
  base: '/admin/',
  plugins: [
    vue(),
    AutoImport({ resolvers: [ElementPlusResolver({ importStyle: false })] }),
    Components({ resolvers: [ElementPlusResolver({ importStyle: false })] }),
  ],
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
