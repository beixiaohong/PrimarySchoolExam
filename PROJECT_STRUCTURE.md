# 智学学堂 · 项目结构与工作量评估

> 最后更新：2026-08-12（初中九科 + 学期解锁 + 课堂同步落地）

---

## 一、技术栈概览

| 层 | 技术 | 说明 |
|---|---|---|
| 后端框架 | FastAPI + Uvicorn | Python 3.12，ASGI 异步服务，38 个路由模块 |
| 数据库 | MySQL 8（utf8mb4，生产 / 本地统一） | SQLAlchemy 2.0 ORM + 自建迁移系统（42 个版本脚本，MySQL-only，基线策略见下） |
| 前端 | Vue 3 + Vite 工程化（web/） | SPA，构建产物 web/dist 由后端托管（已移除旧版 frontend/ 与 frontend-admin/） |
| AI 接入 | 智谱 GLM / Relay 中转 / DeepSeek | 多供应商 fallback，按 token 扣钻石 |
| 文档生成 | python-docx + matplotlib + edge-tts | 试卷 Word、数学图形、TTS 音频 |
| 测试 | pytest + FastAPI TestClient | tests/ 目录 58 个回归用例（14 个文件），独立 MySQL 测试库（DB_NAME + _test）隔离 |

---

## 二、完整文件清单与说明

### 根目录

```
run.py                          # 启动入口（uvicorn 启动 FastAPI）
requirements.txt                # Python 依赖清单
.env.example                    # 环境变量模板（AI API Key 等）
.gitignore                      # Git 忽略规则
README.md                       # 项目简介与启动说明
DEPLOY.md                       # 服务器部署指南（Nginx + systemd）
deploy.sh                       # 一键部署脚本（Ubuntu/CentOS）
PROJECT_STRUCTURE.md            # 本文件
```

### app/ — 后端主包

```
app/__init__.py                 # 包标识
app/main.py                     # FastAPI 应用工厂：注册 38 个路由、lifespan 启动流程
app/config.py                   # 全局配置：数据库路径、输出目录、默认参数
app/database.py                 # SQLAlchemy 引擎、会话工厂、Base 声明、init_db()
```

### app/models/ — 数据模型（22 个文件）

```
app/models/__init__.py          # 统一导出所有模型
app/models/user.py              # User — 用户档案（用户名即标识，年级/学科/连续登录）
app/models/word.py              # WordBook + Word — 英语单词库（按年级/单元分组）
app/models/phrase.py            # Phrase + Sentence — 英语词组与句子
app/models/problem_type.py      # ProblemCategory + ProblemType — 数学题型分类树
app/models/exam.py              # ExamRecord/Question/WrongRecord/ExamAttempt/AttemptAnswer — 试卷与错题
app/models/vocab.py             # VocabProgress + VocabDailyLog — 背单词进度（艾宾浩斯曲线）
app/models/classical.py         # ClassicalText + ClassicalProgress + ClassicalDailyLog — 古诗文背诵（含 semester 学期字段）
app/models/middle.py            # MiddleQuestion + TeachingProgress — 初中六科静态题库与教学进度
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

### app/routers/ — API 路由（38 个文件）

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
app/services/middle_generator.py # 初中六科出题器（物理/化学/生物/道德与法治/历史/地理，静态题库抽题）
app/services/semester.py        # 学期判断公共函数（9-1月=上/2-8月=下）
```

### app/migrations/ — 数据库迁移系统

```
app/migrations/__init__.py
app/migrations/runner.py        # 迁移执行器（启动时自动运行，幂等执行）
app/migrations/versions/        # 42 个版本化迁移脚本（001-025 为 MySQL 下不执行的 SQLite 历史基线）
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
    029_classical_semester.py      # classical_texts 加 semester 列（MySQL-only）
    030_teaching_progress.py       # 教学进度表 teaching_progress（MySQL-only）
    031_problem_type_chapter.py    # problem_types 加 textbook_chapter 列（MySQL-only）
    032_classical_middle_seed.py   # 初中必背古诗文 48 篇种子（grade 7-9，MySQL-only）
    033_middle_question_seed.py    # 初中六科题库种子（每科 20 题，MySQL-only）
```

**MySQL-only 迁移策略**（runner.py）：001-025 为历史 SQLite 方言存量迁移，
MySQL 侧由 `Base.metadata.create_all` 直接建表，启动时自动把这些版本预置为已执行（不再执行其 SQLite 方言 SQL）；
026+ 全部为幂等迁移（inspector / checkfirst / try-except），启动时会真实顺序执行（含建表、加列、种子）；
历史存量数据（小学/初中词库、题库等）在测试环境由用例或种子逻辑自行插入。
题库发布工具见 tools/qb_release.py（本地增量抽取采集式题库 → 生成版本化更新脚本，手动传到线上执行）。

### app/data/ — 种子数据

```
app/data/words_primary_school.csv      # 1,969 个小学英语单词（人教版 3-6 年级）
app/data/words_middle_school.csv       # 434 个初中英语单词（人教版 7-9 年级，种子版需人工扩充）
app/data/phrases_primary_school.csv    # 118 个英语词组
app/data/sentences_primary_school.csv  # 77 个英语句子
```

### app/tools/

```
# app/tools/ 当前无源码文件（wulal.py 已于优化清理中删除：全仓零调用，PDF 预览走 PyMuPDF 按需另装）
```

### frontend/ 与 frontend-admin/（已删除）

> 旧版 `frontend/` 与管理后台 `frontend-admin/` 已于 MySQL-only 重构时移除，统一使用工程化前端 `web/`（Vue 3 + Vite + Pinia）。后端不再挂载旧版 `/static`、`/admin-static`、`/admin` 入口。

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

### tests/ — pytest 回归套件（58 用例 / 14 文件）

```
tests/conftest.py               # 独立 MySQL 测试库（DB_NAME + _test）+ session 级 TestClient + AI/邮件打桩
tests/test_system.py            # 健康检查与前端入口
tests/test_auth_user.py         # 注册/登录/验证码/频控
tests/test_exam.py              # 出卷/判分/错题本/自动难度定档（含去空题口径）/30%错题题型
tests/test_tasks.py             # 每日任务/多强制任务 roundtrip/补签卡
tests/test_recite.py            # 背诵多轮无上限 + session-quiz 理解型检测
tests/test_middle.py            # 初中九科：六科出卷+年级守卫/mid_*题型/学期过滤+include_next/progress守卫+sync_mode/xsc_bridge/promoted
tests/test_parent.py            # 家长密码守卫/留言
tests/test_rewards.py           # 奖励券/心愿/练习判分
tests/test_admin.py             # 管理员登录与后台接口
```

### tools/ — 运维与迁移工具

```
tools/mysql_preclean.py         # 迁移前清空目标表
tools/mysql_fix_autoincr.py     # 自增主键修正
tools/qb_release.py             # 题库更新脚本生成/应用（本地增量抽取 → 版本化更新脚本，手动传线上）
tools/collect_papers.py         # 采集式题库抓取与入库
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