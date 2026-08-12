// 侧边栏导航分组（P5：16 项平铺 → 4 分组，新增「钱包」）
// 每项：name=路由名/组件名，tab=旧版 tab 标识，label/ico 展示用
export const NAV_GROUPS = [
  {
    title: '学习',
    items: [
      { tab: 'home', label: '今日学习', ico: '🏠' },
      { tab: 'practice', label: '刷题中心', ico: '✏️' },
      { tab: 'recite', label: '背诵中心', ico: '📖' },
      { tab: 'dict', label: '听写磨耳朵', ico: '👂' },
      { tab: 'wrong', label: '错题本', ico: '📝', badge: 'wrong' },
      { tab: 'search', label: '搜题', ico: '🔍' },
      { tab: 'sync', label: '同步学', ico: '📚' },
      { tab: 'reading', label: '阅读专项', ico: '📜' },
      { tab: 'focus', label: '专注钟', ico: '⏰' },
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
    title: '我的',
    items: [
      { tab: 'stats', label: '学习统计', ico: '📊' },
      { tab: 'settings', label: '设置', ico: '⚙️' },
    ],
  },
]

// 移动端底部 TabBar（5 项）
export const TABBAR = [
  { tab: 'home', label: '首页', ico: '🏠' },
  { tab: 'practice', label: '刷题', ico: '✏️' },
  { tab: 'assistant', label: 'AI', ico: '🧑‍🏫' },
  { tab: 'wallet', label: '钱包', ico: '💰' },
  { tab: 'settings', label: '我的', ico: '⚙️' },
]

export const ALL_TABS = NAV_GROUPS.flatMap(g => g.items.map(i => i.tab))
