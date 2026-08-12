import { createApp } from 'vue'
import { createPinia } from 'pinia'
import html2canvas from 'html2canvas'
import App from './App.vue'
import router from './router'
import './styles/style.css'
import SearchView from './views/SearchView.vue'
import SyncView from './views/SyncView.vue'
import ReadingView from './views/ReadingView.vue'

// 周报分享截图依赖（旧版经 CDN 挂到 window，这里改用 npm 依赖并保持 window 引用）
window.html2canvas = html2canvas

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.component('SearchView', SearchView)
app.component('SyncView', SyncView)
app.component('ReadingView', ReadingView)
app.mount('#app')
