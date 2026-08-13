<template>
  <div>
    <h2>用户管理</h2>
    <div class="toolbar">
      <el-input v-model="kw" placeholder="搜索 账号 / 昵称 / 邮箱" style="width: 280px"
                @keyup.enter="load" />
      <el-button type="primary" @click="load">搜索</el-button>
      <el-button @click="kw = ''; load()">重置</el-button>
    </div>

    <el-table :data="rows" border stripe style="margin-top: 12px">
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
      <el-table-column prop="created_at" label="注册" width="100" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="goDetail(row)">详情</el-button>
          <el-button size="small" type="warning" @click="openRecharge(row)">充值</el-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const kw = ref('')

const rechargeOpen = ref(false)
const saving = ref(false)
const cur = ref({})
const form = ref({ asset: 'diamond', amount: 10, reason: '' })

async function load() {
  const { data } = await api.get('/api/admin/users', {
    params: { keyword: kw.value, page: page.value, page_size: pageSize.value },
  })
  rows.value = data.items
  total.value = data.total
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
