<template>
<div class="fade-enter">
  <div class="wallet-wrap">
    <!-- 余额三卡 -->
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

    <!-- 商品区 -->
    <div class="card shop-section">
      <h3>🛒 商城</h3>
      <div v-if="!shop.products.length" class="shop-empty">
        <div class="em">🛒</div>
        <p>暂无商品</p>
      </div>
      <div v-for="group in productGroups" :key="group.type" class="shop-group">
        <div class="sg-title">{{ group.label }}</div>
        <div class="sg-list">
          <div v-for="p in group.items" :key="p.id" class="shop-card">
            <div class="sc-name">{{ p.name }}</div>
            <div class="sc-sub" v-if="p.subtitle">{{ p.subtitle }}</div>
            <div class="sc-benefits">
              <span v-for="b in p.benefits" :key="b.benefit_key" class="sc-tag">{{ benefitLabel(b) }}</span>
            </div>
            <div class="sc-price">
              <span class="sp-now">¥{{ formatPrice(p.price_fen) }}</span>
              <span class="sp-orig" v-if="p.original_fen > p.price_fen">¥{{ formatPrice(p.original_fen) }}</span>
            </div>
            <button class="btn btn-primary btn-sm" @click="handleBuy(p)">立即购买</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 我的订单 -->
    <div class="card shop-section">
      <h3>📦 我的订单</h3>
      <div v-if="!shop.orders.length" class="shop-empty">
        <div class="em">📦</div>
        <p>暂无订单</p>
      </div>
      <div v-for="o in shop.orders" :key="o.order_no" class="order-row">
        <div class="or-top">
          <span class="or-no">{{ o.product_name }}</span>
          <span class="or-status" :class="'st-' + o.status">{{ statusLabel(o.status) }}</span>
        </div>
        <div class="or-mid">
          <span>¥{{ formatPrice(o.amount_fen) }}</span>
          <span class="or-time">{{ formatTime(o.created_at) }}</span>
        </div>
        <div class="or-bot" v-if="o.status === 'PENDING_PAYMENT'">
          <button class="btn btn-primary btn-sm" @click="handlePay(o)">去支付</button>
          <button class="btn btn-ghost btn-sm" @click="handleCancel(o)">取消订单</button>
        </div>
      </div>
    </div>

    <!-- 钻石明细 -->
    <div class="wallet-ledger card" v-if="appCtx.wallet.diamondLedger.length">
      <h3>💎 钻石明细</h3>
      <div class="wl-row" v-for="r in appCtx.wallet.diamondLedger" :key="r.id">
        <span class="wl-reason">{{r.reason}}</span>
        <span class="wl-amt" :class="r.amount>0?'up':'down'">{{r.amount>0?'+':''}}{{r.amount}}</span>
        <span class="wl-time">{{r.created_at}}</span>
      </div>
    </div>
  </div>

  <!-- 支付弹窗 -->
  <div class="modal-mask" :class="{on: shop.payOpen}" @click.self="shop.closePay()">
    <div class="modal modal-pay">
      <div class="modal-head"><h2>💳 支付订单</h2><button class="icon-btn" @click="shop.closePay()">✕</button></div>
      <div class="modal-body" v-if="shop.payInfo">
        <div class="pay-amount">¥{{ formatPrice(shop.payInfo.amount_fen) }}</div>
        <div class="pay-memo">
          <span>付款备注填写：</span>
          <code class="pay-memo-code">{{ shop.payInfo.memo }}</code>
          <button class="btn btn-ghost btn-sm" @click="copyMemo">{{ copied ? '已复制 ✓' : '复制' }}</button>
        </div>
        <div class="pay-qrs">
          <div class="pay-qr" v-if="shop.payInfo.wechat_qr">
            <div class="pqr-title">💚 微信支付</div>
            <img :src="shop.payInfo.wechat_qr" alt="微信收款码" class="pqr-img" @error="onQrError($event)">
          </div>
          <div class="pay-qr" v-if="shop.payInfo.alipay_qr">
            <div class="pqr-title">🔵 支付宝</div>
            <img :src="shop.payInfo.alipay_qr" alt="支付宝收款码" class="pqr-img" @error="onQrError($event)">
          </div>
          <div v-if="!shop.payInfo.wechat_qr && !shop.payInfo.alipay_qr" class="pay-qr-empty">
            收款码尚未配置，请联系客服获取
          </div>
        </div>
        <div class="pay-tips">
          <p>{{ shop.payInfo.tips }}</p>
          <p v-if="shop.payInfo.cs_contact">客服微信：<b>{{ shop.payInfo.cs_contact }}</b></p>
        </div>
        <div class="pay-countdown" v-if="shop.secondsLeft > 0">
          剩余支付时间：{{ formatCountdown(shop.secondsLeft) }}
        </div>
        <div class="pay-order-no">订单号：{{ shop.payInfo.order_no }}</div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-primary" @click="handlePaid">我已完成付款</button>
      </div>
    </div>
  </div>
</div>
</template>

<script>
// WalletView（商城升级版）。业务逻辑由 App.vue 壳通过 appCtx 注入，
// shop store 由 App.vue setup() 返回并通过 inject 访问。自身零 data/methods（除辅助 filter）。
const STATUS_MAP = {
  PENDING_PAYMENT: '待付款',
  PENDING_APPROVAL: '待审批',
  PAID: '已付款·待发货',
  FULFILLED: '已完成',
  CLOSED: '已关闭',
  REFUNDING: '退款中',
  REFUNDED: '已退款',
  REVERSED: '已冲正',
}
const TYPE_LABEL = { diamond: '💎 钻石', membership: '👑 会员', coupon: '🎫 补签卡', combo: '🎁 组合包' }

export default {
  name: 'WalletView',
  inject: ['appCtx'],
  computed: {
    shop() { return this.appCtx.shop },
    productGroups() {
      const map = {}
      for (const p of (this.shop.products || [])) {
        const t = p.type || 'other'
        if (!map[t]) map[t] = { type: t, label: TYPE_LABEL[t] || t, items: [] }
        map[t].items.push(p)
      }
      return Object.values(map)
    },
    copied() { return this.appCtx.rechargeCopied },
  },
  methods: {
    formatPrice(fen) { return ((fen || 0) / 100).toFixed(2) },
    formatTime(s) { return s ? s.replace('T', ' ').slice(0, 16) : '' },
    formatCountdown(sec) {
      const m = Math.floor(sec / 60), s = sec % 60
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    },
    statusLabel(s) { return STATUS_MAP[s] || s },
    benefitLabel(b) {
      if (b.benefit_type === 'diamond') return `+${b.amount} 钻石`
      if (b.benefit_type === 'vip_days') return `${b.amount} 天`
      if (b.benefit_type === 'coupon' && b.benefit_key === 'makeup_card') return `补签卡×${b.amount}`
      return `${b.benefit_key}×${b.amount}`
    },
    async handleBuy(p) {
      const order = await this.shop.createOrder(p.id, this.appCtx.user)
      if (order && order.order_no) {
        await this.shop.loadOrders()
        await this.shop.loadPaymentInfo(order.order_no)
      }
    },
    async handlePay(o) {
      await this.shop.loadPaymentInfo(o.order_no)
    },
    async handleCancel(o) {
      if (confirm('确定取消订单？')) await this.shop.cancelOrder(o.order_no)
    },
    async handlePaid() {
      alert('客服核销后自动到账，通常 5 分钟内')
      this.shop.closePay()
      await this.shop.loadOrders()
      this.appCtx.wallet.load(this.appCtx.user, this.appCtx.makeupCards)
    },
    copyMemo() {
      navigator.clipboard.writeText(this.shop.payInfo.memo).then(() => {
        this.appCtx.rechargeCopied = true
        setTimeout(() => { this.appCtx.rechargeCopied = false }, 2000)
      })
    },
    onQrError(e) {
      e.target.style.display = 'none'
      e.target.parentElement.innerHTML += '<div class="pqr-broken">收款码加载失败</div>'
    },
  },
}
</script>
