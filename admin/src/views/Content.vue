<template>
  <div>
    <h2>内容管理</h2>
    <el-tabs v-model="tab" @tab-change="onTabChange">
      <!-- ═══════ 词库 ═══════ -->
      <el-tab-pane label="📚 词库" name="books">
        <div class="toolbar">
          <el-select v-model="bookFilter.grade" style="width: 120px" clearable placeholder="年级" @change="loadBooks">
            <el-option v-for="g in 9" :key="g" :label="g + ' 年级'" :value="g" />
          </el-select>
          <el-input v-model="bookFilter.kw" placeholder="搜索词书名" style="width: 220px" clearable @keyup.enter="loadBooks" @clear="loadBooks" />
          <el-button type="primary" @click="loadBooks">搜索</el-button>
          <el-button type="success" @click="openBook()">新增词书</el-button>
        </div>
        <el-table :data="books" border stripe style="margin-top: 12px">
          <el-table-column prop="id" label="ID" width="56" />
          <el-table-column prop="name" label="词书名" min-width="180" />
          <el-table-column prop="grade" label="年级" width="60" />
          <el-table-column prop="semester" label="学期" width="56" />
          <el-table-column prop="publisher" label="出版社" width="110" />
          <el-table-column prop="word_count" label="词数" width="70" />
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="openBookWords(row)">单词</el-button>
              <el-button size="small" @click="openBook(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="removeBook(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 词书弹窗 -->
        <el-dialog v-model="bookOpen" :title="curBook.id ? '编辑词书' : '新增词书'" width="440px">
          <el-form label-width="90px">
            <el-form-item label="词书名"><el-input v-model="bookForm.name" placeholder="如：人教版PEP六年级上" /></el-form-item>
            <el-form-item label="年级"><el-input-number v-model="bookForm.grade" :min="1" :max="9" /></el-form-item>
            <el-form-item label="学期">
              <el-select v-model="bookForm.semester" style="width: 100%">
                <el-option label="上" value="上" /><el-option label="下" value="下" /><el-option label="全" value="全" />
              </el-select>
            </el-form-item>
            <el-form-item label="出版社"><el-input v-model="bookForm.publisher" /></el-form-item>
            <el-form-item label="教材版本">
              <el-select v-model="bookForm.textbook_id" clearable style="width: 100%">
                <el-option v-for="v in textbookOptions" :key="v.id" :label="v.name" :value="v.id" />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="bookOpen = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="saveBook">保存</el-button>
          </template>
        </el-dialog>

        <!-- 单词管理弹窗 -->
        <el-dialog v-model="wordsOpen" :title="'📖 ' + (curBook.name || '') + ' 单词管理'" width="900px">
          <div class="toolbar">
            <el-input v-model="wordKw" placeholder="搜索单词" style="width: 200px" clearable @keyup.enter="loadWords" />
            <el-button @click="loadWords">搜索</el-button>
            <el-button type="success" @click="openWord()">新增单词</el-button>
            <el-button type="warning" @click="importOpen = true">批量导入</el-button>
          </div>
          <el-table :data="words" border stripe size="small" style="margin-top: 10px" max-height="420">
            <el-table-column prop="word" label="单词" min-width="110" />
            <el-table-column prop="phonetic" label="音标" width="130" />
            <el-table-column prop="pos" label="词性" width="60" />
            <el-table-column prop="meaning" label="释义" min-width="140" show-overflow-tooltip />
            <el-table-column prop="unit" label="单元" width="70" />
            <el-table-column prop="difficulty" label="难度" width="56" />
            <el-table-column label="操作" width="130">
              <template #default="{ row }">
                <el-button size="small" @click="openWord(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="removeWord(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination style="margin-top: 10px" background layout="prev, pager, next, total" :total="wordTotal"
                         :page-size="wordPageSize" :current-page="wordPage" @current-change="p => { wordPage = p; loadWords() }" />
        </el-dialog>

        <!-- 单词编辑 -->
        <el-dialog v-model="wordOpen" :title="curWord.id ? '编辑单词' : '新增单词'" width="460px">
          <el-form label-width="70px">
            <el-form-item label="单词"><el-input v-model="wordForm.word" /></el-form-item>
            <el-form-item label="音标"><el-input v-model="wordForm.phonetic" /></el-form-item>
            <el-form-item label="词性"><el-input v-model="wordForm.pos" placeholder="n./v./adj." /></el-form-item>
            <el-form-item label="释义"><el-input v-model="wordForm.meaning" /></el-form-item>
            <el-form-item label="单元"><el-input v-model="wordForm.unit" placeholder="Unit 1" /></el-form-item>
            <el-form-item label="难度"><el-input-number v-model="wordForm.difficulty" :min="1" :max="5" /></el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="wordOpen = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="saveWord">保存</el-button>
          </template>
        </el-dialog>

        <!-- 批量导入 -->
        <el-dialog v-model="importOpen" title="批量导入单词" width="640px">
          <p class="tip">每行一条：<code>word|音标|词性|释义</code>，或 <code>word 释义</code>；重复与空行自动跳过</p>
          <el-input v-model="importText" type="textarea" :rows="12" placeholder="apple|ˈæpl|n.|苹果&#10;banana|bəˈnɑːnə|n.|香蕉" />
          <template #footer>
            <el-button @click="importOpen = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="doImport">开始导入</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ═══════ 诗词库 ═══════ -->
      <el-tab-pane label="🪶 诗词库" name="classicals">
        <div class="toolbar">
          <el-input v-model="clKw" placeholder="搜索篇名/作者" style="width: 220px" clearable @keyup.enter="loadClassicals" />
          <el-button type="primary" @click="loadClassicals">搜索</el-button>
          <el-button type="success" @click="openClassical()">新增篇目</el-button>
        </div>
        <el-table :data="classicals" border stripe style="margin-top: 12px">
          <el-table-column prop="title" label="篇名" min-width="150" />
          <el-table-column prop="author" label="作者" width="90" />
          <el-table-column prop="dynasty" label="朝代" width="80" />
          <el-table-column prop="grade" label="年级" width="60" />
          <el-table-column prop="semester" label="学期" width="56" />
          <el-table-column label="正文" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ (row.content || '').slice(0, 60) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openClassical(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="removeClassical(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-dialog v-model="clOpen" :title="curCl.id ? '编辑篇目' : '新增篇目'" width="640px">
          <el-form label-width="70px">
            <el-form-item label="篇名"><el-input v-model="clForm.title" /></el-form-item>
            <div style="display:flex;gap:10px">
              <el-form-item label="作者"><el-input v-model="clForm.author" /></el-form-item>
              <el-form-item label="朝代"><el-input v-model="clForm.dynasty" style="width:120px" /></el-form-item>
            </div>
            <el-form-item label="类型">
              <el-select v-model="clForm.text_type" style="width: 160px">
                <el-option label="古诗" value="poem" /><el-option label="文言文" value="prose" />
              </el-select>
              <span style="margin-left:14px">年级 <el-input-number v-model="clForm.grade" :min="1" :max="9" size="small" /></span>
              <span style="margin-left:14px">学期
                <el-select v-model="clForm.semester" size="small" style="width:80px">
                  <el-option label="上" value="上" /><el-option label="下" value="下" /><el-option label="全" value="全" />
                </el-select>
              </span>
            </el-form-item>
            <el-form-item label="正文">
              <el-input v-model="clForm.content" type="textarea" :rows="8" placeholder="每行一句（用于默写/填空出题）" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="clOpen = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="saveClassical">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ═══════ 语法知识点 ═══════ -->
      <el-tab-pane label="🧠 语法知识点" name="grammar">
        <div class="toolbar">
          <el-input v-model="grKw" placeholder="搜索语法点" style="width: 200px" clearable @keyup.enter="loadGrammar" />
          <el-button type="primary" @click="loadGrammar">搜索</el-button>
          <el-button type="success" @click="openGrammar()">新增语法点</el-button>
        </div>
        <el-table :data="grammars" border stripe style="margin-top: 12px">
          <el-table-column prop="name" label="名称" min-width="130" />
          <el-table-column prop="code" label="编码" width="120" />
          <el-table-column prop="grade" label="年级" width="60" />
          <el-table-column prop="category" label="分类" width="80" />
          <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openGrammar(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="removeGrammar(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-dialog v-model="grOpen" :title="curGr.id ? '编辑语法点' : '新增语法点'" width="560px">
          <el-form label-width="80px">
            <el-form-item label="名称"><el-input v-model="grForm.name" /></el-form-item>
            <el-form-item label="编码"><el-input v-model="grForm.code" placeholder="唯一编码，如 present_simple" /></el-form-item>
            <el-form-item label="分类">
              <el-select v-model="grForm.category" style="width: 160px">
                <el-option v-for="c in ['时态','词法','句型','语态']" :key="c" :label="c" :value="c" />
              </el-select>
              <span style="margin-left:14px">年级 <el-input-number v-model="grForm.grade" :min="1" :max="9" size="small" /></span>
            </el-form-item>
            <el-form-item label="说明"><el-input v-model="grForm.description" type="textarea" :rows="2" /></el-form-item>
            <el-form-item label="例句"><el-input v-model="grForm.examples" type="textarea" :rows="4" placeholder="每行一句" /></el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="grOpen = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="saveGrammar">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ═══════ 采集试卷 ═══════ -->
      <el-tab-pane label="📄 采集试卷" name="papers">
        <div class="toolbar">
          <el-input v-model="paperKw" placeholder="搜索试卷标题" style="width: 220px" clearable @keyup.enter="loadPapers" />
          <el-button type="primary" @click="loadPapers">搜索</el-button>
        </div>
        <el-table :data="papers" border stripe style="margin-top: 12px">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
          <el-table-column prop="subject" label="学科" width="70" />
          <el-table-column prop="grade" label="年级" width="80" />
          <el-table-column prop="source" label="来源" width="80" />
          <el-table-column prop="question_count" label="题目数" width="70" />
          <el-table-column prop="created_at" label="入库" width="110" />
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="viewPaper(row)">详情</el-button>
              <el-button size="small" type="danger" @click="removePaper(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top: 12px" background layout="prev, pager, next, total" :total="paperTotal"
                       :page-size="paperPageSize" :current-page="paperPage" @current-change="p => { paperPage = p; loadPapers() }" />
        <el-dialog v-model="paperDetailOpen" :title="paperDetail.title || '试卷详情'" width="760px">
          <p class="tip">学科：{{ paperDetail.subject }} · 年级：{{ paperDetail.grade }} · 入库：{{ paperDetail.created_at }}</p>
          <el-table :data="paperDetail.questions || []" border size="small" max-height="480">
            <el-table-column prop="seq" label="序号" width="60" />
            <el-table-column prop="question" label="题目" min-width="300" show-overflow-tooltip />
            <el-table-column prop="answer" label="参考答案" min-width="160" show-overflow-tooltip />
            <el-table-column prop="question_type" label="题型" width="90" />
          </el-table>
        </el-dialog>
      </el-tab-pane>

      <!-- ═══════ 网课 ═══════ -->
      <el-tab-pane label="🎬 网课" name="courses">
        <div class="toolbar">
          <el-input v-model="courseKw" placeholder="搜索课程标题" style="width: 220px" clearable @keyup.enter="loadCourses" />
          <el-button type="primary" @click="loadCourses">搜索</el-button>
          <el-button type="success" @click="openCourse()">新增网课</el-button>
        </div>
        <el-table :data="courses" border stripe style="margin-top: 12px">
          <el-table-column prop="id" label="ID" width="56" />
          <el-table-column prop="title" label="课程标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="subject" label="学科" width="80" />
          <el-table-column label="年级" width="80">
            <template #default="{ row }">{{ row.grade ? row.grade + ' 年级' : '不限' }}</template>
          </el-table-column>
          <el-table-column label="视频" min-width="200" show-overflow-tooltip>
            <template #default="{ row }"><a :href="row.video_url" target="_blank" rel="noopener">{{ row.video_url }}</a></template>
          </el-table-column>
          <el-table-column prop="duration_min" label="时长(分)" width="80" />
          <el-table-column label="启用" width="70">
            <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openCourse(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="removeCourse(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-dialog v-model="courseOpen" :title="curCourse.id ? '编辑网课' : '新增网课'" width="560px">
          <el-form label-width="80px">
            <el-form-item label="标题"><el-input v-model="courseForm.title" /></el-form-item>
            <el-form-item label="学科">
              <el-select v-model="courseForm.subject" clearable style="width: 160px">
                <el-option v-for="s in ['数学','语文','英语']" :key="s" :label="s" :value="s" />
              </el-select>
              <span style="margin-left:14px">年级（0=不限）
                <el-input-number v-model="courseForm.grade" :min="0" :max="9" size="small" style="width:100px" />
              </span>
            </el-form-item>
            <el-form-item label="视频URL"><el-input v-model="courseForm.video_url" placeholder="b站/腾讯视频/直链 mp4" /></el-form-item>
            <el-form-item label="封面URL"><el-input v-model="courseForm.cover_url" placeholder="可选" /></el-form-item>
            <el-form-item label="时长(分)"><el-input-number v-model="courseForm.duration_min" :min="0" :max="999" /></el-form-item>
            <el-form-item label="排序"><el-input-number v-model="courseForm.sort_order" :min="0" :max="9999" /></el-form-item>
            <el-form-item label="简介"><el-input v-model="courseForm.description" type="textarea" :rows="2" /></el-form-item>
            <el-form-item label="启用"><el-switch v-model="courseForm.enabled" /></el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="courseOpen = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="saveCourse">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const tab = ref('books')

// ── 词库 ──
const books = ref([])
const bookFilter = ref({ grade: 0, kw: '' })
const textbookOptions = ref([])
const bookOpen = ref(false)
const curBook = ref({})
const bookForm = ref({ name: '', grade: 6, semester: '上', publisher: '人教版PEP', textbook_id: 0 })
const wordsOpen = ref(false)
const words = ref([])
const wordTotal = ref(0)
const wordPage = ref(1)
const wordPageSize = ref(30)
const wordKw = ref('')
const wordOpen = ref(false)
const curWord = ref({})
const wordForm = ref({ word: '', phonetic: '', pos: '', meaning: '', unit: '', difficulty: 1 })
const importOpen = ref(false)
const importText = ref('')
const saving = ref(false)

async function loadBooks() {
  const params = {}
  if (bookFilter.value.grade) params.grade = bookFilter.value.grade
  if (bookFilter.value.kw) params.keyword = bookFilter.value.kw
  const d = await api.get('/api/admin/books', { params })
  books.value = (d && d.items) || []
}
async function loadTextbookOptions() {
  const d = await api.get('/api/admin/textbooks', { params: { subject: '英语' } })
  textbookOptions.value = (d && d.items) || []
}
function openBook(row) {
  curBook.value = row || {}
  bookForm.value = row
    ? { name: row.name, grade: row.grade, semester: row.semester, publisher: row.publisher || '人教版PEP', textbook_id: row.textbook_id || 0 }
    : { name: '', grade: bookFilter.value.grade || 6, semester: '上', publisher: '人教版PEP', textbook_id: 0 }
  bookOpen.value = true
}
async function saveBook() {
  saving.value = true
  try {
    if (curBook.value.id) await api.put(`/api/admin/books/${curBook.value.id}`, bookForm.value)
    else await api.post('/api/admin/books', bookForm.value)
    ElMessage.success('已保存')
    bookOpen.value = false
    loadBooks()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function removeBook(row) {
  try { await ElMessageBox.confirm(`确定删除词书「${row.name}」？其下单词将一并删除`, '提示', { type: 'warning' }) } catch { return }
  try { await api.delete(`/api/admin/books/${row.id}`); ElMessage.success('已删除'); loadBooks() }
  catch (e) { ElMessage.error(e.message) }
}
function openBookWords(row) {
  curBook.value = row
  wordPage.value = 1
  wordKw.value = ''
  wordsOpen.value = true
  loadWords()
}
async function loadWords() {
  const params = { page: wordPage.value, page_size: wordPageSize.value }
  if (wordKw.value) params.keyword = wordKw.value
  const d = await api.get(`/api/admin/books/${curBook.value.id}/words`, { params })
  words.value = (d && d.items) || []
  wordTotal.value = (d && d.total) || 0
}
function openWord(row) {
  curWord.value = row || {}
  wordForm.value = row
    ? { word: row.word, phonetic: row.phonetic, pos: row.pos, meaning: row.meaning, unit: row.unit, difficulty: row.difficulty }
    : { word: '', phonetic: '', pos: '', meaning: '', unit: '', difficulty: 1 }
  wordOpen.value = true
}
async function saveWord() {
  saving.value = true
  try {
    if (curWord.value.id) await api.put(`/api/admin/words/${curWord.value.id}`, wordForm.value)
    else await api.post(`/api/admin/books/${curBook.value.id}/words`, wordForm.value)
    ElMessage.success('已保存')
    wordOpen.value = false
    loadWords(); loadBooks()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function removeWord(row) {
  try { await ElMessageBox.confirm(`删除单词「${row.word}」？`, '提示', { type: 'warning' }) } catch { return }
  try { await api.delete(`/api/admin/words/${row.id}`); ElMessage.success('已删除'); loadWords(); loadBooks() }
  catch (e) { ElMessage.error(e.message) }
}
async function doImport() {
  saving.value = true
  try {
    const d = await api.post(`/api/admin/books/${curBook.value.id}/words/import`, { text: importText.value })
    ElMessage.success(`导入 ${d.added} 个，跳过 ${d.skipped} 个`)
    importOpen.value = false
    importText.value = ''
    loadWords(); loadBooks()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

// ── 诗词库 ──
const classicals = ref([])
const clKw = ref('')
const clOpen = ref(false)
const curCl = ref({})
const clForm = ref({ title: '', author: '', dynasty: '', text_type: 'poem', grade: 3, semester: '全', content: '' })

async function loadClassicals() {
  const params = {}
  if (clKw.value) params.keyword = clKw.value
  const d = await api.get('/api/admin/classicals', { params })
  classicals.value = (d && d.items) || []
}
function openClassical(row) {
  curCl.value = row || {}
  clForm.value = row
    ? { title: row.title, author: row.author, dynasty: row.dynasty, text_type: row.text_type, grade: row.grade, semester: row.semester, content: row.content }
    : { title: '', author: '', dynasty: '', text_type: 'poem', grade: 3, semester: '全', content: '' }
  clOpen.value = true
}
async function saveClassical() {
  saving.value = true
  try {
    if (curCl.value.id) await api.put(`/api/admin/classicals/${curCl.value.id}`, clForm.value)
    else await api.post('/api/admin/classicals', clForm.value)
    ElMessage.success('已保存')
    clOpen.value = false
    loadClassicals()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function removeClassical(row) {
  try { await ElMessageBox.confirm(`删除篇目「${row.title}」？`, '提示', { type: 'warning' }) } catch { return }
  try { await api.delete(`/api/admin/classicals/${row.id}`); ElMessage.success('已删除'); loadClassicals() }
  catch (e) { ElMessage.error(e.message) }
}

// ── 语法知识点 ──
const grammars = ref([])
const grKw = ref('')
const grOpen = ref(false)
const curGr = ref({})
const grForm = ref({ name: '', code: '', grade: 3, category: '时态', description: '', examples: '' })

async function loadGrammar() {
  const params = {}
  if (grKw.value) params.keyword = grKw.value
  const d = await api.get('/api/admin/grammar-points', { params })
  grammars.value = (d && d.items) || []
}
function openGrammar(row) {
  curGr.value = row || {}
  grForm.value = row
    ? { name: row.name, code: row.code, grade: row.grade, category: row.category, description: row.description, examples: row.examples }
    : { name: '', code: '', grade: 3, category: '时态', description: '', examples: '' }
  grOpen.value = true
}
async function saveGrammar() {
  saving.value = true
  try {
    if (curGr.value.id) await api.put(`/api/admin/grammar-points/${curGr.value.id}`, grForm.value)
    else await api.post('/api/admin/grammar-points', grForm.value)
    ElMessage.success('已保存')
    grOpen.value = false
    loadGrammar()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function removeGrammar(row) {
  try { await ElMessageBox.confirm(`删除语法点「${row.name}」？其练习题将一并删除`, '提示', { type: 'warning' }) } catch { return }
  try { await api.delete(`/api/admin/grammar-points/${row.id}`); ElMessage.success('已删除'); loadGrammar() }
  catch (e) { ElMessage.error(e.message) }
}

// ── 采集试卷 ──
const papers = ref([])
const paperTotal = ref(0)
const paperPage = ref(1)
const paperPageSize = ref(20)
const paperKw = ref('')
const paperDetailOpen = ref(false)
const paperDetail = ref({})

async function loadPapers() {
  const params = { page: paperPage.value, page_size: paperPageSize.value }
  if (paperKw.value) params.keyword = paperKw.value
  const d = await api.get('/api/admin/collected-papers', { params })
  papers.value = (d && d.items) || []
  paperTotal.value = (d && d.total) || 0
}
async function viewPaper(row) {
  const d = await api.get(`/api/admin/collected-papers/${row.id}`)
  paperDetail.value = d || {}
  paperDetailOpen.value = true
}
async function removePaper(row) {
  try { await ElMessageBox.confirm(`删除采集试卷「${row.title}」？其题目将一并删除`, '提示', { type: 'warning' }) } catch { return }
  try { await api.delete(`/api/admin/collected-papers/${row.id}`); ElMessage.success('已删除'); loadPapers() }
  catch (e) { ElMessage.error(e.message) }
}

// ── 网课 ──
const courses = ref([])
const courseKw = ref('')
const courseOpen = ref(false)
const curCourse = ref({})
const courseForm = ref({ title: '', subject: '', grade: 0, video_url: '', cover_url: '', duration_min: 0, sort_order: 0, description: '', enabled: true })

async function loadCourses() {
  const params = {}
  if (courseKw.value) params.keyword = courseKw.value
  const d = await api.get('/api/admin/courses', { params })
  courses.value = (d && d.items) || []
}
function openCourse(row) {
  curCourse.value = row || {}
  courseForm.value = row
    ? { title: row.title, subject: row.subject === '不限' ? '' : row.subject, grade: row.grade, video_url: row.video_url, cover_url: row.cover_url, duration_min: row.duration_min, sort_order: row.sort_order, description: row.description, enabled: !!row.enabled }
    : { title: '', subject: '', grade: 0, video_url: '', cover_url: '', duration_min: 0, sort_order: 0, description: '', enabled: true }
  courseOpen.value = true
}
async function saveCourse() {
  saving.value = true
  try {
    if (curCourse.value.id) await api.put(`/api/admin/courses/${curCourse.value.id}`, courseForm.value)
    else await api.post('/api/admin/courses', courseForm.value)
    ElMessage.success('已保存')
    courseOpen.value = false
    loadCourses()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function removeCourse(row) {
  try { await ElMessageBox.confirm(`删除网课「${row.title}」？`, '提示', { type: 'warning' }) } catch { return }
  try { await api.delete(`/api/admin/courses/${row.id}`); ElMessage.success('已删除'); loadCourses() }
  catch (e) { ElMessage.error(e.message) }
}

function onTabChange(name) {
  if (name === 'books') { loadBooks(); loadTextbookOptions() }
  if (name === 'classicals') loadClassicals()
  if (name === 'grammar') loadGrammar()
  if (name === 'papers') loadPapers()
  if (name === 'courses') loadCourses()
}

onMounted(() => { loadBooks(); loadTextbookOptions() })
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.tip { color: #888; font-size: 13px; margin: 0 0 10px; }
</style>
