<template>
  <div>
    <h2>数据中心</h2>
    <el-row :gutter="16">
      <el-col :span="6" v-for="c in userCards" :key="c.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">{{ c.label }}</div>
          <div class="stat-value">{{ c.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <el-card shadow="hover">
          <div class="chart-title">各学习模块使用量</div>
          <el-table :data="moduleRows" size="small" border>
            <el-table-column prop="name" label="模块" />
            <el-table-column prop="value" label="累计量" align="right" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <div class="chart-title">账本 / IM 体量</div>
          <el-table :data="bizRows" size="small" border>
            <el-table-column prop="name" label="类别" />
            <el-table-column prop="value" label="数量" align="right" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" style="margin-top: 16px">
      <div class="chart-title">年级分布</div>
      <el-table :data="gradeRows" size="small" border>
        <el-table-column prop="grade" label="年级" />
        <el-table-column prop="count" label="用户数" align="right" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const d = ref({ users: {}, module_usage: {}, ledger: {}, im: {} })

const userCards = computed(() => {
  const u = d.value.users || {}
  return [
    { label: '总用户', value: u.total ?? 0 },
    { label: '今日活跃', value: u.active_today ?? 0 },
    { label: '近 7 天活跃', value: u.active_7d ?? 0 },
    { label: '今日新增', value: u.new_today ?? 0 },
    { label: 'VIP 用户', value: u.vip ?? 0 },
  ]
})

const moduleRows = computed(() => {
  const m = d.value.module_usage || {}
  const names = {
    exam_attempts: '试卷作答', daily_tasks: '每日任务', vocab_logs: '背单词',
    classical_logs: '古诗文', ai_qa: 'AI 问答', challenges: '挑战赛',
  }
  return Object.keys(m).map((k) => ({ name: names[k] || k, value: m[k] }))
})

const bizRows = computed(() => {
  const l = d.value.ledger || {}
  const i = d.value.im || {}
  return [
    { name: '账单', value: l.bills ?? 0 },
    { name: '账本账户', value: l.accounts ?? 0 },
    { name: '账本分类', value: l.categories ?? 0 },
    { name: 'IM 聊天', value: i.chats ?? 0 },
    { name: 'IM 消息', value: i.messages ?? 0 },
    { name: '好友关系', value: i.friendships ?? 0 },
    { name: '红包', value: i.red_packets ?? 0 },
  ]
})

const gradeRows = computed(() => {
  const g = d.value.users?.grade_distribution || {}
  return Object.keys(g).sort().map((k) => ({ grade: k + ' 年级', count: g[k] }))
})

onMounted(async () => {
  try {
    const { data } = await api.get('/api/admin/stats/dashboard')
    d.value = data
  } catch (e) {
    // 静默失败，页面显示空数据
  }
})
</script>

<style scoped>
.stat-card { text-align: center; }
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 26px; font-weight: 700; margin-top: 6px; color: #303133; }
.chart-title { font-size: 14px; color: #606266; margin-bottom: 8px; }
</style>
