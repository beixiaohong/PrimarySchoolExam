// badges.js：成就徽章墙（新功能 B 升级：进度条 + 分类）的 data / computed / methods。
// 原徽章逻辑与「知识卡图鉴」混在 logic/cards.js，本次按功能拆出独立模块。
// 仅依赖通用 api/showToast（留在主文件）；与其他 logic/* 经展开运算符合并后 this 仍绑定同一实例。
//
// 后端契约（app/domains/engagement/services/achievement.py + routers/badges.py）：
//   GET /api/badges?user_id=  ->
//     { total, earned, newly:[code],
//       categories:[{key,label,total,earned}],
//       items:[{code,emoji,name,desc,category,earned,earned_at,progress:{current,target,pct}}] }
// 实时授予由后端写操作埋点完成（交卷 / 掌握错题 / 完成任务 / 心情打卡），前端无需轮询；
// 每枚徽章的 progress 由后端「指标当前值 / 阈值」派生，前端只负责渲染进度条。

export function badgesData() {
  return {
    badgeData: null,   // GET /api/badges 的完整响应（含 items/categories/total/earned/newly）
    badgeNew: [],      // 本次新解锁的徽章（顶部「恭喜获得」卡片 + Toast 用）
    badgeCat: '',      // 分类过滤：'' = 全部，否则为 categories[].key（study/persist/social）
  };
}

export const badgesComputed = {
  // 当前分类下要渲染的徽章列表（'' 显示全部，保持后端返回顺序）
  badgeItems() {
    const d = this.badgeData;
    if (!d || !d.items) return [];
    if (!this.badgeCat) return d.items;
    return d.items.filter(b => b.category === this.badgeCat);
  },
  // 分类 tab 数据：在「全部」聚合项后接后端 categories
  badgeCats() {
    const d = this.badgeData;
    if (!d || !d.categories) return [];
    return [{ key: '', label: '全部', total: d.total, earned: d.earned }].concat(d.categories);
  },
};

export const badgesMethods = {
  /* ─────────── 成就徽章墙（新功能 B：实时授予 + 进度 + 分类） ─────────── */
  // 拉取徽章墙。announce=true 时对新解锁徽章弹 Toast（进入徽章页时用）
  loadBadges(announce) {
    if (!this.user) return;
    this.api(`/api/badges?user_id=${encodeURIComponent(this.user)}`)
      .then(d => {
        const prevNew = this.badgeNew;
        this.badgeData = d;
        if (d.newly && d.newly.length) {
          this.badgeNew = (d.items || []).filter(b => (d.newly || []).includes(b.code));
          if (announce && this.badgeNew.length) {
            this.showToast(`🎉 获得新徽章：${this.badgeNew.map(b => b.name).join('、')}！`);
          }
        } else if (prevNew.length) {
          this.badgeNew = prevNew;
        }
      })
      .catch(() => { this.badgeData = null; });
  },
  // 切换分类过滤（前端本地过滤，不重新请求）
  setBadgeCat(key) {
    if (this.badgeCat === key) return;
    this.badgeCat = key;
  },
};
