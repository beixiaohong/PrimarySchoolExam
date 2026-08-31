// 侧边栏导航分组（B2 导航收敛：桌面端 5 分组，学习组按场景折叠子组）
// 每项：tab=旧版 tab 标识（叶子节点才有，驱动路由），label/ico 展示用；
//       含 children 的项为「场景折叠父节点」，本身不跳转，点击展开/收起子项。
// NAV_GROUPS 驱动 App.vue 侧边栏渲染，ALL_TABS 仅汇总叶子 tab（见文件底部）。
export const NAV_GROUPS = [
  {
    title: '学习',
    items: [
      { tab: 'home', label: '今日学习', ico: '🏠' },
      {
        label: '练习', ico: '✏️',
        children: [
          { tab: 'practice', label: '刷题中心', ico: '✏️' },
          { tab: 'wrong', label: '错题本', ico: '📝', badge: 'wrong' },
        ],
      },
      {
        label: '阅读', ico: '📜',
        children: [
          { tab: 'reading', label: '阅读专项', ico: '📜' },
          { tab: 'kp', label: '知识点卡', ico: '🧩' },
          { tab: 'sync', label: '同步学', ico: '📚' },
          { tab: 'courses', label: '网课', ico: '🎬' },
        ],
      },
      { tab: 'recite', label: '背诵中心', ico: '📖' },
      { tab: 'goals', label: '学习目标', ico: '🎯' },
    ],
  },
  {
    title: '成长与激励',
    items: [
      { tab: 'pet', label: '宠物家园', ico: '🐣', badge: 'pet' },
      { tab: 'tree', label: '成长树', ico: '🌳' },
      { tab: 'badges', label: '成就徽章', ico: '🏅', badge: 'badge' },
      { tab: 'cards', label: '知识卡图鉴', ico: '🃏' },
      { tab: 'wallet', label: '钱包', ico: '💰' },
    ],
  },
  {
    title: 'AI 伙伴',
    items: [
      { tab: 'qa', label: '十万个为什么', ico: '❓' },
      { tab: 'aiquiz', label: 'AI 趣味出题', ico: '🎲' },
      { tab: 'assistant', label: 'AI 学习助手', ico: '🧑‍🏫' },
    ],
  },
  {
    title: '工具',
    items: [
      { tab: 'search', label: '搜题', ico: '🔍' },
      { tab: 'focus', label: '专注钟', ico: '⏰' },
      { tab: 'dict', label: '听写磨耳朵', ico: '👂' },
    ],
  },
  {
    title: '我的',
    items: [
      { tab: 'stats', label: '学习统计', ico: '📊' },
      { tab: 'settings', label: '设置', ico: '⚙️' },
    ],
  },
]

// 移动端底部 TabBar（6 项；含「背诵」入口，与桌面端侧边栏一致）
export const TABBAR = [
  { tab: 'home', label: '首页', ico: '🏠' },
  { tab: 'practice', label: '刷题', ico: '✏️' },
  { tab: 'recite', label: '背诵', ico: '📖' },
  { tab: 'assistant', label: 'AI', ico: '🧑‍🏫' },
  { tab: 'wallet', label: '钱包', ico: '💰' },
  { tab: 'settings', label: '我的', ico: '⚙️' },
]

// 汇总所有「叶子」tab 标识（跳过仅作场景折叠的父节点），用于校验 URL/路由合法性、切换白名单等
export const ALL_TABS = NAV_GROUPS.flatMap(g => g.items.flatMap(i => i.children ? i.children.map(c => c.tab) : [i.tab]))
