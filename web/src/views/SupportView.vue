<template>
<div class="fade-enter">
  <div class="support-wrap">
    <div class="card">
      <h3>📞 联系客服</h3>
      <div class="sup-cs">
        <div class="sup-row">
          <span>客服微信：</span>
          <code class="sup-id">{{ csContact || '加载中...' }}</code>
          <button class="btn btn-ghost btn-sm" @click="copyContact">{{ copied ? '已复制 ✓' : '复制' }}</button>
        </div>
        <div class="sup-qr" v-if="csQr">
          <img :src="csQr" alt="客服二维码" class="sup-qr-img" @error="onQrError">
        </div>
        <div class="sup-qr-empty" v-else-if="loaded">
          客服二维码尚未配置，请通过微信号联系客服
        </div>
      </div>
    </div>

    <div class="card">
      <h3>❓ 常见问题</h3>
      <div class="sup-faq">
        <details class="faq-item">
          <summary>付款后多久到账？</summary>
          <p>客服核销后通常 5 分钟内自动到账。钻石、补签卡即时发放，VIP 即时开通。</p>
        </details>
        <details class="faq-item">
          <summary>忘记填订单号备注怎么办？</summary>
          <p>请联系客服微信，提供付款截图和您的账号，客服手动匹配发放。</p>
        </details>
        <details class="faq-item">
          <summary>如何申请退款？</summary>
          <p>已到账的订单可在「我的订单」中申请退款，客服审核后原路退回。未到账的订单可直接取消。</p>
        </details>
        <details class="faq-item">
          <summary>钻石未到账怎么查？</summary>
          <p>请在「钱包 → 钻石明细」中查看记录。如显示已付款但明细无记录，请联系客服并提供订单号。</p>
        </details>
      </div>
    </div>

    <div class="card">
      <h3>🕐 服务时段</h3>
      <p class="sup-hours">每日 9:00 - 22:00，通常 30 分钟内响应。</p>
    </div>
  </div>
</div>
</template>

<script>
// SupportView：帮助与客服页。inject appCtx 访问壳状态，自身零 data。
// 客服信息通过 /api/diamond/recharge/config 获取（无需登录，含 cs_contact / cs_qr）。
export default {
  name: 'SupportView',
  inject: ['appCtx'],
  data() {
    return { csContact: '', csQr: '', loaded: false, copied: false }
  },
  mounted() {
    this.loadSupportInfo()
  },
  methods: {
    async loadSupportInfo() {
      try {
        const d = await fetch('/api/diamond/recharge/config').then(r => r.json())
        this.csContact = d.cs_contact || ''
        this.csQr = d.cs_qr || ''
        this.loaded = true
      } catch (e) {
        this.loaded = true
      }
    },
    copyContact() {
      navigator.clipboard.writeText(this.csContact).then(() => {
        this.copied = true
        setTimeout(() => { this.copied = false }, 2000)
      })
    },
    onQrError(e) {
      e.target.style.display = 'none'
    },
  },
}
</script>

<style scoped>
.support-wrap{max-width:600px;margin:0 auto;padding:12px}
.sup-cs{margin-top:8px}
.sup-row{display:flex;align-items:center;gap:8px;font-size:14px}
.sup-id{background:#F5F7FA;padding:4px 10px;border-radius:6px;font-size:15px;font-weight:700}
.sup-qr{margin-top:10px}
.sup-qr-img{width:160px;height:160px;border-radius:10px;border:1px solid var(--border,#ececf4);object-fit:contain}
.sup-qr-empty{font-size:13px;color:#999;margin-top:8px}
.sup-faq{display:flex;flex-direction:column;gap:8px}
.faq-item{border-bottom:1px solid var(--border,#ececf4);padding:8px 0}
.faq-item summary{font-weight:600;cursor:pointer;font-size:14px}
.faq-item p{margin:6px 0 0;font-size:13px;color:var(--text-2,#8a8fa3);line-height:1.6}
.sup-hours{font-size:13px;color:var(--text-2,#8a8fa3)}
</style>
