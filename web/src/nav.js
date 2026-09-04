// 侧边栏导航分组（B2 导航收敛：桌面端 5 分组，学习组按场景折叠子组）
// 每项：tab=旧版 tab 标识（叶子节点才有，驱动路由），label/icon 展示用；
//   icon=AppIcon 组件的内联 SVG 名称（B3 全站图标统一，取代原先 emoji ico）；
//   含 children 的项为「场景折叠父节点」，本身不跳转，点击展开/收起子项。
// NAV_GROUPS 驱动 App.vue 侧边栏渲染，ALL_TABS 仅汇总叶子 tab（见文件底部）。
export const NAV_GROUPS = [
  {
    title: '学习',
    items: [
      { tab: 'home', label: '今日学习', icon: 'home' },
      {
        label: '练习', icon: 'practice',
        children: [
          { tab: 'practice', label: '刷题中心', icon: 'practice' },
          { tab: 'wrong', label: '错题本', icon: 'wrong', badge: 'wrong' },
        ],
      },
      {
        label: '阅读', icon: 'reading',
        children: [
          { tab: 'reading', label: '阅读专项', icon: 'reading' },
          { tab: 'kp', label: '知识点卡', icon: 'kp' },
          { tab: 'sync', label: '同步学', icon: 'sync' },
          { tab: 'courses', label: '网课', icon: 'courses' },
        ],
      },
      { tab: 'recite', label: '背诵中心', icon: 'recite' },
      { tab: 'goals', label: '学习目标', icon: 'goals' },
    ],
  },
  {
    title: '成长与激励',
    items: [
      { tab: 'pet', label: '宠物家园', icon: 'pet', badge: 'pet' },
      { tab: 'tree', label: '成长树', icon: 'tree' },
      { tab: 'badges', label: '成就徽章', icon: 'badges', badge: 'badge' },
      { tab: 'cards', label: '知识卡图鉴', icon: 'cards' },
      { tab: 'wallet', label: '钱包', icon: 'wallet' },
    ],
  },
  {
    title: 'AI 伙伴',
    items: [
      { tab: 'qa', label: '十万个为什么', icon: 'qa' },
      { tab: 'aiquiz', label: 'AI 趣味出题', icon: 'aiquiz' },
      { tab: 'assistant', label: 'AI 学习助手', icon: 'assistant' },
    ],
  },
  {
    title: '工具',
    items: [
      { tab: 'search', label: '搜题', icon: 'search' },
      { tab: 'focus', label: '专注钟', icon: 'focus' },
      { tab: 'dict', label: '听写磨耳朵', icon: 'dict' },
    ],
  },
  {
    title: '我的',
    items: [
      { tab: 'stats', label: '学习统计', icon: 'stats' },
      { tab: 'settings', label: '设置', icon: 'settings' },
      { tab: 'parent', label: '家长管理', icon: 'parent', badge: 'parent' },
    ],
  },
]

// 移动端底部 TabBar（6 项；含「背诵」入口，与桌面端侧边栏一致）
// icon 同样引用 AppIcon 的 SVG 名称（B3 统一）
export const TABBAR = [
  { tab: 'home', label: '首页', icon: 'home' },
  { tab: 'practice', label: '刷题', icon: 'practice' },
  { tab: 'recite', label: '背诵', icon: 'recite' },
  { tab: 'assistant', label: 'AI', icon: 'assistant' },
  { tab: 'wallet', label: '钱包', icon: 'wallet' },
  { tab: 'settings', label: '我的', icon: 'settings' },
]

// 汇总所有「叶子」tab 标识（跳过仅作场景折叠的父节点），用于校验 URL/路由合法性、切换白名单等
export const ALL_TABS = NAV_GROUPS.flatMap(g => g.items.flatMap(i => i.children ? i.children.map(c => c.tab) : [i.tab]))
