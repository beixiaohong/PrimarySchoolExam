<template>
  <div>
    <div style="display:flex;align-items:center;gap:12px">
      <el-button text @click="$router.push('/users')">← 返回用户列表</el-button>
      <h2 style="margin:0">用户详情：{{ userId }}</h2>
      <el-button type="primary" size="small" @click="openEdit">编辑资料</el-button>
    </div>

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

    <div class="ops">
      <el-button size="small" @click="openResetPwd">重置密码</el-button>
      <el-button v-if="!info.is_vip" size="small" type="warning" @click="openAddVip">设为 VIP</el-button>
      <el-button v-else size="small" type="danger" @click="removeVip">取消 VIP</el-button>
    </div>

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

    <!-- 编辑资料弹窗 -->
    <el-dialog v-model="editOpen" title="编辑用户资料" width="460px">
      <el-form label-width="72px">
        <el-form-item label="昵称">
          <el-input v-model="editForm.nickname" maxlength="64" />
        </el-form-item>
        <el-form-item label="年级">
          <el-input-number v-model="editForm.grade" :min="1" :max="12" />
        </el-form-item>
        <el-form-item label="学科">
          <el-input v-model="editForm.subject" maxlength="20" placeholder="如 英语/数学/语文" />
        </el-form-item>
        <el-form-item label="城市">
          <el-input v-model="editForm.city" maxlength="50" placeholder="用于首页天气" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="留空表示解绑" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="editForm.phone" placeholder="留空表示解绑" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveProfile">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="pwdOpen" title="重置登录密码" width="420px">
      <el-form label-width="80px">
        <el-form-item label="目标账号">
          <el-input :model-value="userId" disabled />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.password" type="password" show-password
                    maxlength="32" placeholder="4-32 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdOpen = false">取消</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="submitResetPwd">确认重置</el-button>
      </template>
    </el-dialog>

    <!-- VIP 设置弹窗 -->
    <el-dialog v-model="vipOpen" title="设置 VIP" width="420px">
      <el-form label-width="80px">
        <el-form-item label="目标账号">
          <el-input :model-value="userId" disabled />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="vipForm.note" placeholder="开通原因/有效期" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="vipOpen = false">取消</el-button>
        <el-button type="primary" :loading="vipSaving" @click="submitAddVip">确认开通</el-button>
      </template>
    </el-dialog>
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

// 编辑资料
const editOpen = ref(false)
const editSaving = ref(false)
const editForm = ref({ nickname: '', grade: 6, subject: '', city: '', email: '', phone: '' })

function openEdit() {
  editForm.value = {
    nickname: info.value.nickname || '',
    grade: info.value.grade || 6,
    subject: info.value.subject || '',
    city: info.value.city || '',
    email: info.value.email || '',
    phone: info.value.phone || '',
  }
  editOpen.value = true
}

async function saveProfile() {
  editSaving.value = true
  try {
    await api.put('/api/admin/users/' + encodeURIComponent(userId), { ...editForm.value })
    ElMessage.success('资料已更新')
    editOpen.value = false
    loadInfo()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '保存失败')
  } finally {
    editSaving.value = false
  }
}

// 重置密码（复用 POST /api/admin/users/account reset_password）
const pwdOpen = ref(false)
const pwdSaving = ref(false)
const pwdForm = ref({ password: '' })
function openResetPwd() {
  pwdForm.value = { password: '' }
  pwdOpen.value = true
}
async function submitResetPwd() {
  const pw = pwdForm.value.password
  if (!pw || pw.length < 4 || pw.length > 32) {
    ElMessage.warning('密码需 4-32 位')
    return
  }
  pwdSaving.value = true
  try {
    await api.post('/api/admin/users/account', {
      user_id: userId, action: 'reset_password', value: pw,
    })
    ElMessage.success('密码已重置')
    pwdOpen.value = false
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '操作失败')
  } finally {
    pwdSaving.value = false
  }
}

// VIP 设置（复用 POST /api/admin/vip add/remove）
const vipOpen = ref(false)
const vipSaving = ref(false)
const vipForm = ref({ note: '' })
function openAddVip() {
  vipForm.value = { note: '' }
  vipOpen.value = true
}
async function submitAddVip() {
  vipSaving.value = true
  try {
    await api.post('/api/admin/vip', {
      user_id: userId, action: 'add', note: vipForm.value.note,
    })
    ElMessage.success('已开通 VIP')
    vipOpen.value = false
    loadInfo()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '操作失败')
  } finally {
    vipSaving.value = false
  }
}
async function removeVip() {
  try {
    await api.post('/api/admin/vip', { user_id: userId, action: 'remove' })
    ElMessage.success('已取消 VIP')
    loadInfo()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '操作失败')
  }
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
.ops { margin: 12px 0; display: flex; gap: 10px; align-items: center; }
.sum { margin-left: 8px; font-size: 14px; color: #303133; }
.det { color: #909399; font-size: 12px; margin-top: 2px; }
</style>
