<template>
  <!-- 统一开关控件：**全站只有这一份实现**，页面里不要再手写「状态词按钮」或第二套开关样式。
       状态用三重表达 —— 文字（label）+ 颜色（tone）+ 开关位置（on）。
       用途示例：
         <state-switch :on="x" :label="x ? '已开启' : '已关闭'" :tone="x ? 'ok' : 'off'"
                       :title="x ? '点击关闭' : '点击开启'" @toggle="toggle()" /> -->
  <span class="ss">
    <em v-if="label" class="ss-txt" :class="'is-' + tone">{{ label }}</em>
    <button class="ss-sw" role="switch"
            :aria-checked="on ? 'true' : 'false'"
            :aria-label="label || title || '开关'"
            :class="{ on: on, busy: busy }"
            :disabled="disabled || busy"
            :title="title || (on ? '点击关闭' : '点击开启')"
            @click="$emit('toggle')"><i></i></button>
  </span>
</template>

<script>
// 起因（用户反馈原话）：「是否开启通知的显示不明确，我都不知道当前是开的还是关的」。
// 原先是一个按钮、按钮上写着**状态词**（「已开启」/「已关闭」），但按钮本身是**动作** ——
// 点「已开启」其实是把它关掉，读状态和做操作在同一元素上互相干扰。
// 现在拆开：状态用文字 + 颜色表达，动作交给开关的位置（位置即状态，点它才切换）。
//
// ⚠️ 用 role="switch" 的 button 而非 <input type="checkbox">：checkbox 的 :checked 是
// 属性绑定，Vue 只在值变化时打补丁 —— 一旦请求失败需要把界面回滚成原状态，
// 会出现「界面开着、数据是关的」这种更难排查的不一致。button 的 class 绑定没有这个问题。
export default {
  name: 'StateSwitch',
  props: {
    on: { type: Boolean, default: false },      // 当前状态（开/关）
    label: { type: String, default: '' },       // 状态文字，如「已开启」「接收」；留空表示只用开关本身（左侧已有说明）
    tone: { type: String, default: 'off' },     // 文字颜色：ok | warn | danger | off
    disabled: { type: Boolean, default: false },
    busy: { type: Boolean, default: false },    // 请求进行中：置灰并禁止连点
    title: { type: String, default: '' },       // 悬停提示，写清「点下去会怎样」
  },
  emits: ['toggle'],
}
</script>

<style scoped>
.ss{display:inline-flex;align-items:center;gap:8px;flex:0 0 auto}
.ss-txt{font-style:normal;font-size:12px;font-weight:600;color:var(--text-3)}
.ss-txt.is-ok{color:var(--success)}
.ss-txt.is-warn{color:var(--warning)}
.ss-txt.is-danger{color:var(--danger)}
.ss-txt.is-off{color:var(--text-3)}
.ss-sw{position:relative;flex:0 0 auto;width:40px;height:22px;padding:0;border-radius:999px;
  background:#D7DCE8;transition:background .18s}
.ss-sw i{position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;
  background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);transition:transform .18s}
.ss-sw.on{background:var(--success)}
.ss-sw.on i{transform:translateX(18px)}
.ss-sw.busy{opacity:.6}
.ss-sw:disabled{opacity:.45;cursor:not-allowed}
</style>
