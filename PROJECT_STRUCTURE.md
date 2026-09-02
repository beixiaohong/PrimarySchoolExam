# 智学学堂 · 项目结构与模块清单

> 最后更新：2026-09-02（同步至迁移 052 / 路由端点 377 / 测试用例 124）
> **数据口径声明**：本文所有数字均由代码实测得出，非手工估算。刷新方式见文末「九、口径自检」。

---

## 一、技术栈概览

| 层 | 技术 | 实测规模 |
|---|---|---|
| 后端框架 | FastAPI + Uvicorn（Python 3.12+） | 45 个路由前缀、**377 个 HTTP 端点**（递归统计） |
| 数据库 | MySQL 8（utf8mb4，生产/本地同构） | SQLAlchemy 2.0 ORM，**85 个模型类 / 40 个模型文件** |
| 迁移 | 自建版本化迁移（`app/migrations/`） | **56 个版本脚本**（001–025 MySQL 下预置已执行，026+ 幂等真实执行） |
| 前端（学生端） | Vue 3 + Vite（`web/`） | 23 个页面 + 2 个组件 + 6 个 JS 模块 |
| 前端（管理端） | Vue 3 + Vite（`admin/`） | 10 个页面（Hash 路由 `/admin#/...`） |
| AI 接入 | 智谱 GLM / Relay 中转 / DeepSeek | 单入口 `app/services/ai.py`，按 token 扣钻石 |
| 文档与媒体 | python-docx / matplotlib / edge-tts / PyMuPDF | 试卷 Word、数学图形、TTS 音频、PDF 渲染 |
| 测试 | pytest + FastAPI TestClient | **20 个文件 / 124 个用例**，独立 MySQL 测试库（`DB_NAME` + `_test`） |

---

## 二、仓库总览（代码体量）

| 区域 | 文件数 | 行数 | 说明 |
|---|---:|---:|---|
| `app/`（后端） | 256 | 37,966 | 路由 45 / 服务 24+2 包 / 模型 40 / 迁移 56 |
| `tests/` | 20 | 3,703 | 回归套件，AI 与邮件全打桩 |
| `tools/` | 16 | 4,628 | 运维、采集、同步、调度脚本 |
| `web/src/` | 32 | 8,463 | Vue 4,550 行 + JS 3,913 行 |
| `admin/src/` | 14 | 2,164 | Vue 2,089 行 + JS 75 行 |

---

## 三、目录树

```
PrimarySchoolExam/
├── run.py                      # 启动入口：uvicorn app.main:app
├── requirements.txt            # 生产依赖（锁版本）
├── requirements-dev.txt        # 测试依赖
├── pytest.ini                  # pytest 配置（MySQL 测试库隔离）
├── deploy.sh                   # 服务器一键部署（双端 build + systemd 重启）
├── .env / .env.example         # 运行配置（.env 已 gitignore）
│
├── app/                        # 后端主包
│   ├── main.py                 # 应用工厂：注册 45 个路由前缀、挂载 dist、lifespan
│   ├── config.py               # 唯一配置源（DB 连接串/充值二维码/Token TTL/文档开关）
│   ├── database.py             # 引擎与会话工厂、init_db()、_ensure_column、采集暂存库
│   ├── logging_setup.py        # 按天 + 按大小滚动日志（log/YYYY-MM-DD[.partN].log）
│   ├── models/                 # 40 个模型文件 / 85 个 ORM 类
│   ├── routers/                # 38 个路由文件 + 7 个路由子包
│   ├── services/               # 24 个服务文件 + init_data/ math_generator/ 两个子包
│   ├── schemas/                # 7 个 Pydantic 模型文件
│   ├── migrations/             # runner.py + versions/（56 个版本脚本）
│   └── data/                   # 4 份种子 CSV（小学/初中词库、词组、句子）
│
├── web/                        # 学生端 Vue3 + Vite（构建到 web/dist，后端 / 托管）
├── admin/                      # 管理后台 Vue3 + Vite（构建到 admin/dist，后端 /admin 托管）
├── tests/                      # 20 个测试文件 / 124 用例
├── tools/                      # 16 个运维与采集脚本
├── docs/                       # 项目文档（见 docs/INDEX.md）
├── log/                        # 运行日志（gitignore）
├── output/                     # 生成的试卷/图片/音频（gitignore）
├── data/                       # 采集产物与 SQLite 暂存（gitignore）
├── qb_versions/                # 题库版本化更新脚本（gitignore，手动传线上执行）
└── temp/                       # 临时调试脚本（gitignore）
```

---

## 四、后端模块清单

### 4.1 `app/` 核心文件

| 文件 | 职责 |
|---|---|
| `main.py` | 建 FastAPI 实例；注册 45 个路由前缀；挂载 `web/dist`（`/`）与 `admin/dist`（`/admin`）；lifespan 执行「建表 → 迁移 → 种子」 |
| `config.py` | **唯一配置源**：`DATABASE_URL`、输出目录、充值二维码/客服、昵称登录开关、`ENABLE_DOCS`、`USER_TOKEN_TTL_HOURS`、`QUIZ_SECRET` |
| `database.py` | 引擎（pool_size=10 / max_overflow=30 / pool_timeout=15 / pool_pre_ping / pool_recycle=3600）、`SessionLocal`、`get_db`、`init_db()`、`_ensure_column()`（跨 dialect 安全加列）、采集暂存库 `StagingSessionLocal` |
| `logging_setup.py` | `DailySizeRotatingHandler`：每天一个文件，超 20MB 拆 `.partN`，保留 30 天 |

### 4.2 `app/routers/` — 路由层（38 文件 + 7 子包）

**子包（按业务域拆分的大模块）**

| 子包 | 文件 | 说明 |
|---|---|---|
| `admin/` | 16 | 管理后台：auth/users/assets/vip/config/content/courses/textbooks/dashboard/analytics/log/review/study_records/ledger/common |
| `study/` | 9 | 学习中心：analysis/dashboard/errors/practice/progress/retry/review/common |
| `tasks/` | 10 | 每日任务：daily/settings/custom/progress/makeup/makeup_service/confirm/service/constants |
| `exam/` | 7 | 试卷：generate/attempts/records/wrong/collection/common |
| `classical/` | 6 | 古诗文：texts/recite/quiz/stats/common |
| `rewards/` | 6 | 奖励闭环：coupons/wish/exchange/timeline/common |
| `vocab/` | 5 | 背单词：words/session/stats/common |

**端点分布（按前缀降序，实测合计 377 条）**

| 前缀 | 端点 | 前缀 | 端点 | 前缀 | 端点 |
|---|---:|---|---:|---|---:|
| `/api/admin` | 70 | `/api/grammar` | 8 | `/api/challenge` | 3 |
| `/api/ledger` | 42 | `/api/vocab` | 8 | `/api/dictation` | 3 |
| `/api/im` | 29 | `/api/words` | 8 | `/api/focus` | 3 |
| `/api/exam` | 19 | `/api/ai` | 7 | `/api/search` | 3 |
| `/api/tasks` | 18 | `/api/math` | 7 | `/api/task-confirm` | 3 |
| `/api/study` | 16 | `/api/teach` | 7 | `/api/textbook` | 3 |
| `/api/rewards` | 13 | `/api/auth` | 6 | `/api/appeal` | 3 |
| `/api/parent` | 12 | `/api/english` | 6 | `/api/ai-quiz` | 3 |
| `/api/learning-goals` | 12 | `/api/sync` | 5 | `/api/assistant` | 2 |
| `/api/classical` | 11 | `/api/knowledge` | 5 | `/api/cards` | 2 |
| `/api` （钻石 `diamond`） | 5 | `/api/pet` | 5 | `/api/mood` | 2 |
| `/api/qa` | 5 | `/api/user` | 4 | `/api/reading` | 2 |
| `/api/courses` | 4 | `/api/goals` | 4 | `/api/weather` | 2 |
| `/`（前端静态与根路由） | 4 | `/api/tree` | 1 | `/api/badges` | 1 |
| | | `/api/announcements` | 1 | | |

> 注：`ai.py` 与 `grading.py` 同挂 `/api/ai`，路径分别为 `/explain|/report|/encourage|/explain-mark` 与 `/grade-essay|/grade-short-answer`，**无冲突**。
> `diamond.py` 内部 `prefix="/diamond"`、main 挂 `/api`，真实路径为 `/api/diamond/*`。
> 统计口径：递归展开 `_IncludedRouter` 后的 `APIRoute` 数量；`app.routes` 顶层仅 45 项（多为子路由聚合），**不可直接用**。
> `/api/im` 另有 WebSocket 端点（不计入上表 377）。

**单文件路由模块（36 个，`app/routers/*.py`，不含 `__init__.py` 与依赖模块 `quiet_hours.py`）**

`ai` `ai_quiz` `admin_panel` `announcement` `appeal` `assistant` `auth` `badges` `cards` `challenge` `courses` `diamond` `dictation` `focus` `goals` `grading` `grammar` `im` `knowledge` `ledger` `learning_goals` `math` `mood` `parent` `pet` `phrases` `qa` `reading` `search` `sync` `teach` `textbook` `tree` `user` `weather` `words`

> `quiet_hours.py` **不是路由模块**，而是 router 级依赖：实现 22:30–次日 07:00 夜间免打扰拦截，挂载在 9 个动作类前缀上。

### 4.3 `app/services/` — 业务服务层（24 文件 + 2 子包）

| 分类 | 文件 |
|---|---|
| AI 与判分 | `ai.py`（唯一 AI 客户端，多供应商 fallback + 钻石计费）、`judge.py`（AI 复核/重判）、`answer_check.py`（填空容错判定）、`answer_generator.py`（采集题库答案生成） |
| 出题引擎 | `math_generator/`（**子包 13 文件**：app/calc/geo/logic/number/ratio/stat/unit/middle/core/common/util）、`english_generator.py`、`chinese_generator.py`、`middle_generator.py` |
| 试卷与采集 | `paper_crawler.py`（第一试卷网采集）、`question_parser.py`（doc/docx/pdf 解析）、`collection_practice.py`（采集式练习） |
| 渲染输出 | `docx_service.py`（Word A4 排版）、`figure_renderer.py`（matplotlib 配图）、`audio_renderer.py`（edge-tts） |
| 业务支撑 | `diamond.py`（钻石扣费）、`parent_guard.py`（家长密码守卫）、`sysconfig.py`（系统配置 KV）、`semester.py`（学期判定）、`sync_service.py`（同步学 HMAC）、`review_service.py`（复习队列）、`reading_service.py`、`search_service.py`、`im_crud.py`（IM 数据访问） |
| 基础设施 | `init_data/`（**子包 9 文件**：core/words/phrases/sentences/grammar/problem_types/users/common）、`mailer.py`、`sms.py` |

### 4.4 `app/models/` — 数据模型（40 文件 / 85 类）

| 业务域 | 表（示例） |
|---|---|
| 账号与权限 | `users` `admins` `auth_codes` `vip_users` `parent_passwords` |
| 词句与背诵 | `words` `word_books` `phrases` `sentences` `vocab_progress` `vocab_daily_log` `classical_texts` `classical_progress` `classical_daily_log` |
| 题库与考试 | `questions` `exam_records` `wrong_records` `exam_attempts` `attempt_answers` `problem_types` `problem_categories` `middle_questions` `grammar_points` `grammar_exercises` `reading_passages` `knowledge_points` |
| 采集题库 | `papers` `paper_questions`（与出题式 `questions` 完全解耦） |
| 任务与激励 | `daily_tasks` `custom_tasks` `parent_custom_tasks` `parent_task_settings` `task_confirms` `makeup_cards` `makeup_usage` `reward_coupons` `wish_items` `goal_items` `badge_earned` `mood_checkins` `focus_sessions` |
| 资产与计费 | `diamond_accounts` `diamond_ledger` `ai_usage_log` `coin_ledger` `pet_profiles` |
| 家长与治理 | `parent_messages` `exam_min_counts` `answer_appeals` `judge_review_issues` `content_reviews` `admin_operation_logs` `admin_announcements` |
| 教材与课程 | `textbook_versions` `user_textbook_prefs` `online_courses` `teaching_progress` `teaching_records` |
| 学习目标 | `learning_goals` `learning_checkins` `learning_weekly_reviews` |
| IM | `db_im_chats` `db_im_messages` `db_im_friendships` `db_im_group_members` `db_im_read_receipts` `db_im_red_packets` `db_im_red_packet_claims` |
| 账本 | `db_ledger_accounts` `db_ledger_bills` `db_ledger_categories` `db_ledger_projects` `db_ledger_persons` `db_ledger_merchants` `db_ledger_locations` `db_ledger_recurring_transactions` `db_ledger_notification_logs` `db_ledger_user_report_settings` |
| 其它 | `essay_grades` `weekly_reports` `ai_qa` `sync_quiz_log` `study_errors` `challenge_records` `system_config` |

### 4.5 `app/migrations/`

- `runner.py`：按文件名编号顺序执行未应用版本，结果记 `schema_migrations` 表。
- `versions/`：56 个脚本。**001–025 为历史 SQLite 方言**，MySQL 侧由 `create_all` 建表并预置「已执行」；**026+ 为幂等真实执行**。
- 近期迁移：047 教材版本 → 048 网课 → 049 用户启用标记 → 050 知识点 → 051 任务确认状态统一 → 052 家长自定义任务补列。

### 4.6 `app/data/` — 种子数据

| 文件 | 内容 |
|---|---|
| `words_primary_school.csv` | 小学英语单词 1,969（人教版 3–6 年级） |
| `words_middle_school.csv` | 初中英语单词 434（人教版 7–9 年级） |
| `phrases_primary_school.csv` | 英语词组 118 |
| `sentences_primary_school.csv` | 英语句子 77 |

---

## 五、前端

### `web/` 学生端（Vue 3 + Vite）

```
web/src/
├── main.js               # 应用初始化
├── App.vue               # 主壳（895 行）：导航 + 全局弹窗 + 路由出口
├── router/index.js       # vue-router
├── api/http.js           # API 封装（统一 token 头与错误处理）
├── logic/appOptions.js   # 组件方法集（3,643 行，最大文件）
├── stores/wallet.js      # Pinia 钱包状态
├── styles/style.css      # 全局样式（1,082 行）
├── components/           # AntiCheatInput.vue、AppIcon.vue
└── views/                # 23 个页面
```

页面：Home / Practice / Papers / Recite / Sync / Reading / Search / Qa / Assistant / Aiquiz / Dict / Wrong / Stats / Pet / Tree / Badges / Cards / Courses / Knowledge / LearningGoals / Focus / Wallet / Settings。

### `admin/` 管理后台（Vue 3 + Vite，Hash 路由）

```
admin/src/
├── main.js / App.vue
├── api/index.js          # 后台接口封装（含 X-Admin-Token）
├── router/index.js
└── views/                # 10 个页面
```

页面：Login / Dashboard / Users / UserDetail / Content / Analytics / DataCenter / Textbooks / Announcements / Manage。

> 两套前端各自独立（独立 `package.json`），未抽取共享组件/类型包 —— 见 `docs/优化建议书.md`。
> **前端改动必须重建 dist**：`cd web && npm run build`（管理端同理），否则后端托管的仍是旧产物。

---

## 六、测试 `tests/`（20 文件 / 124 用例）

| 文件 | 用例 | 覆盖 |
|---|---:|---|
| `test_tasks.py` | 19 | 每日任务、强制任务配置 roundtrip、自定义任务、补签卡、完成确认 |
| `test_auth_user.py` | 11 | 注册/登录/验证码/频控/账号绑定 |
| `test_math_answers.py` | 12 | 数学题答案正确性（含折扣/利润/百分比回归） |
| `test_middle.py` | 10 | 初中九科出卷、年级守卫、学期过滤 |
| `test_exam.py` | 8 | 出卷/判分/错题本/难度定档 |
| `test_admin.py` | 7 | 管理员登录与后台接口 |
| `test_judge_ai.py` | 6 | AI 判分 |
| `test_recite.py` | 6 | 背诵多轮与理解型检测 |
| `test_rewards.py` | 6 | 奖励券/心愿/练习判分 |
| `test_search.py` | 6 | 搜题 |
| `test_sync_study.py` | 6 | 同步学 |
| `test_essay.py` | 5 | 作文判分 |
| `test_judge_semantic.py` | 4 | 语义判定 |
| `test_parent.py` | 5 | 家长密码守卫/留言 |
| `test_answer_check.py` | 3 | 填空容错 |
| `test_coupon_progress.py` | 2 | 奖励券进度 |
| `test_system.py` | 2 | 健康检查与前端入口 |
| `test_courses.py` | 1 | 网课 |
| `conftest.py` | — | MySQL `_test` 隔离库、session 级 TestClient、AI/邮件打桩 |

---

## 七、运维脚本 `tools/`（16 个）

| 脚本 | 用途 |
|---|---|
| `scheduler.py` | **代码内置定时器**（随 git 提交）：`JOBS` 声明 once/daily/weekly 任务，状态记 `tools/.scheduler_state.json`，配 crontab 每 15 分钟触发 |
| `collect_daily.py` | 每日试卷采集（每天一个 SQLite + 跨日去重注册表） |
| `collect_papers.py` / `collect_papers_sqlite.py` | 采集入库（主库 / SQLite 暂存两版） |
| `import_local_papers.py` | 本地已有试卷导入 |
| `backfill_image_base64.py` / `backfill_paper_answers.py` | 历史数据回填（图片 base64、答案） |
| `qb_release.py` | 题库版本化：本地增量抽取 → `qb_versions/NNN_*.py` 幂等 upsert 脚本 → 手动传线上 apply |
| `sync_prod_to_local.py` | 线上库 → 本地克隆库全量同步（读 `.env.prod`） |
| `sync_db_comments.py` | 同步表/列注释 |
| `mysql_preclean.py` / `mysql_fix_autoincr.py` | 迁移前清表 / 自增主键修复 |
| `seed_junior_grade7.py` | 七年级知识点种子 |
| `gen_kp_sql.py` | 知识点 SQL 生成 |
| `reset_admin_pwd.py` | 强制重置管理员密码 |
| `verify_math_answers.py` | 数学答案批量校验 |

---

## 八、功能模块速查

| # | 模块 | 主路由 | 说明 |
|:--:|---|---|---|
| 1 | 用户系统 | `/api/user` `/api/auth` | 邮箱验证码注册/登录/重置、Token 会话、自动升年级 |
| 2 | 英语词库 | `/api/words` `/api/english` | 单词/词组/句子 CRUD + 导入 |
| 3 | 数学出题 | `/api/math` `/api/exam` | 题型管理与生成、试卷 Word 下载、智能难度定档（70% 随机 + 30% 错题题型） |
| 4 | 背单词 | `/api/vocab` | 艾宾浩斯新学 + 复习，session-quiz 理解型检测 |
| 5 | 古诗文 | `/api/classical` | 背诵 + 默写 + 按学期解锁 |
| 6 | 英语语法 | `/api/grammar` | 知识点与专项练习 |
| 7 | 错题体系 | `/api/exam/wrong` `/api/study` | 试卷错题 + 学习错题双轨 |
| 8 | 每日任务 | `/api/tasks` `/api/task-confirm` | 强制/可选双轨、家长自定义、补签卡、完成确认 |
| 9 | 学习目标 | `/api/learning-goals` | 目标台：今日建议量、连续打卡（每周 1 休息日）、预计完成日、逾期红卡 |
| 10 | 知识点互动 | `/api/knowledge` | 讲解→例子→挖空自测，零 AI 调用 |
| 11 | 教材版本 | `/api/textbook` | 版本列表 + 用户选择，供取词过滤 |
| 12 | 网课 | `/api/courses` | 系统网课 + 家长自建网课 |
| 13 | AI 能力 | `/api/ai` `/api/qa` `/api/assistant` `/api/ai-quiz` | 讲解/周报/鼓励、十万个为什么、学习助手、趣味出题（钻石计费） |
| 14 | 心情打卡 | `/api/mood` | 每日心情与趋势预警 |
| 15 | 奖励系统 | `/api/rewards` `/api/goals` | 家长发券、孩子心愿、目标倒计时 |
| 16 | 限时挑战 | `/api/challenge` | 60 秒速答 |
| 17 | 小老师 | `/api/teach` | 费曼学习法讲题 |
| 18 | 家长端 | `/api/parent` | 密码守卫、任务设置、学习同步设置、周报留言 |
| 19 | 答题申诉 | `/api/appeal` | AI 复核 + 家长确认 |
| 20 | 金币宠物 | `/api/pet` | 宠物养成 + 金币经济 |
| 21 | 成长树/徽章/知识卡 | `/api/tree` `/api/badges` `/api/cards` | 可视化与收集 |
| 22 | 听写磨耳朵 | `/api/dictation` | TTS 朗读 + 拼写校验 |
| 23 | 专注钟 | `/api/focus` | 番茄钟 |
| 24 | 钻石系统 | `/api/diamond` | AI 按 token 扣费（1 万 token = 1 钻石） |
| 25 | IM 即时通讯 | `/api/im` | 单聊/群聊/好友/红包/已读回执，含 WebSocket（29 端点 + WS） |
| 26 | 个人账本 | `/api/ledger` | 账户/账单/分类/周期账/报表（42 端点） |
| 27 | 公告 | `/api/announcements` | 学生端拉取（后台由 `admin_panel.py` 发布） |
| 28 | 管理后台 | `/api/admin` | 用户/资产/VIP/内容/教材/看板/日志（70 端点） |
| 29 | 采集题库 | — | `papers` / `paper_questions`，与出题式题库解耦 |
| 30 | 夜间免打扰 | `quiet_hours.py` | 22:30–07:00 拦截动作类端点（router 级依赖） |

---

## 九、已知大文件与技术债

| 文件 | 行数 | 说明 |
|---|---:|---|
| `web/src/logic/appOptions.js` | 3,643 | 学生端逻辑集中在单一 mixin，已在 `docs/user-app-optimization-plan.md` 规划拆分 |
| `app/routers/im.py` | 1,251 | 由外部 IM 模块迁移而来，建议按「会话/消息/好友/红包」拆分 |
| `app/routers/ledger.py` | 1,086 | 同上，建议按「账户/账单/统计」拆分 |
| `app/services/paper_crawler.py` | 891 | 采集流程与解析逻辑耦合 |
| `app/services/math_generator/calc.py` | 658 | 题型实现体量大（已按题型域拆分到 13 个子模块，仍偏大） |

> 完整治理方案见 `docs/优化建议书.md`、`docs/user-app-optimization-plan.md`、`docs/admin-optimization-plan.md`。

---

## 十、口径自检（如何刷新本文数字）

```powershell
# 路由端点总数（必须递归 _IncludedRouter，app.routes 顶层仅 45 项）
.\.venv\Scripts\python.exe -c "import app.main as m; from fastapi.routing import APIRoute
def walk(a):
    n=0
    for r in a.routes:
        inc=getattr(r,'original_router',None)
        if inc is not None: n+=walk(inc)
        elif isinstance(r,APIRoute): n+=1
    return n
print(walk(m.app))"

# 模型类数量
.\.venv\Scripts\python.exe -c "import app.models as M
print(sum(1 for v in vars(M).values() if isinstance(v,type) and hasattr(v,'__tablename__')))"

# 测试用例数量
.\.venv\Scripts\python.exe -m pytest tests/ -q
```
