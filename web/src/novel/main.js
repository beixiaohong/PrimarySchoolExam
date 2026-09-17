// 小说站独立入口：与学生端（src/main.js）完全隔离的第二个 Vue 应用。
// 只依赖 vue / vue-router（web 工程已装），不引 element-plus 等后台专用库。
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)

// 全局错误边界：单页异常不白屏，给出非阻塞提示
app.config.errorHandler = (err, instance, info) => {
  console.error('[NovelError]', info, err)
}

app.use(router)
app.mount('#app')
