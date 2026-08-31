<template>
<div class="fade-enter">
        <div class="hero" style="background:linear-gradient(135deg,#f7971e,#ffd200)">
          <div style="flex:1">
            <h1>🐣 宠物家园</h1>
            <p class="sub" style="color:rgba(255,255,255,.92)">完成任务、答对题目、讲清错题都能赚金币，喂饱小宠物陪它长大！</p>
          </div>
          <div class="pet-coin" v-if="appCtx.petProfile">
            <div class="pet-coin-num">{{appCtx.petProfile.coins}}</div>
            <div class="pet-coin-label">🪙 金币</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="pet-stage" v-if="appCtx.petProfile">
            <div class="pet-emoji">{{appCtx.petEmoji(appCtx.petProfile.level)}}</div>
            <div class="pet-name">{{appCtx.petName(appCtx.petProfile.level)}}<span class="tag tag-gold" style="margin-left:8px">Lv.{{appCtx.petProfile.level}}</span></div>
            <div class="pet-desc">{{appCtx.petDesc(appCtx.petProfile.level)}}</div>
            <div class="pet-exp-bar">
              <div class="pet-exp-fill" :style="{width: appCtx.petExpPct(appCtx.petProfile) + '%'}"></div>
            </div>
            <div class="pet-exp-text" v-if="appCtx.petProfile.exp_next">{{appCtx.petProfile.exp}} / {{appCtx.petProfile.exp_next}} 经验<span v-if="appCtx.petProfile.max_level">（已满级）</span></div>
            <div v-else class="pet-exp-text">⭐ 已满级，太棒啦！</div>
            <div class="pet-actions">
              <button class="btn btn-primary" :disabled="appCtx.petBusy || (appCtx.petProfile && appCtx.petProfile.coins < 10)" @click="appCtx.petFeed()">
                🍎 喂食（-10 金币，+5 经验）<span v-if="appCtx.petProfile && appCtx.petProfile.feeds_today"> · 今天已喂 {{appCtx.petProfile.feeds_today}} 次</span>
              </button>
              <button class="btn" :disabled="appCtx.petBusy || (appCtx.petProfile && appCtx.petProfile.pats_today >= 3)" @click="appCtx.petPat()">
                🤗 摸摸头（+1 经验）<span v-if="appCtx.petProfile"> · 今天 {{appCtx.petProfile.pats_today}}/3 次</span>
              </button>
            </div>
            <div v-if="appCtx.petMsg" class="pet-msg">{{appCtx.petMsg}}</div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>🪙 金币流水</b><span class="more" style="font-size:12px;color:var(--text-3)">余额：{{appCtx.petProfile ? appCtx.petProfile.coins : 0}}</span></div>
          <div v-if="!appCtx.petLedger.length" class="empty" style="padding:24px">
            <div class="em">🪙</div><h3>还没有金币记录</h3><p>完成任务、答题全对、错题掌握、小老师讲清楚都可以赚金币哦</p>
          </div>
          <div v-else class="pet-ledger-list">
            <div v-for="(l, i) in appCtx.petLedger" :key="i" class="pet-ledger-item">
              <span class="pet-ledger-reason">{{l.reason}}</span>
              <span class="pet-ledger-time">{{l.created_at}}</span>
              <span class="pet-ledger-amt" :class="{minus: l.amount < 0}">{{l.amount > 0 ? '+' : ''}}{{l.amount}}</span>
            </div>
          </div>
        </div>

        <div class="card" style="max-width:760px;margin-top:16px">
          <div class="card-head"><b>📜 赚金币规则</b></div>
          <div class="pet-rules">
            <div v-for="r in appCtx.petRules" :key="r.action" class="pet-rule-item">
              <div class="pet-rule-left"><b>{{r.action}}</b><span class="pet-rule-desc">{{r.desc}}</span></div>
              <span class="pet-rule-coin" :class="{minus: r.coins < 0}">{{r.coins > 0 ? '+' : ''}}{{r.coins}}</span>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// PetView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'PetView',
  inject: ['appCtx'],
}
</script>
