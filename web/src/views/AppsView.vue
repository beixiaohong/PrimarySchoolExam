<template>
  <!-- 应用中心（tab='apps'）：展示平台全部可用模块（blog.md §8）。
       模块清单来自 web/src/apps.js 注册表（不在页面里硬编码），
       点击经 appCtx.wsOpenApp 上报访问后跳转对应 tab。 -->
  <div class="fade-enter">
    <div class="card apps-card">
      <div class="card-head">
        <b><app-icon name="apps" :size="18"></app-icon> 应用中心</b>
        <span class="more">{{ groups.reduce((s, g) => s + g.items.length, 0) }} 个模块</span>
        <button class="btn btn-ghost btn-sm" @click="appCtx.goTab('workspace')">← 工作台</button>
      </div>

      <div v-for="g in groups" :key="'ag' + g.group" class="apps-group">
        <div class="apps-group-title">{{ g.group }}</div>
        <div class="apps-grid">
          <div v-for="a in g.items" :key="'ap' + a.key" class="apps-item" @click="appCtx.wsOpenApp(a)">
            <app-icon :name="a.icon" :size="28" class="apps-icon"></app-icon>
            <div class="apps-main">
              <b class="apps-name">{{ a.name }}</b>
              <span class="apps-desc">{{ a.desc }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 应用中心（tab='apps'）。仅 inject appCtx；模块清单由 ../apps.js 提供（纯展示常量）。
import { appGroups } from '../apps.js'

export default {
  name: 'AppsView',
  inject: ['appCtx'],
  data() {
    return { groups: appGroups() }
  },
}
</script>

<style scoped>
.apps-card { max-width: 860px; }
.apps-card .card-head b { display: inline-flex; align-items: center; gap: 6px; }
.apps-card .card-head .more { flex: 1; }
.apps-group { margin-bottom: 16px; }
.apps-group-title { font-size: 13px; color: #8a8fa3; margin: 0 0 8px; }
.apps-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
.apps-item {
  display: flex; align-items: center; gap: 12px; padding: 12px;
  border: 1px solid #efedf7; border-radius: 12px; cursor: pointer;
  transition: background .12s, border-color .12s;
}
.apps-item:hover { background: #f9f8fd; border-color: #ddd6f5; }
.apps-icon { color: #8b7cf6; flex: none; }
.apps-main { min-width: 0; }
.apps-name { display: block; font-size: 14px; color: #3b3555; }
.apps-desc { display: block; font-size: 12px; color: #8a8fa3; margin-top: 2px; line-height: 1.4; }
@media (max-width: 640px) {
  .apps-grid { grid-template-columns: 1fr; }
}
</style>
