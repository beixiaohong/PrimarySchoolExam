<template>
<div class="fade-enter">
        <div class="filter-bar">
          <button class="btn btn-primary" @click="appCtx.goTab('practice')">＋ 生成新试卷</button>
          <span class="filter-sep"></span><span class="tag tag-blue">{{appCtx.subject}}</span>
        </div>
        <div class="card">
          <div v-if="!appCtx.papers.length" class="empty"><div class="em">📄</div><h3>还没有试卷</h3><p>去刷题中心生成第一份试卷吧</p><button class="btn btn-primary" @click="appCtx.goTab('practice')">去生成</button></div>
          <div v-for="p in appCtx.papers" :key="p.id" class="paper-item">
            <div class="p-ico" :class="p.subject==='数学'?'t-orange':p.subject==='语文'?'t-violet':'t-blue'">{{p.subject==='数学'?'🧮':p.subject==='语文'?'📖':'🔤'}}</div>
            <div class="p-body">
              <b>{{p.title}}</b>
              <span class="meta">{{p.subject}} · {{p.grade}}年级 · {{p.difficulty}} · {{p.question_count}}题 · {{p.created_at}}</span>
            </div>
            <div class="p-actions">
              <button class="btn btn-ghost btn-sm" @click="appCtx.previewPaper(p)">在线做题</button>
              <button class="btn btn-ghost btn-sm" @click="appCtx.downloadPaper(p)">下载 Word</button>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// PapersView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'PapersView',
  inject: ['appCtx'],
}
</script>
