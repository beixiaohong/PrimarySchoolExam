# 账本系统 PRD（对标随手记，完善为「个人财务记账系统」）

> 文档状态：初版 PRD（2026-09-30），待评审后进入实施。
> 范围：仅限 D9 冻结域（`app/domains/frozen/routers/ledger.py` + `web/src/{views,components,logic}/ledger*`），
> 不新增跨域依赖；数据库变更走迁移；D9 冻结约束见 `app/domains/frozen/contracts.py`（不对外暴露能力，仅 `app/main.py` 在
> `ENABLE_LEDGER` 为真时挂载）。
> 现状依据：迁移自 `temp/wulala/ledger/route_ledger.py`，当前约 42 端点、4 个前端页、14 例测试通过。

---

## 0. 背景与目标

当前账本本质是「**一个用户的单本流水账**」：一个 `Bill` 表记收入/支出/转账，配账户/分类/地点/商户/人员/项目六个维度，
加周期交易与基础统计。它已能记账，但离「完善的财务记账系统」还差随手记的几根支柱——

**目标**：补齐「多账本 / 预算 / 借贷 / 资产与净资产 / 模板 / 提醒」六大支柱，让账本从
"记几笔流水" 升级为 "能管钱、能看家底、能控预算、能追债权债务" 的个人财务系统。
**不做**（本期）：AI 语音/OCR 记账、成员多人协同共享、理财基金购买、社区、云同步（服务端已天然多端同源）、皮肤主题。

---

## 1. 随手记功能点全景分析

来自官网与各大应用市场（金蝶·铭数，com.mymoney，V13.2）的功能拆解：

### 1.1 记账体验（录入方式）
| 方式 | 说明 | 我们是否要 |
|---|---|---|
| 手动记账 | 3 秒记一笔，选分类/账户/金额 | ✅ 已有 |
| 自动/周期账 | 房租/订阅按日周月年自动生成账单 | ✅ 已有（recurring + scheduler 01:00） |
| 语音记账 | 开口记 | ❌ 本期不做（需 AI，D9 冻结） |
| 拍照/票据 | 图片备忘 + 小票 OCR | ⚠️ 本期仅做「附件」占位，不做识别 |
| 模板记账 | 预设常用收支组合，一键复用 | ✅ **本期新增** |
| 退款 | 关联原支出流水，显示已退金额 | ✅ **本期新增** |

### 1.2 记一笔要素
类别（精美图标）、成员（多人）、项目（用途缘由）、拍照、模板、备注、时间。
→ 当前「成员(person)/项目(project)」已建模；**模板**与**退款关联**缺失。

### 1.3 情景账本（**随手记灵魂**）
个人/家庭/生意/旅游/装修/结婚/汽车/宝宝/多人账等 40+ 模板，每本独立分类与数据隔离。
→ 当前**只有单本**，这是与随手记最大的结构性差距。**本期核心**。

### 1.4 全面财务管理
| 能力 | 随手记 | 本期 |
|---|---|---|
| 币种 | 多币种 + 多币种卡 | ✅ **新增**（账户币种 + 本位币折算） |
| 预算 | 月预算 / 分类预算 / **超支提醒** | ✅ **新增**（当前仅有 project.budget，无月/分类预算与提醒） |
| 账户 | 资产负债来龙去脉 | ⚠️ 升级：增加「负债类账户」与净资产视图 |
| 报表 | 近 20 种图表 | ✅ 增强（现有 summary/category/monthly/budget + 前端圆环/柱状，补趋势线与资产负债报表） |
| 报销 | 差旅应酬票据统一处理 | ✅ **新增**（报销子流程，复用 project + 标记） |
| 借贷 | 关系查看、逐笔追踪 | ✅ **新增**（债权/债务 + 还款追踪） |
| 同步/备份 | 三端同步/云备份 | — 服务端同源，无需做 |
| 安全 | 加密/生物识别 | — 复用现有登录体系 |

### 1.5 提醒与报告
记账提醒（每日）、预算超支预警、信用卡还款/周期到期提醒、周报/月报。
→ 当前有 `NotificationLog` / `UserReportSettings` 两张表但**没有任何生产者**；本期让提醒真正落地
（周期到期、超支、每日记账提醒），报告仍返回 JSON（不发邮件，符合 D9 移除邮件推送的约定）。

---

## 2. 当前账本模块能力盘点（已实现，PRD 基线）

**数据模型**（`app/models/ledger.py`）：`Bill` / `Account`(储蓄卡/信用卡/虚拟账户) / `Category`(三级) /
`Location` / `Merchant` / `Person` / `Project`(带 budget) / `RecurringTransaction` /
`NotificationLog`(空置) / `UserReportSettings`(空置)。

**后端接口**（约 42 个，`/api/ledger`，均 `require_user` 本人校验）：
- 六维 CRUD：accounts / categories / locations / merchants / persons / projects（各 POST/GET/PUT/DELETE）
- 记账：transactions（POST/GET 列表(高级筛选)/GET 详情/PUT/DELETE，自动维持余额）
- 统计：statistics/summary、/category、/monthly、/budget（仅项目预算）
- 周期：recurring（POST/GET/PUT/DELETE/toggle）+ `/recurring/run-due`（scheduler 01:00 调用）
- 报告：`/reports/summary`（weekly/monthly/yearly，环比）
- 导入导出：`/export/csv`、`/import/csv`（仅金额/类型/时间/备注，不映射分类账户）

**前端**（4 页 + 通用弹窗，`web/src`）：`LedgerRecord`(记一笔) / `LedgerBills`(账单+筛选+分页) /
`LedgerAnalysis`(概览卡片+分类圆环+月度柱状+项目预算) / `LedgerSettings`(六维 CRUD + 周期开关+立即补跑)。
状态全部走 `logic/ledger.js`（壳 provide / View inject 解耦，与高项一致）。

**测试**：`tests/test_ledger_api.py` + `tests/test_ledger_web.py` 共 14 例，通过。

---

## 3. 差距分析（功能 × 随手记 × 当前 × 缺口）

| # | 能力 | 随手记 | 当前 | 缺口等级 |
|---|---|---|---|---|
| 1 | **多账本** | 40+ 情景账本，数据隔离 | 仅单本 | 🔴 核心 |
| 2 | 月/分类预算 + 超支提醒 | 有 | 仅项目预算，无提醒 | 🔴 核心 |
| 3 | 借贷（债权/债务追踪） | 有 | 仅 person，无借贷流水 | 🔴 核心 |
| 4 | 资产与净资产 | 资产负债/年终对账 | 仅账户余额，无负债视图 | 🟠 重要 |
| 5 | 退款关联原支出 | 有 | 无 | 🟠 重要 |
| 6 | 记账模板 | 有 | 无 | 🟠 重要 |
| 7 | 多币种 | 有 | 无 | 🟡 一般 |
| 8 | 报销子流程 | 有 | 无 | 🟡 一般 |
| 9 | 提醒真正落地（每日/到期） | 有 | 表空置，无生产者 | 🟠 重要 |
| 10 | 报表增强（趋势线/环比/资产负债） | 20 种 | 4 类 + 前端 3 图 | 🟡 一般 |
| 11 | 票据附件 | 有 | 无 | ⚪ 可选 |
| 12 | 健壮性（next_run 真实月份/余额行锁） | — | +30 天近似/无锁 | 🔴 必修 |

---

## 4. 目标产品定义（MVP 边界）

一个**多账本**的个人财务系统：每本账有独立分类与数据；支持预算控超支、借贷追债权债务、
资产看净资产、模板速记、退款关联、多币种折算、提醒落地。首期聚焦 **M0+M1+M2+M3**，M4 视情况。

---

## 5. 实施路线图

### M0 健壮性加固（必做，低风险）
- `ledger_calc._advance_next_run`：monthly/yearly 改真实月份推进（`dateutil.relativedelta` 或手写月底截断），不再 `+30/+365` 天。
- 余额更新 `_adjust_balance` 与记账/编辑/删除：对涉及账户加 `with_for_update()`（遵循「改真资产前必须行锁」铁律），消除并发丢更新。
- 转账/编辑边界校验：编辑时若 `transaction_type` 变 TRANSFER 必须 `to_account_id`；`update_transaction` 在改账户/类型时完整回滚旧影响再应用新影响（当前已做，补单测钉死）。
- 清理 `ledger.py` 头部「调度器已移除」等过期注释（实际 `tools/scheduler.py` 01:00 跑）。

### M1 多账本（核心概念升级）
- 新表 `LedgerBook`：`user_id, name, template(枚举/自由), icon, color, currency_base, sort, is_default`。
- `Bill` / `Account` / `RecurringTransaction` 增加 `book_id`（非空，默认归入首本）。
- **迁移**：`030_ledger_tables` 之后新增迁移，给历史数据建「日常账本」并回填 `book_id`。
- 所有列表/统计/记账接口增加 `book_id` 过滤（不传=当前选中本；默认本存前端）。
- 前端：账本切换条（顶部）+ 新建/选模板弹窗（`LedgerView` 新增 `LedgerBooks` 组件或并入 Settings）。

### M2 预算 + 超支提醒
- 新表 `LedgerBudget`：`book_id, scope(month|category|project), category_id?, amount, notify_threshold(默认 0.8)`。
- 统计接口 `statistics/summary` 与 `statistics/budget` 返回预算执行率；超 `notify_threshold` 写 `NotificationLog(status=pending)`。
- 前端：预算设置入口（Settings 或独立 Tab）、概览卡「本月预算 X/Y」进度条、超支红标。

### M3 借贷 + 退款 + 资产管理
- 新表 `LedgerDebt`：`book_id, person_id, direction(借出/借入), total, repaid, balance, due_date, status(进行中/已清), note`；
  还款用一条 `Bill`(type=expense/income) 关联 `debt_id`，联动 `repaid/balance`。
- `Bill` 增加 `refund_of_id`（关联原支出）、`attachment_url`（可选）。
- 资产管理接口 `statistics/networth`：资产=各账户余额之和 + 借出未收；负债=信用卡应还(近似) + 借入未还；净资产=资产−负债。
- 前端：借贷中心（新增组件）、退款在记一笔时可选「退这笔」、净资产卡。

### M4 模板 + 多币种 + 提醒生产者
- 新表 `LedgerTxTemplate`：`book_id, name, transaction_type, amount, category_id, from_account_id, to_account_id, note`（一键复用）。
- `Account.currency` + `rate_to_base`；`Bill` 记录原币金额 `amount_orig` / `currency` / `rate`，展示按本位币。
- 提醒生产者（新增 `tools/ledger_reminders.py`，挂 `tools/scheduler.py`）：
  - 每日记账提醒（按 `UserReportSettings` 或默认）；
  - 周期交易到期前 1 天提醒；
  - 信用卡还款日提醒（账户 `account_type=credit_card` + `due_day` 字段）。
  提醒只写 `NotificationLog`（前端轮询/角标展示，不接短信邮件——符合 D9 约束）。

### 贯穿：报表增强
- 趋势线图（近 12 月收支）、分类环比、资产负债报表；前端 `LedgerAnalysis` 补 SVG 折线 + 净资产模块。

---

## 6. 数据模型变更总览（新增/改）

新增表：
- `db_ledger_books`（LedgerBook）
- `db_ledger_budgets`（LedgerBudget）
- `db_ledger_debts`（LedgerDebt）
- `db_ledger_tx_templates`（LedgerTxTemplate）

字段变更：
- `Bill.book_id`（FK，必填）、`Bill.refund_of_id`（FK，可空）、`Bill.attachment_url`（可空）、
  `Bill.amount_orig`/`Bill.currency`/`Bill.rate_to_base`（多币种）
- `Account.book_id`（FK）、`Account.currency`（默认 CNY）、`Account.due_day`（信用卡还款日，可空）
- `RecurringTransaction.book_id`（FK）

> 所有表 `user_id` 隔离保持不变；多账本下仍按 `user_id` + `book_id` 双层隔离（不跨用户共享，本期不做多人协同）。

---

## 7. 新增接口设计（草案）

```
POST   /users/{uid}/books/                建账本（含选模板初始化分类）
GET    /users/{uid}/books/                账本列表（含每本净资产/本月收支摘要）
PUT    /users/{uid}/books/{bid}           改名/换封面/设默认
DELETE /users/{uid}/books/{bid}           删账本（校验无未清借贷/可迁移数据）

GET    /users/{uid}/books/{bid}/statistics/summary   带预算执行率的概览
GET    /users/{uid}/books/{bid}/statistics/networth  净资产

POST   /users/{uid}/books/{bid}/budgets/          设预算
PUT|DELETE /users/{uid}/budgets/{id}

POST   /users/{uid}/books/{bid}/debts/            记一笔借出/借入
POST   /users/{uid}/debts/{id}/repay              还款（生成 Bill 并联动）
GET    /users/{uid}/books/{bid}/debts/            借贷清单（按人进行中/已清）

POST   /users/{uid}/books/{bid}/templates/        建模板
POST   /users/{uid}/transactions/                 记一笔支持 book_id + refund_of_id + template_id
```

（具体 schema 在实施阶段随 `app/schemas/ledger.py` 落地，并补 `tests/test_ledger_*.py`。）

---

## 8. 前端页面规划

现有 4 页保留，调整：
- **账本切换条**：`LedgerView` 顶部新增本切换（List + 新建/模板）；选中本存 `localStorage`。
- **记一笔**：补「选账本 / 选模板 / 退款关联 / 附件(可选) / 多币种」；转账需选目标账户。
- **账单**：默认按当前本；补「借/贷/退款」标记、附件缩略。
- **分析**：补净资产卡、预算进度、趋势折线、借贷概览。
- **设置**：六维 CRUD 归属当前本；新增「预算」「借贷中心」「模板」「币种」入口。

---

## 9. 非功能性约束
- **冻结域**：仅 D9 内改，不对外 `contracts._EXPORTS` 暴露；跨域若需（如高项/商城）走各自 `contracts`。
- **铁律**：余额/资产变更前 `with_for_update`；AI 不在账本域使用（无 AI 需求）。
- **迁移**：每表变更一个 Alembic 版本，迁移带默认值回填（历史数据自动归「日常账本」）。
- **测试**：每阶段补 `tests/test_ledger_*.py`（M0 余额锁/next_run、M1 多本隔离、M2 预算超支、M3 借贷联动）；
  改完跑 `tools/regression_check.py` + `lint-imports` + `pytest`。
- **上线**：本地 commit+push → 线上 `git pull && sudo bash deploy.sh`（迁移在 `run_migrations()` 自动执行）。

---

## 10. 验收标准（M0–M3）
1. M0：周期 next_run 在月末/闰月正确推进；并发记同一账户余额不丢更新；测试覆盖。
2. M1：可建多本并切换；各本数据隔离；历史数据归日常本；筛选/统计按本生效。
3. M2：可设月/分类预算；超 80% 进度提示、超 100% 红标并落 `NotificationLog`。
4. M3：借出/借入可记、还款联动余额与债务；退款关联原支出并展示；净资产卡正确。
5. 全量 `pytest` 0 失败、`regression_check` 7 项通过、`web` 构建通过。
