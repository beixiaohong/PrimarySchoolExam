import { createApp } from 'vue'
import { createPinia } from 'pinia'
import html2canvas from 'html2canvas'
import App from './App.vue'
import router from './router'
import './styles/style.css'
import SearchView from './views/SearchView.vue'
import SyncView from './views/SyncView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import ReadingView from './views/ReadingView.vue'
import LearningGoalsView from './views/LearningGoalsView.vue'
import AntiCheatInput from './components/AntiCheatInput.vue'

// 周报分享截图依赖（旧版经 CDN 挂到 window，这里改用 npm 依赖并保持 window 引用）
window.html2canvas = html2canvas

// 创建根应用实例
const app = createApp(App)
// 注册全局状态管理（Pinia）与哈希路由
app.use(createPinia())
app.use(router)
// 显式注册为全局组件，便于 App.vue 用动态组件按 tab 切换视图
app.component('SearchView', SearchView)
app.component('SyncView', SyncView)
app.component('KnowledgeView', KnowledgeView)
app.component('ReadingView', ReadingView)
app.component('LearningGoalsView', LearningGoalsView)
app.component('AntiCheatInput', AntiCheatInput)
// 挂载到 index.html 中的 #app 节点
app.mount('#app')
