<template>
  <div class="anti-cheat-input" :class="mode">
    <!-- text：真实文本框，支持输入法（背古诗/默写场景；原候选字点选太难找字） -->
    <input
      v-if="mode === 'text'"
      class="aci-input"
      :value="modelValue"
      :placeholder="placeholder"
      autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"
      @input="$emit('update:modelValue', $event.target.value)"
    >
    <template v-else>
      <div class="aci-display">
        <span class="aci-value" :class="{ empty: !modelValue }">{{ modelValue || placeholder }}</span>
        <button class="aci-clear" type="button" @click="clear" v-if="modelValue">✕</button>
      </div>
      <div class="aci-pad">
        <button
          v-for="(k, i) in keys"
          :key="mode + '-' + i + '-' + k"
          class="aci-key"
          type="button"
          @click="press(k)"
        >{{ k }}</button>
        <button class="aci-key aci-back" type="button" @click="back">⌫</button>
      </div>
    </template>
  </div>
</template>

<script>
export default {
  name: 'AntiCheatInput',
  props: {
    // 'text' = 真实文本框（输入法可用）；'alpha' = 字母+数字软键盘（英文/拼音，无 IME）；
    // 'hanzi' = 点选字面板（防 IME 联想）
    mode: { type: String, default: 'alpha' },
    modelValue: { type: String, default: '' },
    placeholder: { type: String, default: '' },
    chars: { type: Array, default: () => [] }, // hanzi 模式的候选字（父组件经 API 提供）
  },
  emits: ['update:modelValue'],
  computed: {
    keys() {
      if (this.mode === 'alpha') {
        return 'abcdefghijklmnopqrstuvwxyz0123456789'.split('')
      }
      return this.chars || []
    },
  },
  methods: {
    press(k) {
      this.$emit('update:modelValue', (this.modelValue || '') + k)
    },
    back() {
      this.$emit('update:modelValue', (this.modelValue || '').slice(0, -1))
    },
    clear() {
      this.$emit('update:modelValue', '')
    },
  },
}
</script>

<style scoped>
.anti-cheat-input {
  width: 100%;
  max-width: 560px;
}
.aci-display {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 46px;
  padding: 8px 12px;
  border: 1px solid #e5e1f5;
  border-radius: 12px;
  background: #fff;
  font-size: 18px;
  letter-spacing: 1px;
}
.aci-value.empty {
  color: #b9b3d0;
  font-size: 14px;
  letter-spacing: 0;
}
.aci-clear {
  margin-left: auto;
  border: none;
  background: #f0edfa;
  color: #8b7cf6;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  cursor: pointer;
  font-size: 12px;
}
.aci-input {
  width: 100%;
  box-sizing: border-box;
  min-height: 46px;
  padding: 8px 12px;
  border: 1px solid #e5e1f5;
  border-radius: 12px;
  background: #fff;
  font-size: 18px;
  letter-spacing: 1px;
  color: #3a3450;
  outline: none;
}
.aci-input:focus {
  border-color: #8b7cf6;
  box-shadow: 0 0 0 3px rgba(139, 124, 246, 0.15);
}
.aci-pad {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.aci-key {
  min-width: 38px;
  height: 42px;
  padding: 0 10px;
  border: 1px solid #e5e1f5;
  border-radius: 10px;
  background: #fff;
  color: #3a3450;
  font-size: 17px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.12s, transform 0.06s;
}
.aci-key:hover {
  background: #f3f0fc;
}
.aci-key:active {
  transform: scale(0.94);
  background: #e8e2fb;
}
.aci-key.aci-back {
  background: #f7f5fd;
  color: #8b7cf6;
}
.anti-cheat-input.hanzi .aci-key {
  min-width: 44px;
  font-size: 20px;
}
</style>
