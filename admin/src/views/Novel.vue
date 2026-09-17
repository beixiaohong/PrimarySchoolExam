<template>
  <div>
    <h2>小说站管理</h2>
    <p class="tip">
      上传 TXT 自动导入：系统自动探测编码（UTF-8 / GBK / GB18030），能识别章节就自动分章
      （读者端可看目录、按章下滑加载）；识别不出章节则按等大文本块切片，读者端下滑流式加载。
      前端入口：<b>/novel</b>（独立于学生学习端）。
    </p>

    <!-- ── 上传导入 ── -->
    <el-card shadow="never" style="margin-bottom: 14px">
      <template #header><b>上传 TXT 导入</b></template>
      <el-form label-width="80px" :inline="true">
        <el-form-item label="TXT 文件" required>
          <input type="file" accept=".txt" @change="onFile" style="max-width: 260px" />
          <span class="hint" v-if="file">已选：{{ file.name }}（{{ (file.size / 1024).toFixed(0) }} KB）</span>
        </el-form-item>
        <el-form-item label="书名">
          <el-input v-model="form.title" placeholder="留空则取文件名" style="width: 180px" />
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="form.author" style="width: 130px" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="如 玄幻/都市/校园" style="width: 150px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100px">
            <el-option label="连载" value="serial" />
            <el-option label="完本" value="finished" />
            <el-option label="草稿" value="draft" />
          </el-select>
        </el-form-item>
        <el-form-item label="立即上架">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <el-form label-width="80px">
        <el-form-item label="简介">
          <el-input v-model="form.intro" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="uploading" @click="upload">开始导入</el-button>
          <span class="hint" style="margin-left:10px">单文件上限 20MB，大书导入需数秒，请耐心等待</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ── 列表 ── -->
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索书名/作者" style="width: 200px"
                clearable @keyup.enter="load" @clear="load" />
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="书名" min-width="150" show-overflow-tooltip />
      <el-table-column prop="author" label="作者" width="100" />
      <el-table-column prop="category" label="分类" width="90" />
      <el-table-column label="阅读模式" width="100">
        <template #default="{ row }">
          <el-tag :type="row.chapter_mode === 'chapter' ? 'success' : 'warning'" size="small">
            {{ row.chapter_mode === 'chapter' ? '已分章' : '流式分块' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="chapter_count" label="章/段" width="80" />
      <el-table-column label="字数" width="90">
        <template #default="{ row }">{{ fmtWords(row.word_count) }}</template>
      </el-table-column>
      <el-table-column prop="view_count" label="人气" width="80" />
      <el-table-column label="上架" width="80">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '已上架' : '已下架' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openChapters(row)">章节</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" @click="toggle(row)">{{ row.enabled ? '下架' : '上架' }}</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div style="margin-top: 12px; display: flex; justify-content: flex-end">
      <el-pagination background layout="prev, pager, next" :total="total"
                     :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <!-- ── 编辑元信息 ── -->
    <el-dialog v-model="editOpen" title="编辑小说" width="460px">
      <el-form label-width="80px">
        <el-form-item label="书名"><el-input v-model="ef.title" /></el-form-item>
        <el-form-item label="作者"><el-input v-model="ef.author" /></el-form-item>
        <el-form-item label="分类"><el-input v-model="ef.category" /></el-form-item>
        <el-form-item label="封面URL"><el-input v-model="ef.cover_url" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="ef.status" style="width: 100%">
            <el-option label="连载" value="serial" />
            <el-option label="完本" value="finished" />
            <el-option label="草稿" value="draft" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序"><el-input-number v-model="ef.sort_order" :min="0" :max="9999" /></el-form-item>
        <el-form-item label="上架"><el-switch v-model="ef.enabled" /></el-form-item>
        <el-form-item label="简介"><el-input v-model="ef.intro" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- ── 章节维护 ── -->
    <el-dialog v-model="chapOpen" :title="`章节管理 - ${cur.title || ''}`" width="820px">
      <el-table :data="chapters" border stripe max-height="440">
        <el-table-column prop="idx" label="#" width="60" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="word_count" label="字数" width="80" />
        <el-table-column prop="preview" label="正文预览" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openChapterEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="removeChapter(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center">
        <span class="hint">共 {{ chapTotal }} 段</span>
        <el-pagination background layout="prev, pager, next" :total="chapTotal"
                       :page-size="chapPageSize" v-model:current-page="chapPage" @current-change="loadChapters" />
      </div>
    </el-dialog>

    <!-- ── 章节正文编辑 ── -->
    <el-dialog v-model="chapEditOpen" title="编辑章节" width="720px">
      <el-form label-width="60px">
        <el-form-item label="标题"><el-input v-model="cf.title" /></el-form-item>
        <el-form-item label="正文"><el-input v-model="cf.content" type="textarea" :rows="14" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="chapEditOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveChapter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const rows = ref([])
const keyword = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

const file = ref(null)
const uploading = ref(false)
const form = ref({ title: '', author: '', category: '', intro: '', status: 'serial', enabled: true })

const editOpen = ref(false)
const saving = ref(false)
const cur = ref({})
const ef = ref({})

const chapOpen = ref(false)
const chapters = ref([])
const chapPage = ref(1)
const chapPageSize = 20
const chapTotal = ref(0)

const chapEditOpen = ref(false)
const cf = ref({ id: 0, title: '', content: '' })

function fmtWords(n) {
  n = n || 0
  return n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n)
}

function onFile(e) { file.value = e.target.files && e.target.files[0] }

async function load() {
  const { data: d } = await api.get('/api/admin/novel/list', {
    params: { keyword: keyword.value, page: page.value, page_size: pageSize },
  })
  rows.value = (d && d.items) || []
  total.value = (d && d.total) || 0
}

async function upload() {
  if (!file.value) { ElMessage.warning('请先选择 TXT 文件'); return }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    Object.keys(form.value).forEach((k) => {
      // FormData 只收字符串，布尔值按 'true'/'false' 传给后端 Form(...)
      fd.append(k, String(form.value[k]))
    })
    const { data: d } = await api.post('/api/admin/novel/upload', fd)
    ElMessage.success(
      `导入成功：${d.mode === 'chapter' ? '已自动分章' : '未识别章节，按块流式加载'}，` +
      `共 ${d.chapter_count} 段 / ${d.word_count} 字`
    )
    file.value = null
    form.value = { title: '', author: '', category: '', intro: '', status: 'serial', enabled: true }
    await load()
  } catch (e) {
    ElMessage.error((e.response && e.response.data && (e.response.data.message || e.response.data.detail)) || '导入失败')
  } finally {
    uploading.value = false
  }
}

function openEdit(row) {
  cur.value = row
  ef.value = {
    title: row.title, author: row.author || '', category: row.category || '',
    cover_url: row.cover_url || '', intro: row.intro || '', status: row.status || 'serial',
    sort_order: row.sort_order || 0, enabled: !!row.enabled,
  }
  editOpen.value = true
}

async function saveEdit() {
  saving.value = true
  try {
    await api.patch(`/api/admin/novel/${cur.value.id}`, ef.value)
    ElMessage.success('已保存')
    editOpen.value = false
    await load()
  } finally { saving.value = false }
}

async function toggle(row) {
  await api.post(`/api/admin/novel/${row.id}/toggle`)
  ElMessage.success('已更新')
  await load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除《${row.title}》？章节与阅读记录将一并删除，不可恢复。`, '删除确认', { type: 'warning' })
  } catch (e) { return }
  await api.delete(`/api/admin/novel/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

async function openChapters(row) {
  cur.value = row
  chapPage.value = 1
  chapOpen.value = true
  await loadChapters()
}

async function loadChapters() {
  const { data: d } = await api.get(`/api/admin/novel/${cur.value.id}/chapters`, {
    params: { offset: (chapPage.value - 1) * chapPageSize, limit: chapPageSize, preview: 60 },
  })
  chapters.value = (d && d.items) || []
  chapTotal.value = (d && d.total) || 0
}

function openChapterEdit(row) {
  cf.value = { id: row.id, title: row.title || '', content: '' }
  // 正文单独拉（列表只返回预览），避免对话框打开过慢
  api.get(`/api/admin/novel/${cur.value.id}/chapters`, {
    params: { offset: row.idx - 1, limit: 1, with_content: true },
  }).then(({ data: d }) => {
    const hit = (d.items || []).find((x) => x.id === row.id)
    cf.value.content = hit ? (hit.content || '') : ''
  })
  chapEditOpen.value = true
}

async function saveChapter() {
  saving.value = true
  try {
    await api.patch(`/api/admin/novel/${cur.value.id}/chapter/${cf.value.id}`, {
      title: cf.value.title, content: cf.value.content,
    })
    ElMessage.success('已保存')
    chapEditOpen.value = false
    await loadChapters()
  } finally { saving.value = false }
}

async function removeChapter(row) {
  try {
    await ElMessageBox.confirm(`确认删除第 ${row.idx} 段？`, '删除确认', { type: 'warning' })
  } catch (e) { return }
  await api.delete(`/api/admin/novel/${cur.value.id}/chapter/${row.id}`)
  ElMessage.success('已删除')
  await loadChapters()
}

onMounted(load)
</script>
