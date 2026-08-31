<template>
<div class="fade-enter">
        <div class="page-head"><h2>🎬 网课</h2><span class="page-sub">跟着视频课学习，家长可在「设置-家长管理」里添加更多课程</span></div>
        <div v-if="!appCtx.courses.length" class="empty">
          <div class="em">🎬</div><h3>还没有网课</h3>
          <p>请家长在「设置 → 家长管理 → 网课设置」里添加课程</p>
        </div>
        <div v-else class="course-grid">
          <div v-for="c in appCtx.courses" :key="c.id" class="course-card" @click="appCtx.playCourse(c)">
            <div class="course-cover" :style="c.cover_url ? {backgroundImage:'url('+c.cover_url+')'} : {}">
              <span class="course-play">▶</span>
              <span v-if="c.duration_min" class="course-dur">{{c.duration_min}}分钟</span>
              <span class="course-tag" v-if="c.subject && c.subject!=='不限'">{{c.subject}}</span>
              <span class="course-tag course-tag-src" v-if="c.source==='parent'">家长添加</span>
            </div>
            <div class="course-body">
              <b class="course-title">{{c.title}}</b>
              <p class="course-desc" v-if="c.description">{{c.description}}</p>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// CoursesView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'CoursesView',
  inject: ['appCtx'],
}
</script>
