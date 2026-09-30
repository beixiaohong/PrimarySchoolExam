// logic/blog.js：内容 / Blog 视图（tab='blog'）专属的 data / computed / methods。
//
// 与 ledger.js / parent.js 同构——导出三个纯字典，由 appOptions.js 用展开运算符合并：
//   data()    { return { ...blogData(), ...其余 } }
//   computed: { ...blogComputed, ...其余 }
//   methods:  { ...blogMethods,  ...其余 }
// 展开后 this 仍绑定同一个 App 实例（App.vue provide appCtx=this），BlogView 仅 inject appCtx。
// 收尾强制校验：本文件全部键带 blog 前缀，与 appOptions 其它模块键交集必须为空。
//
// 权限口径（后端为准，前端只做按钮隐藏）：
//   读：登录用户可读全部已发布文章；草稿仅作者本人可见（后端对他人返回 404）。
//   写：仅作者本人；分类/标签的管理在后台 /admin/blog，不属于本文件。
import { renderMarkdown, plainSummary } from '../utils/markdown.js'

// ─────────── Blog data（由 appOptions.data 用 ...blogData() 合并）───────────
export function blogData() {
  return {
    blogView: 'list',        // list 列表 / detail 详情 / edit 编辑（含新建）
    blogLoading: false,
    // 列表
    blogArticles: [],
    blogTotal: 0,
    blogPage: 1,
    blogPageSize: 10,
    blogFilter: { keyword: '', category_id: '', tag_id: '', mine: false },
    // 分类 / 标签（只读，管理在后台）
    blogCats: [],
    blogTags: [],
    // 详情
    blogDetail: null,
    blogDetailHtml: '',
    // 编辑表单（editId 非空 = 编辑既有文章）
    blogForm: {
      editId: null, title: '', slug: '', summary: '', cover: '', content_md: '',
      category_id: '', tag_ids: [], status: 'draft', is_top: false, is_recommend: false,
    },
    blogPreview: false,      // 编辑器「预览」开关
  }
}

// ─────────── Blog computed ───────────
export const blogComputed = {
  // 当前详情是否为本人所写（决定「编辑/删除/发布」按钮是否出现）
  blogCanEdit() {
    const d = this.blogDetail
    return !!(d && this.user && d.author_id === this.user)
  },
  // 编辑器预览 HTML（与详情共用同一个渲染器，保证预览=最终效果）
  blogPreviewHtml() {
    return renderMarkdown(this.blogForm.content_md || '')
  },
  // 列表卡片摘要：优先 summary，缺省时从正文截一段纯文本
  blogCardSummary() {
    return a => (a && a.summary) ? a.summary : plainSummary(a && a.content_md, 60)
  },
  blogTotalPages() {
    return Math.max(1, Math.ceil((this.blogTotal || 0) / (this.blogPageSize || 10)))
  },
}

// ─────────── Blog methods ───────────
export const blogMethods = {
  /* ─────────── 基础 ─────────── */
  blogQs(extra) {
    // 统一拼 user_id（AuthClient 风格：业务接口需带；后端 require_self 校验一致）
    const qs = new URLSearchParams({ user_id: this.user })
    if (extra) for (const k of Object.keys(extra)) {
      const v = extra[k]
      if (v !== '' && v !== null && v !== undefined) qs.set(k, String(v))
    }
    return qs.toString()
  },
  blogFmtDate(s) {
    if (!s) return ''
    return String(s).slice(0, 16).replace('T', ' ')
  },
  blogCatName(id) {
    const c = (this.blogCats || []).find(x => x.id === id)
    return c ? c.name : ''
  },

  /* ─────────── 初始化 ─────────── */
  async initBlog() {
    this.blogLoading = true
    try {
      await Promise.all([this.blogLoadCats(), this.blogLoadTags()])
      if (this.blogView === 'list') await this.blogLoadList()
    } finally {
      this.blogLoading = false
    }
  },
  async blogLoadCats() {
    const d = await this.api(`/api/blog/categories?${this.blogQs()}`).catch(() => [])
    this.blogCats = d || []
  },
  async blogLoadTags() {
    const d = await this.api(`/api/blog/tags?${this.blogQs()}`).catch(() => [])
    this.blogTags = d || []
  },
  async blogLoadList() {
    this.blogLoading = true
    try {
      const f = this.blogFilter
      const d = await this.api(`/api/blog/articles?${this.blogQs({
        page: this.blogPage, page_size: this.blogPageSize,
        category_id: f.category_id, tag_id: f.tag_id, keyword: f.keyword,
        mine: f.mine ? 'true' : '',
      })}`).catch(e => { this.showToast(e.message); return null })
      if (!d) return
      this.blogArticles = d.items || []
      this.blogTotal = d.total || 0
    } finally {
      this.blogLoading = false
    }
  },
  blogGoPage(p) {
    const max = this.blogTotalPages
    this.blogPage = Math.min(Math.max(1, p), max)
    this.blogLoadList()
  },
  blogSetFilter(patch) {
    Object.assign(this.blogFilter, patch)
    this.blogPage = 1
    this.blogLoadList()
  },
  blogResetFilter() {
    this.blogFilter = { keyword: '', category_id: '', tag_id: '', mine: false }
    this.blogPage = 1
    this.blogLoadList()
  },
  blogToggleMine() {
    this.blogSetFilter({ mine: !this.blogFilter.mine })
  },

  /* ─────────── 详情 ─────────── */
  async blogOpenDetail(a) {
    const id = a && a.id
    if (!id) return
    const d = await this.api(`/api/blog/articles/${id}?${this.blogQs()}`)
      .catch(e => { this.showToast(e.message); return null })
    if (!d) return
    this.blogDetail = d
    // v-html 渲染：markdown 渲染器已先转义再解析，输出不含用户可控裸标签
    this.blogDetailHtml = renderMarkdown(d.content_md || '')
    this.blogView = 'detail'
  },
  blogBackToList() {
    this.blogDetail = null
    this.blogDetailHtml = ''
    this.blogView = 'list'
    this.blogLoadList()
  },

  /* ─────────── 编辑 / 新建 ─────────── */
  blogNewArticle() {
    this.blogForm = {
      editId: null, title: '', slug: '', summary: '', cover: '', content_md: '',
      category_id: '', tag_ids: [], status: 'draft', is_top: false, is_recommend: false,
    }
    this.blogPreview = false
    this.blogView = 'edit'
  },
  blogEditArticle(a) {
    const art = a || this.blogDetail
    if (!art) return
    this.blogForm = {
      editId: art.id,
      title: art.title || '',
      slug: art.slug || '',
      summary: art.summary || '',
      cover: art.cover || '',
      content_md: art.content_md || '',
      category_id: art.category_id ? String(art.category_id) : '',
      tag_ids: (art.tags || []).map(t => t.id),
      status: art.status || 'draft',
      is_top: !!art.is_top,
      is_recommend: !!art.is_recommend,
    }
    this.blogPreview = false
    this.blogView = 'edit'
  },
  blogToggleTag(id) {
    const arr = this.blogForm.tag_ids || []
    const i = arr.indexOf(id)
    if (i >= 0) arr.splice(i, 1); else arr.push(id)
    this.blogForm.tag_ids = arr.slice()
  },
  async blogSaveArticle(publish) {
    const f = this.blogForm
    if (!String(f.title || '').trim()) return this.showToast('请填写标题')
    const body = {
      title: String(f.title).trim(),
      slug: f.slug || null,
      summary: f.summary || null,
      cover: f.cover || null,
      content_md: f.content_md || '',
      category_id: f.category_id ? Number(f.category_id) : null,
      tag_ids: f.tag_ids || [],
      status: publish ? 'published' : (f.status || 'draft'),
      is_top: !!f.is_top,
      is_recommend: !!f.is_recommend,
    }
    const base = `/api/blog/articles${f.editId ? '/' + f.editId : ''}`
    const req = f.editId
      ? this.api(`${base}?${this.blogQs()}`, { method: 'PUT', body: JSON.stringify(body) })
      : this.api(`/api/blog/articles?${this.blogQs()}`, { method: 'POST', body: JSON.stringify(body) })
    const d = await req.catch(e => { this.showToast(e.message); return null })
    if (!d) return
    this.showToast(f.editId ? '已保存 ✅' : '已创建 ✅')
    // 保存后回详情，便于立刻点「发布」
    this.blogDetail = d
    this.blogDetailHtml = renderMarkdown(d.content_md || '')
    this.blogView = 'detail'
  },
  async blogSetPublished(published) {
    const d0 = this.blogDetail
    if (!d0) return
    const url = `/api/blog/articles/${d0.id}/${published ? 'publish' : 'unpublish'}?${this.blogQs()}`
    const d = await this.api(url, { method: 'POST' }).catch(e => { this.showToast(e.message); return null })
    if (!d) return
    this.blogDetail = d
    this.blogDetailHtml = renderMarkdown(d.content_md || '')
    this.showToast(published ? '已发布 ✅' : '已转为草稿')
  },
  async blogDeleteArticle() {
    const d0 = this.blogDetail
    if (!d0) return
    if (!confirm(`删除文章「${d0.title}」？删除后不可恢复。`)) return
    await this.api(`/api/blog/articles/${d0.id}?${this.blogQs()}`, { method: 'DELETE' })
      .then(() => {
        this.showToast('已删除')
        this.blogBackToList()
      })
      .catch(e => this.showToast(e.message))
  },
}
