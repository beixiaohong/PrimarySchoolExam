<template>
  <div>
    <h2>充值 · 商品与订单</h2>
    <el-tabs v-model="tab">
      <!-- ======================= 商品管理 ======================= -->
      <el-tab-pane label="商品管理" name="products">
        <div class="toolbar">
          <el-select v-model="pFilter.status" placeholder="状态" style="width: 110px" clearable @change="loadProducts">
            <el-option label="已上架" value="online" />
            <el-option label="已下架" value="offline" />
          </el-select>
          <el-select v-model="pFilter.type" placeholder="类型" style="width: 120px" clearable @change="loadProducts">
            <el-option label="会员" value="membership" />
            <el-option label="钻石" value="diamond" />
            <el-option label="优惠券" value="coupon" />
            <el-option label="组合包" value="bundle" />
          </el-select>
          <el-input v-model="pFilter.keyword" placeholder="搜索 名称 / SKU" style="width: 200px" clearable @keyup.enter="loadProducts" />
          <el-button type="primary" @click="loadProducts">搜索</el-button>
          <div style="flex:1"></div>
          <el-button type="primary" @click="openProduct()">新增商品</el-button>
        </div>

        <el-table :data="products" border stripe style="margin-top: 12px">
          <el-table-column prop="id" label="ID" width="64" />
          <el-table-column prop="sku" label="SKU" min-width="110" />
          <el-table-column prop="name" label="商品名" min-width="150" show-overflow-tooltip />
          <el-table-column label="类型" width="90">
            <template #default="{ row }"><el-tag size="small">{{ typeName(row.type) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="售价" width="90">
            <template #default="{ row }"><span class="price">¥{{ fen2yuan(row.price_fen) }}</span></template>
          </el-table-column>
          <el-table-column label="原价" width="90">
            <template #default="{ row }"><span class="line">¥{{ fen2yuan(row.original_fen) }}</span></template>
          </el-table-column>
          <el-table-column prop="duration_days" label="天数" width="70" />
          <el-table-column prop="grade_scope" label="学段" width="90" />
          <el-table-column prop="sort_order" label="排序" width="70" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'online' ? 'success' : 'info'" size="small">{{ row.status === 'online' ? '已上架' : '已下架' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openProduct(row)">编辑</el-button>
              <el-button v-if="row.status === 'offline'" size="small" type="success" @click="setStatus(row, 'online')">上架</el-button>
              <el-button v-else size="small" type="warning" @click="setStatus(row, 'offline')">下架</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top: 12px" background layout="prev, pager, next, total"
                       :total="pTotal" :page-size="pSize" :current-page="pPage"
                       @current-change="(p) => { pPage = p; loadProducts() }" />
      </el-tab-pane>

      <!-- ======================= 订单管理 ======================= -->
      <el-tab-pane label="订单管理" name="orders">
        <div class="toolbar">
          <el-select v-model="oFilter.status" placeholder="状态" style="width: 130px" clearable @change="loadOrders">
            <el-option v-for="(v, k) in ORDER_STATUS" :key="k" :label="v" :value="k" />
          </el-select>
          <el-input v-model="oFilter.user_id" placeholder="用户 ID" style="width: 160px" clearable @keyup.enter="loadOrders" />
          <el-input v-model="oFilter.order_no" placeholder="订单号" style="width: 180px" clearable @keyup.enter="loadOrders" />
          <el-button type="primary" @click="loadOrders">搜索</el-button>
        </div>

        <el-table :data="orders" border stripe style="margin-top: 12px">
          <el-table-column prop="order_no" label="订单号" min-width="180" />
          <el-table-column prop="user_id" label="用户" min-width="110" />
          <el-table-column prop="product_name" label="商品" min-width="140" show-overflow-tooltip />
          <el-table-column label="金额" width="90">
            <template #default="{ row }"><span class="price">¥{{ fen2yuan(row.amount_fen) }}</span></template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusName(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="100">
            <template #default="{ row }">{{ (row.created_at || '').slice(0, 16).replace('T', ' ') }}</template>
          </el-table-column>
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openDetail(row)">详情</el-button>
              <el-button v-if="row.status === 'PENDING_PAYMENT' || row.status === 'PENDING_APPROVAL'" size="small" type="primary" @click="openConfirm(row)">核销</el-button>
              <el-button v-if="row.status === 'PENDING_APPROVAL'" size="small" type="success" @click="approveOrder(row)">审批</el-button>
              <el-button v-if="row.status === 'PENDING_APPROVAL'" size="small" type="warning" @click="rejectOrder(row)">驳回</el-button>
              <el-button v-if="row.status === 'FULFILLED'" size="small" type="danger" @click="openRefund(row)">退款</el-button>
              <el-button v-if="row.status === 'PAID'" size="small" type="danger" @click="openReverse(row)">冲正</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top: 12px" background layout="prev, pager, next, total"
                       :total="oTotal" :page-size="oSize" :current-page="oPage"
                       @current-change="(p) => { oPage = p; loadOrders() }" />
      </el-tab-pane>
    </el-tabs>

    <!-- 商品编辑弹窗 -->
    <el-dialog v-model="pOpen" :title="pCur.id ? '编辑商品' : '新增商品'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="SKU"><el-input v-model="pForm.sku" placeholder="全局唯一编码，如 vip_1y" /></el-form-item>
        <el-form-item label="商品名"><el-input v-model="pForm.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="pForm.type" style="width: 100%">
            <el-option label="会员 membership" value="membership" />
            <el-option label="钻石 diamond" value="diamond" />
            <el-option label="优惠券 coupon" value="coupon" />
            <el-option label="组合包 bundle" value="bundle" />
          </el-select>
        </el-form-item>
        <el-form-item label="副标题"><el-input v-model="pForm.subtitle" /></el-form-item>
        <el-form-item label="售价(元)"><el-input-number v-model="pForm.price_yuan" :min="0" :precision="2" :step="1" style="width: 100%" /></el-form-item>
        <el-form-item label="原价(元)"><el-input-number v-model="pForm.original_yuan" :min="0" :precision="2" :step="1" style="width: 100%" /></el-form-item>
        <el-form-item label="会员天数"><el-input-number v-model="pForm.duration_days" :min="0" :max="99999" /><span class="hint">membership 类型用</span></el-form-item>
        <el-form-item label="适用学段"><el-input v-model="pForm.grade_scope" placeholder="如 1-6 / 初中 / 全部" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="pForm.sort_order" :min="0" :max="9999" /><span class="hint">越大越靠前</span></el-form-item>
        <el-form-item label="详情"><el-input v-model="pForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveProduct">保存</el-button>
      </template>
    </el-dialog>

    <!-- 订单详情弹窗 -->
    <el-dialog v-model="oDetailOpen" title="订单详情" width="640px">
      <template v-if="oDetail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="订单号" :span="2">{{ oDetail.order_no }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ oDetail.user_id }}</el-descriptions-item>
          <el-descriptions-item label="金额">¥{{ fen2yuan(oDetail.amount_fen) }}</el-descriptions-item>
          <el-descriptions-item label="商品">{{ oDetail.product_name }}（{{ oDetail.product_sku }}）</el-descriptions-item>
          <el-descriptions-item label="状态">{{ statusName(oDetail.status) }}</el-descriptions-item>
          <el-descriptions-item label="创建">{{ fmt(oDetail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="支付">{{ fmt(oDetail.paid_at) }}</el-descriptions-item>
          <el-descriptions-item label="履约">{{ fmt(oDetail.fulfilled_at) }}</el-descriptions-item>
          <el-descriptions-item label="到期">{{ fmt(oDetail.expire_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="oDetail.close_reason" label="关单原因" :span="2">{{ oDetail.close_reason }}</el-descriptions-item>
          <el-descriptions-item v-if="oDetail.remark" label="备注" :span="2">{{ oDetail.remark }}</el-descriptions-item>
        </el-descriptions>

        <h4 style="margin: 16px 0 8px">支付流水</h4>
        <el-table :data="oDetail.transactions || []" border size="small">
          <el-table-column prop="action" label="动作" width="100" />
          <el-table-column prop="gateway" label="网关" width="90" />
          <el-table-column label="金额" width="90">
            <template #default="{ row }"><span class="price">¥{{ fen2yuan(row.received_fen) }}</span></template>
          </el-table-column>
          <el-table-column prop="external_no" label="流水号" min-width="130" show-overflow-tooltip />
          <el-table-column prop="operator_name" label="操作人" width="90" />
          <el-table-column label="时间" width="130">
            <template #default="{ row }">{{ fmt(row.created_at) }}</template>
          </el-table-column>
        </el-table>

        <h4 style="margin: 16px 0 8px">审计记录</h4>
        <el-table :data="oDetail.audit_logs || []" border size="small">
          <el-table-column prop="admin" label="管理员" width="100" />
          <el-table-column prop="action" label="动作" width="150" />
          <el-table-column prop="detail" label="详情" min-width="180" show-overflow-tooltip />
          <el-table-column label="时间" width="130">
            <template #default="{ row }">{{ fmt(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-dialog>

    <!-- 核销弹窗 -->
    <el-dialog v-model="confirmOpen" title="核销订单" width="440px">
      <el-form label-width="100px">
        <el-form-item label="订单号"><el-input :model-value="oCur.order_no" disabled /></el-form-item>
        <el-form-item label="应付金额"><el-input :model-value="'¥' + fen2yuan(oCur.amount_fen)" disabled /></el-form-item>
        <el-form-item label="实收(元)"><el-input-number v-model="confirmForm.received_yuan" :min="0" :precision="2" :step="1" style="width: 100%" /></el-form-item>
        <el-form-item label="外部流水号"><el-input v-model="confirmForm.external_no" placeholder="支付宝/微信/银行流水号" /></el-form-item>
        <el-form-item label="渠道">
          <el-select v-model="confirmForm.channel" style="width: 100%">
            <el-option label="手动核销" value="manual" />
            <el-option label="支付宝" value="alipay" />
            <el-option label="微信" value="wechat" />
            <el-option label="银行转账" value="bank" />
          </el-select>
        </el-form-item>
        <el-form-item label="凭证链接"><el-input v-model="confirmForm.evidence_url" placeholder="可选" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="confirmForm.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="confirmOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="confirmPayment">确认核销</el-button>
      </template>
    </el-dialog>

    <!-- 退款弹窗 -->
    <el-dialog v-model="refundOpen" title="发起退款" width="440px">
      <el-form label-width="100px">
        <el-form-item label="订单号"><el-input :model-value="oCur.order_no" disabled /></el-form-item>
        <el-form-item label="退款金额(元)"><el-input-number v-model="refundForm.amount_yuan" :min="0" :precision="2" :step="1" style="width: 100%" /><span class="hint">留空退全额</span></el-form-item>
        <el-form-item label="原因"><el-input v-model="refundForm.reason" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="refundOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRefund">确认退款</el-button>
      </template>
    </el-dialog>

    <!-- 冲正弹窗 -->
    <el-dialog v-model="reverseOpen" title="冲正订单" width="440px">
      <el-form label-width="100px">
        <el-form-item label="订单号"><el-input :model-value="oCur.order_no" disabled /></el-form-item>
        <el-form-item label="原因"><el-input v-model="reverseForm.reason" type="textarea" :rows="2" placeholder="冲正原因（必填）" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reverseOpen = false">取消</el-button>
        <el-button type="danger" :loading="saving" @click="submitReverse">确认冲正</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const tab = ref('products')
const saving = ref(false)

// 订单状态字典
const ORDER_STATUS = {
  PENDING_PAYMENT: '待支付',
  PENDING_APPROVAL: '待审批',
  PAID: '已支付',
  FULFILLED: '已履约',
  CLOSED: '已关闭',
  REFUNDING: '退款中',
  REFUNDED: '已退款',
  REVERSED: '已冲正',
}
const STATUS_TYPE = {
  PENDING_PAYMENT: 'warning', PENDING_APPROVAL: 'warning',
  PAID: 'primary', FULFILLED: 'success', CLOSED: 'info',
  REFUNDING: 'warning', REFUNDED: 'info', REVERSED: 'danger',
}
const TYPE_NAME = { membership: '会员', diamond: '钻石', coupon: '优惠券', bundle: '组合包' }

function fen2yuan(fen) { return ((Number(fen) || 0) / 100).toFixed(2) }
function yuan2fen(yuan) { return Math.round((Number(yuan) || 0) * 100) }
function typeName(t) { return TYPE_NAME[t] || t }
function statusName(s) { return ORDER_STATUS[s] || s }
function statusType(s) { return STATUS_TYPE[s] || 'info' }
function fmt(d) { return d ? d.slice(0, 16).replace('T', ' ') : '-' }

// ======================= 商品 =======================
const products = ref([])
const pTotal = ref(0), pPage = ref(1), pSize = ref(20)
const pFilter = ref({ status: '', type: '', keyword: '' })
const pOpen = ref(false)
const pCur = ref({})
const pForm = ref({})

async function loadProducts() {
  const params = { page: pPage.value, size: pSize.value }
  if (pFilter.value.status) params.status = pFilter.value.status
  if (pFilter.value.type) params.type = pFilter.value.type
  if (pFilter.value.keyword) params.keyword = pFilter.value.keyword
  const { data: d } = await api.get('/api/admin/commerce/products', { params })
  products.value = (d && d.items) || []
  pTotal.value = (d && d.total) || 0
}

function openProduct(row) {
  pCur.value = row || {}
  pForm.value = row
    ? { sku: row.sku, name: row.name, type: row.type, subtitle: row.subtitle || '', description: row.description || '', price_yuan: Number(row.price_fen) / 100, original_yuan: Number(row.original_fen) / 100, duration_days: row.duration_days || 0, grade_scope: row.grade_scope || '', sort_order: row.sort_order || 0 }
    : { sku: '', name: '', type: 'membership', subtitle: '', description: '', price_yuan: 0, original_yuan: 0, duration_days: 0, grade_scope: '', sort_order: 0 }
  pOpen.value = true
}

async function saveProduct() {
  if (!pForm.value.sku || !pForm.value.name) { ElMessage.warning('请填写 SKU 与商品名'); return }
  const body = {
    sku: pForm.value.sku, name: pForm.value.name, type: pForm.value.type,
    subtitle: pForm.value.subtitle || '', description: pForm.value.description || '',
    price_fen: yuan2fen(pForm.value.price_yuan),
    original_fen: yuan2fen(pForm.value.original_yuan),
    duration_days: pForm.value.duration_days || 0,
    grade_scope: pForm.value.grade_scope || '', sort_order: pForm.value.sort_order || 0,
  }
  saving.value = true
  try {
    if (pCur.value.id) await api.put(`/api/admin/commerce/products/${pCur.value.id}`, body)
    else await api.post('/api/admin/commerce/products', body)
    ElMessage.success('已保存')
    pOpen.value = false
    loadProducts()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '保存失败') }
  finally { saving.value = false }
}

async function setStatus(row, status) {
  try { await api.post(`/api/admin/commerce/products/${row.id}/status`, { status }) } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || '操作失败'); return
  }
  ElMessage.success(status === 'online' ? '已上架' : '已下架')
  loadProducts()
}

// ======================= 订单 =======================
const orders = ref([])
const oTotal = ref(0), oPage = ref(1), oSize = ref(20)
const oFilter = ref({ status: '', user_id: '', order_no: '' })
const oCur = ref({})
const oDetailOpen = ref(false), oDetail = ref(null)

const confirmOpen = ref(false), confirmForm = ref({})
const refundOpen = ref(false), refundForm = ref({})
const reverseOpen = ref(false), reverseForm = ref({})

async function loadOrders() {
  const params = { page: oPage.value, size: oSize.value }
  if (oFilter.value.status) params.status = oFilter.value.status
  if (oFilter.value.user_id) params.user_id = oFilter.value.user_id
  if (oFilter.value.order_no) params.order_no = oFilter.value.order_no
  const { data: d } = await api.get('/api/admin/commerce/orders', { params })
  orders.value = (d && d.items) || []
  oTotal.value = (d && d.total) || 0
}

async function openDetail(row) {
  oCur.value = row
  try {
    const { data: d } = await api.get(`/api/admin/commerce/orders/${row.id}`)
    oDetail.value = d
    oDetailOpen.value = true
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '加载详情失败') }
}

function openConfirm(row) {
  oCur.value = row
  confirmForm.value = { received_yuan: Number(row.amount_fen) / 100, external_no: '', channel: 'manual', evidence_url: '', remark: '' }
  confirmOpen.value = true
}
async function confirmPayment() {
  if (!confirmForm.value.external_no.trim()) { ElMessage.warning('请填写外部流水号'); return }
  saving.value = true
  try {
    await api.post(`/api/admin/commerce/orders/${oCur.value.id}/confirm-payment`, {
      external_no: confirmForm.value.external_no,
      received_fen: yuan2fen(confirmForm.value.received_yuan),
      channel: confirmForm.value.channel,
      evidence_url: confirmForm.value.evidence_url || '',
      remark: confirmForm.value.remark || '',
    })
    ElMessage.success('已核销')
    confirmOpen.value = false
    loadOrders()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '核销失败') }
  finally { saving.value = false }
}

async function approveOrder(row) {
  try { await ElMessageBox.confirm(`审批通过订单「${row.order_no}」？`, '提示', { type: 'warning' }) } catch { return }
  try {
    await api.post(`/api/admin/commerce/orders/${row.id}/approve`)
    ElMessage.success('已审批通过'); loadOrders()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '审批失败') }
}
async function rejectOrder(row) {
  try { await ElMessageBox.confirm(`驳回订单「${row.order_no}」？将退回待支付`, '提示', { type: 'warning' }) } catch { return }
  try {
    await api.post(`/api/admin/commerce/orders/${row.id}/reject`)
    ElMessage.success('已驳回'); loadOrders()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '驳回失败') }
}

function openRefund(row) {
  oCur.value = row
  refundForm.value = { amount_yuan: null, reason: '' }
  refundOpen.value = true
}
async function submitRefund() {
  const body = { reason: refundForm.value.reason || '' }
  if (refundForm.value.amount_yuan != null) body.amount_fen = yuan2fen(refundForm.value.amount_yuan)
  saving.value = true
  try {
    await api.post(`/api/admin/commerce/orders/${oCur.value.id}/refund`, body)
    ElMessage.success('已发起退款'); refundOpen.value = false; loadOrders()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '退款失败') }
  finally { saving.value = false }
}

function openReverse(row) {
  oCur.value = row
  reverseForm.value = { reason: '' }
  reverseOpen.value = true
}
async function submitReverse() {
  if (!reverseForm.value.reason.trim()) { ElMessage.warning('请填写冲正原因'); return }
  saving.value = true
  try {
    await api.post(`/api/admin/commerce/orders/${oCur.value.id}/reverse`, { reason: reverseForm.value.reason })
    ElMessage.success('已冲正'); reverseOpen.value = false; loadOrders()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '冲正失败') }
  finally { saving.value = false }
}

onMounted(() => { loadProducts(); loadOrders() })
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; }
.price { color: #f56c6c; font-weight: 600; }
.line { color: #999; text-decoration: line-through; font-size: 12px; }
.hint { color: #999; font-size: 12px; margin-left: 8px; }
</style>
