<template>
  <div>
    <h2>系统公告 / 站内信</h2>
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">发布新公告</el-button>
    </div>

    <el-table :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column label="受众" width="110">
        <template #default="{ row }">
          <el-tag size="small" v-if="row.target_type === 'all'">全部</el-tag>
          <el-tag size="small" type="warning" v-else-if="row.target_type === 'grade'">年级 {{ row.target_value }}</el-tag>
          <el-tag size="small" type="info" v-else>指定用户</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_pinned" label="置顶" width="70">
        <template #default="{ row }"><el-tag v-if="row.is_pinned" type="danger" size="small">置顶</el-tag><span v-else>-</span></template>
      </el-table-column>
      <el-table-column prop="created_by" label="发布人" width="100" />
      <el-table-column prop="created_at" label="发布时间" width="140" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="open" title="发布系统公告" width="520px">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="公告标题" />
        </el-form-item>
        <el-form-item label="受众">
          <el-select v-model="form.target_type" style="width: 100%">
            <el-option label="全部用户" value="all" />
            <el-option label="按年级" value="grade" />
            <el-option label="指定用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级/账号" v-if="form.target_type !== 'all'">
          <el-input v-model="form.target_value" :placeholder="form.target_type === 'grade' ? '年级数字，如 3' : 'user_id'" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="form.content" type="textarea" :rows="4" placeholder="公告内容" />
        </el-form-item>
        <el-form-item label="置顶">
          <el-switch v-model="form.is_pinned" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const rows = ref([])
const open = ref(false)
const saving = ref(false)
const form = ref({ title: '', content: '', target_type: 'all', target_value: '', is_pinned: false })

async function load() {
  const { data } = await api.get('/api/admin/announcements')
  rows.value = data.items
}
function openCreate() {
  form.value = { title: '', content: '', target_type: 'all', target_value: '', is_pinned: false }
  open.value = true
}
async function submit() {
  if (!form.value.title.trim() || !form.value.content.trim()) {
    ElMessage.warning('请填写标题与正文')
    return
  }
  saving.value = true
  try {
    await api.post('/api/admin/announcements', form.value)
    ElMessage.success('已发布')
    open.value = false
    load()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '发布失败')
  } finally {
    saving.value = false
  }
}
async function remove(row) {
  try {
    await ElMessageBox.confirm('确认删除该公告？', '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.delete('/api/admin/announcements/' + row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && e.response.data.detail) || '删除失败')
  }
}
onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; margin-bottom: 4px; }
</style>
