<template>
  <div>
    <h2>教材版本管理</h2>
    <p class="tip">每年级每科目单独配置教材版本；用户端未选择时默认取排序最靠前（id 最小）的启用版本。地区留空为「全国通用」，填省份后仅该省用户默认命中（如上海→沪教版）。词库（内容管理）可按版本绑定。</p>

    <div class="toolbar">
      <el-select v-model="filter.subject" placeholder="学科" style="width: 130px" clearable @change="load">
        <el-option label="数学" value="数学" />
        <el-option label="语文" value="语文" />
        <el-option label="英语" value="英语" />
      </el-select>
      <el-input-number v-model="filter.grade" :min="0" :max="9" controls-position="right" style="width: 110px" placeholder="年级" @change="load" />
      <el-select v-model="filter.region" placeholder="地区" style="width: 130px" clearable @change="load">
        <el-option v-for="r in regionOptions" :key="r.code" :label="r.name" :value="r.code" />
      </el-select>
      <el-button type="primary" @click="openEdit()">新增版本</el-button>
    </div>

    <el-table :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="64" />
      <el-table-column prop="subject" label="学科" width="80" />
      <el-table-column prop="grade" label="年级" width="80" />
      <el-table-column prop="name" label="版本名" min-width="140" />
      <el-table-column label="地区" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.region" type="warning" size="small">{{ regionName(row.region) }}</el-tag>
          <el-tag v-else type="info" size="small">全国通用</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sort_order" label="排序" width="80" />
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建" width="100" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="editOpen" :title="cur.id ? '编辑教材版本' : '新增教材版本'" width="440px">
      <el-form label-width="90px">
        <el-form-item label="学科">
          <el-select v-model="form.subject" style="width: 100%">
            <el-option label="数学" value="数学" />
            <el-option label="语文" value="语文" />
            <el-option label="英语" value="英语" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级">
          <el-input-number v-model="form.grade" :min="1" :max="9" />
        </el-form-item>
        <el-form-item label="版本名">
          <el-input v-model="form.name" placeholder="如：人教版 / 北师大版 / 外研版" />
        </el-form-item>
        <el-form-item label="地区">
          <el-select v-model="form.region" style="width: 100%">
            <el-option v-for="r in regionOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
          <span class="hint">留空=全国通用；填省份后仅该省默认命中</span>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
          <span class="hint">数字越小越靠前（默认选中）</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const rows = ref([])
const filter = ref({ subject: '', grade: 0, region: '' })
const editOpen = ref(false)
const saving = ref(false)
const cur = ref({})
const form = ref({ subject: '英语', grade: 6, name: '', sort_order: 0, enabled: true, region: '', remark: '' })
const regions = ref([])

// 地区下拉：全国通用（''）+ 省码字典
const regionOptions = computed(() => [{ code: '', name: '全国通用' }, ...regions.value])

function regionName(code) {
  const hit = regions.value.find(r => r.code === code)
  return hit ? hit.name : code
}

async function load() {
  const params = {}
  if (filter.value.subject) params.subject = filter.value.subject
  if (filter.value.grade > 0) params.grade = filter.value.grade
  if (filter.value.region) params.region = filter.value.region
  const { data: d } = await api.get('/api/admin/textbooks', { params })
  rows.value = (d && d.items) || []
}

async function loadRegions() {
  const { data: d } = await api.get('/api/admin/textbooks/regions')
  regions.value = (d && d.regions) || []
}

function openEdit(row) {
  cur.value = row || {}
  form.value = row
    ? { subject: row.subject, grade: row.grade, name: row.name, sort_order: row.sort_order, enabled: !!row.enabled, region: row.region || '', remark: row.remark || '' }
    : { subject: filter.value.subject || '英语', grade: filter.value.grade || 6, name: '', sort_order: 0, enabled: true, region: filter.value.region || '', remark: '' }
  editOpen.value = true
}

async function save() {
  if (!form.value.name || !form.value.subject) { ElMessage.warning('请填写学科与版本名'); return }
  saving.value = true
  try {
    if (cur.value.id) {
      await api.put(`/api/admin/textbooks/${cur.value.id}`, form.value)
    } else {
      await api.post('/api/admin/textbooks', form.value)
    }
    ElMessage.success('已保存')
    editOpen.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除版本「${row.name}」？`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/admin/textbooks/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

onMounted(() => { load(); loadRegions() })
</script>

<style scoped>
.tip { color: #888; font-size: 13px; margin: 0 0 12px; }
.toolbar { display: flex; gap: 10px; align-items: center; }
.hint { color: #999; font-size: 12px; margin-left: 8px; }
</style>
