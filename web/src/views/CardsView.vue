<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#4facfe,#00f2fe)">
          <div style="flex:1">
            <h1>🃏 知识卡图鉴</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">掌握一个知识点就点亮一张卡，集齐图鉴成为知识收藏家！</p>
          </div>
          <div class="card-count" v-if="appCtx.cardData">
            <div class="card-count-num">{{appCtx.cardData.collected}} / {{appCtx.cardData.total}}</div>
            <div class="card-count-label">🃏 已点亮</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🎴 今日抽卡</b>
            <button class="btn btn-primary" style="padding:6px 14px;font-size:12.5px" @click="appCtx.cardDraw()" :disabled="appCtx.cardDrawing">
              {{appCtx.cardDrawing ? '抽卡中…' : '抽 3 张 →'}}
            </button>
          </div>
          <p class="card-desc">从还没点亮的卡里抽 3 张，看看今天该去学什么！</p>
          <div v-if="appCtx.drawAllCollected" class="empty" style="padding:20px">
            <div class="em">🏆</div><h3>全部收集完成！</h3><p>你就是知识收藏家！</p>
          </div>
          <div v-else-if="appCtx.drawCards.length" class="draw-cards">
            <div v-for="(c, i) in appCtx.drawCards" :key="i" class="draw-card" :style="{animationDelay: i * 0.15 + 's'}">
              <div class="draw-card-emoji">{{c.emoji}}</div>
              <div class="draw-card-title">{{c.title}}</div>
              <div class="draw-card-sub">{{c.sub}}</div>
              <div class="draw-card-desc">{{c.desc}}</div>
            </div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📚 我的图鉴</b><span class="more" style="font-size:12px;color:var(--text-3)">掌握即点亮</span></div>
          <div v-if="!appCtx.cardData || !appCtx.cardData.categories.length" class="empty" style="padding:24px">
            <div class="em">🃏</div><h3>图鉴还是空的</h3><p>掌握第一个知识点，点亮第一张卡吧！</p>
          </div>
          <div v-else v-for="cat in appCtx.cardData.categories" :key="cat.key" class="card-cat">
            <div class="card-cat-head"><b>{{cat.emoji}} {{cat.name}}</b><span class="more" style="font-size:12px;color:var(--text-3)">{{cat.collected}} / {{cat.total}}</span></div>
            <div v-if="!cat.cards.length" class="card-cat-empty">还没有收集，去学习吧！</div>
            <div v-else class="card-grid">
              <div v-for="c in cat.cards" :key="c.id" class="card-tile">
                <span class="card-tile-emoji">{{c.emoji}}</span>
                <span class="card-tile-title">{{c.title}}</span>
                <span class="card-tile-sub">{{c.sub}}</span>
              </div>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// CardsView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'CardsView',
  inject: ['appCtx'],
}
</script>
