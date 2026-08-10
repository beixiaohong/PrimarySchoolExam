import { createApp } from 'vue'
import { createPinia } from 'pinia'
import html2canvas from 'html2canvas'
import App from './App.vue'
import router from './router'
import './styles/style.css'

// 周报分享截图依赖（旧版经 CDN 挂到 window，这里改用 npm 依赖并保持 window 引用）
window.html2canvas = html2canvas

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
