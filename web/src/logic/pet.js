// 宠物家园（P2-1 金币宠物） & 成长树（P2-2 创意 7）
// 从 appOptions.js 机械抽取，沿用 logic/ 下三字典(spread)范式：
//   petData() 提供 data 字段，petMethods 提供方法，由 appOptions.js 展开合并。
// 注意：loadDiamonds(钻石余额) 为钱包/钻石系统共享加载器，留在 appOptions.js。
// petEmoji/petName/petDesc/petExpPct 为纯展示 methods（非 computed），随宠物方法一并迁出。

export function petData() {
  return {
    petProfile: null, petLedger: [], petRules: [], petMsg: '', petBusy: false, petLeveledUp: false,

      // 成长树（P2-2 创意 7）
      treeData: null,
      treeStages: [
        { name: '小种子', emoji: '🌱' }, { name: '小幼苗', emoji: '🌿' }, { name: '小树苗', emoji: '🪴' },
        { name: '青葱小树', emoji: '🌳' }, { name: '茁壮大树', emoji: '🌳' }, { name: '枝繁叶茂', emoji: '🌳' },
        { name: '开花啦', emoji: '🌸' }, { name: '硕果累累', emoji: '🍎' }, { name: '森林之王', emoji: '🌟' },
      ],
  };
}

export const petMethods = {
    /* ─────────── 宠物家园（P2-1 金币宠物） ─────────── */
    loadPet() {
      if (!this.user) return;
      this.api(`/api/pet?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.petProfile = d; })
        .catch(() => { this.petProfile = null; });
    },
    loadPetLedger() {
      if (!this.user) return;
      this.api(`/api/pet/ledger?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.petLedger = d || []; })
        .catch(() => { this.petLedger = []; });
    },
    loadPetRules() {
      if (this.petRules.length) return;
      this.api('/api/pet/rules')
        .then(d => { this.petRules = (d && d.items) || []; })
        .catch(() => {});
    },
    petFeed() {
      if (this.petBusy) return;
      this.petBusy = true;
      this.petMsg = '';
      this.api('/api/pet/feed', { method: 'POST', body: JSON.stringify({ user_id: this.user }) })
        .then(d => {
          const leveled = !!d.leveled;
          this.petProfile = d;
          if (leveled) {
            this.petLeveledUp = true;
            this.petMsg = '🎉 升级啦！宠物长成新的样子了！';
            this.showToast(`🎉 宠物升级到 Lv.${d.level}！`);
          } else {
            this.petMsg = '🍎 嗷呜～真好吃！经验 +5';
          }
          this.loadPetLedger();
        })
        .catch(e => { this.petMsg = e.message; })
        .finally(() => { this.petBusy = false; });
    },
    petPat() {
      if (this.petBusy) return;
      this.petBusy = true;
      this.petMsg = '';
      this.api('/api/pet/pat', { method: 'POST', body: JSON.stringify({ user_id: this.user }) })
        .then(d => {
          this.petProfile = d;
          this.petMsg = d.leveled ? '🎉 升级啦！宠物长成新的样子了！' : '🤗 好舒服～经验 +1';
          if (d.leveled) { this.petLeveledUp = true; this.showToast(`🎉 宠物升级到 Lv.${d.level}！`); }
        })
        .catch(e => { this.petMsg = e.message; })
        .finally(() => { this.petBusy = false; });
    },
    petEmoji(level) {
      if (level >= 9) return '🦚';
      if (level >= 7) return '🦜';
      if (level >= 5) return '🐥';
      if (level >= 3) return '🐤';
      return '🥚';
    },
    petName(level) {
      if (level >= 9) return '🦚 凤凰奇奇';
      if (level >= 7) return '🦜 鹦鹉小七';
      if (level >= 5) return '🐥 大黄鸭';
      if (level >= 3) return '🐤 小黄鸡';
      return '🥚 宠物蛋';
    },
    petDesc(level) {
      if (level >= 9) return '传说中的凤凰，闪闪发光，同学都会羡慕你！';
      if (level >= 7) return '学会说人话了，会跟着你朗读课文！';
      if (level >= 5) return '长出翅膀了，越来越精神！';
      if (level >= 3) return '破壳啦！一只毛茸茸的小家伙';
      return '还是一颗蛋，努力赚金币喂它，很快就会孵出来！';
    },
    petExpPct(p) {
      if (!p || !p.exp_next) return 100;
      return Math.min(100, Math.round(p.exp / p.exp_next * 100));
    },
    /* ─────────── 成长树（P2-2 创意 7） ─────────── */
    loadTree() {
      if (!this.user) return;
      this.api(`/api/tree?user_id=${encodeURIComponent(this.user)}`)
        .then(d => { this.treeData = d; })
        .catch(() => { this.treeData = null; });
    },
    treeStageName(idx) {
      const s = this.treeStages[idx];
      return s ? s.name : '';
    },
};
