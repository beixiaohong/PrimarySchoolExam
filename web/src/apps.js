// apps.js：平台模块注册表（应用中心 / 工作台「我的应用」的唯一数据源）。
//
// 为什么单独成文件：temp/blog.md §8.1 要求「不要把所有模块入口硬编码在一个 Vue 页面里」，
// 应用中心与工作台都从这份配置渲染，将来新增模块只改这里。
//
// 字段约定：
//   key      模块唯一标识（写进 db_workspace_app_usage.app_key，改名要慎重）
//   name     展示名
//   desc     一句话说明（应用中心卡片副标题）
//   icon     AppIcon 的内联 SVG 名（必须在 AppIcon.ICONS 中已定义，regression_check 第[6]项会校验）
//   tab      App.vue 的 tab 标识（点击后跳转 /#/<tab>）
//   enabled  是否上架应用中心
//   group    应用中心分组
export const APPS = [
  { key: 'study', name: '今日学习', desc: '今日任务、学习总览与待办', icon: 'home', tab: 'home', enabled: true, group: '学习' },
  { key: 'exam', name: '学生答题', desc: '在线答题、题库、错题和学习记录', icon: 'practice', tab: 'practice', enabled: true, group: '学习' },
  { key: 'wrong', name: '错题本', desc: '错题回顾与巩固练习', icon: 'wrong', tab: 'wrong', enabled: true, group: '学习' },
  { key: 'recite', name: '背诵中心', desc: '单词与古诗文背诵', icon: 'recite', tab: 'recite', enabled: true, group: '学习' },
  { key: 'reading', name: '阅读专项', desc: '阅读理解训练与讲解', icon: 'reading', tab: 'reading', enabled: true, group: '学习' },
  { key: 'gaoxiang', name: '高项学习', desc: '高级项目管理师学习、资料和考试准备', icon: 'gaoxiang', tab: 'gaoxiang', enabled: true, group: '学习' },
  { key: 'ledger', name: '账本', desc: '个人财务、收入支出和账目管理', icon: 'ledger', tab: 'ledger', enabled: true, group: '生活' },
  { key: 'chat', name: '聊天', desc: '即时聊天和消息交流', icon: 'im', tab: 'im', enabled: true, group: '生活' },
  { key: 'blog', name: '内容', desc: '文章、知识、技术分享和个人内容', icon: 'blog', tab: 'blog', enabled: true, group: '生活' },
  { key: 'assistant', name: 'AI 学习助手', desc: '随问随答的学习伙伴', icon: 'assistant', tab: 'assistant', enabled: true, group: '工具' },
  { key: 'search', name: '搜题', desc: '拍照/输入搜题与讲解', icon: 'search', tab: 'search', enabled: true, group: '工具' },
  { key: 'pet', name: '宠物家园', desc: '金币喂养与宠物成长', icon: 'pet', tab: 'pet', enabled: true, group: '工具' },
  { key: 'stats', name: '学习统计', desc: '学习数据与趋势分析', icon: 'stats', tab: 'stats', enabled: true, group: '工具' },
  { key: 'wallet', name: '钱包', desc: '钻石与资产明细', icon: 'wallet', tab: 'wallet', enabled: true, group: '工具' },
]

/** 上架应用（应用中心展示） */
export function enabledApps() {
  return APPS.filter(a => a.enabled)
}

/** app_key → 模块定义（工作台按使用记录反查展示信息） */
export function appByKey(key) {
  return APPS.find(a => a.key === key) || null
}

/** tab → 模块定义（进入某 tab 时判断是否属于已注册模块） */
export function appByTab(tab) {
  return APPS.find(a => a.tab === tab) || null
}

/** 应用中心分组（保持 APPS 中的出现顺序） */
export function appGroups() {
  const order = []
  const map = {}
  for (const a of enabledApps()) {
    if (!map[a.group]) { map[a.group] = []; order.push(a.group) }
    map[a.group].push(a)
  }
  return order.map(g => ({ group: g, items: map[g] }))
}
