<template>
<div class="fade-enter">
  <div class="hero" style="background:linear-gradient(135deg,#7b6cf6,#4facfe)">
    <div style="flex:1">
      <h1>🎖️ 等级成长</h1>
      <p class="sub" style="color:rgba(255,255,255,.92)">认真学习积累经验，升级解锁称号、头像框与钻石奖励。</p>
    </div>
    <div class="lv-hero">
      <div class="lv-hero-num">Lv.{{appCtx.levelNum}}</div>
      <div class="lv-hero-title">{{appCtx.levelTitle || '—'}}</div>
    </div>
  </div>

  <!-- 当前等级与进度 -->
  <div class="card lv-card">
    <div class="lv-row">
      <b class="lv-cur">Lv.{{appCtx.levelNum}} · {{appCtx.levelTitle || '加载中'}}</b>
      <span class="lv-exp">累计经验 {{appCtx.levelInfo ? appCtx.levelInfo.exp : 0}}</span>
    </div>
    <div class="lv-bar">
      <div class="lv-bar-fill" :class="{max: appCtx.levelIsMax}" :style="{width: appCtx.levelPct + '%'}"></div>
    </div>
    <div class="lv-hint">
      <template v-if="appCtx.levelIsMax">🎉 已满级（Lv.{{appCtx.levelInfo ? appCtx.levelInfo.max_level : 20}}），你就是智学之光！</template>
      <template v-else-if="appCtx.levelInfo">距 Lv.{{appCtx.levelInfo.next_level}}「{{appCtx.levelInfo.next_title}}」还差 <b>{{appCtx.levelExpToNext}}</b> 经验（本区间 {{appCtx.levelPct}}%）</template>
      <template v-else>正在读取等级信息…</template>
    </div>
    <div class="lv-perk" v-if="appCtx.levelInfo">🎁 当前特权：{{appCtx.levelInfo.perk}}</div>
    <div class="lv-tip">经验来自真实学习行为：交卷 · 掌握错题 · 完成任务 · 心情打卡 · 每日签到 · 番茄专注</div>
  </div>

  <!-- 完整等级阶梯 -->
  <div class="card lv-ladder-card">
    <div class="card-head"><b>等级阶梯</b></div>
    <div class="lv-ladder">
      <div v-for="l in appCtx.levelLadder" :key="l.lv" class="lv-item"
           :class="appCtx.levelItemClass(l)">
        <div class="lv-item-lv">Lv.{{l.lv}}</div>
        <div class="lv-item-body">
          <b>{{l.title}}</b>
          <span class="lv-item-perk">{{l.perk}}</span>
        </div>
        <div class="lv-item-exp">{{l.min_exp}} 经验</div>
        <div class="lv-item-reward" v-if="l.reward_diamond">💎{{l.reward_diamond}}</div>
        <div class="lv-item-state">{{appCtx.levelItemState(l)}}</div>
      </div>
    </div>
    <div v-if="appCtx.levelLoading && !appCtx.levelInfo" class="lv-loading">加载中…</div>
  </div>
</div>
</template>

<script>
// LevelView（新功能 C：等级 / 成长体系）。
// 业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有（等级部分已抽到 logic/level.js），
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods（与 BadgesView 等 B1 组件一致）。
// 数据只读：经验由服务端行为埋点累加，前端无写入入口。
export default {
  name: 'LevelView',
  inject: ['appCtx'],
}
</script>
