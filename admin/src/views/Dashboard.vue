<template>
  <div>
    <h2>运营概览</h2>
    <el-row :gutter="16">
      <el-col :span="6" v-for="c in cards" :key="c.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">{{ c.label }}</div>
          <div class="stat-value">{{ c.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <el-card shadow="hover"><div class="chart-title">注册趋势（近 30 天）</div><div ref="regChart" class="chart"></div></el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover"><div class="chart-title">日活（近 7 天）</div><div ref="actChart" class="chart"></div></el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="24">
        <el-card shadow="hover">
          <div class="chart-title">次留（近 14 天注册用户在次日仍活跃占比）</div>
          <div ref="retChart" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
// echarts 按需引入：本页只用 折线图 + 柱状图 + 基础坐标轴/提示框 + Canvas 渲染器，
// 不要 import * as echarts from 'echarts'（会把全部图表类型拉进包，编译期内存暴涨）。
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, CanvasRenderer])
import api from '../api'

const cards = ref([])
const regChart = ref(null)
const actChart = ref(null)
const retChart = ref(null)

function lineOption(title, rows, key, color) {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: rows.map((r) => r.date.slice(5)), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' },
    series: [{ type: 'line', smooth: true, data: rows.map((r) => r[key]), itemStyle: { color }, areaStyle: { opacity: 0.15 } }],
  }
}

onMounted(async () => {
  const [dash, ana] = await Promise.all([
    api.get('/api/admin/dashboard'),
    api.get('/api/admin/analytics'),
  ])
  const d = dash.data
  const a = ana.data
  cards.value = [
    { label: '总用户', value: a.overview.total_users },
    { label: '近 7 天新增', value: a.overview.new_users_7d },
    { label: '近 30 天新增', value: a.overview.new_users_30d },
    { label: '今日活跃', value: a.overview.dau_today },
    { label: 'VIP 用户', value: a.overview.vip_count },
    { label: '钻石总量', value: a.overview.diamond_total },
    { label: '金币总量', value: a.overview.coin_total },
    { label: '补签卡总量', value: a.overview.makeup_total },
  ]
  await nextTick()
  echarts.init(regChart.value).setOption(lineOption('', a.registration_trend, 'count', '#409eff'))
  echarts.init(actChart.value).setOption(lineOption('', a.active_trend, 'count', '#67c23a'))
  echarts.init(retChart.value).setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: a.retention.map((r) => r.date.slice(5)), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', max: 100 },
    series: [{ type: 'bar', data: a.retention.map((r) => r.rate), itemStyle: { color: '#e6a23c' } }],
  })
})
</script>

<style scoped>
.stat-card { text-align: center; }
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 26px; font-weight: 700; margin-top: 6px; color: #303133; }
.chart-title { font-size: 14px; color: #606266; margin-bottom: 8px; }
.chart { height: 280px; }
</style>
