<template>
<div class="fade-enter">
  <div class="fv-tabs">
    <button class="fv-tab" :class="{active: appCtx.favoritesType===''}" @click="appCtx.setFavoritesType('')">全部</button>
    <button class="fv-tab" :class="{active: appCtx.favoritesType==='paper'}" @click="appCtx.setFavoritesType('paper')">试卷</button>
    <button class="fv-tab" :class="{active: appCtx.favoritesType==='question'}" @click="appCtx.setFavoritesType('question')">题目</button>
    <span class="fv-count" v-if="appCtx.favoritesTotal">共 {{appCtx.favoritesTotal}} 条</span>
  </div>
  <div class="card">
    <div v-if="!appCtx.favorites.length && !appCtx.favoritesLoading" class="empty">
      <div class="em">⭐</div>
      <h3>还没有收藏</h3>
      <p>在「刷题中心 / 我的试卷」里点 ⭐ 即可收藏到这里</p>
      <button class="btn btn-primary" @click="appCtx.goTab('practice')">去刷题</button>
    </div>
    <div v-for="f in appCtx.favorites" :key="f.id" class="fv-item">
      <span class="fv-type" :class="f.item_type==='paper'?'t-blue':'t-violet'">{{f.item_type==='paper'?'试卷':'题目'}}</span>
      <div class="fv-body">
        <b>{{f.title || (f.item_type + ' #' + f.item_id)}}</b>
        <span class="meta">收藏于 {{f.created_at}}</span>
      </div>
      <button class="btn btn-ghost btn-sm" @click="appCtx.toggleFavorite(f.item_type, f.item_id, f.title)">取消收藏</button>
    </div>
    <button v-if="appCtx.favoritesHasMore" class="btn btn-ghost fv-more" :disabled="appCtx.favoritesLoading" @click="appCtx.loadMoreFavorites()">加载更多</button>
    <div v-if="appCtx.favoritesLoading" class="fv-loading">加载中…</div>
  </div>
</div>
</template>

<script>
// FavoritesView（新功能 D：我的收藏）。业务逻辑由 App.vue 壳通过 appOptions/favorites mixin 持有，
// 本组件仅 inject appCtx 访问响应式状态与方法，自身零 data/methods（与 PapersView 等 B1 组件一致）。
export default {
  name: 'FavoritesView',
  inject: ['appCtx'],
}
</script>
