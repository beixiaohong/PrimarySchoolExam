// favorites.js：我的收藏（新功能 D，2026Q4）的 data / computed / methods，从 appOptions.js 机械抽出。
// 仅依赖通用 api/showToast（保留在主文件）；与其他 logic/* 经展开运算符合并后 this 仍绑定同一实例。
// 后端契约见 app/domains/engagement/routers/favorites.py：
//   GET  /api/favorites?item_type=&page=&page_size=
//        -> {items:[{id,user_id,item_type,item_id,title,created_at}], total, page, page_size}（按时间倒序）
//   POST /api/favorites  body {item_type, item_id, title}
//        -> {id,...}（幂等：已收藏返回现有记录，不重复插入）
//   DELETE /api/favorites/{id}  -> {ok:true, id}
// 列表仅存快照 title，跨域最新详情由各域经 contracts 提供，避免循环依赖（与后端设计一致）。

export function favoritesData() {
  return {
    favorites: [],          // 当前列表（按收藏时间倒序）
    favoritesTotal: 0,      // 该过滤条件下的总数（驱动「加载更多」）
    favoritesPage: 1,
    favoritesPageSize: 20,  // 与后端默认一致；后端 clamp[1,200]
    favoritesType: '',      // 过滤：'' | 'paper' | 'question'
    favoritesLoading: false,
    favSet: {},             // 快速查重：键 `${item_type}:${item_id}` -> 收藏记录 id（供列表/试卷星标即时判断）
  };
}

export const favoritesComputed = {
  // 是否还有更多可加载（分页）
  favoritesHasMore() {
    return this.favorites.length < this.favoritesTotal;
  },
};

export const favoritesMethods = {
  /* ─────────── 我的收藏（新功能 D） ─────────── */
  // 加载收藏列表；reset=true 时从第一页开始（切换分类/进入页面用），否则追加下一页
  loadFavorites(reset = true) {
    if (!this.user) return;
    if (reset) this.favoritesPage = 1;
    this.favoritesLoading = true;
    let url = `/api/favorites?page=${this.favoritesPage}&page_size=${this.favoritesPageSize}`;
    if (this.favoritesType) url += `&item_type=${encodeURIComponent(this.favoritesType)}`;
    this.api(url)
      .then(d => {
        const items = d.items || [];
        this.favorites = reset ? items : this.favorites.concat(items);
        this.favoritesTotal = d.total || 0;
        // 重建查重表（仅覆盖当前页，满足列表与试卷星标即时状态所需）
        if (reset) this.favSet = {};
        for (const f of items) this.favSet[`${f.item_type}:${f.item_id}`] = f.id;
      })
      .catch(() => { /* 静默：收藏为非关键功能，失败不阻断主流程 */ })
      .finally(() => { this.favoritesLoading = false; });
  },
  // 加载下一页（无限滚动/「加载更多」按钮）
  loadMoreFavorites() {
    if (this.favoritesLoading || !this.favoritesHasMore) return;
    this.favoritesPage += 1;
    this.loadFavorites(false);
  },
  // 切换分类过滤（全部/试卷/题目）
  setFavoritesType(t) {
    if (this.favoritesType === t) return;
    this.favoritesType = t;
    this.loadFavorites(true);
  },
  // 是否已收藏某 item（供试卷 ⭐ 按钮即时回显）
  isFavorited(itemType, itemId) {
    return !!this.favSet[`${itemType}:${itemId}`];
  },
  // 取收藏记录 id（用于取消收藏）
  favIdOf(itemType, itemId) {
    return this.favSet[`${itemType}:${itemId}`] || null;
  },
  // ⭐ 收藏 / 取消收藏 切换（幂等安全：取消走 record id，收藏走 item 唯一键）
  toggleFavorite(itemType, itemId, title) {
    if (!this.user) { this.showToast('请先登录'); return; }
    if (this.isFavorited(itemType, itemId)) {
      const id = this.favIdOf(itemType, itemId);
      this.api(`/api/favorites/${id}`, { method: 'DELETE' })
        .then(() => {
          delete this.favSet[`${itemType}:${itemId}`];
          this.favorites = this.favorites.filter(f => f.id !== id);
          this.favoritesTotal = Math.max(0, this.favoritesTotal - 1);
          this.showToast('已取消收藏');
        })
        .catch(e => this.showToast(e.message));
    } else {
      this.api('/api/favorites', {
        method: 'POST',
        body: JSON.stringify({ item_type: itemType, item_id: String(itemId), title: title || '' }),
      })
        .then(f => {
          this.favorites.unshift(f);              // 置顶显示最新收藏
          this.favoritesTotal += 1;
          this.favSet[`${f.item_type}:${f.item_id}`] = f.id;
          this.showToast('⭐ 已收藏');
        })
        .catch(e => this.showToast(e.message));
    }
  },
};
