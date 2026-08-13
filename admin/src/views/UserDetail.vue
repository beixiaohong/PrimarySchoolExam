<template>
  <div>
    <el-button text @click="$router.push('/users')">← 返回用户列表</el-button>
    <h2>用户详情：{{ userId }}</h2>

    <el-descriptions border :column="4" style="margin: 12px 0">
      <el-descriptions-item label="昵称">{{ info.nickname || '-' }}</el-descriptions-item>
      <el-descriptions-item label="年级">{{ info.grade || '-' }}</el-descriptions-item>
      <el-descriptions-item label="邮箱">{{ info.email || '-' }}</el-descriptions-item>
      <el-descriptions-item label="VIP">
        <el-tag v-if="info.is_vip" type="danger" size="small">VIP</el-tag><span v-else>否</span>
      </el-descriptions-item>
      <el-descriptions-item label="钻石">{{ info.diamonds }}</el-descriptions-item>
      <el-descriptions-item label="金币">{{ info.coins }}</el-descriptions-item>
      <el-descriptions-item label="补签卡">{{ info.makeup_cards }}</el-descriptions-item>
      <el-descriptions-item label="注册">{{ info.created_at || '-' }}</el-descriptions-item>
    </el-descriptions>

    <el-tabs v-model="tab">
      <!-- 学习记录 -->
      <el-tab-pane label="学习记录" name="study">
        <div class="toolbar">
          <el-select v-model="studyCat" style="width: 150px" @change="loadStudy">
            <el-option label="全部" value="all" />
            <el-option v-for="(cn, key) in catMap" :key="key" :label="cn" :value="key" />
          </el-select>
          <el-tag v-for="(cn, key) in catMap" :key="'c' + key" type="info" size="small" style="margin-left:8px">
            {{ cn }}：{{ counts[key] || 0 }}
          </el-tag>
        </div>
        <el-timeline style="margin-top: 16px">
          <el-timeline-item v-for="(e, i) in studyItems" :key="i" :timestamp="e.time" placement="top">
            <el-tag size="small" :type="catType(e.category)">{{ e.category_name }}</el-tag>
            <span class="sum">{{ e.summary }}</span>
            <div class="det" v-if="e.detail">{{ e.detail }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="!studyItems.length" description="暂无记录" />
        <el-pagination background layout="prev, pager, next, total" :total="studyTotal"
                      :page-size="studyPageSize" :current-page="studyPage"
                      @current-change="(p) => { studyPage = p; loadStudy() }" />
      </el-tab-pane>

      <!-- 资产流水 -->
      <el-tab-pane label="资产流水" name="ledger">
        <div class="toolbar">
          <el-select v-model="ledgerKind" style="width: 150px" @change="loadLedger">
            <el-option label="全部" value="all" />
            <el-option label="金币" value="coin" />
            <el-option label="钻石" value="diamond" />
            <el-option label="补签卡" value="makeup" />
            <el-option label="卡券" value="coupon" />
          </el-select>
          <el-tag type="info" size="small" style="margin-left:8px">当前持有：金币 {{ ledgerBal.coin }} · 钻石 {{ ledgerBal.diamond }} · 补签卡 {{ ledgerBal.makeup }}</el-tag>
        </div>
        <el-table :data="ledgerItems" border stripe style="margin-top: 12px">
          <el-table-column prop="time" label="时间" width="150" />
          <el-table-column prop="kind_name" label="类型" width="90" />
          <el-table-column label="变动" width="100">
            <template #default="{ row }">
              <span :style="{ color: row.amount >= 0 ? '#67c23a' : '#f56c6c' }">
                {{ row.amount >= 0 ? '+' : '' }}{{ row.amount }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="balance_after" label="余额/持有" width="110" />
          <el-table-column prop="reason" label="说明" min-width="200" show-overflow-tooltip />
        </el-table>
        <el-pagination style="margin-top: 12px" background layout="prev, pager, next, total"
                      :total="ledgerTotal" :page-size="ledgerPageSize" :current-page="ledgerPage"
                      @current-change="(p) => { ledgerPage = p; loadLedger() }" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const userId = decodeURIComponent(route.params.userId)

const info = ref({})
const tab = ref('study')

const catMap = { exam: '做题', wrong: '错题', classical: '背诵', vocab: '背单词', challenge: '刷题', ai: 'AI对话', parent: '家长记录' }
function catType(c) {
  return { exam: '', wrong: 'danger', classical: 'success', vocab: 'warning', challenge: 'info', ai: 'primary', parent: '' }[c] || ''
}

// 学习记录
const studyCat = ref('all')
const studyItems = ref([])
const studyTotal = ref(0)
const studyPage = ref(1)
const studyPageSize = ref(30)
const counts = ref({})

async function loadStudy() {
  const { data } = await api.get('/api/admin/users/' + encodeURIComponent(userId) + '/study-records', {
    params: { category: studyCat.value, page: studyPage.value, page_size: studyPageSize.value },
  })
  studyItems.value = data.items
  studyTotal.value = data.total
  counts.value = data.counts
}

// 资产流水
const ledgerKind = ref('all')
const ledgerItems = ref([])
const ledgerTotal = ref(0)
const ledgerPage = ref(1)
const ledgerPageSize = ref(30)
const ledgerBal = ref({ coin: 0, diamond: 0, makeup: 0 })

async function loadLedger() {
  const { data } = await api.get('/api/admin/users/' + encodeURIComponent(userId) + '/ledger', {
    params: { kind: ledgerKind.value, page: ledgerPage.value, page_size: ledgerPageSize.value },
  })
  ledgerItems.value = data.items
  ledgerTotal.value = data.total
  ledgerBal.value = data.balance || { coin: 0, diamond: 0, makeup: 0 }
}

async function loadInfo() {
  const { data } = await api.get('/api/admin/users', { params: { keyword: userId, page: 1, page_size: 20 } })
  info.value = data.items.find((u) => u.user_id === userId) || {}
}

watch(tab, (t) => {
  if (t === 'ledger') loadLedger()
})

onMounted(() => {
  loadInfo()
  loadStudy()
})
</script>

<style scoped>
.toolbar { display: flex; align-items: center; flex-wrap: wrap; }
.sum { margin-left: 8px; font-size: 14px; color: #303133; }
.det { color: #909399; font-size: 12px; margin-top: 2px; }
</style>
