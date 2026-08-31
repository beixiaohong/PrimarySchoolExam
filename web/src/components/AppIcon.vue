<template>
  <span class="app-icon" v-html="svg" role="img" :aria-label="name"></span>
</template>

<script>
// B3 全站图标统一：内联 SVG 图标集。
// 统一规范：24x24 视图、stroke=currentColor（继承文字颜色/主题色）、描边线帽圆润，
// 与全局 design token 风格一致（替代原先 nav 的 emoji，消除 emoji 与页内 SVG 割裂）。
// 用法：<app-icon name="home" :size="20" />，name 取自下方 ICONS 的键。
const ICONS = {
  // —— 导航条目图标（与 nav.js 的 icon 字段一一对应）——
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/>',
  practice: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  wrong: '<path d="M4 4h11a2 2 0 0 1 2 2v14H6a2 2 0 0 1-2-2Z"/><path d="M4 4v16"/><path d="M9.5 9.5l3 3M12.5 9.5l-3 3"/>',
  reading: '<path d="M12 6c-2-1.5-5-1.5-7 0v12c2-1.5 5-1.5 7 0 2-1.5 5-1.5 7 0V6c-2-1.5-5-1.5-7 0Z"/><path d="M12 6v12"/>',
  kp: '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="M3 13l9 5 9-5"/>',
  sync: '<path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-8-5"/><path d="M3 12a9 9 0 0 1 9-9 9 9 0 0 1 8 5"/><path d="M21 3v6h-6"/><path d="M3 21v-6h6"/>',
  courses: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M10 9l5 3-5 3Z"/>',
  recite: '<path d="M5 4h11a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2V4Z"/><path d="M9 8h6M9 12h6"/>',
  goals: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4"/>',
  pet: '<circle cx="7" cy="9" r="1.5"/><circle cx="12" cy="7.5" r="1.5"/><circle cx="17" cy="9" r="1.5"/><path d="M12 11c-2.5 0-4.5 2-4.5 4 0 2 2 3.4 4.5 3.4S16.5 17 16.5 15c0-2-2-4-4.5-4Z"/>',
  tree: '<path d="M12 21v-5"/><circle cx="12" cy="9" r="6"/><path d="M9 9.5h.01M15 9.5h.01"/>',
  badges: '<circle cx="12" cy="9" r="5"/><path d="M9 13.5 7.5 21 12 18.5 16.5 21 15 13.5"/>',
  cards: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="8.5" cy="9.5" r="1.4"/><path d="M21 16l-5-5L7 20"/>',
  wallet: '<path d="M3 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2"/><rect x="3" y="9" width="18" height="11" rx="2.5"/><circle cx="16.5" cy="14.5" r="1.3"/>',
  qa: '<circle cx="12" cy="12" r="9"/><path d="M9.2 9.3a2.8 2.8 0 0 1 5.3 1.1c0 1.9-2.5 2.6-2.5 2.6"/><path d="M12 17h.01"/>',
  aiquiz: '<rect x="4" y="4" width="16" height="16" rx="3.5"/><circle cx="9" cy="9" r="1.1"/><circle cx="15" cy="15" r="1.1"/><circle cx="15" cy="9" r="1.1"/><circle cx="9" cy="15" r="1.1"/>',
  assistant: '<rect x="5" y="8" width="14" height="11" rx="2.5"/><path d="M12 8V5"/><circle cx="12" cy="4" r="1.4"/><circle cx="9" cy="11" r="1"/><circle cx="15" cy="11" r="1"/><path d="M9.5 14h5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  focus: '<circle cx="12" cy="13" r="8"/><path d="M12 13V9"/><path d="M9 2h6"/>',
  dict: '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="13" width="4" height="7" rx="1.6"/><rect x="17" y="13" width="4" height="7" rx="1.6"/>',
  stats: '<path d="M4 20V10M9 20V4M14 20v-7M19 20v-11"/>',
  settings: '<circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/>',
  // —— 任务域图标（B3 批次2：首页今日任务卡 / 复习队列）——
  abc: '<path d="M4 18 7 6l3 12"/><path d="M5 14h4"/><path d="M14 18v-6a2.3 2.3 0 0 1 4.6 0v6"/><path d="M14 14.5h4"/>',
  repeat: '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
  memo: '<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M8.5 9h7M8.5 13h7M8.5 17h4"/>',
  scroll: '<path d="M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 0 2 2H9a2 2 0 0 1-2-2V4Z"/><path d="M6 4a2 2 0 0 0-2 2v1h2"/><path d="M10 8h6M10 12h6"/>',
  abacus: '<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8 7h8"/><circle cx="9" cy="11" r="1"/><circle cx="12" cy="11" r="1"/><circle cx="15" cy="11" r="1"/><circle cx="9" cy="15" r="1"/><circle cx="12" cy="15" r="1"/><circle cx="15" cy="15" r="1"/>',
  // —— 折叠指示 ——
  caret: '<path d="M6 9l6 6 6-6"/>',
  // —— 占位（name 未命中时）——
  placeholder: '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
}

export default {
  name: 'AppIcon',
  props: {
    name: { type: String, required: true },
    size: { type: [Number, String], default: 20 },
    stroke: { type: [Number, String], default: 2 },
  },
  computed: {
    svg() {
      const inner = ICONS[this.name] || ICONS.placeholder
      const s = this.size
      return (
        '<svg viewBox="0 0 24 24" width="' + s + '" height="' + s +
        '" fill="none" stroke="currentColor" stroke-width="' + this.stroke +
        '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        inner + '</svg>'
      )
    },
  },
}
</script>

<style scoped>
.app-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  vertical-align: middle;
  line-height: 0;
}
.app-icon svg {
  display: block;
}
</style>
