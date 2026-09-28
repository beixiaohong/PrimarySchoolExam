<template>
  <div>
    <h2>消息推送</h2>
    <p class="hint">
      OneSignal Web Push：用户在浏览器中授权后即可收到通知。推送密钥在
      <b>系统配置 → 消息推送</b> 中填写；用户可在自己的「设置 → 消息推送」里逐项关闭。
    </p>

    <!-- 通道状态：一眼看出「为什么发不出去」 -->
    <el-alert
      v-if="status && !status.enabled"
      type="warning" show-icon :closable="false" style="margin-bottom: 14px"
      title="推送通道未配置"
      description="请到「系统配置」的「消息推送」分组填写 ONESIGNAL_APP_ID 与 ONESIGNAL_REST_API_KEY，60 秒内生效。" />

    <el-row :gutter="14" style="margin-bottom: 14px">
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">通道状态</div>
          <div class="stat-value">
            <el-tag :type="status && status.enabled ? 'success' : 'info'" size="large">
              {{ status && status.enabled ? '已就绪' : '未配置' }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">已授权设备</div>
          <div class="stat-value">{{ (status && status.stats && status.stats.subscriptions) || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">覆盖用户</div>
          <div class="stat-value">{{ (status && status.stats && status.stats.users) || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">密钥</div>
          <div class="stat-value" style="font-size: 13px">
            App ID：{{ status && status.configured && status.configured.app_id ? '✔' : '✘' }}
            &nbsp;/&nbsp;
            REST Key：{{ status && status.configured && status.configured.rest_api_key ? '✔' : '✘' }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-bottom: 14px">
      <template #header><b>发送推送</b></template>
      <el-form label-width="90px" style="max-width: 720px">
        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="120" show-word-limit placeholder="如：本周数学小测安排" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="form.body" type="textarea" :rows="3" maxlength="500" show-word-limit
                    placeholder="通知栏会截断过长正文，建议 40 字以内" />
        </el-form-item>
        <el-form-item label="点击跳转">
          <el-input v-model="form.url" placeholder="留空则点击仅关闭通知，如 /#/home" />
        </el-form-item>
        <el-form-item label="目标">
          <el-radio-group v-model="form.target">
            <el-radio value="all">全体订阅者</el-radio>
            <el-radio value="grade">按年级</el-radio>
            <el-radio value="user">指定用户</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="年级" v-if="form.target === 'grade'">
          <el-input-number v-model="form.grade" :min="1" :max="12" />
        </el-form-item>
        <el-form-item label="用户 ID" v-if="form.target === 'user'">
          <el-input v-model="form.user_ids" type="textarea" :rows="2"
                    placeholder="多个用逗号或换行分隔" />
        </el-form-item>
        <el-form-item label="事件类型">
          <el-select v-model="form.event" style="width: 220px">
            <el-option v-for="e in (status && status.events) || []" :key="e.value"
                       :label="e.label" :value="e.value" />
          </el-select>
          <span class="hint" style="margin-left: 10px">
            公告/群发类不占用户每日额度，其余类型每人每天有上限
          </span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="sending" @click="send">发送</el-button>
          <span class="hint" style="margin-left: 12px">
            全体推送不可撤回，发送前请确认文案
          </span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between">
          <b>最近发送记录</b>
          <div>
            <el-select v-model="logEvent" size="small" style="width: 150px; margin-right: 8px"
                       @change="loadLogs">
              <el-option label="全部类型" value="" />
              <el-option v-for="e in (status && status.events) || []" :key="e.value"
                         :label="e.label" :value="e.value" />
            </el-select>
            <el-button size="small" @click="loadLogs">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table :data="logs" border stripe size="small">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="event_label" label="类型" width="90" />
        <el-table-column prop="title" label="标题" min-width="150" />
        <el-table-column prop="user_id" label="接收用户" width="130" />
        <el-table-column prop="recipients" label="触达订阅" width="90" />
        <el-table-column label="结果" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.ok ? 'success' : 'danger'">{{ row.ok ? '成功' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误" min-width="140" />
      </el-table>
      <el-empty v-if="!logs.length" description="暂无发送记录" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const status = ref(null)
const logs = ref([])
const logEvent = ref('')
const sending = ref(false)
const form = ref({
  title: '', body: '', url: '/#/home', target: 'all', grade: 1,
  user_ids: '', event: 'broadcast',
})

async function loadStatus() {
  try {
    const { data } = await api.get('/api/admin/push/status')
    status.value = data
  } catch (e) {
    ElMessage.error('读取推送状态失败')
  }
}

async function loadLogs() {
  try {
    const { data } = await api.get('/api/admin/push/logs', {
      params: { limit: 50, event: logEvent.value },
    })
    logs.value = data.items || []
  } catch (e) {
    logs.value = []
  }
}

async function send() {
  if (!form.value.title.trim() || !form.value.body.trim()) {
    ElMessage.warning('请填写标题与正文')
    return
  }
  if (form.value.target === 'user' && !form.value.user_ids.trim()) {
    ElMessage.warning('请填写用户 ID')
    return
  }
  // 全体/年级推送会即时打断大量用户，必须二次确认
  const scopeText = form.value.target === 'all'
    ? '全体已授权订阅者'
    : (form.value.target === 'grade' ? ('年级 ' + form.value.grade + ' 的用户') : '指定用户')
  try {
    await ElMessageBox.confirm(`确认向「${scopeText}」发送推送？`, '发送确认', { type: 'warning' })
  } catch { return }

  sending.value = true
  try {
    const payload = {
      title: form.value.title.trim(),
      body: form.value.body.trim(),
      url: form.value.url.trim(),
      target: form.value.target,
      event: form.value.event,
      grade: form.value.grade,
      user_ids: form.value.user_ids.split(/[,，\s]+/).filter(Boolean),
    }
    const { data } = await api.post('/api/admin/push/send', payload)
    if (data.ok) {
      ElMessage.success(`已提交，触达订阅 ${data.recipients || 0} 个`)
    } else {
      ElMessage.warning(data.hint || data.message || '发送未成功')
    }
    loadLogs()
  } catch (e) {
    // 后端统一错误信封为 {code, message}（不是 detail）
    const d = (e.response && e.response.data) || {}
    ElMessage.error(d.message || d.detail || '发送失败')
  } finally {
    sending.value = false
  }
}

onMounted(() => { loadStatus(); loadLogs() })
</script>

<style scoped>
.hint { color: #909399; font-size: 12px; line-height: 1.6; }
.stat-label { color: #909399; font-size: 12px; margin-bottom: 6px; }
.stat-value { font-size: 20px; font-weight: 600; }
</style>
