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
import ReciteView from './views/ReciteView.vue'
import PracticeView from './views/PracticeView.vue'
// B1 组件化：App.vue 内联块抽出的 16 个视图（壳通过 provide appCtx 注入，本文件统一全局注册）
import HomeView from './views/HomeView.vue'
import WrongView from './views/WrongView.vue'
import PapersView from './views/PapersView.vue'
import StatsView from './views/StatsView.vue'
import QaView from './views/QaView.vue'
import PetView from './views/PetView.vue'
import TreeView from './views/TreeView.vue'
import BadgesView from './views/BadgesView.vue'
import CardsView from './views/CardsView.vue'
import DictView from './views/DictView.vue'
import FocusView from './views/FocusView.vue'
import AiquizView from './views/AiquizView.vue'
import AssistantView from './views/AssistantView.vue'
import WalletView from './views/WalletView.vue'
import SettingsView from './views/SettingsView.vue'
import CoursesView from './views/CoursesView.vue'
import AntiCheatInput from './components/AntiCheatInput.vue'
// B3 全站图标统一：内联 SVG 图标集（nav.js / App.vue 侧边栏 & TabBar 统一引用）
import AppIcon from './components/AppIcon.vue'

// 周报分享截图依赖（旧版经 CDN 挂到 window，这里改用 npm 依赖并保持 window 引用）
window.html2canvas = html2canvas

// 创建根应用实例
const app = createApp(App)
// 全局错误边界：捕获单个视图渲染/逻辑中的未处理异常，避免整页白屏拖垮整个 SPA
// （例如某页面访问了不存在的响应式字段）。出错时仅该视图渲染失败，其余页面仍可正常使用。
app.config.errorHandler = (err, instance, info) => {
  const name = (instance && instance.$options && instance.$options.name) || 'AnonymousComponent'
  // 打到控制台，便于定位根因（含组件名与出错阶段 render/setup 等）
  console.error(`[AppError] 组件 ${name} 在 ${info} 阶段抛出异常：`, err)
  // 同时在页面顶部给出非阻塞提示，用户可继续操作其他页面
  try {
    const tip = document.createElement('div')
    tip.style.cssText = 'position:fixed;left:50%;top:12px;transform:translateX(-50%);z-index:9999;background:#fff3f3;color:#c0392b;border:1px solid #f5c6c6;padding:8px 14px;border-radius:10px;font-size:13px;max-width:90vw;box-shadow:0 4px 16px rgba(0,0,0,.12)'
    tip.textContent = `⚠️ 「${name}」页面出错（已隔离，不影响其他页面）：${err && err.message ? err.message : err}`
    document.body.appendChild(tip)
    setTimeout(() => tip.remove(), 6000)
  } catch (e) { /* 忽略 UI 提示异常 */ }
}
// 注册全局状态管理（Pinia）与哈希路由
app.use(createPinia())
app.use(router)
// 显式注册为全局组件，便于 App.vue 用动态组件按 tab 切换视图
app.component('SearchView', SearchView)
app.component('SyncView', SyncView)
app.component('KnowledgeView', KnowledgeView)
app.component('ReadingView', ReadingView)
app.component('LearningGoalsView', LearningGoalsView)
app.component('ReciteView', ReciteView)
app.component('PracticeView', PracticeView)
// B1 组件化：16 个抽出视图的全局注册（组件名 PascalCase，App.vue 用 kebab 标签匹配）
app.component('HomeView', HomeView)
app.component('WrongView', WrongView)
app.component('PapersView', PapersView)
app.component('StatsView', StatsView)
app.component('QaView', QaView)
app.component('PetView', PetView)
app.component('TreeView', TreeView)
app.component('BadgesView', BadgesView)
app.component('CardsView', CardsView)
app.component('DictView', DictView)
app.component('FocusView', FocusView)
app.component('AiquizView', AiquizView)
app.component('AssistantView', AssistantView)
app.component('WalletView', WalletView)
app.component('SettingsView', SettingsView)
app.component('CoursesView', CoursesView)
app.component('AntiCheatInput', AntiCheatInput)
app.component('AppIcon', AppIcon)
// 挂载到 index.html 中的 #app 节点
app.mount('#app')
