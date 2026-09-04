<template>
  <div>
    <h2>RBAC · 角色权限</h2>
    <el-tabs v-model="tab">
      <el-tab-pane label="权限矩阵" name="matrix">
        <div class="row">
          <aside class="role-pane">
            <div class="hint" style="margin-bottom: 8px">角色</div>
            <el-radio-group v-model="curRole" @change="loadMatrix">
              <el-radio-button v-for="r in roles" :key="r.name" :label="r.name">{{ r.name }}</el-radio-button>
            </el-radio-group>
          </aside>
          <main class="perm-pane">
            <div class="toolbar" style="margin-bottom: 8px">
              <el-button type="primary" :loading="saving" @click="setAll">整体覆盖保存</el-button>
              <span class="hint">勾选要授予「{{ curRole }}」的权限点，保存后立即生效（其他角色不变）</span>
            </div>
            <el-table :data="permRows" border size="small" @selection-change="s => selected = s.map(x => x.code)">
              <el-table-column type="selection" width="42" />
              <el-table-column prop="code" label="权限码" min-width="180" />
              <el-table-column prop="group" label="分组" width="120" />
              <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
              <el-table-column label="高危" width="70">
                <template #default="{ row }"><el-tag v-if="row.is_high_risk" type="danger" size="small">高危</el-tag></template>
              </el-table-column>
            </el-table>
          </main>
        </div>
      </el-tab-pane>

      <el-tab-pane label="管理员角色" name="assign">
        <div class="toolbar" style="margin-bottom: 8px">
          <el-input v-model="userKw" placeholder="搜索管理员用户名" style="width: 200px" clearable @keyup.enter="loadAdmins" />
          <el-button type="primary" @click="loadAdmins">搜索</el-button>
        </div>
        <el-table :data="admins" border stripe size="small">
          <el-table-column prop="id" label="ID" width="64" />
          <el-table-column prop="username" label="账号" min-width="140" />
          <el-table-column label="当前角色" width="120">
            <template #default="{ row }"><el-tag size="small">{{ row.role || '—' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="分配角色" width="220">
            <template #default="{ row }">
              <el-select v-model="row._newRole" size="small" style="width: 160px">
                <el-option v-for="r in roles" :key="r.name" :label="r.name" :value="r.name" />
              </el-select>
              <el-button size="small" type="primary" :loading="row._saving" style="margin-left: 6px" @click="assignRole(row)">应用</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="last_login_at" label="最近登录" width="160" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="权限点目录" name="catalog">
        <el-table :data="perms" border stripe size="small">
          <el-table-column prop="code" label="权限码" min-width="200" />
          <el-table-column prop="group" label="分组" width="120" />
          <el-table-column label="高危" width="70">
            <template #default="{ row }"><el-tag v-if="row.is_high_risk" type="danger" size="small">高危</el-tag></template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'

const tab = ref('matrix')
const roles = ref([])
const perms = ref([])
const curRole = ref('admin')
const permRows = ref([])
const selected = ref([])
const saving = ref(false)
const admins = ref([])
const userKw = ref('')

async function loadRoles() {
  const d = await api.get('/api/admin/rbac/roles')
  // 兼容两种返回结构：{roles: {super: [...], admin: [...], ops: [...]}} 或 {super,admin,ops}
  const r = (d && d.roles) || d || {}
  roles.value = Object.keys(r).map(name => ({ name, permissions: r[name] || [] }))
  if (roles.value.length && !roles.value.find(x => x.name === curRole.value)) curRole.value = roles.value[0].name
}

async function loadPerms() {
  const d = await api.get('/api/admin/rbac/permissions')
  perms.value = (d && (d.permissions || d.items)) || []
}

function loadMatrix() {
  const r = roles.value.find(x => x.name === curRole.value)
  const have = new Set(r ? r.permissions : [])
  // 全量过一遍权限目录，把当前角色已勾选的勾上
  permRows.value = (perms.value || []).map(p => ({ ...p, _has: have.has(p.code) }))
  // el-table selection-change 依赖勾选动作触发 selected 更新；此处预填
  selected.value = (perms.value || []).filter(p => have.has(p.code)).map(p => p.code)
}

async function setAll() {
  saving.value = true
  try {
    await api.put(`/api/admin/rbac/roles/${curRole.value}`, { permissions: selected.value })
    ElMessage.success(`已覆盖「${curRole.value}」权限集`)
    await loadRoles(); loadMatrix()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '保存失败') }
  finally { saving.value = false }
}

async function loadAdmins() {
  // 复用后台用户接口（需要 audit/users 类权限——这里仅读取角色字段）
  const params = { page: 1, page_size: 50 }
  if (userKw.value) params.keyword = userKw.value
  try {
    const d = await api.get('/api/admin/users', { params })
    admins.value = ((d && d.items) || []).map(a => ({ ...a, _newRole: a.role || '' }))
  } catch (e) { /* RBAC 启用时可能无用户列表权限，忽略 */ admins.value = [] }
}

async function assignRole(row) {
  if (!row._newRole) { ElMessage.warning('请选择角色'); return }
  row._saving = true
  try {
    await api.post(`/api/admin/rbac/admins/${row.id}/role`, { role: row._newRole })
    ElMessage.success('已分配'); loadAdmins()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '分配失败') }
  finally { row._saving = false }
}

onMounted(async () => { await loadRoles(); await loadPerms(); loadMatrix(); loadAdmins() })
</script>

<style scoped>
.row { display: flex; gap: 16px; }
.role-pane { width: 200px; }
.perm-pane { flex: 1; }
.hint { color: #999; font-size: 12px; }
</style>
