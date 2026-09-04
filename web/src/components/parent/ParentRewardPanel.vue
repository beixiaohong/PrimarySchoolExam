<template>
  <!-- 激励兑现类：兑换券管理。默认收起。 -->
  <div class="pc-fold-group">
    <details class="pc-fold">
      <summary class="pc-fold-head">
        <app-icon name="caret" :size="16" class="pc-fold-caret"></app-icon>
        <span class="pc-fold-title">🎫 兑换券管理</span>
        <span class="more">可设全勤天数门槛，孩子达成即获得；家长核销兑现 · 成长奖励记录只展示已获取的券</span>
      </summary>
      <div class="pc-fold-body">
        <div class="pc-row" style="flex-wrap:wrap">
          <input v-model="appCtx.newCoupon.title" class="fill-input" maxlength="30" placeholder="如：周末看动画半小时" style="min-width:150px">
          <select v-model="appCtx.newCoupon.kind" class="fill-input" style="min-width:140px">
            <option value="cartoon">动画时间</option><option value="snack">零食券</option>
            <option value="sticker">贴纸券</option><option value="toy">玩具券</option>
            <option value="outing">外出券</option><option value="custom">自定义</option>
          </select>
          <input v-model.number="appCtx.newCoupon.requiredDays" type="number" min="0" max="30" class="fill-input" style="width:120px" placeholder="全勤几天">
          <span class="more">0=添加即获得</span>
          <input v-model.number="appCtx.newCoupon.requiredWithinDays" type="number" min="0" max="365" :disabled="!appCtx.newCoupon.requiredDays" class="fill-input" style="width:120px" placeholder="限几天内">
          <span class="more">0=不限期</span>
          <input v-model="appCtx.newCoupon.reason" class="fill-input" maxlength="50" placeholder="奖励理由（选填）" style="min-width:150px">
          <button class="btn btn-primary btn-sm" @click="appCtx.createCoupon()">添加</button>
        </div>
        <div class="pc-list" v-if="appCtx.allCoupons.length">
          <div class="pc-item" v-for="c in appCtx.allCoupons" :key="c.id" style="flex-wrap:wrap">
            <span class="ci">{{appCtx.couponIcon(c.kind)}}</span>
            <div class="c-body">
              <b>{{c.title}}</b>
              <!-- 原 SettingsView 四层嵌套 <template> 条件文案抽成 couponRuleText(c)，此处只留一次插值 -->
              <span>{{couponRuleText(c)}}</span>
              <span v-if="c.status==='active'">已获得 {{c.granted_count}} 张 · 剩余 {{c.left}} 张</span>
              <span v-else>已停用（历史获得 {{c.granted_count}} 张）</span>
            </div>
            <button v-if="c.status==='active' && c.left>0" class="btn btn-success btn-sm" @click="appCtx.redeemCoupon(c)">核销 1 张</button>
            <button class="btn btn-sm" :class="c.status==='active' ? 'btn-ghost' : 'btn-primary'" @click="appCtx.toggleCoupon(c)">{{c.status==='active' ? '停用' : '启用'}}</button>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<script>
// 家长管理·激励兑现面板。inject appCtx 委托业务动作；couponRuleText 为本组件内纯展示函数
// （把券的门槛规则拼成一行文案，等价替换原 SettingsView.vue:310 的四层嵌套 template，不改任何逻辑）。
export default {
  name: 'ParentRewardPanel',
  inject: ['appCtx'],
  methods: {
    couponRuleText(c) {
      let s = c.kind_label || '';
      if (c.required_days > 0) {
        s += ` · 三科全勤 ${c.required_days} 天得 1 张`;
        if (c.required_within_days > 0) s += ` · 限 ${c.required_within_days} 天内 · 超时进度清零重启`;
        else s += ' · 7天内最多缺1天，超出从头计算';
      }
      if (c.reason) s += ` · 🎯 ${c.reason}`;
      return s;
    },
  },
}
</script>
