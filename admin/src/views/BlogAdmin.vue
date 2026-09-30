<template>
  <div>
    <h2>Blog 内容管理</h2>
    <!-- 说明：分类/标签只有后台能增删改，前台 /api/blog 下均为只读（管理员 token 与用户 token
         无法共存于同一个 Authorization 头，故写操作一律走 /api/admin/blog/*）。 -->
    <el-tabs v-model="tab">
      <!-- ══════════════════ 文章 ══════════════════ -->
      <el-tab-pane label="文章" name="articles">
        <div class="toolbar">
          <el-input v-model="kw" placeholder="标题/摘要/正文关键词" clearable style="width: 220px"
                    @keyup.enter="page = 1; loadArticles()" />
          <el-select v-model="status" placeholder="状态" clearable style="width: 130px" @change="page = 1; loadArticles()">
            <el-option label="已发布" value="published" />
            <el-option label="草稿" value="draft" />
          </el-select>
          <el-button type="primary" @click="page = 1; loadArticles()">查询</el-button>
          <el-button @click="openCreateArticle">新建文章</el-button>
        </div>

        <el-table :data="articles" border stripe v-loading="loadingArticles" style="margin-top: 12px">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column label="分类" width="110">
            <template #default="{ row }">{{ row.category_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="author_id" label="作者" width="140" show-overflow-tooltip />
          <el-table-column label="状态" width="150">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'published' ? 'success' : 'info'">
                {{ row.status === 'published' ? '已发布' : '草稿' }}
              </el-tag>
              <el-tag size="small" type="danger" v-if="row.is_top">置顶</el-tag>
              <el-tag size="small" type="warning" v-if="row.is_recommend">推荐</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="view_count" label="浏览" width="80" />
          <el-table-column label="发布时间" width="150">
            <template #default="{ row }">{{ fmt(row.published_at || row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEditArticle(row)">编辑</el-button>
              <el-button size="small" :type="row.status === 'published' ? 'info' : 'success'"
                         @click="togglePublish(row)">{{ row.status === 'published' ? '转草稿' : '发布' }}</el-button>
              <el-button size="small" type="danger" @click="removeArticle(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pager">
          <el-button size="small" :disabled="page <= 1" @click="goPage(page - 1)">上一页</el-button>
          <span class="pager-text">{{ page }} / {{ totalPages }}（共 {{ total }} 篇）</span>
          <el-button size="small" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</el-button>
        </div>
      </el-tab-pane>

      <!-- ══════════════════ 分类 ══════════════════ -->
      <el-tab-pane label="分类" name="categories">
        <div class="toolbar">
          <el-button type="primary" @click="openCreate('category')">新建分类</el-button>
          <span class="hint">分类下仍有文章时不允许删除</span>
        </div>
        <el-table :data="categories" border stripe style="margin-top: 12px">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="slug" label="标识" width="160" />
          <el-table-column prop="sort_order" label="排序" width="80" />
          <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEdit('category', row)">编辑</el-button>
              <el-button size="small" type="danger" @click="removeTaxo('category', row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ══════════════════ 标签 ══════════════════ -->
      <el-tab-pane label="标签" name="tags">
        <div class="toolbar">
          <el-button type="primary" @click="openCreate('tag')">新建标签</el-button>
          <span class="hint">同名标签会被拒绝；删除标签会同时清理文章关联</span>
        </div>
        <el-table :data="tags" border stripe style="margin-top: 12px">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="名称" min-width="200" />
          <el-table-column prop="slug" label="标识" width="200" />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEdit('tag', row)">编辑</el-button>
              <el-button size="small" type="danger" @click="removeTaxo('tag', row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ══════════════════ 文章编辑弹窗 ══════════════════ -->
    <el-dialog v-model="articleOpen" :title="articleForm.id ? '编辑文章' : '新建文章'" width="720px">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="articleForm.title" maxlength="200" placeholder="文章标题" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="articleForm.summary" type="textarea" :rows="2" maxlength="200"
                    placeholder="可空，缺省前台自动取正文开头" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="articleForm.category_id" clearable style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="articleForm.tag_ids" multiple style="width: 100%">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="封面">
          <el-input v-model="articleForm.cover" placeholder="图片 URL，可空" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="articleForm.content_md" type="textarea" :rows="10"
                    placeholder="Markdown 正文" />
        </el-form-item>
        <el-form-item label="属性">
          <el-switch v-model="articleForm.is_top" active-text="置顶" />
          <el-switch v-model="articleForm.is_recommend" active-text="推荐" style="margin-left: 20px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="articleOpen = false">取消</el-button>
        <el-button @click="submitArticle(false)">存草稿</el-button>
        <el-button type="primary" :loading="saving" @click="submitArticle(true)">{{ articleForm.id ? '保存并发布' : '发布' }}</el-button>
      </template>
    </el-dialog>

    <!-- ══════════════════ 分类/标签编辑弹窗 ══════════════════ -->
    <el-dialog v-model="taxoOpen" :title="(taxoKind === 'category' ? '分类' : '标签') + (taxoForm.id ? '编辑' : '新建')" width="460px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="taxoForm.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="标识">
          <el-input v-model="taxoForm.slug" maxlength="50" placeholder="英文标识，可空" />
        </el-form-item>
        <el-form-item label="排序" v-if="taxoKind === 'category'">
          <el-input-number v-model="taxoForm.sort_order" :min="0" :max="999" />
        </el-form-item>
        <el-form-item label="说明" v-if="taxoKind === 'category'">
          <el-input v-model="taxoForm.description" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taxoOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitTaxo">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const tab = ref('articles')

// ── 文章 ──
const articles = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const kw = ref('')
const status = ref('')
const loadingArticles = ref(false)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ── 分类 / 标签 ──
const categories = ref([])
const tags = ref([])

// ── 弹窗状态 ──
const saving = ref(false)
const articleOpen = ref(false)
const articleForm = ref(blankArticle())
const taxoOpen = ref(false)
const taxoKind = ref('category')   // 'category' | 'tag'
const taxoForm = ref({ id: null, name: '', slug: '', sort_order: 0, description: '' })

function blankArticle() {
  return {
    id: null, title: '', summary: '', cover: '', content_md: '',
    category_id: null, tag_ids: [], is_top: false, is_recommend: false,
  }
}

/** 统一错误文案：后端错误信封是 {code,message,request_id}，部分场景仍是 {detail} */
function errText(e, fallback) {
  const d = e && e.response && e.response.data
  return (d && (d.message || d.detail)) || fallback
}
function fmt(s) {
  return s ? String(s).slice(0, 16).replace('T', ' ') : '-'
}

async function loadArticles() {
  loadingArticles.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (kw.value.trim()) params.keyword = kw.value.trim()
    if (status.value) params.status = status.value
    const { data } = await api.get('/api/admin/blog/articles', { params })
    articles.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error(errText(e, '加载文章失败'))
  } finally {
    loadingArticles.value = false
  }
}
async function loadTaxonomy() {
  try {
    const c = await api.get('/api/admin/blog/categories')
    categories.value = c.data || []
    const t = await api.get('/api/admin/blog/tags')
    tags.value = t.data || []
  } catch (e) {
    ElMessage.error(errText(e, '加载分类/标签失败'))
  }
}
function goPage(p) {
  page.value = Math.min(Math.max(1, p), totalPages.value)
  loadArticles()
}

/* ── 文章增删改 ── */
function openCreateArticle() {
  articleForm.value = blankArticle()
  articleOpen.value = true
}
function openEditArticle(row) {
  articleForm.value = {
    id: row.id,
    title: row.title || '',
    summary: row.summary || '',
    cover: row.cover || '',
    content_md: row.content_md || '',
    category_id: row.category_id || null,
    tag_ids: (row.tags || []).map(t => t.id),
    is_top: !!row.is_top,
    is_recommend: !!row.is_recommend,
  }
  articleOpen.value = true
}
async function submitArticle(publish) {
  if (!String(articleForm.value.title || '').trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  const body = {
    title: String(articleForm.value.title).trim(),
    summary: articleForm.value.summary || null,
    cover: articleForm.value.cover || null,
    content_md: articleForm.value.content_md || '',
    category_id: articleForm.value.category_id || null,
    tag_ids: articleForm.value.tag_ids || [],
    is_top: !!articleForm.value.is_top,
    is_recommend: !!articleForm.value.is_recommend,
    // 新建时直接决定状态；编辑时先按原状态保存， publish=true 再单独调发布接口
    status: publish ? 'published' : 'draft',
  }
  saving.value = true
  try {
    if (articleForm.value.id) {
      // 编辑：不带 status，避免「存草稿」把已发布文章误转草稿；发布走独立接口
      delete body.status
      await api.put('/api/admin/blog/articles/' + articleForm.value.id, body)
      if (publish) await api.post(`/api/admin/blog/articles/${articleForm.value.id}/publish`)
    } else {
      await api.post('/api/admin/blog/articles', body)
    }
    ElMessage.success(publish ? '已发布' : '已保存')
    articleOpen.value = false
    loadArticles()
  } catch (e) {
    ElMessage.error(errText(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
async function togglePublish(row) {
  const toPublished = row.status !== 'published'
  try {
    await api.post(`/api/admin/blog/articles/${row.id}/${toPublished ? 'publish' : 'unpublish'}`)
    ElMessage.success(toPublished ? '已发布' : '已转为草稿')
    loadArticles()
  } catch (e) {
    ElMessage.error(errText(e, '操作失败'))
  }
}
async function removeArticle(row) {
  try {
    await ElMessageBox.confirm(`确认删除文章「${row.title}」？`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.delete('/api/admin/blog/articles/' + row.id)
    ElMessage.success('已删除')
    loadArticles()
  } catch (e) {
    ElMessage.error(errText(e, '删除失败'))
  }
}

/* ── 分类 / 标签增删改 ── */
function openCreate(kind) {
  taxoKind.value = kind
  taxoForm.value = { id: null, name: '', slug: '', sort_order: 0, description: '' }
  taxoOpen.value = true
}
function openEdit(kind, row) {
  taxoKind.value = kind
  taxoForm.value = {
    id: row.id, name: row.name || '',
    slug: row.slug || '', sort_order: row.sort_order || 0, description: row.description || '',
  }
  taxoOpen.value = true
}
async function submitTaxo() {
  if (!String(taxoForm.value.name || '').trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  const kind = taxoKind.value
  const base = '/api/admin/blog/' + (kind === 'category' ? 'categories' : 'tags')
  const body = { name: String(taxoForm.value.name).trim(), slug: taxoForm.value.slug || null }
  if (kind === 'category') {
    body.sort_order = Number(taxoForm.value.sort_order) || 0
    body.description = taxoForm.value.description || null
  }
  saving.value = true
  try {
    if (taxoForm.value.id) {
      await api.put(`${base}/${taxoForm.value.id}`, body)
    } else {
      await api.post(base, body)
    }
    ElMessage.success('已保存')
    taxoOpen.value = false
    loadTaxonomy()
  } catch (e) {
    ElMessage.error(errText(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
async function removeTaxo(kind, row) {
  try {
    await ElMessageBox.confirm(`确认删除${kind === 'category' ? '分类' : '标签'}「${row.name}」？`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/admin/blog/${kind === 'category' ? 'categories' : 'tags'}/${row.id}`)
    ElMessage.success('已删除')
    loadTaxonomy()
    if (kind === 'category') loadArticles()
  } catch (e) {
    ElMessage.error(errText(e, '删除失败（分类下可能仍有文章）'))
  }
}

onMounted(() => {
  loadTaxonomy()
  loadArticles()
})
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.pager { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.pager-text { font-size: 13px; color: #606266; }
</style>
