# 智学学堂 · 项目结构与工作量评估

> 最后更新：2026-08-11

---

## 一、技术栈概览

| 层 | 技术 | 说明 |
|---|---|---|
| 后端框架 | FastAPI + Uvicorn | Python 3.12，ASGI 异步服务，31 个路由模块 |
| 数据库 | MySQL 8（生产 utf8mb4）/ SQLite（开发） | SQLAlchemy 2.0 ORM + 自建迁移系统（28 个版本脚本，MySQL 基线策略见下） |
| 前端 | Vue 3 + Vite 工程化（web/） | SPA，构建产物 web/dist 由后端托管；frontend/ 旧版已废弃 |
| AI 接入 | 智谱 GLM / DeepSeek | 多供应商 fallback，按 token 扣钻石 |
| 文档生成 | python-docx + matplotlib + edge-tts | 试卷 Word、数学图形、TTS 音频 |
| 测试 | pytest + FastAPI TestClient | tests/ 目录 48 个回归用例，临时 SQLite 隔离 |

---

## 二、完整文件清单与说明

### 根目录

```
run.py                          # 启动入口（uvicorn 启动 FastAPI）
requirements.txt                # Python 依赖清单
.env.example                    # 环境变量模板（AI API Key 等）
.gitignore                      # Git 忽略规则
primary_school.db               # SQLite 数据库文件（运行后自动生成）
README.md                       # 项目简介与启动说明
DEPLOY.md                       # 服务器部署指南（Nginx + systemd）
deploy.sh                       # 一键部署脚本（Ubuntu/CentOS）
PROJECT_STRUCTURE.md            # 本文件
```

### app/ — 后端主包

```
app/__init__.py                 # 包标识
app/main.py                     # FastAPI 应用工厂：注册 28 个路由、lifespan 启动流程
app/config.py                   # 全局配置：数据库路径、输出目录、默认参数
app/database.py                 # SQLAlchemy 引擎、会话工厂、Base 声明、init_db()
```

### app/models/ — 数据模型（21 个文件）

```
app/models/__init__.py          # 统一导出所有模型
app/models/user.py              # User — 用户档案（用户名即标识，年级/学科/连续登录）
app/models/word.py              # WordBook + Word — 英语单词库（按年级/单元分组）
app/models/phrase.py            # Phrase + Sentence — 英语词组与句子
app/models/problem_type.py      # ProblemCategory + ProblemType — 数学题型分类树
app/models/exam.py              # ExamRecord/Question/WrongRecord/ExamAttempt/AttemptAnswer — 试卷与错题
app/models/vocab.py             # VocabProgress + VocabDailyLog — 背单词进度（艾宾浩斯曲线）
app/models/classical.py         # ClassicalText + ClassicalProgress + ClassicalDailyLog — 古诗文背诵
app/models/grammar.py           # GrammarPoint + GrammarExercise — 英语语法知识点与练习
app/models/study_error.py       # StudyError — 学习模块错题（背诵/语法/听写，独立于试卷错题）
app/models/daily_task.py        # DailyTask — 每日任务（三科，家长可配置目标数）
app/models/ai_usage.py          # AIUsageLog + WeeklyReport + AiQa — AI 用量/周报/问答缓存
app/models/mood.py              # MoodCheckin — 心情打卡
app/models/reward.py            # RewardCoupon + WishItem + GoalItem — 奖励券/心愿/目标
app/models/sprint4.py           # ChallengeRecord + TeachingRecord — 挑战赛/小老师记录
app/models/parent.py            # ParentPassword + ExamMinCount + ParentMessage — 家长管理
app/models/appeal.py            # AnswerAppeal — 答题申诉（孩子提交 → 家长审核）
app/models/pet.py               # CoinLedger + PetProfile — 金币流水 + 虚拟宠物
app/models/badge.py             # BadgeEarned — 成就徽章墙
app/models/focus.py             # FocusSession — 番茄专注钟记录
app/models/diamond.py           # DiamondAccount + DiamondLedger — 钻石余额与明细（AI 扣费）
```

### app/schemas/ — Pydantic 请求/响应模型

```
app/schemas/__init__.py
app/schemas/exam.py             # 试卷创建、题目输出、错题输出等 Schema
app/schemas/phrase.py           # 词组/句子 CRUD Schema
app/schemas/problem.py          # 题型管理、数学题目生成 Schema
app/schemas/vocab.py            # 单词学习/复习/统计 Schema
app/schemas/word.py             # 单词/词书 CRUD + 导入 Schema
```

### app/routers/ — API 路由（28 个文件）

```
app/routers/__init__.py
app/routers/user.py             # /api/user — 登录/年级更新/称号系统/自动升年级
app/routers/words.py            # /api/words — 英语单词 CRUD + CSV/Excel 导入
app/routers/phrases.py          # /api/english — 词组与句子管理
app/routers/math.py             # /api/math — 题型管理 + 题目生成
app/routers/exam.py             # /api/exam — 试卷生成/下载/做题/错题本/做题记录
app/routers/vocab.py            # /api/vocab — 背单词（艾宾浩斯新学+复习+统计）
app/routers/classical.py        # /api/classical — 古诗文背诵（艾宾浩斯+默写生成）
app/routers/grammar.py          # /api/grammar — 英语语法练习与统计
app/routers/study.py            # /api/study — 今日任务总览/错题分析/重试/自比较
app/routers/tasks.py            # /api/tasks — 每日任务池（含昨日错题复习）
app/routers/ai.py               # /api/ai — AI 讲解/周报/鼓励（钻石扣费）
app/routers/qa.py               # /api/qa — 十万个为什么（AI 问答+缓存+多轮对话）
app/routers/mood.py             # /api/mood — 心情打卡与趋势预警
app/routers/rewards.py          # /api/rewards — 家长发券/孩子心愿/成长周报
app/routers/challenge.py        # /api/challenge — 60 秒限时挑战赛
app/routers/teach.py            # /api/teach — 小老师模式（孩子讲题给家长）
app/routers/goals.py            # /api/goals — 学期目标倒计时
app/routers/parent.py           # /api/parent — 家长面板（密码/留言/设置/数据）
app/routers/appeal.py           # /api/appeal — 答题申诉（AI 复核 + 家长确认）
app/routers/pet.py              # /api/pet — 金币宠物（喂养/升级/流水）
app/routers/tree.py             # /api/tree — 成长树可视化
app/routers/badges.py           # /api/badges — 成就徽章（13+ 种）
app/routers/cards.py            # /api/cards — 知识卡图鉴收集
app/routers/dictation.py        # /api/dictation — 听写磨耳朵（TTS + 拼写校验）
app/routers/focus.py            # /api/focus — 番茄专注钟
app/routers/ai_quiz.py          # /api/ai-quiz — AI 趣味出题（主题化）
app/routers/assistant.py        # /api/assistant — AI 学习助手（个性化对话）
app/routers/diamond.py          # /api/diamond — 钻石余额/增减/全量发放/明细查询
```

### app/services/ — 业务逻辑层（12 个文件）

```
app/services/__init__.py
app/services/ai.py              # 多供应商 AI 路由（智谱免费 → Relay 备用 → DeepSeek 付费）
app/services/answer_check.py    # 填空题答案容错判断（数学表达式解析）
app/services/audio_renderer.py  # edge-tts 语音合成
app/services/chinese_generator.py # 语文出题器（6 种题型：拼音/笔顺/组词/造句/修辞/阅读）
app/services/diamond.py         # 钻石余额/扣费/充值服务（1 万 token = 1 钻石）
app/services/docx_service.py    # Word 试卷文档生成（A4 排版/信息栏/分类标题）
app/services/english_generator.py # 英语出题器（10 种题型）
app/services/figure_renderer.py # matplotlib 数学图形生成
app/services/init_data.py       # 种子数据初始化（题型/单词/词组/古诗文）
app/services/judge.py           # AI 答案复核/重判服务
app/services/math_generator.py  # 数学出题器（24+ 题型，注册表模式 @register）
```

### app/migrations/ — 数据库迁移系统

```
app/migrations/__init__.py
app/migrations/runner.py        # 迁移执行器（启动时自动运行，幂等执行）
app/migrations/versions/        # 28 个版本化迁移脚本
    001_exam_records_user_id.py    # 对齐 exam_records.user_id 列
    002_classical_seed.py          # 导入古诗文种子数据（1-6 年级）
    003_daily_tasks.py             # 创建 daily_tasks 表
    004_ai_usage.py                # 创建 AI 用量/周报/心情表
    005_rewards.py                 # 创建奖励券/心愿/目标表
    006_weekly_parent_note.py      # 周报增加家长留言字段
    007_sprint4_tables.py          # 创建挑战赛/小老师记录表
    008_parent_task_settings.py    # 创建家长任务配置表
    009_vip_users.py               # 创建 VIP 用户表
    010_ai_qa.py                   # 创建 AI 问答缓存表
    011_parent.py                  # 创建家长密码/题数/留言表
    012_coupon_flow.py             # 奖励券增加进度跟踪字段
    013_answer_appeals.py          # 创建答题申诉表
    014_next_review.py             # 增加延期复习日期字段
    015_qa_session.py              # 增加多轮对话 session_id
    016_pet_coin.py                # 创建金币流水 + 宠物表
    017_badges.py                  # 创建成就徽章表
    018_focus_sessions.py          # 创建专注钟记录表
    019_unanswered.py              # 增加未答题标记 + 修正历史数据
    020_diamonds.py                # 创建钻石账户/明细表 + 全员发放 100 万
    021_daily_task_overhaul.py     # 每日任务双轨改造（强制/可选）
    022_fix_daily_task_unique.py   # daily_tasks 唯一索引修正
    023_wish_optional_streak.py    # 心愿/可选任务/连续天数字段
    024_custom_tasks.py            # 自定义任务表（孩子发起家长确认）
    025_p0_hardening.py            # P0 防刷加固相关字段与索引
    026_user_auth.py               # 用户认证（邮箱/密码/验证码，方言兼容）
    027_admin.py                   # 管理员账号表 + 初始 admin
    028_wish_deadline.py           # 心愿截止日期字段
```

**MySQL 基线策略**（runner.py）：001-025 均为 SQLite 方言存量迁移，
MySQL 侧由 `Base.metadata.create_all` 直接建表，启动时自动把这些版本预置为已执行；
026 及之后的迁移必须用方言兼容写法（两种驱动都会真实执行）。
数据迁移工具见 tools/sqlite_to_mysql.py（逐表迁移 + 行数对账 + --ensure-admin 补建管理员）。

### app/data/ — 种子数据

```
app/data/words_primary_school.csv      # 1,968 个小学英语单词（人教版 3-6 年级）
app/data/phrases_primary_school.csv    # 118 个英语词组
app/data/sentences_primary_school.csv  # 77 个英语句子
```

### app/tools/

```
app/tools/wulal.py              # PDF 转图片工具（PyMuPDF）
```

### frontend/ — 旧版前端（已废弃，仅存档）

> 生产前端已迁移到 web/（Vue 3 + Vite 工程化），以下文件不再维护。

```
frontend/index.html             # 旧版主页面模板
frontend/static/app.js          # 旧版 Vue 应用逻辑
frontend/static/style.css       # 旧版样式表
```

### web/ — 生产前端（Vue 3 + Vite）

```
web/index.html                  # Vite 入口
web/src/main.js                 # 应用初始化
web/src/App.vue                 # 主组件（全部页面模板，~2,200 行）
web/src/nav.js                  # 导航结构
web/src/logic/appOptions.js     # 组件方法集（数据加载/交互逻辑，~2,800 行）
web/src/api/http.js             # API 封装
web/src/router/index.js         # vue-router 配置
web/src/stores/wallet.js        # pinia 钱包状态
web/src/styles/style.css        # 样式表
web/dist/                       # 构建产物（gitignore，部署时 npm run build 生成）
```

### tests/ — pytest 回归套件（48 用例）

```
tests/conftest.py               # 临时 SQLite + session 级 TestClient + AI/邮件打桩
tests/test_system.py            # 健康检查与前端入口
tests/test_auth_user.py         # 注册/登录/验证码/频控
tests/test_exam.py              # 出卷/判分/错题本/自动难度定档（含去空题口径）/30%错题题型
tests/test_tasks.py             # 每日任务/多强制任务 roundtrip/补签卡
tests/test_recite.py            # 背诵多轮无上限 + session-quiz 理解型检测
tests/test_parent.py            # 家长密码守卫/留言
tests/test_rewards.py           # 奖励券/心愿/练习判分
tests/test_admin.py             # 管理员登录与后台接口
```

### tools/ — 运维与迁移工具

```
tools/sqlite_to_mysql.py        # SQLite → MySQL 全量迁移（批量 500/外键拓扑序/行数对账，--dry-run/--ensure-admin）
tools/chk_mysql_data.py         # MySQL 数据核对
tools/mysql_preclean.py         # 迁移前清空目标表
tools/mysql_fix_autoincr.py     # 自增主键修正
```

### output/ — 生成文件（gitignore）

```
output/audio/*.mp3              # TTS 音频文件
output/figures/*.png            # 数学图形图片
output/*.docx                   # 生成的试卷文档
```

---

## 三、功能模块速查

| 编号 | 模块 | 核心路由 | 说明 |
|:---:|------|---------|------|
| 1 | 用户系统 | /api/user | 登录、年级管理、称号、自动升级 |
| 2 | 英语词库 | /api/words, /api/english | 单词/词组/句子 CRUD + 导入 |
| 3 | 数学出题 | /api/math, /api/exam | 24+ 题型生成（含初中 5 题型）+ 试卷 Word 下载；自动难度定档 + 70%随机/30%错题题型分布 |
| 4 | 背单词 | /api/vocab | 艾宾浩斯曲线新学 + 复习；多轮无上限；session-quiz 理解型检测（每词 4 题） |
| 5 | 古诗文 | /api/classical | 背诵 + 默写 + 艾宾浩斯复习；session-quiz 理解型检测（每篇 3 题） |
| 6 | 英语语法 | /api/grammar | 知识点 + 专项练习 |
| 7 | 错题本 | /api/exam/wrong, /api/study | 试卷错题 + 学习错题双轨 |
| 8 | 每日任务 | /api/tasks | 三科默认强制 + 家长每科追加多个强制 + 可选任务池 + 补签卡 |
| 9 | AI 讲解 | /api/ai | 错题 AI 分析 + 周报 + 鼓励 |
| 10 | 十万个为什么 | /api/qa | AI 问答 + 缓存 + 多轮对话 |
| 11 | 心情打卡 | /api/mood | 每日心情 + 趋势预警 |
| 12 | 奖励系统 | /api/rewards | 家长发券 + 孩子心愿 + 成长周报 |
| 13 | 限时挑战 | /api/challenge | 60 秒数学/单词速答 |
| 14 | 小老师 | /api/teach | 孩子讲题给家长，费曼学习法 |
| 15 | 学期目标 | /api/goals | 目标设定 + 倒计时 |
| 16 | 家长管理 | /api/parent | 密码保护 + 留言 + 数据查看 |
| 17 | 答题申诉 | /api/appeal | AI 复核 + 家长二次确认 |
| 18 | 金币宠物 | /api/pet | 虚拟宠物养成 + 金币经济 |
| 19 | 成长树 | /api/tree | 学习数据可视化成长树 |
| 20 | 成就徽章 | /api/badges | 13+ 种成就徽章 |
| 21 | 知识卡 | /api/cards | 知识卡图鉴收集 |
| 22 | 听写磨耳朵 | /api/dictation | TTS 朗读 + 拼写校验 |
| 23 | 专注钟 | /api/focus | 番茄钟计时器 |
| 24 | AI 趣味出题 | /api/ai-quiz | 主题化 AI 出题 |
| 25 | AI 学习助手 | /api/assistant | 个性化 AI 对话 |
| 26 | 钻石系统 | /api/diamond | AI 按 token 扣费（1 万 token = 1 钻石） |

---

## 四、改造工作量评估

### 1. 前端迁移到 Vue 组件化（Vite + SFC）

**当前状态**：已完成。生产前端已迁移到 web/（Vue 3 + Vite + vue-router + pinia），
App.vue ~2,200 行 + logic/appOptions.js ~2,800 行；旧版 frontend/ 已废弃存档。

**工作内容**：
- 搭建 Vite + Vue 3 工程化脚手架（vue-router、pinia）
- 将 20+ 个页面拆分为独立 .vue 组件（每个 tab 一个组件）
- 抽取公共组件：顶栏、侧边栏、弹窗、答题卡片、结算页等
- 状态管理迁移：data() → pinia store（按模块拆分）
- API 调用层封装为 composables
- CSS 模块化或 scoped 样式迁移
- 前端路由配置（替代当前 tab 切换）

**预估工作量**：**5-7 天**（1 个熟悉项目的前端开发者）

**风险点**：当前前端逻辑与 HTML 模板深度耦合（大量 v-if/v-for 内联），拆分时需要仔细梳理依赖关系；全局状态（quiz 答题状态机、combo 连击特效等）跨页面共享较多。

---

### 2. 数据库从 SQLite 迁移到 MySQL

**当前状态**：已完成。生产环境运行 MySQL 8（utf8mb4），DB_DRIVER 切换驱动，
迁移脚本已扩至 28 个（026+ 方言兼容），数据经 tools/sqlite_to_mysql.py 全量迁移并对账。

**工作内容**：
- 部署 MySQL 实例 + 创建数据库
- 修改 `database.py` 连接串（sqlite → mysql+pymysql）
- 逐文件排查 SQL 方言差异（日期函数、空值处理、自增主键、布尔值）
- 迁移脚本改写：20 个版本脚本全部需要用 MySQL 语法重写
- 处理 SQLite 特有行为：`func.random()` → `func.rand()`、`DATE('now')` → `CURDATE()` 等
- 并发写入测试（SQLite 单写 → MySQL 多写）
- 数据迁移工具：编写 SQLite → MySQL 数据导出导入脚本
- 连接池配置（pool_size、pool_recycle）
- 字符集与排序规则配置（utf8mb4）

**预估工作量**：**3-5 天**

**风险点**：部分路由中直接写了 SQLite 原生 SQL（如 `runner.py` 中的 `INSERT OR IGNORE`），需要逐一排查替换；`func.random()` 在多处使用需替换为 `func.rand()`；日期函数差异较多。

---

### 3. 增加完整代码注释

**当前状态**：部分完成。约 100+ 个 Python 文件 + web/ 前端（App.vue ~2,200 行 + appOptions.js ~2,800 行），
核心模块（models/services/主要 routers）已补模块与方法级注释，部分工具脚本与前端仍缺注释。

**工作内容**：
- 所有 models 添加字段级注释（docstring 或 comment）
- 所有 routers 添加接口说明（参数、返回值、业务逻辑）
- 所有 services 添加算法说明和边界条件注释
- 前端 app.js 添加方法分组注释和关键逻辑说明
- 迁移脚本添加变更说明
- 配置文件添加参数说明

**预估工作量**：**3-4 天**

**说明**：这是纯文档工作，不影响功能，可以分批进行。建议优先注释 models + services + routers 核心逻辑，前端可后续补充。

---

### 4. 增加用户注册登录充值体系

**当前状态**：用户名即登录，无密码、无注册、无充值。钻石系统已有余额和流水，但无充值入口。

**工作内容**：

**注册登录**（2-3 天）：
- User 模型增加 password_hash、phone/email 字段
- 注册接口（用户名 + 密码 / 手机号 + 验证码）
- 登录接口改造（密码校验 / 短信验证码）
- JWT Token 签发与校验中间件
- 前端登录页改造（注册/登录切换、密码输入）
- 密码找回（手机验证码 / 邮箱）
- 现有用户数据兼容（无密码用户首次登录引导设置密码）

**充值体系**（3-4 天）：
- 接入支付渠道（微信支付 / 支付宝 / 苹果内购）
- 充值套餐配置（如 10 元 = 100 钻石、50 元 = 600 钻石）
- 充值订单模型（Order）：创建/支付/回调/退款
- 支付回调处理（异步通知 + 主动查询双保险）
- 前端充值页面（套餐选择 + 支付二维码/跳转）
- 充值记录查询
- 管理端充值统计

**预估工作量**：**5-7 天**（不含第三方支付审核等待时间）

**风险点**：微信支付商户号申请需要营业执照；支付回调的幂等性和安全性需要仔细处理；涉及资金流转需要充分的测试。

---

### 5. 接入天气和提醒系统

**当前状态**：无天气功能，无定时提醒。已有心情打卡和每日任务系统，但无主动推送能力。

**工作内容**：

**天气系统**（1-2 天）：
- 接入天气 API（和风天气 / 高德天气 / 中国天气网）
- 用户城市配置（注册/设置页选择城市）
- 首页天气卡片（温度、天气状况、穿衣建议）
- 学习建议联动（恶劣天气推荐室内学习、好天气推荐户外运动）

**提醒系统**（3-4 天）：
- 提醒规则模型（Reminder）：类型/时间/频率/目标用户
- 提醒类型：每日学习提醒、复习到期提醒、任务完成提醒、天气变化提醒
- 推送通道选择：
  - 微信公众号/小程序模板消息（推荐，覆盖率高）
  - 短信通知（需短信服务商）
  - 站内通知（已有基础，需增强）
- 定时任务调度器（APScheduler / Celery Beat）
- 家长端提醒：孩子学习状态周报、连续未学习预警、充值提醒
- 孩子端提醒：每日学习任务、复习到期、宠物需要喂养
- 前端提醒设置页面（家长配置提醒时间和方式）

**预估工作量**：**4-6 天**

**风险点**：推送通道依赖第三方平台（微信公众号需要认证服务号）；定时任务的可靠性需要监控；短信成本需要控制。

---

### 6. 系统管理后台

**当前状态**：无管理后台。管理操作通过直接调用 API（如钻石增减）或数据库操作。

**工作内容**：

**后端管理 API**（2-3 天）：
- 管理员角色/权限模型（Admin / 超级管理员 / 运营）
- 用户管理：列表/搜索/禁用/重置密码/查看学习数据
- 内容管理：题库增删改查、古诗文管理、单词库管理
- 数据看板：注册趋势、日活、学习时长、AI 用量、钻石消耗
- 订单管理：充值记录、退款处理
- 系统配置：钻石套餐、学习任务默认值、AI 模型切换
- 操作日志：管理员操作审计

**前端管理页面**（3-5 天）：
- 独立管理后台前端（可用 Vue + Element Plus / Ant Design Vue）
- 仪表盘（核心数据图表：ECharts）
- 用户管理页面（表格 + 搜索 + 详情弹窗）
- 内容管理页面（CRUD 表格）
- 数据统计页面（多维度图表）
- 系统设置页面（配置表单）

**预估工作量**：**5-8 天**

**风险点**：管理后台是一个独立的完整前端项目；权限系统需要仔细设计防止越权；数据统计的性能在数据量大时需要优化（考虑加缓存或异步聚合）。

---

### 工作量汇总

| 改造项 | 预估工时 | 优先级建议 | 状态 |
|--------|---------|-----------|---------|
| 前端 Vue 组件化 | 5-7 天 | ★★★ 高 | 已完成（web/ + Vite） |
| SQLite → MySQL | 3-5 天 | ★★★ 高 | 已完成（含数据迁移与方言修复） |
| 完整代码注释 | 3-4 天 | ★★ 中 | 部分完成（核心模块已补） |
| 注册登录充值 | 5-7 天 | ★★★ 高 | 注册登录已完成（026_user_auth），充值未启动 |
| 天气与提醒 | 4-6 天 | ★★ 中 | 未启动 |
| 系统管理后台 | 5-8 天 | ★★★ 高 | 后端已完成（027_admin + admin API），独立前端未启动 |
| **合计** | **25-37 天** | — | 后续方向见 docs/ROADMAP.md |

> 以上估算是基于 1 个熟悉项目的开发者全职投入。如果多人并行，前端 Vue 化 + MySQL 迁移 + 管理后台可以同时推进，总工期可压缩到 **15-20 天**。
