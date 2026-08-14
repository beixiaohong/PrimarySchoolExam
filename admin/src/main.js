import { createApp } from 'vue'
// 注意：element-plus 已改为「按需自动导入」（见 vite.config.js 的 unplugin 配置），
// 模板里用到的 <el-*> 组件和 ElMessage 等 API 会在编译期按需注入，无需全量 app.use(ElementPlus)。
// 这里只引入完整样式表，保证所有组件（含 ElMessage 弹窗）样式齐全。
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(router)
app.mount('#app')
