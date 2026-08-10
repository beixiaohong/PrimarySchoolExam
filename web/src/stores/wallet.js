import { defineStore } from 'pinia'
import api from '../api/http.js'

// 钱包（P5 新增）：聚合钻石 / 金币 / 补签卡余额与流水
export const useWalletStore = defineStore('wallet', {
  state: () => ({
    loaded: false,
    loading: false,
    diamonds: 0,
    coins: 0,
    diamondLedger: [],
    coinLedger: [],
    error: '',
  }),
  getters: {
    // 流水按正负分为收入/支出，便于展示
    diamondIncome: s => s.diamondLedger.filter(r => r.amount > 0),
    diamondExpense: s => s.diamondLedger.filter(r => r.amount < 0),
  },
  actions: {
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
