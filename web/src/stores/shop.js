import { defineStore } from 'pinia'
import api from '../api/http.js'

// 商城 store：商品列表 / 我的订单 / 支付信息 / 倒计时
export const useShopStore = defineStore('shop', {
  state: () => ({
    products: [],
    orders: [],
    loading: false,
    error: '',
    payOpen: false,
    payInfo: null,
    secondsLeft: 0,
    _timer: null,
  }),
  getters: {
    pendingOrders: s => s.orders.filter(o => o.status === 'PENDING_PAYMENT'),
  },
  actions: {
    async loadProducts() {
      try {
        const d = await api('/api/commerce/products').catch(() => [])
        this.products = Array.isArray(d) ? d : []
      } catch (e) {
        console.warn('[shop] loadProducts', e)
      }
    },
    async loadOrders() {
      try {
        const d = await api('/api/commerce/orders').catch(() => [])
        this.orders = Array.isArray(d) ? d : []
      } catch (e) {
        console.warn('[shop] loadOrders', e)
      }
    },
    async createOrder(productId, userId) {
      this.error = ''
      const key = 'web_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
      try {
        const d = await api('/api/commerce/orders', {
          method: 'POST',
          body: JSON.stringify({
            user_id: userId,
            product_id: productId,
            idempotency_key: key,
          }),
        })
        return d
      } catch (e) {
        this.error = e.message || '下单失败'
        return null
      }
    },
    async loadPaymentInfo(orderNo) {
      try {
        const d = await api(`/api/commerce/orders/${orderNo}/payment-info`)
        this.payInfo = d
        this.secondsLeft = d.seconds_left || 0
        this.payOpen = true
        this.startCountdown()
        return d
      } catch (e) {
        this.error = e.message || '获取支付信息失败'
        return null
      }
    },
    async cancelOrder(orderNo) {
      try {
        await api(`/api/commerce/orders/${orderNo}/cancel`, { method: 'POST' })
        await this.loadOrders()
      } catch (e) {
        this.error = e.message || '取消失败'
      }
    },
    startCountdown() {
      this.clearCountdown()
      this._timer = setInterval(() => {
        if (this.secondsLeft <= 0) {
          this.clearCountdown()
          this.payOpen = false
          this.loadOrders()
          return
        }
        this.secondsLeft--
      }, 1000)
    },
    clearCountdown() {
      if (this._timer) {
        clearInterval(this._timer)
        this._timer = null
      }
    },
    closePay() {
      this.payOpen = false
      this.payInfo = null
      this.clearCountdown()
    },
  },
})
