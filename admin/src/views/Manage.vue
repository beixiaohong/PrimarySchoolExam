<template>
  <div>
    <h2>账本 · IM 管理</h2>
    <el-tabs v-model="tab">
      <el-tab-pane label="账单" name="bills">
        <el-table :data="bills.items" border size="small" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="user_id" label="用户" min-width="110" />
          <el-table-column prop="transaction_type" label="类型" width="90" />
          <el-table-column prop="amount" label="金额" width="100" />
          <el-table-column prop="note" label="备注" show-overflow-tooltip />
          <el-table-column prop="transaction_time" label="时间" width="140" />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="del('ledger/bills', row.id, 'bills')">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:10px" background layout="prev,pager,next,total" :total="bills.total"
                       :page-size="50" :current-page="billsPage" @current-change="(p)=>{billsPage=p; loadBills()}" />
      </el-tab-pane>

      <el-tab-pane label="账户" name="accounts">
        <el-table :data="accounts.items" border size="small" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="user_id" label="用户" min-width="110" />
          <el-table-column prop="account_name" label="名称" min-width="100" />
          <el-table-column prop="account_type" label="类型" width="100" />
          <el-table-column prop="balance" label="余额" width="110" />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="del('ledger/accounts', row.id, 'accounts')">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="分类" name="categories">
        <el-table :data="categories.items" border size="small" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="user_id" label="用户" min-width="110" />
          <el-table-column prop="category_type" label="类型" width="90" />
          <el-table-column prop="level1" label="一级" />
          <el-table-column prop="level2" label="二级" />
          <el-table-column prop="level3" label="三级" />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="del('ledger/categories', row.id, 'categories')">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="聊天" name="chats">
        <el-table :data="chats.items" border size="small" v-loading="loading">
          <el-table-column prop="id" label="聊天ID" min-width="220" show-overflow-tooltip />
          <el-table-column prop="name" label="名称" min-width="100" />
          <el-table-column prop="chat_type" label="类型" width="90" />
          <el-table-column prop="created_by" label="创建者" min-width="110" />
          <el-table-column prop="member_count" label="成员" width="80" />
          <el-table-column prop="message_count" label="消息" width="80" />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="del('im/chats', row.id, 'chats')">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:10px" background layout="prev,pager,next,total" :total="chats.total"
                       :page-size="50" :current-page="chatsPage" @current-change="(p)=>{chatsPage=p; loadChats()}" />
      </el-tab-pane>

      <el-tab-pane label="好友关系" name="friendships">
        <el-table :data="friendships.items" border size="small" v-loading="loading">
          <el-table-column prop="id" label="关系ID" min-width="220" show-overflow-tooltip />
          <el-table-column prop="requester_id" label="发起方" min-width="110" />
          <el-table-column prop="addressee_id" label="接收方" min-width="110" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="del('im/friendships', row.id, 'friendships')">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="红包" name="redpackets">
        <el-table :data="redpackets.items" border size="small" v-loading="loading">
          <el-table-column prop="id" label="红包ID" min-width="220" show-overflow-tooltip />
          <el-table-column prop="sender_id" label="发送者" min-width="110" />
          <el-table-column prop="total_amount" label="总额" width="90" />
          <el-table-column prop="total_count" label="个数" width="80" />
          <el-table-column prop="remaining_amount" label="剩余" width="90" />
          <el-table-column prop="status" label="状态" width="90" />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="del('im/red-packets', row.id, 'redpackets')">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- IM 消息审计（D4 合规）：按会话/用户/关键词/类型检索 + 违规消息软删除 -->
      <el-tab-pane label="消息审计" name="messages">
        <el-form :inline="true" :model="msgQuery" size="small" style="margin-bottom:8px">
          <el-form-item label="会话ID"><el-input v-model="msgQuery.chat_id" placeholder="可选" clearable style="width:140px" /></el-form-item>
          <el-form-item label="用户ID"><el-input v-model="msgQuery.user_id" placeholder="可选" clearable style="width:140px" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="msgQuery.message_type" placeholder="全部" clearable style="width:120px">
              <el-option label="text" value="text" /><el-option label="image" value="image" />
              <el-option label="voice" value="voice" /><el-option label="file" value="file" />
              <el-option label="red_packet" value="red_packet" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键词"><el-input v-model="msgQuery.keyword" placeholder="内容模糊匹配" clearable style="width:160px" @keyup.enter="loadMessages" /></el-form-item>
          <el-form-item><el-button type="primary" @click="loadMessages">检索</el-button></el-form-item>
        </el-form>
        <el-table :data="messages.items" border size="small" v-loading="loading">
          <el-table-column prop="id" label="消息ID" min-width="200" show-overflow-tooltip />
          <el-table-column prop="chat_id" label="会话" min-width="160" show-overflow-tooltip />
          <el-table-column prop="sender_id" label="发送者" min-width="110" />
          <el-table-column prop="message_type" label="类型" width="90" />
          <el-table-column prop="content" label="内容" min-width="220" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="160" />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="delMsg(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:10px" background layout="prev,pager,next,total" :total="messages.total"
                       :page-size="50" :current-page="messagesPage" @current-change="(p)=>{messagesPage=p; loadMessages()}" />
      </el-tab-pane>

      <!-- 敏感词管理（D4 合规）：CRUD + 命中记录查询 + 缓存热加载 -->
      <el-tab-pane label="敏感词" name="sensitive">
        <el-row :gutter="12" style="margin-bottom:8px">
          <el-col :span="14">
            <el-table :data="sensitiveWords" border size="small" v-loading="loading">
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="word" label="敏感词" min-width="120" />
              <el-table-column prop="scene" label="场景" width="100" />
              <el-table-column prop="action" label="动作" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.action==='reject'?'danger':(row.action==='replace'?'warning':'info')" size="small">
                    {{ row.action==='reject'?'拒绝':row.action==='replace'?'替换':'放行' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="category" label="分类" width="100" />
              <el-table-column label="启用" width="80">
                <template #default="{ row }">
                  <el-switch v-model="row.enabled" @change="toggleWord(row)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" type="primary" @click="editWord(row)">编辑</el-button>
                  <el-button size="small" type="danger" @click="del('im/sensitive-words', row.id, 'sensitive', loadSensitiveWords)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-col>
          <el-col :span="10">
            <el-card shadow="never" size="small">
              <template #header><span style="font-weight:600">{{ wordForm.id?'编辑敏感词':'新增敏感词' }}</span></template>
              <el-form :model="wordForm" label-width="60px" size="small">
                <el-form-item label="词语"><el-input v-model="wordForm.word" placeholder="如：脏话" /></el-form-item>
                <el-form-item label="场景">
                  <el-select v-model="wordForm.scene" style="width:100%">
                    <el-option label="消息" value="message" /><el-option label="群名" value="group_name" />
                    <el-option label="群公告" value="announcement" /><el-option label="红包祝福" value="blessing" />
                  </el-select>
                </el-form-item>
                <el-form-item label="动作">
                  <el-select v-model="wordForm.action" style="width:100%">
                    <el-option label="替换为 *" value="replace" /><el-option label="拒绝发送" value="reject" />
                  </el-select>
                </el-form-item>
                <el-form-item label="分类"><el-input v-model="wordForm.category" placeholder="如：脏话/广告/政治" /></el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveWord">{{ wordForm.id?'保存':'新增' }}</el-button>
                  <el-button v-if="wordForm.id" @click="resetWordForm">取消</el-button>
                </el-form-item>
              </el-form>
            </el-card>
            <div style="margin-top:8px; color:#909399; font-size:11px">⚠️ 增删改后自动失效服务端 1 分钟词表缓存，下次发消息即时生效。</div>
          </el-col>
        </el-row>

        <el-divider>命中记录（最近 50 条）</el-divider>
        <el-table :data="sensitiveHits.items" border size="small">
          <el-table-column prop="user_id" label="用户" min-width="110" />
          <el-table-column prop="chat_id" label="会话" min-width="160" show-overflow-tooltip />
          <el-table-column prop="scene" label="场景" width="100" />
          <el-table-column prop="matched_word" label="命中词" min-width="100" />
          <el-table-column prop="original_text" label="原文" min-width="180" show-overflow-tooltip />
          <el-table-column prop="action" label="动作" width="80" />
          <el-table-column prop="created_at" label="时间" width="160" />
        </el-table>
      </el-tab-pane>

      <!-- IM 平台统计 -->
      <el-tab-pane label="IM 统计" name="imstats">
        <el-row :gutter="12" v-if="imStats">
          <el-col :span="6"><el-card><h3>会话数</h3><div style="font-size:24px">{{ imStats.chat_count }}</div></el-card></el-col>
          <el-col :span="6"><el-card><h3>消息数</h3><div style="font-size:24px">{{ imStats.message_count }}</div></el-card></el-col>
          <el-col :span="6"><el-card><h3>红包总额</h3><div style="font-size:24px">{{ (imStats.red_packet_total_milli/1000).toFixed(2) }} 钻</div></el-card></el-col>
          <el-col :span="6"><el-card><h3>已领取</h3><div style="font-size:24px">{{ (imStats.red_packet_claimed_milli/1000).toFixed(2) }} 钻</div></el-card></el-col>
        </el-row>
        <el-row :gutter="12" style="margin-top:12px" v-if="imStats">
          <el-col :span="6"><el-card><h3>敏感词命中</h3><div style="font-size:24px;color:#f56c6c">{{ imStats.sensitive_hit_count }}</div></el-card></el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const tab = ref('bills')
const loading = ref(false)
const bills = ref({ total: 0, items: [] })
const accounts = ref({ total: 0, items: [] })
const categories = ref({ total: 0, items: [] })
const chats = ref({ total: 0, items: [] })
const friendships = ref({ total: 0, items: [] })
const redpackets = ref({ total: 0, items: [] })
const billsPage = ref(1)
const chatsPage = ref(1)
const messagesPage = ref(1)
const messages = ref({ total: 0, items: [] })
const msgQuery = ref({ chat_id: '', user_id: '', keyword: '', message_type: '' })
const sensitiveWords = ref([])
const sensitiveHits = ref({ total: 0, items: [] })
const imStats = ref(null)
const wordForm = ref({ id: null, word: '', scene: 'message', action: 'replace', category: '' })

async function loadBills() {
  const { data } = await api.get('/api/admin/ledger/bills', { params: { skip: (billsPage.value - 1) * 50, limit: 50 } })
  bills.value = data
}
async function loadAccounts() {
  const { data } = await api.get('/api/admin/ledger/accounts')
  accounts.value = data
}
async function loadCategories() {
  const { data } = await api.get('/api/admin/ledger/categories')
  categories.value = data
}
async function loadChats() {
  const { data } = await api.get('/api/admin/im/chats', { params: { skip: (chatsPage.value - 1) * 50, limit: 50 } })
  chats.value = data
}
async function loadFriendships() {
  const { data } = await api.get('/api/admin/im/friendships')
  friendships.value = data
}
async function loadRedPackets() {
  const { data } = await api.get('/api/admin/im/red-packets')
  redpackets.value = data
}
async function loadMessages() {
  loading.value = true
  try {
    const params = { skip: (messagesPage.value - 1) * 50, limit: 50 }
    if (msgQuery.value.chat_id) params.chat_id = msgQuery.value.chat_id
    if (msgQuery.value.user_id) params.user_id = msgQuery.value.user_id
    if (msgQuery.value.keyword) params.keyword = msgQuery.value.keyword
    if (msgQuery.value.message_type) params.message_type = msgQuery.value.message_type
    const { data } = await api.get('/api/admin/im/messages', { params })
    messages.value = data
  } finally { loading.value = false }
}
async function loadSensitiveWords() {
  loading.value = true
  try {
    const { data } = await api.get('/api/admin/im/sensitive-words', { params: { limit: 200 } })
    sensitiveWords.value = data.items || []
  } finally { loading.value = false }
}
async function loadSensitiveHits() {
  const { data } = await api.get('/api/admin/im/sensitive-hits', { params: { limit: 50 } })
  sensitiveHits.value = data
}
async function loadImStats() {
  const { data } = await api.get('/api/admin/im/stats')
  imStats.value = data
}

const loaders = {
  bills: loadBills, accounts: loadAccounts, categories: loadCategories,
  chats: loadChats, friendships: loadFriendships, redpackets: loadRedPackets,
  messages: loadMessages, sensitive: async () => { await loadSensitiveWords(); await loadSensitiveHits() },
  imstats: loadImStats,
}

async function del(path, id, key, refresh) {
  try {
    await ElMessageBox.confirm('确认删除？该操作不可恢复', '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/admin/${path}/${id}`)
    ElMessage.success('已删除')
    if (refresh) await refresh()
    else if (loaders[key]) await loaders[key]()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '删除失败')
  }
}
async function delMsg(id) {
  try {
    await ElMessageBox.confirm('确认软删除该消息？合规审计用', '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/admin/im/messages/${id}`)
    ElMessage.success('已删除')
    await loadMessages()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '删除失败')
  }
}

function editWord(w) {
  wordForm.value = { id: w.id, word: w.word, scene: w.scene, action: w.action, category: w.category || '' }
}
function resetWordForm() { wordForm.value = { id: null, word: '', scene: 'message', action: 'replace', category: '' } }
async function saveWord() {
  const f = wordForm.value
  if (!f.word) { ElMessage.warning('请填写敏感词'); return }
  try {
    if (f.id) {
      await api.put(`/api/admin/im/sensitive-words/${f.id}`, { action: f.action, category: f.category, enabled: true })
      ElMessage.success('已更新')
    } else {
      await api.post('/api/admin/im/sensitive-words', { word: f.word, scene: f.scene, action: f.action, category: f.category, enabled: true })
      ElMessage.success('已新增')
    }
    resetWordForm()
    await loadSensitiveWords()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '操作失败')
  }
}
async function toggleWord(w) {
  try {
    await api.put(`/api/admin/im/sensitive-words/${w.id}`, { enabled: w.enabled })
  } catch (e) {
    w.enabled = !w.enabled  // 失败回滚
    ElMessage.error('操作失败')
  }
}

watch(tab, (t) => loaders[t] && loaders[t]())
onMounted(loadBills)
</script>
