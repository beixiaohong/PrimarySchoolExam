# 数据所有权登记表（S1-R Step 6）

> 本表是 S1 阶段「数据所有权先于代码拆分」的执行载体：85 张存量表逐一标注归属域，
> 并登记当前跨域访问事实。S1.5 的表级静态护栏（见 `.importlinter` 契约 3）以本表为唯一口径。
>
> 上游文档：`docs/enterprise/02-模块拆分与开发方案.md` 第三章「各域详细定义 · 数据归属」。
> 本表在其基础上做了 3 处修正（见 §1.3），并补齐文档未登记的 18 张表。

---

## 一、口径与取证方法

### 1.1 表清单来源（权威口径）

不是手工整理，而是从运行态元数据导出：

```
.venv\Scripts\python.exe -c "import app.models; from app.database import Base; print(len(Base.metadata.tables))"
```

- **85 张表 / 40 个模型文件**（`Base.registry.mappers` 全量遍历，按 `cls.__module__.__file__` 归组）
- 统计时间：S1-R Step 6，对应提交序列 `30ef472`（D9）→ `d5ec4c4`（Step 5 护栏）
- 「引用方」列的取证方式：以每张表的 ORM 类名在 `app/**/*.py` 全量文件里做词边界匹配并计数，
  按所在目录归属到域（`app/domains/<域>/`）或共享层（`app/routers/admin/` = 后台装配层、
  `app/migrations/` = 迁移、`app/schemas/`、`app/database.py`）。**只统计 ORM 类名**，
  裸 SQL 访问单独在 §6.2 登记（否则 `parent_task_settings` 会被误判为「无访问者」）。

### 1.2 与文档 02 的对账

| 项 | 数量 | 说明 |
|---|---:|---|
| 文档 02「数据归属」行列出的存量表 | 68 | 其中 `makeup_usage` 是笔误 |
| 库中实际存在的表 | 85 | 本表口径 |
| 两者重合 | 67 | 文档正确覆盖 |
| 文档列出但库中不存在 | 1 | `makeup_usage`（实名 `makeup_usage_log`） |
| 库中存在但文档未登记 | 18 | 17 张 `db_im_*`/`db_ledger_*` + `makeup_usage_log` |

即：**文档 02 第三章覆盖了 67/85，缺口全部集中在 D9 冻结域**（文档只在处置条目里提到
「数据已用 `db_im_*`/`db_ledger_*` 前缀隔离」，未逐表登记），加一处表名笔误。

### 1.3 本表相对文档 02 的 3 处修正（计划 Step 6 要求）

| # | 文档 02 | 本表 | 依据 |
|---|---|---|---|
| 1 | `sync_quiz_log` 归 **D3** | 归 **D6 family** | 唯一引用方是 `family(5)`（`routers/sync.py` + `services/sync_service.py`），D3 无任何引用 |
| 2 | `db_im_*`(7) / `db_ledger_*`(10) 未逐表登记 | 归 **D9 frozen**，逐表列出 | 前缀隔离 + 引用方实测为 `frozen`；例外见 §6.3（D8 admin_panel 直读其中 7 表做计数） |
| 3 | `makeup_usage` | **`makeup_usage_log`** | 库中实名，模型 `app/models/makeup_card.py` |

另有 1 处归属冲突需裁决：`content_reviews` 在文档 02 中 **D2 与 D8 各列一次**（重复登记），
本表判给 **D8**（理由见 §2.8），并记为待裁决项。

### 1.4 无表功能说明（计划 Step 6 要求补 weather）

| 功能 | 归属 | 是否有自有表 | 事实 |
|---|---|---|---|
| `/api/weather` | D8 platform | **无** | `routers/weather.py`：和风天气 GeoAPI + `/v7/weather/now`、`/v7/weather/3d`；**进程内 dict 缓存**（key=城市，TTL 4 小时），无 Redis、无落库。配置项 `QWEATHER_API_KEY`/`QWEATHER_API_HOST`/`IPINFO_API_TOKEN` 存于 D8 自有的 `system_config`（经 `services/sysconfig`）；城市解析回退会读 **D1 的 `users.city`**（跨域表读，见 §6.1） |
| 夜间静默时段 | D8 platform | **无** | `routers/quiet_hours.py`：`QUIET_START=22:30`、`QUIET_END=07:00` 与 `STATIC_ACTION_PREFIXES`（**26 条**动作端点前缀）**全部是代码内硬编码常量**，不读 `system_config`、不落库。以 `check_quiet_hours` 作 router 级依赖挂在 `main.py` 的 **9 个前缀**上（math/exam/vocab/classical/grammar/study/challenge/dictation/ai-quiz）；组合根不在护栏 `source_modules` 内，故不构成跨域 import |

> 推论：这两项功能在 S1.5 做表级护栏时**无需登记任何表**，但 weather 的 `users.city` 读需按 §6.1 收口。

---

## 二、85 张表归属登记（按域）

各域表数：D1=4、D2=18、D3=9、D4=8、D5=15、D6=4、D7=4、D8=6、D9=17，**合计 85**（对账见 §8）。

### 2.1 D1 身份与账号域（identity）— 4 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `users` | `user.py` | identity(29)、platform(26)、engine(13)、**frozen(114)**、commerce(5)、content(2)、engagement(2)、后台装配层(86) | 全域最高扇出（7 域 + D9 + 装配层）。同文件混放 D7 的 `vip_users`。S1.5 须经 D1 契约 `UserService` 收口 |
| `admins` | `admin.py` | 后台装配层(75)、**frozen(14)**、content(7)、platform(5) | 同文件混放 D8 的 `system_config`/`admin_operation_logs`。D9 直读 admins 做后台鉴权，是 D9 无法完全独立的原因之一 |
| `auth_codes` | `auth.py` | identity(13) | 单域独占。文档 02 已列为存量表（非「新增」），与库一致 |
| `parent_passwords` | `parent.py` | family(6)、identity(2) | 守卫实现在 `identity/services/parent_guard.py`，经 D1 契约 `ensure_parent_pwd` 暴露。模型文件四域混放（见 §3） |

### 2.2 D2 内容与教研域（content）— 18 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `words` | `word.py` | **engine(72)**、content(37)、assessment(21)、family(13)、engagement(11)、后台装配层(29) | 最大消费方是 D4 背单词引擎，非属主域 |
| `word_books` | `word.py` | **engine(38)**、content(32)、assessment(8)、family(3)、engagement(3)、后台装配层(18) | 同上 |
| `phrases` | `phrase.py` | content(20)、assessment(3) | |
| `sentences` | `phrase.py` | content(20)、assessment(3)、engine(2) | |
| `grammar_points` | `grammar.py` | content(36)、engine(3)、后台装配层(12)、迁移(1) | |
| `grammar_exercises` | `grammar.py` | content(38)、engine(15)、后台装配层(3) | |
| `classical_texts` | `classical.py` | content(56)、family(15)、engine(14)、engagement(9)、assessment(5)、后台装配层(12)、迁移(3) | 模型文件与 D4 的两张进度表混放 |
| `knowledge_points` | `knowledge.py` | content(15)、后台装配层(19) | 后台装配层引用多于属主域（知识点维护面板） |
| `reading_passages` | `reading.py` | **engine(9)** | 唯一 ORM 访问者是 D4 `services/reading_service.py`；D2 的 `routers/reading.py` 不碰表，经 D4 契约 `get_passages`/`submit_reading_quiz` 调用。属主按文档留在 D2（内容素材），S1.5 需裁决「服务移入 D2」或「表改归 D4」 |
| `textbook_versions` | `textbook.py` | content(19)、后台装配层(20) | |
| `user_textbook_prefs` | `textbook.py` | content(8) | 单域独占 |
| `online_courses` | `online_course.py` | content(22)、后台装配层(14) | |
| `teaching_progress` | `middle.py` | **engine(13)**、family(1) | 与 D3 的 `middle_questions` 同文件混放；D2 自身无引用，实际由 D4 初中教学进度使用 → S1.5 需裁决归属 |
| `teaching_records` | `sprint4.py` | **assessment(40)**、engagement(12) | 与 D3 的 `challenge_records` 同文件混放；D2 自身无引用 → S1.5 需裁决归属 |
| `papers` | `paper.py` | content(7)、后台装配层(7)、`database.py`(2) | 另有裸 SQL 读：`content/services/question_parser.py:388`（属主域自用，合规） |
| `paper_questions` | `paper.py` | content(31)、assessment(25)、后台装配层(10)、`database.py`(2) | |
| `problem_types` | `problem_type.py` | assessment(31)、content(12)、family(12)、engagement(5)、后台装配层(4)、迁移(5) | |
| `problem_categories` | `problem_type.py` | assessment(17)、content(12)、后台装配层(3) | |

> `content_reviews` 文档 02 在 D2 也列了一次，本表判给 D8，见 §2.8。故 D2 为 18 表（文档列 19）。

### 2.3 D3 练习与测评域（assessment）— 9 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `questions` | `exam.py` | assessment(50)、engine(18)、engagement(9)、platform(6)、后台装配层(1) | 题库主表，扇出高 |
| `middle_questions` | `middle.py` | **family(27)**、assessment(6)、platform(3)、engine(2) | 最大消费方是 D6（家长端初中题），非属主域 |
| `exam_records` | `exam.py` | assessment(21)、engagement(16)、engine(5)、platform(1)、后台装配层(1) | |
| `exam_attempts` | `exam.py` | **engagement(43)**、assessment(22)、后台装配层(13)、platform(11)、family(9)、engine(6)、identity(3) | 6 域引用，扇出第二高 |
| `attempt_answers` | `exam.py` | assessment(27)、family(17)、engagement(13)、迁移(1)、schemas(1) | |
| `essay_grades` | `essay.py` | assessment(2) | 单域独占 |
| `wrong_records` | `exam.py` | assessment(61)、engine(33)、engagement(23)、platform(9)、family(8)、identity(4)、后台装配层(12)、迁移(3) | 6 域引用；D4 错题本重练是主要外部消费方 |
| `challenge_records` | `sprint4.py` | **engagement(16)**、assessment(6)、后台装配层(5)、identity(3)、platform(2) | 与 D2 的 `teaching_records` 同文件混放 |
| `judge_review_issues` | `judge_review.py` | assessment(6) | 单域独占 |

> `sync_quiz_log` 文档 02 列在 D3，本表按实测修正到 D6，见 §2.6。故 D3 为 9 表（文档列 10）。

### 2.4 D4 学习引擎域（engine）— 8 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `vocab_progress` | `vocab.py` | engine(60)、engagement(28)、assessment(7)、后台装配层(12) | |
| `vocab_daily_log` | `vocab.py` | engine(31)、engagement(8)、platform(7)、后台装配层(6)、identity(5) | |
| `classical_progress` | `classical.py` | **content(37)**、engagement(27)、engine(15)、assessment(3)、后台装配层(9) | 属主域引用数排第三；最大消费方是 D2 古诗文模块 → S1.5 需裁决归属（与 `classical_texts` 同文件） |
| `classical_daily_log` | `classical.py` | **content(15)**、engine(12)、engagement(11)、platform(7)、后台装配层(6)、identity(5) | 同上 |
| `study_errors` | `study_error.py` | engine(58)、engagement(16)、assessment(11)、platform(11)、content(7)、identity(6)、family(4)、后台装配层(3)、迁移(1) | **7 域引用**，与 `users` 并列最高扇出 |
| `learning_goals` | `learning_goal.py` | engine(30)、engagement(3) | |
| `learning_checkins` | `learning_goal.py` | engine(36) | 单域独占 |
| `learning_weekly_reviews` | `learning_goal.py` | engine(13) | 单域独占 |

> 文档 02 为 D4 规划的 `mastery_records`/`diagnostic_sessions`/`learning_paths` 尚未建表，见 §5。

### 2.5 D5 激励与成长域（engagement）— 15 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `daily_tasks` | `daily_task.py` | engagement(88)、platform(12)、family(10)、identity(4)、迁移(2) | |
| `custom_tasks` | `custom_task.py` | engagement(13) | 单域独占 |
| `parent_custom_tasks` | `parent_custom_task.py` | engagement(24)、迁移(2) | |
| `parent_task_settings` | `parent.py` | **无 ORM 访问者**；engagement 经裸 SQL 读写 | `tasks/service.py:34,77` 读 `settings_json`；`tasks/settings.py:209,212,214` exists/UPDATE/INSERT upsert。模型类 `ParentTaskSettings` 存在但零引用 → 表级护栏必须同时扫裸 SQL（§6.2） |
| `task_confirms` | `task_confirm.py` | engagement(15)、迁移(2) | |
| `makeup_cards` | `makeup_card.py` | engagement(22)、后台装配层(15) | |
| `makeup_usage_log` | `makeup_card.py` | engagement(30)、后台装配层(7)、迁移(1) | 文档 02 写作 `makeup_usage`（笔误，修正 3） |
| `reward_coupons` | `reward.py` | engagement(30)、后台装配层(3) | |
| `wish_items` | `reward.py` | engagement(54)、family(3) | |
| `goal_items` | `reward.py` | engagement(25) | |
| `badge_earned` | `badge.py` | engagement(4)、platform(3) | |
| `mood_checkins` | `mood.py` | engagement(22)、platform(6) | |
| `focus_sessions` | `focus.py` | engagement(11) | 单域独占 |
| `pet_profiles` | `pet.py` | engagement(7) | 单域独占 |
| `coin_ledger` | `pet.py` | engagement(13)、**后台装配层(31)**、~~content(4)~~ | content 的 4 处直写已在 Step 4 补漏中收口为 `PetService.grant_coins`/`.balance`（`content/routers/knowledge.py`），现仅剩 D5 域内 + 装配层只读统计 |

### 2.6 D6 家长与家校区（family）— 4 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `parent_messages` | `parent.py` | family(10)、后台装配层(5) | |
| `exam_min_counts` | `parent.py` | family(5)、assessment(2) | |
| `answer_appeals` | `appeal.py` | family(21)、assessment(6)、engine(6)、迁移(1) | 申诉数据回流为内容质量信号（文档 02 D6 本期重点） |
| `sync_quiz_log` | `sync.py` | family(5) | **修正 1**：文档 02 归 D3，实测唯一引用方是 D6（`routers/sync.py` + `services/sync_service.py`），单域独占 |

### 2.7 D7 交易与商业化域（commerce）— 4 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `diamond_accounts` | `diamond.py` | commerce(14)、后台装配层(15) | 资金相关，文档 02 要求独立备份与审计 |
| `diamond_ledger` | `diamond.py` | commerce(9)、后台装配层(22) | 完整流水表，装配层引用多于属主域（充值/发放后台） |
| `ai_usage_log` | `ai_usage.py` | 后台装配层(14)、platform(8)、assessment(2) | **属主域零引用**：实际由 D8 AI 网关写入（经 `DiamondService.consume` 计费后记日志），与 D8 的 `ai_qa`/`weekly_reports` 同文件混放 |
| `vip_users` | `user.py` | 后台装配层(15)、platform(2 ORM + 1 裸 SQL) | **属主域零引用**；`platform/services/ai.py:54` 用裸 SQL `SELECT user_id FROM vip_users` 取 VIP 名单（§6.2）。与 D1 的 `users` 同文件混放 |

### 2.8 D8 平台与运营域（platform）— 6 表

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `system_config` | `admin.py` | 后台装配层(6)、platform(3) | 经 `services/sysconfig` 统一读取；weather 的 3 个 API Key 也存这里 |
| `admin_operation_logs` | `admin.py` | 后台装配层(6) | 审计日志，仅装配层 `_audit` 写入 |
| `admin_announcements` | `announcement.py` | platform(16)、迁移(3) | |
| `content_reviews` | `content_review.py` | **engine(7)** | **归属冲突裁决**：文档 02 在 D2 与 D8 各列一次。判给 D8 —— 「内容审核工作流」是 D8 职责行明列项，且后台审核面板（`app/routers/admin/review.py`）在 D8 侧；D2 是内容生产方即被审核对象，不应同时拥有审核记录表。**但当前唯一写入者是 D4 `engine/services/review_service.py`**（多 AI 联合校对：`middle_question`/`reading_passage` 双供应商独立审阅 + 人工裁决），装配层经 D4 契约 `review_service` 调用它 → S1.5 需裁决：`review_service` 移入 D8，或本表改归 D4 |
| `ai_qa` | `ai_usage.py` | platform(61)、assessment(8)、后台装配层(5) | |
| `weekly_reports` | `ai_usage.py` | engagement(9)、platform(6)、后台装配层(3) | 最大消费方是 D5（周报激励），非属主域 |

### 2.9 D9 隔离域（frozen）— 17 表

**修正 2**：文档 02 未逐表登记，本表补齐。全部带 `db_im_`/`db_ledger_` 前缀，物理隔离已就位。
`ENABLE_IM`/`ENABLE_LEDGER` 开关只控制路由挂载，**表与数据不受开关影响**。

| 表 | 模型文件 | 当前引用方（次数） | 备注 |
|---|---|---|---|
| `db_im_chats` | `im.py` | frozen(27)、**platform(2)**、迁移(2) | platform 侧见 §6.3 |
| `db_im_messages` | `im.py` | frozen(38)、**platform(2)**、迁移(2) | 同上 |
| `db_im_friendships` | `im.py` | frozen(49)、**platform(2)**、迁移(3) | 同上 |
| `db_im_group_members` | `im.py` | frozen(68)、迁移(2) | |
| `db_im_read_receipts` | `im.py` | frozen(12)、迁移(2) | |
| `db_im_red_packets` | `im.py` | frozen(12)、**platform(2)**、迁移(2) | |
| `db_im_red_packet_claims` | `im.py` | frozen(10)、迁移(2) | |
| `db_ledger_bills` | `ledger.py` | frozen(109)、**platform(2)**、迁移(2) | |
| `db_ledger_accounts` | `ledger.py` | frozen(32)、**platform(2)**、迁移(2) | |
| `db_ledger_categories` | `ledger.py` | frozen(39)、**platform(2)**、迁移(2) | |
| `db_ledger_projects` | `ledger.py` | frozen(11)、迁移(2) | |
| `db_ledger_persons` | `ledger.py` | frozen(9)、迁移(2) | |
| `db_ledger_merchants` | `ledger.py` | frozen(9)、迁移(2) | |
| `db_ledger_locations` | `ledger.py` | frozen(9)、迁移(2) | |
| `db_ledger_recurring_transactions` | `ledger.py` | frozen(17)、迁移(2) | |
| `db_ledger_notification_logs` | `ledger.py` | 迁移(2) | **运行时零访问者**：仅建表，frozen 域内无 ORM 引用 |
| `db_ledger_user_report_settings` | `ledger.py` | 迁移(2) | **运行时零访问者**：同上 |

---

## 三、跨域混合的模型文件（S1.5 物理拆分清单）

计划修订 3 决定 S1 只搬 routers/services，`app/models/` 留作共享内核。代价是：**40 个模型文件里有
6 个横跨多个域**，因此文件粒度的静态规则在 S1 无法用作硬门禁（会误伤自有表访问）。

| 模型文件 | 内含表（归属域） | 涉及域 | S1.5 拆分动作 |
|---|---|---|---|
| `user.py` | `users`(D1)、`vip_users`(D7) | D1 / D7 | 拆为 `identity/models/user.py` + `commerce/models/vip.py` |
| `admin.py` | `admins`(D1)、`system_config`(D8)、`admin_operation_logs`(D8) | D1 / D8 | 拆为 `identity/models/admin.py` + `platform/models/{sysconfig,audit}.py` |
| `parent.py` | `parent_passwords`(D1)、`parent_messages`+`exam_min_counts`(D6)、`parent_task_settings`(D5) | D1 / D5 / D6 | **三域混放**，拆为 3 个文件；`parent_task_settings` 需同时把裸 SQL 改回 ORM |
| `ai_usage.py` | `ai_qa`+`weekly_reports`(D8)、`ai_usage_log`(D7) | D7 / D8 | 拆为 `platform/models/ai_qa.py` + `commerce/models/ai_usage_log.py` |
| `classical.py` | `classical_texts`(D2)、`classical_progress`+`classical_daily_log`(D4) | D2 / D4 | 拆分前需先裁决 §2.4 的归属争议（实际最大消费方是 D2） |
| `sprint4.py` | `challenge_records`(D3)、`teaching_records`(D2) | D2 / D3 | 同上，`teaching_records` 实际由 D3/D5 使用 |
| `middle.py` | `middle_questions`(D3)、`teaching_progress`(D2) | D2 / D3 | 同上，`teaching_progress` 实际由 D4 使用 |

其余 33 个模型文件均为单域独占，可直接整文件 `git mv` 到 `app/domains/<域>/models/`。

---

## 四、共享层访问说明

| 共享层 | 说明 |
|---|---|
| `app/routers/admin/`（后台装配层） | 全部 admin 模块注册在同一个 `router` 对象上，无法按域物理拆分（S1.5 随 models 一起处理）。它对 30+ 张表有只读统计/维护访问，本表已在各表「引用方」列计入。**它访问域服务时必须走契约**（`.importlinter` 已白名单 `app.routers.admin.** -> app.domains.*.contracts`） |
| `app/migrations/` | 建表/改表脚本必然 import 多域模型，属组合层职责，不计为跨域债 |
| `app/schemas/` | Pydantic 响应模型，S1 与 models 一同留作共享内核 |
| `app/database.py` | 引擎/会话/`Base`；对 `papers`/`paper_questions` 有 2 处启动期引用（create_all 相关） |

---

## 五、文档 02 规划但库中尚不存在的表（18 张，按域）

这些是文档 02「数据归属」行中标注 **新增** 的表，S1 阶段一律**未建表、未登记 ORM 模型**，
本表只登记规划归属，供后续立项时使用（不在 85 张存量表计数内）：

| 域 | 规划表 | 用途（文档 02） |
|---|---|---|
| D1 | `guardian_consents`、`roles`、`permissions`、`age_verifications` | 监护人同意存证、RBAC、未成年人年龄识别（合规 P0） |
| D4 | `mastery_records`、`diagnostic_sessions`、`learning_paths` | 掌握度模型、诊断测评、个性化路径（M0 最高优先级） |
| D7 | `products`、`orders`、`payments`、`subscriptions`、`refunds`、`entitlements`、`reconciliation_logs` | 正规交易链路，取代现有二维码人工充值 |
| D8 | `events`、`notifications`、`experiments`、`audit_logs` | 埋点（现为 0）、推送召回（现为 0）、A/B 实验、审计 |
| D2 / D3 / D5 / D6 / D9 | — | 文档 02 未规划新增表；D9 冻结新需求，**不得新增表** |

> 注：文档 02 把 `auth_codes` 列在 D1 的存量表中，实测库内已存在（`app/models/auth.py`），无需新建。

---

## 六、跨域表访问债（S1.5 表级护栏的输入）

### 6.1 高扇出表 TOP 6（跨域读，须经属主域契约收口）

| 表 | 属主 | 引用域数 | 说明 |
|---|---|---:|---|
| `users` | D1 | 7 域 + D9 + 装配层 | 含 D8 `routers/weather.py:19` 直读 `users.city` 做城市回退 |
| `study_errors` | D4 | 7 域 + 装配层 | 错题本是全域共享资产，扇出与 `users` 并列 |
| `exam_attempts` | D3 | 6 域 + 装配层 | D5 激励侧引用(43) 多于属主域(22) |
| `wrong_records` | D3 | 6 域 + 装配层 | |
| `words` | D2 | 5 域 + 装配层 | D4 背单词引擎(72) 是最大消费方 |
| `classical_texts` | D2 | 5 域 + 装配层 | |

### 6.2 裸 SQL 访问（ORM 类名匹配扫不到，护栏必须额外覆盖）

`app/domains/**` 内共 **7 处** `text("...")` 形式的裸 SQL：

| 位置 | 涉及表 | 属主 | 判定 |
|---|---|---|---|
| `content/services/question_parser.py:388` | `papers` | D2 | 属主域自用，合规 |
| `engagement/routers/tasks/service.py:34,77` | `parent_task_settings` | D5 | 属主域自用，但**绕过了 ORM 模型**（`ParentTaskSettings` 零引用） |
| `engagement/routers/tasks/settings.py:209,212,214` | `parent_task_settings` | D5 | 同上（exists/UPDATE/INSERT upsert） |
| `platform/services/ai.py:54` | `vip_users` | **D7** | **跨域**：D8 AI 网关裸 SQL 直读 D7 的 VIP 名单，模块级护栏完全看不见这条边 |

### 6.3 D8 → D9 数据层穿透（护栏契约 2 覆盖不到的部分）

`platform/routers/admin_panel.py:30-31` 直接 import D9 的 ORM 模型：

```python
from app.models.ledger import Bill, Account, Category
from app.models.im import Chat, Message, Friendship, RedPacket
```

用途是运营面板的 `count()` 统计（`ledger_stats` 3 项 + `im_stats` 4 项，第 68-78 行）。

- **代码层**：不构成 `.importlinter` 契约 2 的违规——它 import 的是共享内核 `app.models.*`，
  不是 `app.domains.frozen`。这正是模块级护栏的盲区。
- **运行层风险**：`ENABLE_IM=false` / `ENABLE_LEDGER=false` 时路由不挂载（应用可正常启动、主流程可用），
  但这 7 张表的 `count()` 仍会执行；若未来 D9 数据被清理或迁走，该统计端点会 500。
- **建议**（S1.5）：统计块随开关短路，或改由 D9 契约暴露 `stats()`；表级护栏启用后这条边会被自动拦下。

### 6.4 为什么 S1 不能直接上表级门禁（实测取证）

1. **粒度不匹配**：依赖图是模块级的，无法区分 `from app.models.parent import ParentTaskSettings`
   （D5 自有）与 `from app.models.parent import ParentMessage`（D6）——同一模块、不同属主。
2. **模型文件本身跨域混合**：6 个文件横跨 2-3 个域（§3），按文件粒度设禁会误伤合法的自有表访问。
3. **存量规模**：`app/domains/**` 内 `app.models.*` 的 import 共 **316 行**，收敛为
   **101 组（域 → 模型文件）**、分布在 **102 个文件**。
4. **裸 SQL 盲区**：§6.2 的 7 处、§6.3 的 D9 穿透，都需要额外的字符串扫描规则。

故 S1 的执行载体是**本登记表 + 人工评审**，静态门禁只到域级（`.importlinter` 契约 1、2）。

---

## 七、S1.5 启用表级护栏的步骤

1. 先裁决 §2.2/§2.4/§2.8 的 4 处归属争议（`reading_passages`、`teaching_progress`、
   `teaching_records`、`classical_progress`+`classical_daily_log`、`content_reviews`）；
2. 按 §3 拆 6 个混合模型文件，其余 33 个整文件 `git mv` 到 `app/domains/<域>/models/`；
3. 打开 `.importlinter` 中注释形态的契约 3（`table-ownership-*` 模板已就位），逐域一条 forbidden；
4. 补一条自定义检查覆盖裸 SQL（扫 `text("...")` 里出现的表名 vs 所在域），先处理 §6.2 的
   `platform/services/ai.py:54`；
5. 处理 §6.3 的 D8 → D9 穿透；
6. 全部通过后，本表从「执行载体」降级为「文档说明」，护栏成为唯一口径。

---

## 八、验收对照（计划 Step 6：85 张表全部登记，无悬空）

| 域 | 表数 | 表名首字母序首末 |
|---|---:|---|
| D1 identity | 4 | `admins` … `users` |
| D2 content | 18 | `classical_texts` … `word_books` |
| D3 assessment | 9 | `attempt_answers` … `wrong_records` |
| D4 engine | 8 | `classical_daily_log` … `vocab_progress` |
| D5 engagement | 15 | `badge_earned` … `wish_items` |
| D6 family | 4 | `answer_appeals` … `sync_quiz_log` |
| D7 commerce | 4 | `ai_usage_log` … `vip_users` |
| D8 platform | 6 | `admin_announcements` … `weekly_reports` |
| D9 frozen | 17 | `db_im_chats` … `db_ledger_user_report_settings` |
| **合计** | **85** | 与 `Base.metadata.tables` 实测数量一致 |

复核命令（任一表名未出现在本文件即为悬空）：

```powershell
.venv\Scripts\python.exe -c "import app.models; from app.database import Base; import pathlib; d=pathlib.Path('docs/data-ownership.md').read_text(encoding='utf-8'); miss=[t for t in Base.metadata.tables if ('`'+t+'`') not in d]; print('TOTAL', len(Base.metadata.tables), 'MISSING', miss)"
```
