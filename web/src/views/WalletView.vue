<template>
<div class="fade-enter">
        <div class="wallet-wrap">
          <div class="wallet-cards">
            <div class="wallet-card wc-diamond">
              <div class="wc-ico">💎</div>
              <div class="wc-num">{{appCtx.wallet.diamonds}}</div>
              <div class="wc-label">钻石</div>
            </div>
            <div class="wallet-card wc-coin">
              <div class="wc-ico">🪙</div>
              <div class="wc-num">{{appCtx.wallet.coins}}</div>
              <div class="wc-label">金币</div>
            </div>
            <div class="wallet-card wc-makeup">
              <div class="wc-ico">🎫</div>
              <div class="wc-num">{{appCtx.makeupCards}}</div>
              <div class="wc-label">补签卡</div>
            </div>
          </div>
          <div class="wallet-actions">
            <button class="btn btn-primary" @click="appCtx.openRecharge()">💎 购买钻石</button>
            <span class="wallet-hint">1 元 = 1 钻石 · 扫码付款后联系客服发放</span>
          </div>
          <div class="wallet-ledger card" v-if="appCtx.wallet.diamondLedger.length">
            <h3>💎 钻石明细</h3>
            <div class="wl-row" v-for="r in appCtx.wallet.diamondLedger" :key="r.id">
              <span class="wl-reason">{{r.reason}}</span>
              <span class="wl-amt" :class="r.amount>0?'up':'down'">{{r.amount>0?'+':''}}{{r.amount}}</span>
              <span class="wl-time">{{r.created_at}}</span>
            </div>
          </div>
        </div>
</div>
</template>

<script>
// WalletView（B1 组件化自动抽取）。业务逻辑由 App.vue 壳通过 appOptions mixin 统一持有，
// 本组件仅 inject appCtx 访问壳的响应式状态与方法，自身零 data/methods。
export default {
  name: 'WalletView',
  inject: ['appCtx'],
}
</script>
