# Blog 与 Workspace（首页）设计方案

> 需求来源：`temp/blog.md`（62 节，含「AI 在编码前必须输出 A–G 分析报告」的硬性要求）。
> 本文即该报告，也是实施蓝图。**编码前需用户确认「六、待确认决策」**。
> 最高原则：增量开发、最小修改、不重写、不破坏现有四个系统。

---

## 一、A. 当前架构（实测，非假设）

| 项 | 实际情况 |
|---|---|
| 前端 | Vue 3（Options API 单体 `App.vue`）+ vue-router **hash 模式**（`/#/tab`）；业务按模块拆 `views/*.vue` + `logic/*.js`（`appOptions.js` 展开合并） |
| 后端 | FastAPI；**九域分层** `app/domains/{identity,content,assessment,engine,engagement,family,commerce,platform,frozen}` |
| 数据库 | MySQL-only；表命名两种：`users`（历史）与 `db_<模块>_<实体>`（新模块，如 `db_ledger_books`、`db_novels`） |
| ORM | SQLAlchemy  declarative（`app/models/*.py`，按实体分文件，**非**单 models.py） |
| 认证 | Bearer token 会话制。`require_user`（登录）/ `require_self`（严格账号绑定，query 或 body 取 user_id）/ `_require_admin`（后台 Admin 表，TTL 12h） |
| 权限 | 无独立 RBAC 表；靠「登录态 + 账号绑定 + 后台 admin 会话」三档 |
| API | `app/main.py` 统一 `include_router(prefix="/api/xxx", dependencies=user_auth_deps)`；Pydantic schema 在 `app/schemas/*.py`（按模块分文件） |
| 迁移 | **自研 runner**（非 Alembic）：`app/migrations/versions/NNN_*.py`，约定 `upgrade(db)`；现最新 `088`，本次新增 `089` |
| 架构护栏 | `.importlinter`：九域独立（跨域只经 `contracts.py`）+ D9 frozen 禁被 D1–D8 import |
| UI | 无组件库；图标 `AppIcon.vue` 内联 SVG（`nav.js` 引用名需在其中定义） |
| Markdown | **项目当前没有任何 markdown 依赖**（requirements.txt 无） |

## 二、B. 现有模块位置

| blog.md 所指模块 | 本项目实际落点 |
|---|---|
| 学生答题 | tab `practice`/`wrong`/`papers`/`exam`；后端 `/api/exam`、`/api/study`、`/api/math`；域 `assessment` |
| 账本 | tab `ledger`；后端 `/api/ledger`；域 **D9 `frozen`**（冻结域）；前端 `views/LedgerView.vue` + `logic/ledger.js` |
| 聊天 | tab `im`；后端 `/api/im`（WebSocket）；域 **D9 `frozen`**；前端 `logic/im.js` |
| 高项学习 | tab `gaoxiang`（不对普通用户展示导航，设置页连点 5 次或 URL 直达）；后端 `/api/gx` |
| **内容 / Blog** | **不存在，本次新增** |
| Workspace / 应用中心 | **不存在**；当前默认首页是 tab `home`（今日学习，`HomeView.vue`） |

> ⚠️ **关键冲突**：`app/domains/content` 已存在，且是「学习内容」域
> （`routers/{courses,grammar,knowledge,novel,phrases,reading,textbook,words}.py`）。
> 因此**不能**再建一个叫 `content` 的域。blog.md §5/§27.1 亦明确「实际实现必须遵循现有项目命名规范」
> 「不要为了符合示意图强制迁移/重命名」→ **代码与路由用 `blog`，平台导航中文名用「内容」**。

## 三、C. Workspace 接入方案

| 问题 | 方案 |
|---|---|
| 现有默认首页 | `/#/home`（`HomeView.vue` 今日学习）。router 里 `/` → `/home` |
| 如何接入 `/workspace` | 新增前端 tab `workspace`；router 的通配 `/:tab` 已天然支持，无需改 router |
| 登录后跳转 | **待确认 D1**：改默认落地页为 `/workspace`，或保留 `/home` |
| 旧首页是否保留 | **保留**，`home` 仍是完整页面，可从工作台进入 |
| 顶部导航如何接入 | 侧边栏 `nav.js` 新增「工作台」「应用中心」「内容」三项；各业务模块页提供「← 工作台」返回 |
| 应用中心 | 新增 tab `apps` + `web/src/apps.js` 模块注册表（key/name/desc/icon/tab/enabled），**禁止在 Vue 页面里硬编码五宫格**（blog.md §8.1） |
| 常用应用 / 最近使用 | **待确认 D3**：阶段一用 localStorage 记录访问次数与最近时间；或后端建表 |
| 数据摘要 | 只复用**已有**接口（账本 `statistics/summary`、学习 `/api/study/dashboard/today`），**不为首页改任何业务模块**（blog.md §32） |

Workspace 后端聚合端点放 `app/domains/platform/routers/workspace.py`（D8 已是平台层，不是业务域），
只经各域 `contracts.py` 取数，**不直接查业务表**（blog.md §11）。

## 四、D. 内容 / Blog 模块方案

**新增文件**
- 后端：`app/domains/blog/{__init__,contracts}.py`、`routers/{articles,categories,tags}.py`、`services/*.py`；`app/models/blog.py`；`app/schemas/blog.py`；`app/routers/admin/blog.py`（后台）
- 迁移：`app/migrations/versions/089_blog_init.py`
- 前端：`views/BlogView.vue`（前台首页/列表/详情/搜索）、`components/blog/*`、`logic/blog.js`；`views/WorkspaceView.vue` + `logic/workspace.js`；`views/AppsView.vue`；`apps.js`

**新增表**（`db_blog_` 前缀，仅新增不动存量）
```
db_blog_articles      id/title/slug/summary/cover/content_md/author_id/category_id/
                      status(draft|published)/is_top/is_recommend/view_count/
                      created_at/updated_at/published_at
db_blog_categories    id/name/slug/sort_order/description
db_blog_tags          id/name/slug
db_blog_article_tags  article_id/tag_id（多对多）
```
阶段一**不做**评论/收藏/关注/RSS/ES（blog.md §25.1、§39）。

**新增 API**（`/api/blog`，沿用现有 include_router + require_user）
```
GET  /api/blog/articles        列表（分页/分类/标签/状态/关键词）
GET  /api/blog/articles/{id}   详情（并自增 view_count）
POST /api/blog/articles        新建（作者=当前登录用户）
PUT  /api/blog/articles/{id}   编辑（仅作者本人或 admin）
DELETE /api/blog/articles/{id}
POST /api/blog/articles/{id}/publish | /unpublish
GET/POST/PUT/DELETE /api/blog/categories
GET/POST/PUT/DELETE /api/blog/tags
GET  /api/blog/latest          轻量聚合（供 Workspace「最新内容」）
```
后台 `/api/admin/blog/*` 走 `app/routers/admin/blog.py`（复用共享 `router` + admin 鉴权），
内部只经 `app.domains.blog.contracts` 访问。

**权限**（复用现有三档，不新建 BlogPermission/BlogRole）
- 前台只读：`require_user`
- 作者管理自己的文章：后端校验 `author_id == 当前用户`，否则 403
- 全量管理（含分类/标签）：`_require_admin`
- 前端只做按钮隐藏，**判定以后端为准**

**Markdown**：项目无 markdown 依赖且不宜新增（requirements 铁律 + §55 反新框架）→ 自研极简渲染器
（标题/粗斜体/行内代码/代码块/列表/链接/图片/段落），编辑预览与详情共用。**待确认 D4**。

## 五、E. 复用情况

| 能力 | 复用对象 |
|---|---|
| 用户表 | `users`（`app/models/user.py`），`author_id → users.user_id`，**不复制用户信息**、**不新建用户表** |
| 认证 | `require_user` / `require_self` / `_require_admin` 原样复用 |
| 数据库 | `app.database.get_db` / `Base`，**同一 MySQL、同一连接池** |
| 迁移 | 自研 runner + `Base.metadata.create_all(bind=engine, tables=[...])` 幂等写法（照抄 085） |
| 分页 | `app/core/pagination.py`（若已有则复用；否则沿用 ledger 的 skip/limit） |
| 异常/响应 | 现有 `HTTPException` + 统一错误信封中间件，**不建第二套** |
| 前端骨架 | `App.vue` tab 机制、`nav.js`、`AppIcon.vue`、`api()` 封装、`showToast()` |
| 编辑器 | 无现成富文本/Markdown 编辑器可复用 → 自研极简（见 D4） |
| 首页摘要接口 | 直接调已有 `/api/study/dashboard/today`、`/api/ledger/.../statistics/summary` |

## 六、待确认决策（编码前需拍板）

| # | 决策 | 推荐 | 理由 |
|---|---|---|---|
| D1 | 登录后默认落地页 | **改为 `/workspace`**（保留 `/#/home` 直达） | blog.md §51.1 要求；`/home` 仍可从工作台进入，回归可控 |
| D2 | Blog 域归属 | **新建 `app/domains/blog`（第 10 域）** | `content` 已被学习内容占用；独立域符合 §12.5「Blog 不是任何模块的子功能」。代价：`.importlinter` 加 2 行 |
| D3 | 常用应用/最近使用 存储 | **localStorage（阶段一）** | 无迁移风险、无新表；blog.md §9 明确最近使用不是阻塞项 |
| D4 | Markdown 渲染 | **自研极简渲染器** | 项目无依赖且新增依赖有启动期 502 风险（requirements 铁律） |
| D5 | 后台管理入口 | **`/admin/blog`（复用 admin 共享 router）** | 符合现有后台子模块范式 |

## 七、F. 修改范围

**新增**（约 20 个文件）：见「四、D」
**修改**（仅 5 个，且都是加行不改逻辑）
1. `app/main.py` — 2 行：`include_router(blog..., prefix="/api/blog")`；admin blog 由 `app/routers/admin/__init__.py` 注册
2. `app/routers/admin/__init__.py` — 1–2 行：import + `from .blog import *`
3. `.importlinter` — 2 行：把 `app.domains.blog` 加入契约 1 的 modules 与契约 2 的 source_modules
4. `web/src/nav.js` — 新增 3 个导航项 + `AppIcon` 图标
5. `web/src/App.vue` — 3 个 `v-if` 挂载新视图（不改任何现有 v-if）
6. `web/src/router/index.js` — 仅当 D1 选「改落地页」时改 1 行 redirect

**明确不修改**：`frozen`（账本/IM）、`assessment`、`content`、`gaoxiang` 的任何业务逻辑；
用户/认证/权限体系；现有表结构；`HomeView.vue` 内部逻辑。

## 八、G. 风险与对策

| 风险 | 对策 |
|---|---|
| 路由冲突 | 已核实：全仓无 `blog` 命名，无 `/api/blog`，无 `blog` tab ✅ |
| 登录跳转影响（D1） | 保留 `/home` 直达与导航入口；仅在 router 改 1 行 redirect，可 1 行回退 |
| 新增域破坏 import-linter | `blog` 域不 import 任何业务域内部，只经 `contracts.py`；改完立即跑 `lint-imports` 验证 2 kept / 0 broken |
| 数据库迁移风险 | 只 `create_all` 新增 4 张表，**不改任何存量表/列**；幂等可重跑 |
| 前端键名冲突 | `logic/blog.js` 全部键加 `blog` 前缀，与 `appOptions` 现有键做交集校验（沿用账本约定） |
| Markdown XSS | 自研渲染器先做 HTML 转义再解析，不输出裸 HTML |
| 现有四系统回归 | 收尾跑全量：`regression_check.py` 7 项 + `lint-imports` + `pytest` + `web` 构建 |

## 九、实施顺序（blog.md §45 的十一阶段压缩为六批，每批验证后再进下一批）

1. **后端骨架**：`app/models/blog.py` + `app/schemas/blog.py` + 迁移 `089` + `blog` 域骨架 + `.importlinter` 2 行 → 跑 lint + migration 冒烟
2. **后端 API**：articles / categories / tags CRUD + publish/unpublish + latest → 补 `tests/test_blog_web.py`
3. **后台**：`app/routers/admin/blog.py`（文章/分类/标签管理）
4. **前端 Blog**：`logic/blog.js` + `BlogView.vue` + 组件（列表/详情/编辑/搜索/分类/标签）
5. **前端 Workspace + 应用中心**：`apps.js` + `AppsView.vue` + `WorkspaceView.vue` + `logic/workspace.js`
6. **导航接入 + 全量回归**：`nav.js` / `App.vue` / router redirect → 七项自检 + pytest + 构建 + 提交
