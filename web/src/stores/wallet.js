import { defineStore } from 'pinia'
import api from '../api/http.js'

// 钱包（P5 新增）：聚合钻石 / 金币 / 补签卡余额与流水
export const useWalletStore = defineStore('wallet', {
  state: () => ({
    loaded: false,    // 是否已成功加载过一次
    loading: false,   // 是否正在请求中（防重复加载/展示 loading）
    diamonds: 0,      // 钻石余额（高级货币）
    coins: 0,         // 金币余额（宠物/日常货币）
    makeupCards: 0,   // 补签卡数量（由 load 入参写入，用于补签消耗）
    diamondLedger: [],// 钻石收支流水
    coinLedger: [],   // 金币收支流水
    error: '',
  }),
  getters: {
    // 流水按正负分为收入/支出，便于展示
    diamondIncome: s => s.diamondLedger.filter(r => r.amount > 0),
    diamondExpense: s => s.diamondLedger.filter(r => r.amount < 0),
  },
  actions: {
    // 加载钱包全量数据：并发拉取钻石余额、钻石流水、宠物(含金币)、金币流水。
    // makeupCards 为父级（如首页）传入的可用补签卡数，单独写入 state。
    // 各请求独立 catch，避免单接口失败导致整个钱包空白。
    async load(userId, makeupCards = 0) {
      if (!userId) return
      this.loading = true
      this.error = ''
      this.makeupCards = makeupCards
      try {
        const [dBal, dLedger, pet, cLedger] = await Promise.all([
          api(`/api/diamond/balance?user_id=${encodeURIComponent(userId)}`).catch(() => ({ balance: 0 })),
          api(`/api/diamond/ledger?user_id=${encodeURIComponent(userId)}&limit=30`).catch(() => []),
          api(`/api/pet?user_id=${encodeURIComponent(userId)}`).catch(() => null),
          api(`/api/pet/ledger?user_id=${encodeURIComponent(userId)}`).catch(() => []),
        ])
        this.diamonds = dBal.balance || 0
        this.diamondLedger = Array.isArray(dLedger) ? dLedger : []
        this.coins = pet ? (pet.coins || 0) : 0
        this.coinLedger = Array.isArray(cLedger) ? cLedger : []
        this.loaded = true
      } catch (e) {
        this.error = e.message || '加载钱包失败'
      } finally {
        this.loading = false
      }
    },
  },
})
