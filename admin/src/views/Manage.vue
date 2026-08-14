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

const loaders = {
  bills: loadBills, accounts: loadAccounts, categories: loadCategories,
  chats: loadChats, friendships: loadFriendships, redpackets: loadRedPackets,
}

async function del(path, id, key) {
  try {
    await ElMessageBox.confirm('确认删除？该操作不可恢复', '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/admin/${path}/${id}`)
    ElMessage.success('已删除')
    await loaders[key]()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '删除失败')
  }
}

watch(tab, (t) => loaders[t] && loaders[t]())
onMounted(loadBills)
</script>
