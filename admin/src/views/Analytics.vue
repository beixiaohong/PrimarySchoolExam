<template>
  <div>
    <h2>运营数据分析</h2>

    <el-row :gutter="16">
      <el-col :span="12"><el-card shadow="hover"><div class="ct">注册趋势（近 30 天）</div><div ref="regChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card shadow="hover"><div class="ct">日活（近 7 天）</div><div ref="actChart" class="chart"></div></el-card></el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12"><el-card shadow="hover"><div class="ct">次日留存（近 14 天）</div><div ref="retChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card shadow="hover"><div class="ct">资产流向（近 30 天：发放 / 消耗）</div><div ref="flowChart" class="chart"></div></el-card></el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12"><el-card shadow="hover"><div class="ct">AI 用量（近 30 天，按功能）</div><div ref="aiChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card shadow="hover"><div class="ct">各功能活跃（近 30 天）</div><div ref="featChart" class="chart"></div></el-card></el-col>
    </el-row>

    <el-card shadow="hover" style="margin-top: 16px">
      <div class="ct">活跃榜（近 30 天做题次数 Top 10）</div>
      <el-table :data="topUsers" border stripe>
        <el-table-column type="index" label="排名" width="70" />
        <el-table-column prop="user_id" label="账号" />
        <el-table-column prop="count" label="做题次数" width="120" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
// echarts 按需引入：本页只用 折线图 + 柱状图 + 基础坐标轴/提示框 + Canvas 渲染器。
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, CanvasRenderer])
import api from '../api'

const regChart = ref(null)
const actChart = ref(null)
const retChart = ref(null)
const flowChart = ref(null)
const aiChart = ref(null)
const featChart = ref(null)
const topUsers = ref([])

function line(rows, key, color) {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 45, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: rows.map((r) => r.date.slice(5)), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' },
    series: [{ type: 'line', smooth: true, data: rows.map((r) => r[key]), itemStyle: { color }, areaStyle: { opacity: 0.15 } }],
  }
}

onMounted(async () => {
  const { data } = await api.get('/api/admin/analytics')
  const a = data
  await nextTick()
  echarts.init(regChart.value).setOption(line(a.registration_trend, 'count', '#409eff'))
  echarts.init(actChart.value).setOption(line(a.active_trend, 'count', '#67c23a'))
  echarts.init(retChart.value).setOption({
    tooltip: { trigger: 'axis' }, grid: { left: 45, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: a.retention.map((r) => r.date.slice(5)), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', max: 100 },
    series: [{ type: 'bar', data: a.retention.map((r) => r.rate), itemStyle: { color: '#e6a23c' } }],
  })
  const f = a.asset_flow
  echarts.init(flowChart.value).setOption({
    tooltip: { trigger: 'axis' }, grid: { left: 50, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: ['钻石发放', '钻石消耗', '金币发放', '金币消耗'] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: [f.diamond_grant_30d, f.diamond_spend_30d, f.coin_grant_30d, f.coin_spend_30d],
      itemStyle: { color: '#909399' } }],
  })
  echarts.init(aiChart.value).setOption({
    tooltip: { trigger: 'axis' }, grid: { left: 45, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: a.ai_usage.by_feature.map((x) => x.feature), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: a.ai_usage.by_feature.map((x) => x.count), itemStyle: { color: '#9254de' } }],
  })
  echarts.init(featChart.value).setOption({
    tooltip: { trigger: 'axis' }, grid: { left: 45, right: 16, top: 16, bottom: 60 },
    xAxis: { type: 'category', data: a.feature_activity.map((x) => x.name), axisLabel: { fontSize: 10, rotate: 25 } },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: a.feature_activity.map((x) => x.count), itemStyle: { color: '#13c2c2' } }],
  })
  topUsers.value = a.top_users
})
</script>

<style scoped>
.ct { font-size: 14px; color: #606266; margin-bottom: 8px; }
.chart { height: 260px; }
</style>
