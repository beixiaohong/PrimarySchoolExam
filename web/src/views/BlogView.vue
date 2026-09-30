<template>
  <!-- 内容 / Blog（tab='blog'）：内容型前台页面（非后台管理页）。
       三个内部视图：list 列表 / detail 详情 / edit 编辑。
       状态与方法全在 logic/blog.js（经 appOptions 合并进 App 壳），本视图仅 inject appCtx。 -->
  <div class="fade-enter">
    <div class="card blog-card">

      <!-- ─────────── 列表视图 ─────────── -->
      <template v-if="appCtx.blogView === 'list'">
        <div class="card-head">
          <!-- blog.md §36：进入任意模块后都能方便地回到工作台 -->
          <button class="btn btn-ghost btn-sm" @click="appCtx.goTab('workspace')">← 工作台</button>
          <b><app-icon name="blog" :size="18"></app-icon> 内容</b>
          <span class="more">{{ appCtx.blogTotal }} 篇</span>
          <button class="btn btn-primary btn-sm" @click="appCtx.blogNewArticle()">✍️ 写文章</button>
        </div>

        <!-- 搜索 + 我的切换 -->
        <div class="blg-search">
          <input v-model="appCtx.blogFilter.keyword" class="fill-input" maxlength="50"
                 placeholder="搜索标题 / 摘要 / 正文" @keyup.enter="appCtx.blogSetFilter({})">
          <button class="btn btn-primary btn-sm" @click="appCtx.blogSetFilter({})">搜索</button>
          <button class="btn btn-ghost btn-sm" @click="appCtx.blogResetFilter()">重置</button>
          <button class="btn btn-ghost btn-sm" :class="{ 'blg-on': appCtx.blogFilter.mine }"
                  @click="appCtx.blogToggleMine()">{{ appCtx.blogFilter.mine ? '✓ 我的' : '我的' }}</button>
        </div>

        <!-- 分类 / 标签筛选 -->
        <div class="blg-filters">
          <select v-model="appCtx.blogFilter.category_id" class="fill-input blg-sel"
                  @change="appCtx.blogSetFilter({})">
            <option value="">全部分类</option>
            <option v-for="c in appCtx.blogCats" :key="'bc' + c.id" :value="String(c.id)">{{ c.name }}</option>
          </select>
          <button class="blg-chip" :class="{ 'blg-chip-on': !appCtx.blogFilter.tag_id }"
                  @click="appCtx.blogSetFilter({ tag_id: '' })">全部标签</button>
          <button v-for="t in appCtx.blogTags" :key="'bt' + t.id" class="blg-chip"
                  :class="{ 'blg-chip-on': String(appCtx.blogFilter.tag_id) === String(t.id) }"
                  @click="appCtx.blogSetFilter({ tag_id: String(t.id) })">{{ t.name }}</button>
        </div>

        <!-- 推荐 / 热门（blog.md §14.2；仅在无筛选时展示，避免与筛选结果混淆） -->
        <div v-if="!appCtx.blogHasFilter" class="blg-featured">
          <div v-if="appCtx.blogRecommended.length" class="blg-feat">
            <div class="blg-feat-title">⭐ 推荐内容</div>
            <div v-for="a in appCtx.blogRecommended" :key="'br' + a.id" class="blg-feat-item"
                 @click="appCtx.blogOpenDetail(a)">
              <b>{{ a.title }}</b>
              <span v-if="a.category_name" class="blg-cat">{{ a.category_name }}</span>
            </div>
          </div>
          <div v-if="appCtx.blogHot.length" class="blg-feat">
            <div class="blg-feat-title">🔥 热门内容</div>
            <div v-for="a in appCtx.blogHot" :key="'bh' + a.id" class="blg-feat-item"
                 @click="appCtx.blogOpenDetail(a)">
              <b>{{ a.title }}</b>
              <span class="blg-views">👁 {{ a.view_count }}</span>
            </div>
          </div>
        </div>

        <div v-if="appCtx.blogLoading" class="blg-empty">🔄 加载中…</div>
        <div v-else-if="!appCtx.blogArticles.length" class="blg-empty">
          <p>还没有文章</p>
          <button class="btn btn-primary btn-sm" @click="appCtx.blogNewArticle()">写第一篇 ✍️</button>
        </div>

        <div v-else class="blg-list">
          <div v-for="a in appCtx.blogArticles" :key="'ba' + a.id" class="blg-item"
               @click="appCtx.blogOpenDetail(a)">
            <div v-if="a.cover" class="blg-cover" :style="{ backgroundImage: 'url(' + a.cover + ')' }"></div>
            <div class="blg-main">
              <div class="blg-title-row">
                <i v-if="a.is_top" class="blg-badge top">置顶</i>
                <i v-if="a.is_recommend" class="blg-badge rec">推荐</i>
                <i v-if="a.status !== 'published'" class="blg-badge draft">草稿</i>
                <b class="blg-title">{{ a.title }}</b>
              </div>
              <p class="blg-sum">{{ appCtx.blogCardSummary(a) }}</p>
              <div class="blg-meta">
                <span v-if="a.category_name" class="blg-cat">{{ a.category_name }}</span>
                <span v-for="t in a.tags" :key="'it' + t.id" class="blg-tag">#{{ t.name }}</span>
                <span class="blg-time">{{ appCtx.blogFmtDate(a.published_at || a.created_at) }}</span>
                <span class="blg-views">👁 {{ a.view_count }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div v-if="appCtx.blogTotalPages > 1" class="blg-pager">
          <button class="btn btn-ghost btn-sm" :disabled="appCtx.blogPage <= 1"
                  @click="appCtx.blogGoPage(appCtx.blogPage - 1)">‹ 上一页</button>
          <span class="blg-page">{{ appCtx.blogPage }} / {{ appCtx.blogTotalPages }}</span>
          <button class="btn btn-ghost btn-sm" :disabled="appCtx.blogPage >= appCtx.blogTotalPages"
                  @click="appCtx.blogGoPage(appCtx.blogPage + 1)">下一页 ›</button>
        </div>
      </template>

      <!-- ─────────── 详情视图 ─────────── -->
      <template v-else-if="appCtx.blogView === 'detail' && appCtx.blogDetail">
        <div class="card-head">
          <button class="btn btn-ghost btn-sm" @click="appCtx.blogBackToList()">‹ 返回列表</button>
          <span class="more">{{ appCtx.blogFmtDate(appCtx.blogDetail.published_at || appCtx.blogDetail.created_at) }}</span>
        </div>
        <div class="blg-detail">
          <h2 class="blg-detail-title">{{ appCtx.blogDetail.title }}</h2>
          <div class="blg-meta">
            <span v-if="appCtx.blogDetail.category_name" class="blg-cat">{{ appCtx.blogDetail.category_name }}</span>
            <span v-for="t in appCtx.blogDetail.tags" :key="'dt' + t.id" class="blg-tag">#{{ t.name }}</span>
            <span class="blg-views">👁 {{ appCtx.blogDetail.view_count }}</span>
            <span class="blg-author">作者 {{ appCtx.blogDetail.author_id }}</span>
          </div>
          <div v-if="appCtx.blogDetail.cover" class="blg-detail-cover">
            <img :src="appCtx.blogDetail.cover" :alt="appCtx.blogDetail.title">
          </div>
          <!-- Markdown 渲染结果：先转义再解析，无用户可控裸标签。
               注意：v-html 产出的节点不带 scoped 属性，样式必须用 :deep()（见 style 段）。 -->
          <div class="blg-md" v-html="appCtx.blogDetailHtml"></div>
          <div v-if="appCtx.blogCanEdit" class="blg-detail-ops">
            <button class="btn btn-ghost btn-sm" @click="appCtx.blogEditArticle()">✎ 编辑</button>
            <button v-if="appCtx.blogDetail.status === 'published'" class="btn btn-ghost btn-sm"
                    @click="appCtx.blogSetPublished(false)">转为草稿</button>
            <button v-else class="btn btn-primary btn-sm" @click="appCtx.blogSetPublished(true)">🚀 发布</button>
            <button class="btn btn-ghost btn-sm blg-del" @click="appCtx.blogDeleteArticle()">🗑 删除</button>
          </div>
        </div>
      </template>

      <!-- ─────────── 编辑视图 ─────────── -->
      <template v-else-if="appCtx.blogView === 'edit'">
        <div class="card-head">
          <b>{{ appCtx.blogForm.editId ? '编辑文章' : '写文章' }}</b>
          <span class="more">Markdown 语法</span>
        </div>
        <div class="blg-edit">
          <div class="blg-field">
            <label class="blg-label">标题 <i class="blg-req">*</i></label>
            <input v-model="appCtx.blogForm.title" class="fill-input" maxlength="200" placeholder="文章标题">
          </div>
          <div class="blg-row">
            <div class="blg-field">
              <label class="blg-label">分类</label>
              <select v-model="appCtx.blogForm.category_id" class="fill-input">
                <option value="">（不选）</option>
                <option v-for="c in appCtx.blogCats" :key="'ec' + c.id" :value="String(c.id)">{{ c.name }}</option>
              </select>
            </div>
            <div class="blg-field">
              <label class="blg-label">封面 URL</label>
              <input v-model="appCtx.blogForm.cover" class="fill-input" placeholder="可空">
            </div>
          </div>
          <div class="blg-field">
            <label class="blg-label">标签（可多选）</label>
            <div class="blg-tags">
              <button v-for="t in appCtx.blogTags" :key="'et' + t.id" class="blg-chip"
                      :class="{ 'blg-chip-on': appCtx.blogForm.tag_ids.indexOf(t.id) >= 0 }"
                      @click="appCtx.blogToggleTag(t.id)">{{ t.name }}</button>
              <span v-if="!appCtx.blogTags.length" class="blg-hint">还没有标签，需后台创建</span>
            </div>
          </div>
          <div class="blg-field">
            <label class="blg-label">摘要</label>
            <input v-model="appCtx.blogForm.summary" class="fill-input" maxlength="200" placeholder="可空，缺省自动取正文开头">
          </div>
          <div class="blg-field">
            <label class="blg-label">
              正文（Markdown）
              <button class="blg-mini" @click="appCtx.blogPreview = !appCtx.blogPreview">
                {{ appCtx.blogPreview ? '继续编辑' : '👁 预览' }}
              </button>
            </label>
            <textarea v-if="!appCtx.blogPreview" v-model="appCtx.blogForm.content_md"
                      class="fill-input blg-md-input" rows="14"
                      placeholder="支持 # 标题、**粗体**、- 列表、```代码块```、[链接](url)"></textarea>
            <div v-else class="blg-md blg-md-preview" v-html="appCtx.blogPreviewHtml"></div>
          </div>
          <label class="blg-check"><input type="checkbox" v-model="appCtx.blogForm.is_top"> 置顶</label>
          <label class="blg-check"><input type="checkbox" v-model="appCtx.blogForm.is_recommend"> 推荐</label>
          <div class="blg-edit-ops">
            <button class="btn btn-ghost btn-sm" @click="appCtx.blogBackToList()">取消</button>
            <button class="btn btn-ghost btn-sm" @click="appCtx.blogSaveArticle(false)">💾 保存草稿</button>
            <button class="btn btn-primary btn-sm" @click="appCtx.blogSaveArticle(true)">🚀 发布</button>
          </div>
        </div>
      </template>

    </div>
  </div>
</template>

<script>
// 内容 / Blog（tab='blog'）。纯模板组件：仅 inject appCtx，无自身业务 data/methods。
export default {
  name: 'BlogView',
  inject: ['appCtx'],
}
</script>

<style scoped>
.blog-card { max-width: 860px; }
.blog-card .card-head b { display: inline-flex; align-items: center; gap: 6px; }
.blog-card .card-head .more { flex: 1; }
/* 搜索 / 筛选 */
.blg-search { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.blg-search .fill-input { flex: 1; min-width: 160px; }
.blg-on { border-color: #8b7cf6; color: #8b7cf6; }
.blg-filters { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.blg-sel { max-width: 160px; }
.blg-chip { border: 1px solid #e5e1f5; background: #fff; color: #5a5470; border-radius: 999px; padding: 3px 11px; font-size: 12px; cursor: pointer; }
.blg-chip-on { background: #8b7cf6; border-color: #8b7cf6; color: #fff; }
.blg-hint { font-size: 12px; color: #a8a3b8; }
/* 推荐 / 热门 */
.blg-featured { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-bottom: 14px; }
.blg-feat { border: 1px solid #efedf7; border-radius: 12px; padding: 10px 12px; }
.blg-feat-title { font-size: 13px; color: #5a5470; margin-bottom: 6px; }
.blg-feat-item { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-top: 1px dashed #f4f2fa; cursor: pointer; }
.blg-feat-item:first-of-type { border-top: none; }
.blg-feat-item:hover { background: #f9f8fd; border-radius: 6px; }
.blg-feat-item b { flex: 1; font-size: 13px; color: #3b3555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
/* 列表 */
.blg-empty { text-align: center; color: #999; padding: 36px 0; font-size: 14px; }
.blg-empty p { margin: 0 0 12px; }
.blg-list { display: flex; flex-direction: column; gap: 10px; }
.blg-item { display: flex; gap: 12px; padding: 10px; border: 1px solid #efedf7; border-radius: 12px; cursor: pointer; transition: background .12s, border-color .12s; }
.blg-item:hover { background: #f9f8fd; border-color: #ddd6f5; }
.blg-cover { flex: none; width: 96px; height: 68px; border-radius: 8px; background-size: cover; background-position: center; background-color: #f1eff8; }
.blg-main { flex: 1; min-width: 0; }
.blg-title-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.blg-title { font-size: 15px; color: #3b3555; }
.blg-badge { font-style: normal; font-size: 10.5px; border-radius: 5px; padding: 1px 5px; }
.blg-badge.top { background: #eef0fd; color: #5b4bc4; }
.blg-badge.rec { background: #fdeee4; color: #c0703a; }
.blg-badge.draft { background: #f1eff8; color: #8a8fa3; }
.blg-sum { margin: 4px 0 6px; font-size: 12.5px; color: #8a8fa3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.blg-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11.5px; color: #a8a3b8; }
.blg-cat { color: #5b4bc4; background: #f3f0fe; border-radius: 5px; padding: 1px 6px; }
.blg-tag { color: #8a8fa3; }
.blg-views { margin-left: auto; }
.blg-author { color: #a8a3b8; }
/* 分页 */
.blg-pager { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 14px; }
.blg-page { font-size: 12.5px; color: #8a8fa3; }
/* 详情 */
.blg-detail { padding: 4px 2px; }
.blg-detail-title { font-size: 20px; color: #3b3555; margin: 6px 0 8px; }
.blg-detail-cover { margin: 10px 0; }
.blg-detail-cover img { max-width: 100%; border-radius: 10px; }
.blg-detail-ops { display: flex; gap: 8px; margin-top: 18px; padding-top: 12px; border-top: 1px dashed #efedf7; flex-wrap: wrap; }
.blg-del { color: #c0392b; }
/* 编辑 */
.blg-edit { padding: 2px 0; }
.blg-field { margin-bottom: 12px; }
.blg-label { display: block; font-size: 12px; color: #8a8fa3; margin-bottom: 4px; }
.blg-req { color: #e57373; font-style: normal; }
.blg-row { display: grid; grid-template-columns: 1fr 2fr; gap: 12px; }
.blg-tags { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.blg-md-input { font-family: Consolas, Menlo, monospace; font-size: 13px; line-height: 1.6; resize: vertical; }
.blg-md-preview { min-height: 160px; border: 1px solid #efedf7; border-radius: 10px; padding: 12px; }
.blg-mini { border: 1px solid #e5e1f5; background: #fff; color: #5b4bc4; border-radius: 6px; font-size: 11px; padding: 1px 7px; cursor: pointer; margin-left: 8px; }
.blg-check { display: inline-flex; align-items: center; gap: 5px; font-size: 13px; color: #5a5470; margin-right: 16px; }
.blg-edit-ops { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; flex-wrap: wrap; }

/* Markdown 正文：v-html 产出的节点没有 data-v-xxx，
   scoped 编译后形如 .blg-md .md-h[data-v-x] 的规则一条都匹配不上，
   因此「作用于 v-html 内容的后代选择器必须 :deep()」。 */
.blg-md :deep(.md-h) { color: #3b3555; margin: 18px 0 8px; line-height: 1.35; }
.blg-md :deep(.md-h1) { font-size: 20px; }
.blg-md :deep(.md-h2) { font-size: 17px; }
.blg-md :deep(.md-h3) { font-size: 15px; }
.blg-md :deep(.md-h4) { font-size: 14px; }
.blg-md :deep(.md-p) { font-size: 14px; line-height: 1.8; color: #4a4463; margin: 0 0 12px; }
.blg-md :deep(.md-ul), .blg-md :deep(.md-ol) { margin: 0 0 12px; padding-left: 22px; font-size: 14px; line-height: 1.8; color: #4a4463; }
.blg-md :deep(.md-quote) { margin: 0 0 12px; padding: 8px 12px; border-left: 3px solid #d9d0fb; background: #f9f8fd; color: #6b6584; font-size: 13.5px; }
.blg-md :deep(.md-pre) { background: #f6f5fb; border: 1px solid #efedf7; border-radius: 8px; padding: 10px 12px; overflow-x: auto; margin: 0 0 12px; }
.blg-md :deep(.md-pre code) { font-family: Consolas, Menlo, monospace; font-size: 12.5px; color: #4a4463; }
.blg-md :deep(.md-code) { background: #f1eff8; border-radius: 4px; padding: 1px 5px; font-size: 13px; color: #c0392b; }
.blg-md :deep(.md-img) { max-width: 100%; border-radius: 8px; margin: 8px 0; }
.blg-md :deep(.md-hr) { border: none; border-top: 1px solid #efedf7; margin: 16px 0; }
.blg-md :deep(a) { color: #5b4bc4; }
@media (max-width: 640px) {
  .blg-row { grid-template-columns: 1fr; }
  .blg-cover { width: 72px; height: 54px; }
}
</style>
