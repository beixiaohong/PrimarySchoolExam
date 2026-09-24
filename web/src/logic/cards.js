// cards.js：知识卡图鉴 / 抽卡（CardsView）的 data 与 methods，从 appOptions.js 机械抽出。
// 仅依赖通用 api/showToast（留在主文件）；与其他 logic/* 经展开运算符合并后 this 仍绑定同一实例。
// loadTitles(称号) 位置靠后且被多处共用，仍留在 appOptions.js。
// 注：成就徽章（badgeData/badgeNew/loadBadges）已独立到 logic/badges.js（新功能 B 升级：进度+分类）。

export function cardsData() {
  return {
    cardData: null, drawCards: [], drawAllCollected: false, cardDrawing: false,
  };
}

export const cardsMethods = {
    /* ─────────── 知识卡图鉴（P2-4 创意 13） ─────────── */
    loadCards() {
      if (!this.user) return;
      this.api(`/api/cards?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.cardData = d; })
        .catch(() => { this.cardData = null; });
    },    cardDraw() {
      if (this.cardDrawing || !this.user) return;
      this.cardDrawing = true;
      this.drawCards = [];
      this.api(`/api/cards/draw?user_id=${encodeURIComponent(this.user)}`)
        .then(d => {
          this.drawAllCollected = !!d.all_collected;
          this.drawCards = d.cards || [];
          if (this.drawCards.length) this.showToast('🎴 抽到 3 张知识卡！');
        })
        .catch(e => this.showToast(e.message))
        .finally(() => { this.cardDrawing = false; });
    },}
