<template>
  <div>
    <h2>知识点标注工作台</h2>
    <el-tabs v-model="tab">
      <el-tab-pane label="待标注队列" name="queue">
        <div class="toolbar">
          <el-select v-model="qFilter.subject" placeholder="学科" style="width: 100px" clearable @change="loadQueue">
            <el-option label="数学" value="数学" />
            <el-option label="语文" value="语文" />
            <el-option label="英语" value="英语" />
          </el-select>
          <el-select v-model="qFilter.source_table" placeholder="题库" style="width: 130px" @change="loadQueue">
            <el-option label="小学 questions" value="questions" />
            <el-option label="采集 paper_questions" value="paper_questions" />
            <el-option label="中学 middle_questions" value="middle_questions" />
          </el-select>
          <el-button @click="loadQueue">刷新</el-button>
          <div style="flex:1"></div>
          <el-button type="primary" :disabled="!checked.length" :loading="batchSaving" @click="batchSubmit">批量提交（{{ checked.length }}）</el-button>
        </div>
        <el-table :data="queue" border stripe size="small" @selection-change="s => checked = s" style="margin-top: 8px">
          <el-table-column type="selection" width="42" />
          <el-table-column prop="id" label="题ID" width="80" />
          <el-table-column prop="question_text" label="题干" min-width="280" show-overflow-tooltip />
          <el-table-column prop="subject" label="学科" width="70" />
          <el-table-column prop="grade" label="年级" width="60" />
          <el-table-column label="知识点" min-width="240">
            <template #default="{ row }">
              <el-cascader-panel
                v-if="kpOptions.length"
                :options="kpOptions"
                :props="{ multiple: true, value: 'id', label: 'title', children: 'children', emitPath: false, checkStrictly: true }"
                v-model="row._kpIds"
                style="min-width: 220px"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" :loading="row._saving" @click="submitOne(row)">提交</el-button>
              <el-button size="small" @click="aiPredict(row)">AI 预标注</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top: 12px" background layout="prev, pager, next, total"
                       :total="qTotal" :page-size="qSize" :current-page="qPage"
                       @current-change="(p) => { qPage = p; loadQueue() }" />
      </el-tab-pane>

      <el-tab-pane label="知识点树" name="tree">
        <div class="toolbar" style="margin-bottom: 8px">
          <el-select v-model="tFilter.subject" placeholder="学科" style="width: 100px" clearable @change="loadTree">
            <el-option label="数学" value="数学" /><el-option label="语文" value="语文" /><el-option label="英语" value="英语" />
          </el-select>
          <el-input-number v-model="tFilter.grade" :min="0" :max="9" controls-position="right" style="width: 110px" placeholder="年级" @change="loadTree" />
          <el-button @click="loadTree">刷新</el-button>
          <div style="flex:1"></div>
          <el-button type="primary" @click="openKp()">新增知识点</el-button>
        </div>
        <el-tree v-if="tree.length" :data="tree" :props="{ label: 'title', children: 'children' }" default-expand-all node-key="id" style="background: #fafafa; padding: 8px; border-radius: 4px" />
        <p v-else class="hint">（暂无知识点）</p>
      </el-tab-pane>

      <el-tab-pane label="标注统计" name="stats">
        <div v-if="stats" class="stats">
          <el-row :gutter="12">
            <el-col :span="6"><el-card><div class="big">{{ stats.annotated_count || 0 }}</div><div class="hint">已标注题</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big">{{ stats.total_count || 0 }}</div><div class="hint">题总数</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big">{{ stats.coverage || '0%' }}</div><div class="hint">覆盖率</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big">{{ stats.avg_per_question || 0 }}</div><div class="hint">平均每题知识点数</div></el-card></el-col>
          </el-row>
          <h4 style="margin: 16px 0 8px">按学科拆分</h4>
          <el-table :data="stats.by_subject || []" border size="small">
            <el-table-column prop="subject" label="学科" width="100" />
            <el-table-column prop="annotated" label="已标注" width="120" />
            <el-table-column prop="total" label="题总数" width="120" />
            <el-table-column prop="coverage" label="覆盖率" width="120" />
          </el-table>
        </div>
        <p v-else class="hint">（暂无数据）</p>
      </el-tab-pane>
    </el-tabs>

    <!-- 知识点编辑弹窗 -->
    <el-dialog v-model="kpOpen" :title="kpCur.id ? '编辑知识点' : '新增知识点'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="学科"><el-select v-model="kpForm.subject" style="width: 100%"><el-option label="数学" value="数学" /><el-option label="语文" value="语文" /><el-option label="英语" value="英语" /></el-select></el-form-item>
        <el-form-item label="年级"><el-input-number v-model="kpForm.grade" :min="1" :max="9" /></el-form-item>
        <el-form-item label="标题"><el-input v-model="kpForm.title" placeholder="知识点标题" /></el-form-item>
        <el-form-item label="单元"><el-input v-model="kpForm.unit" /></el-form-item>
        <el-form-item label="编码"><el-input v-model="kpForm.code" placeholder="可选，如 math-g7-func" /></el-form-item>
        <el-form-item label="父知识点"><el-input-number v-model="kpForm.parent_id" :min="0" /><span class="hint">0=顶级</span></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="kpForm.sort_order" :min="0" /></el-form-item>
        <el-form-item label="教材版本"><el-input v-model="kpForm.textbook_ver" /></el-form-item>
        <el-form-item label="摘要"><el-input v-model="kpForm.summary" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="kpOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveKp">保存</el-button>
      </template>
    </el-dialog>

    <!-- 知识点选择弹窗 -->
    <el-dialog v-model="kpPickOpen" title="选择知识点" width="520px">
      <el-cascader v-model="kpPickValue" :options="kpOptions"
                   :props="{ multiple: true, value: 'id', label: 'title', children: 'children', emitPath: false, checkStrictly: true }"
                   collapse-tags collapse-tags-tooltip
                   style="width: 100%" />
      <template #footer>
        <el-button @click="kpPickOpen = false">取消</el-button>
        <el-button type="primary" @click="confirmKpPick">确定</el-button>
      </template>
    </el-dialog>

    <!-- AI 预标注结果 -->
    <el-dialog v-model="aiOpen" title="AI 预标注建议" width="520px">
      <p v-if="!aiList.length" class="hint">无建议</p>
      <el-table v-else :data="aiList" border size="small">
        <el-table-column prop="kp_id" label="KP ID" width="80" />
        <el-table-column prop="title" label="知识点" min-width="180" />
        <el-table-column prop="confidence" label="置信度" width="100">
          <template #default="{ row }">{{ ((row.confidence || 0) * 100).toFixed(0) }}%</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '../api'

const tab = ref('queue')

// 队列
const queue = ref([]), qTotal = ref(0), qPage = ref(1), qSize = ref(20)
const qFilter = ref({ subject: '', source_table: 'questions' })
const checked = ref([]), batchSaving = ref(false)
const kpOptions = ref([])
const saving = ref(false)

async function loadQueue() {
  const params = { page: qPage.value, page_size: qSize.value, source_table: qFilter.value.source_table }
  if (qFilter.value.subject) params.subject = qFilter.value.subject
  const d = await api.get('/api/admin/content/annotation/queue', { params })
  queue.value = ((d && (d.items || d.queue)) || []).map(x => ({ ...x, _kpIds: x.kp_ids || [], _saving: false }))
  qTotal.value = (d && d.total) || queue.value.length
}

async function loadKpTree() {
  const params = {}
  if (tFilter.value.subject) params.subject = tFilter.value.subject
  if (tFilter.value.grade > 0) params.grade = tFilter.value.grade
  const d = await api.get('/api/admin/content/kp/tree', { params })
  kpOptions.value = (d && d.tree) || []
}

async function submitOne(row) {
  if (!row._kpIds || !row._kpIds.length) { ElMessage.warning('请至少勾选 1 个知识点'); return }
  row._saving = true
  try {
    await api.post('/api/admin/content/annotation', {
      source_table: qFilter.value.source_table,
      question_id: row.id, kp_ids: row._kpIds,
    })
    ElMessage.success('已提交')
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '提交失败') }
  finally { row._saving = false }
}
async function batchSubmit() {
  const items = checked.value.filter(x => x._kpIds && x._kpIds.length).map(x => ({ question_id: x.id, kp_ids: x._kpIds }))
  if (!items.length) { ElMessage.warning('所选题目均未勾选知识点'); return }
  batchSaving.value = true
  try {
    await api.post('/api/admin/content/annotation', { source_table: qFilter.value.source_table, annotations: items })
    ElMessage.success(`批量提交 ${items.length} 题`); loadQueue()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '批量提交失败') }
  finally { batchSaving.value = false }
}

const aiOpen = ref(false), aiList = ref([])
async function aiPredict(row) {
  try {
    const d = await api.post('/api/admin/content/annotation/ai-predict', {
      source_table: qFilter.value.source_table, question_id: row.id,
    })
    aiList.value = (d && d.predictions) || []
    aiOpen.value = true
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || 'AI 预标注失败') }
}

// 知识点树 + 编辑
const tree = ref([]), tFilter = ref({ subject: '', grade: 0 })
const kpOpen = ref(false), kpCur = ref({}), kpForm = ref({})
async function loadTree() {
  const params = {}
  if (tFilter.value.subject) params.subject = tFilter.value.subject
  if (tFilter.value.grade > 0) params.grade = tFilter.value.grade
  const d = await api.get('/api/admin/content/kp/tree', { params })
  tree.value = (d && d.tree) || []
  kpOptions.value = tree.value
}
function openKp(row) {
  kpCur.value = row || {}
  kpForm.value = row
    ? { subject: row.subject, grade: row.grade, title: row.title, unit: row.unit || '', code: row.code || '', parent_id: row.parent_id || 0, sort_order: row.sort_order || 0, textbook_ver: row.textbook_ver || '', summary: row.summary || '' }
    : { subject: '数学', grade: 7, title: '', unit: '', code: '', parent_id: 0, sort_order: 0, textbook_ver: '', summary: '' }
  kpOpen.value = true
}
async function saveKp() {
  if (!kpForm.value.title) { ElMessage.warning('请填写标题'); return }
  saving.value = true
  try {
    await api.post('/api/admin/content/kp', { kp_id: kpCur.value.id || null, ...kpForm.value })
    ElMessage.success('已保存'); kpOpen.value = false; loadTree()
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '保存失败') }
  finally { saving.value = false }
}

// 统计
const stats = ref(null)
async function loadStats() {
  const d = await api.get('/api/admin/content/annotation/stats', { params: { source_table: qFilter.value.source_table } })
  stats.value = d
}

onMounted(() => { loadQueue(); loadKpTree() })
// tab 切换时按需加载
const _ = computed(() => tab.value)
import { watch } from 'vue'
watch(_, (v) => { if (v === 'tree') loadTree(); if (v === 'stats') loadStats() })
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; }
.hint { color: #999; font-size: 12px; }
.stats .el-card { text-align: center; }
.big { font-size: 28px; font-weight: 700; color: #409eff; }
</style>
