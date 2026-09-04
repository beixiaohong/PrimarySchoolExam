<template>
  <div>
    <h2>审计日志</h2>
    <el-tabs v-model="tab" @tab-change="load">
      <el-tab-pane label="全部日志" name="all">
        <div class="toolbar">
          <el-input v-model="kw.action" placeholder="按 action 过滤" style="width: 180px" clearable @keyup.enter="load" />
          <el-input v-model="kw.admin" placeholder="按管理员名" style="width: 160px" clearable @keyup.enter="load" />
          <el-input v-model="kw.target_type" placeholder="按对象类型" style="width: 140px" clearable @keyup.enter="load" />
          <el-button type="primary" @click="load">搜索</el-button>
        </div>
      </el-tab-pane>
      <el-tab-pane label="高危操作" name="risk">
        <span class="hint">仅显示金额非空或命中高危权限分组的操作</span>
      </el-tab-pane>
    </el-tabs>

    <el-table :data="rows" border stripe size="small" style="margin-top: 8px" @row-click="openDetail">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="admin" label="管理员" width="100" />
      <el-table-column prop="action" label="动作" width="170" />
      <el-table-column prop="target" label="对象" width="140" show-overflow-tooltip />
      <el-table-column prop="target_type" label="对象类型" width="100" />
      <el-table-column prop="detail" label="详情" min-width="220" show-overflow-tooltip />
      <el-table-column label="金额" width="90">
        <template #default="{ row }">
          <span v-if="row.amount_fen != null" class="price">¥{{ ((row.amount_fen || 0) / 100).toFixed(2) }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="120" />
      <el-table-column label="高危" width="70">
        <template #default="{ row }"><el-tag v-if="row.is_high_risk" type="danger" size="small">高危</el-tag></template>
      </el-table-column>
      <el-table-column label="时间" width="150">
        <template #default="{ row }">{{ (row.created_at || '').slice(0, 19).replace('T', ' ') }}</template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top: 12px" background layout="prev, pager, next, total"
                   :total="total" :page-size="size" :current-page="page"
                   @current-change="(p) => { page = p; load() }" />

    <el-dialog v-model="detailOpen" title="审计详情" width="640px">
      <template v-if="cur">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="ID">{{ cur.id }}</el-descriptions-item>
          <el-descriptions-item label="管理员">{{ cur.admin }}</el-descriptions-item>
          <el-descriptions-item label="动作" :span="2">{{ cur.action }}</el-descriptions-item>
          <el-descriptions-item label="对象">{{ cur.target }}</el-descriptions-item>
          <el-descriptions-item label="对象类型">{{ cur.target_type }}</el-descriptions-item>
          <el-descriptions-item label="IP">{{ cur.ip }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ cur.created_at }}</el-descriptions-item>
          <el-descriptions-item label="详情" :span="2">{{ cur.detail }}</el-descriptions-item>
          <el-descriptions-item v-if="cur.user_agent" label="UA" :span="2">{{ cur.user_agent }}</el-descriptions-item>
        </el-descriptions>
        <h4 style="margin: 16px 0 8px">extra_json</h4>
        <pre style="background: #f5f7fa; padding: 10px; border-radius: 4px; max-height: 240px; overflow: auto; font-size: 12px;">{{ cur.extra_json || '（无）' }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const tab = ref('all')
const rows = ref([])
const total = ref(0), page = ref(1), size = ref(20)
const kw = ref({ action: '', admin: '', target_type: '' })
const detailOpen = ref(false), cur = ref(null)

async function load() {
  const url = tab.value === 'risk' ? '/api/admin/audit/high-risk' : '/api/admin/audit/logs'
  const params = { page: page.value, page_size: size.value }
  if (tab.value === 'all') {
    if (kw.value.action) params.action = kw.value.action
    if (kw.value.admin) params.admin_name = kw.value.admin
    if (kw.value.target_type) params.target_type = kw.value.target_type
  }
  const { data: d } = await api.get(url, { params })
  rows.value = (d && d.items) || []
  total.value = (d && d.total) || 0
}

function openDetail(row) { cur.value = row; detailOpen.value = true }

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; }
.price { color: #f56c6c; font-weight: 600; }
.hint { color: #999; font-size: 12px; margin-left: 8px; }
</style>
