<template>
  <div>
    <h2>用户管理</h2>
    <div class="toolbar">
      <el-input v-model="kw" placeholder="搜索 账号 / 昵称 / 邮箱" style="width: 220px"
                @keyup.enter="load" />
      <el-select v-model="filter.grade" placeholder="年级" style="width: 100px" clearable @change="resetPage">
        <el-option v-for="g in 9" :key="g" :label="g + '年级'" :value="g" />
      </el-select>
      <el-select v-model="filter.subject" placeholder="学科" style="width: 100px" clearable @change="resetPage">
        <el-option v-for="s in ['数学','语文','英语']" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="filter.vip" placeholder="VIP" style="width: 100px" clearable @change="resetPage">
        <el-option label="仅 VIP" value="1" /><el-option label="非 VIP" value="0" />
      </el-select>
      <el-select v-model="filter.active" placeholder="状态" style="width: 110px" clearable @change="resetPage">
        <el-option label="正常" value="1" /><el-option label="已停用" value="0" />
      </el-select>
      <el-button type="primary" @click="load">搜索</el-button>
      <el-button @click="kw = ''; filter = { grade: 0, subject: '', vip: '', active: '' }; load()">重置</el-button>
      <div style="flex:1"></div>
      <el-button type="warning" :disabled="!selection.length" @click="openBatchRecharge">批量充值（{{ selection.length }}）</el-button>
      <el-button @click="doExport">导出 CSV</el-button>
    </div>

    <el-table :data="rows" border stripe style="margin-top: 12px" @selection-change="s => selection = s">
      <el-table-column type="selection" width="42" />
      <el-table-column prop="user_id" label="账号" min-width="120" />
      <el-table-column prop="nickname" label="昵称" min-width="100" />
      <el-table-column prop="grade" label="年级" width="64" />
      <el-table-column prop="email" label="邮箱" min-width="140" show-overflow-tooltip />
      <el-table-column prop="diamonds" label="钻石" width="80" />
      <el-table-column prop="coins" label="金币" width="80" />
      <el-table-column prop="makeup_cards" label="补签卡" width="80" />
      <el-table-column label="VIP" width="64">
        <template #default="{ row }"><el-tag v-if="row.is_vip" type="danger" size="small">VIP</el-tag><span v-else>-</span></template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '正常' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="注册" width="100" />
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="goDetail(row)">详情</el-button>
          <el-button size="small" type="warning" @click="openRecharge(row)">充值</el-button>
          <el-button v-if="row.is_active" size="small" type="danger" @click="toggleActive(row, false)">停用</el-button>
          <el-button v-else size="small" type="success" @click="toggleActive(row, true)">启用</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination style="margin-top: 12px" background layout="prev, pager, next, total"
                   :total="total" :page-size="pageSize" :current-page="page"
                   @current-change="(p) => { page = p; load() }" />

    <!-- 充值弹窗 -->
    <el-dialog v-model="rechargeOpen" title="账号充值 / 资产调整" width="420px">
      <el-form label-width="90px">
        <el-form-item label="目标账号">
          <el-input :model-value="cur.user_id" disabled />
        </el-form-item>
        <el-form-item label="资产类型">
          <el-select v-model="form.asset" style="width: 100%">
            <el-option label="钻石" value="diamond" />
            <el-option label="金币" value="coin" />
            <el-option label="补签卡" value="makeup" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="form.amount" :min="-999999" :max="999999" />
          <span class="hint">正数增加，负数扣减</span>
        </el-form-item>
        <el-form-item label="理由">
          <el-input v-model="form.reason" placeholder="必填，记录到审计日志" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rechargeOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRecharge">确认</el-button>
      </template>
    </el-dialog>
    <!-- 批量充值弹窗 -->
    <el-dialog v-model="batchRechargeOpen" title="批量充值 / 资产调整（多用户）" width="460px">
      <el-form label-width="90px">
        <el-form-item label="目标数量">
          <el-input :model-value="selection.length + ' 个账号'" disabled />
        </el-form-item>
        <el-form-item label="资产类型">
          <el-select v-model="batchForm.asset" style="width: 100%">
            <el-option label="钻石" value="diamond" />
            <el-option label="金币" value="coin" />
            <el-option label="补签卡" value="makeup" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="batchForm.amount" :min="1" :max="999999" />
          <span class="hint">每个账号分别增加该数量</span>
        </el-form-item>
        <el-form-item label="理由">
          <el-input v-model="batchForm.reason" placeholder="必填，记录到审计日志" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchRechargeOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitBatchRecharge">确认处理</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
// ElMessage 由 vite.config.js 的 unplugin-auto-import 按需自动注入，无需手动 import

const router = useRouter()
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const kw = ref('')
const filter = ref({ grade: 0, subject: '', vip: '', active: '' })
const selection = ref([])

const rechargeOpen = ref(false)
const saving = ref(false)
const cur = ref({})
const form = ref({ asset: 'diamond', amount: 10, reason: '' })

function resetPage() { page.value = 1; load() }

async function load() {
  const params = { page: page.value, page_size: pageSize.value }
  if (kw.value) params.keyword = kw.value
  if (filter.value.grade) params.grade = filter.value.grade
  if (filter.value.subject) params.subject = filter.value.subject
  if (filter.value.vip) params.vip = filter.value.vip
  if (filter.value.active) params.active = filter.value.active
  const d = await api.get('/api/admin/users', { params })
  rows.value = (d && d.items) || []
  total.value = (d && d.total) || 0
}

async function doExport() {
  try {
    const url = '/api/admin/users/export?' + new URLSearchParams({
      ...(kw.value ? { keyword: kw.value } : {}),
      ...(filter.value.grade ? { grade: filter.value.grade } : {}),
      ...(filter.value.subject ? { subject: filter.value.subject } : {}),
      ...(filter.value.vip ? { vip: filter.value.vip } : {}),
      ...(filter.value.active ? { active: filter.value.active } : {}),
    }).toString()
    const r = await api.get(url, { responseType: 'blob' })
    const blob = new Blob([r.data], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'users.csv'
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('已导出')
  } catch (e) { ElMessage.error(e.message || '导出失败') }
}

async function toggleActive(row, active) {
  try {
    await ElMessageBox.confirm(`确定${active ? '启用' : '停用'}账号「${row.user_id}」？停用后该账号无法登录`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.post(`/api/admin/users/${encodeURIComponent(row.user_id)}/active`, { active })
    ElMessage.success(active ? '已启用' : '已停用')
    load()
  } catch (e) { ElMessage.error(e.message || '操作失败') }
}

// 批量充值（逐用户调用资产调整接口）
const batchRechargeOpen = ref(false)
const batchForm = ref({ asset: 'diamond', amount: 10, reason: '' })
function openBatchRecharge() {
  batchForm.value = { asset: 'diamond', amount: 10, reason: '' }
  batchRechargeOpen.value = true
}
async function submitBatchRecharge() {
  if (!batchForm.value.reason.trim()) { ElMessage.warning('请填写理由'); return }
  if (!selection.value.length) return
  saving.value = true
  let ok = 0
  try {
    for (const row of selection.value) {
      try {
        await api.post('/api/admin/assets/adjust', {
          user_id: row.user_id, asset: batchForm.value.asset,
          amount: batchForm.value.amount, reason: batchForm.value.reason,
        })
        ok++
      } catch (e) { /* 单个失败继续 */ }
    }
    ElMessage.success(`批量处理完成：成功 ${ok}/${selection.value.length}`)
    batchRechargeOpen.value = false
    load()
  } finally { saving.value = false }
}

function goDetail(row) {
  router.push('/users/' + encodeURIComponent(row.user_id))
}

function openRecharge(row) {
  cur.value = row
  form.value = { asset: 'diamond', amount: 10, reason: '' }
  rechargeOpen.value = true
}

async function submitRecharge() {
  if (!form.value.reason.trim()) {
    ElMessage.warning('请填写调整理由')
    return
  }
  saving.value = true
  try {
    await api.post('/api/admin/assets/adjust', {
      user_id: cur.value.user_id,
      asset: form.value.asset,
      amount: form.value.amount,
      reason: form.value.reason,
    })
    ElMessage.success('已调整')
    rechargeOpen.value = false
    load()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '操作失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; margin-bottom: 4px; }
.hint { color: #909399; font-size: 12px; margin-left: 10px; }
</style>
