// level.js：等级 / 成长体系（新功能 C，2026Q4）的 data / computed / methods，从 appOptions.js 机械抽出。
// 仅依赖通用 api/goTab/showToast（通用方法保留在主文件）；与其他 logic/* 经展开运算符合并后
// this 仍绑定同一实例。后端契约见 app/domains/engagement/routers/level.py：
//   GET /api/level -> {level, exp, title, perk, level_min_exp, next_level, next_title,
//                      next_level_exp, exp_to_next, progress_pct, is_max, max_level,
//                      reward_diamond, ladder:[{lv,min_exp,title,perk,reward_diamond}]}
//
// 设计约定：**进度/阈值一律用后端返回值**，前端不重算（否则前后端各算一遍阈值，
// 迟早出现进度条与后端等级判定不一致）；这里的 computed 只做「未加载时兜底」与展示格式化。
// 经验由服务端行为埋点累加，前端只读、无写入端点（防刷级，见后端路由注释）。

export function levelData() {
  return {
    levelInfo: null,      // GET /api/level 的响应对象（null = 未加载）
    levelLoading: false,  // 加载中（防重复请求 / 供骨架态展示）
  };
}

export const levelComputed = {
  // 当前等级（未加载时显示 Lv.1，避免顶栏徽标空白/跳动）
  levelNum() {
    return this.levelInfo && this.levelInfo.level ? this.levelInfo.level : 1;
  },
  // 顶栏徽标文案
  levelBadgeText() {
    return 'Lv.' + this.levelNum;
  },
  // 当前称号
  levelTitle() {
    return (this.levelInfo && this.levelInfo.title) || '';
  },
  // 当前等级区间内的进度百分比（0~100，以后端 progress_pct 为准）
  levelPct() {
    const p = this.levelInfo && this.levelInfo.progress_pct;
    return typeof p === 'number' ? p : 0;
  },
  // 完整等级阶梯（未加载时为空数组，避免模板 v-for 取长度报错）
  levelLadder() {
    return (this.levelInfo && this.levelInfo.ladder) || [];
  },
  // 是否已满级（满级后进度条固定 100%、不显示「距下一级」）
  levelIsMax() {
    return !!(this.levelInfo && this.levelInfo.is_max);
  },
  // 距下一级还差多少经验
  levelExpToNext() {
    return (this.levelInfo && this.levelInfo.exp_to_next) || 0;
  },
};

export const levelMethods = {
  /* ─────────── 等级成长（新功能 C） ─────────── */
  loadLevel() {
    if (!this.user) return;
    this.levelLoading = true;
    this.api('/api/level')
      .then(d => { this.levelInfo = d || null; })
      .catch(() => { this.levelInfo = null; })
      .finally(() => { this.levelLoading = false; });
  },
  // 顶栏徽标点击 → 进入等级页（走 goTab 以复用 URL/加载统一逻辑）
  openLevel() {
    this.goTab('level');
  },
  // 阶梯行样式类：已达成 done / 当前级 cur。
  // 放在 JS 而非模板表达式里，是因为模板中若出现 `x < y`（`<` 后紧跟字母）会被 HTML
  // 解析器当作标签开头，进而引发编译/渲染异常——比较运算一律在 JS 侧完成。
  levelItemClass(l) {
    const cur = this.levelNum;
    return { done: l.lv < cur, cur: l.lv === cur };
  },
  // 阶梯行状态文案（同理由 JS 侧判定，模板只做渲染）
  levelItemState(l) {
    const cur = this.levelNum;
    if (l.lv < cur) return '已达成';
    if (l.lv === cur) return '进行中';
    return '';
  },
};
