<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#f093fb,#f5576c)">
          <div style="flex:1">
            <h1>🏅 成就徽章墙</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">每达成一个里程碑，就点亮一枚徽章。看看你已经收集了多少枚？</p>
          </div>
          <div class="badge-count" v-if="appCtx.badgeData">
            <div class="badge-count-num">{{appCtx.badgeData.earned}} / {{appCtx.badgeData.total}}</div>
            <div class="badge-count-label">🏅 已点亮</div>
          </div>
        </div>

        <div v-if="appCtx.badgeNew.length" class="card" style="max-width:760px;margin-top:16px;border-color:#F0C98A;background:#FFF8EC">
          <div class="card-head"><b>🎉 恭喜获得新徽章！</b></div>
          <div class="badge-new-list">
            <div v-for="b in appCtx.badgeNew" :key="b.code" class="badge-new-item">
              <span class="badge-new-emoji">{{b.emoji}}</span>
              <div class="badge-new-info"><b>{{b.name}}</b><span>{{b.desc}}</span></div>
            </div>
          </div>
        </div>

        <!-- 分类 tab（新功能 B）：学习 / 坚持 / 社交与目标 + 全部，含各类已得进度 -->
        <div class="bd-tabs" v-if="appCtx.badgeCats.length">
          <button v-for="c in appCtx.badgeCats" :key="c.key" class="bd-tab"
                  :class="{active: appCtx.badgeCat===c.key}" @click="appCtx.setBadgeCat(c.key)">
            {{c.label}}<span class="bd-tab-num">{{c.earned}}/{{c.total}}</span>
          </button>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="badge-grid" v-if="appCtx.badgeData">
            <div v-for="b in appCtx.badgeItems" :key="b.code" class="badge-item" :class="{locked: !b.earned}">
              <div class="badge-medal">{{b.earned ? b.emoji : '🔒'}}</div>
              <div class="badge-name">{{b.name}}</div>
              <div class="badge-desc">{{b.desc}}</div>
              <!-- 进度条（新功能 B）：current/target 由后端指标派生，已得恒为 100% -->
              <div class="bd-bar" v-if="b.progress">
                <div class="bd-bar-fill" :class="{done: b.earned}" :style="{width: b.progress.pct + '%'}"></div>
              </div>
              <div class="bd-prog" v-if="b.progress && !b.earned">{{b.progress.current}} / {{b.progress.target}}</div>
              <div class="badge-date" v-if="b.earned">{{b.earned_at}} 获得</div>
              <div class="badge-date" v-else>待解锁</div>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// BadgesView（B1 组件化自动抽取；新功能 B 升级：分类 tab + 进度条）。
// 业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有（徽章部分已抽到 logic/badges.js），
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'BadgesView',
  inject: ['appCtx'],
}
</script>
