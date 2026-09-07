# 个人账本（ledger）与即时通讯（IM）功能产品文档

> 面向小学家庭的智能学习平台「智学学堂」中的两个**隔离域功能模块**。
> 代码位置：`app/domains/frozen/`（D9 冻结域）
> 文档生成：2026-09-07　口径：账本 42 端点 + 后台 6 端点；IM 29 端点 + 1 WebSocket + 后台 6 端点；合计 **83 个端点**
>
> ⚠️ **本文描述的是「当前代码现状」**。2026-09-07 已拍板 6 项产品决策，其中
> **红包资产将由 `users.points` 改为钻石体系、语音将后端统一转码、新增敏感词过滤**，
> 这些**尚未落地**，本文件中的相关描述仍为现状口径。
> 要开发的内容以 [IM与账本前端实现方案](./IM与账本前端实现方案.md) 为准（含 §〇 决策记录）。

---

## 一、一句话结论

两个模块**后端功能完整、数据模型完备、已在生产运行**，但当前处于 **D9 冻结域**——
停止新需求、零自动化测试、**学生端（web）无任何 UI 入口**，仅保留后台数据管理兜底。
它们与 K12 学习主线无协同，表已用 `db_im_*` / `db_ledger_*` 前缀隔离，随时可整体关闭或独立部署。

---

## 二、模块一：个人账本（ledger）

### 2.1 产品定位

个人 / 家庭记账工具。核心是「一笔交易 + 六个维度」的多维记账模型：
每笔收支可同时挂接 **分类、账户、地点、商户、人员、项目**，从而支持任意维度的交叉统计与预算管控。

| 维度 | 作用 | 典型场景 |
| --- | --- | --- |
| 三级分类 | 支出/收入的科目体系 | 食品 > 饮食 > 三餐 |
| 支付账户 | 资金载体，保存实时余额 | 储蓄卡 / 信用卡 / 虚拟账户（支付宝、微信） |
| 支付地点 | 消费发生地 | 家附近超市、公司楼下 |
| 支付商户 | 交易对手 | 沃尔玛、星巴克 |
| 相关人员 | 交易涉及的自然人 | 朋友、同事、家人（用于人情往来/代付） |
| 关联项目 | 带预算的专项 | 装修、旅游、学习（可设预算并统计执行率） |

### 2.2 数据模型（10 张表）

| 表名 | 说明 | 关键字段 |
| --- | --- | --- |
| `db_ledger_bills` | **交易账单**（核心表） | `transaction_type` `amount` `category_id` `from_account_id` `to_account_id` `location_id` `merchant_id` `person_id` `project_id` `note` `transaction_time` |
| `db_ledger_accounts` | 支付账户 | `account_name` `account_type` `account_subtype` `account_number` `balance` |
| `db_ledger_locations` | 支付地点 | `name` `address` |
| `db_ledger_merchants` | 支付商户 | `name` `description` |
| `db_ledger_persons` | 相关人员 | `name` `phone` `relationship` |
| `db_ledger_projects` | 关联项目 | `name` `description` `budget` |
| `db_ledger_categories` | 三级分类 | `category_type` `level1` `level2` `level3` |
| `db_ledger_notification_logs` | 报告推送记录 | `report_period` `period_start/end` `report_content` `status` `sent_at` `error_message` |
| `db_ledger_user_report_settings` | 报告推送设置 | `weekly_day` `monthly_day` `yearly_month/day` `include_charts` `include_comparison` `include_recommendations` |
| `db_ledger_recurring_transactions` | 周期性交易 | `name` `amount` `frequency` `next_run` `is_active` |

**枚举定义**

| 枚举 | 取值 |
| --- | --- |
| `TransactionType` | `income` 收入 / `expense` 支出 / `transfer` 转账 |
| `AccountType` | `savings_card` 储蓄卡 / `credit_card` 信用卡 / `virtual_account` 虚拟账户 |
| `CategoryType` | `INCOME` / `EXPENSE` |
| `ReportPeriod` | `weekly` / `monthly` / `yearly` |
| `NotificationStatus` | `pending` / `sent` / `failed` |

> ⚠️ **口径差异**：`docs/enterprise/07-技术实施方案.md` §1.2 记「`db_ledger_*`（11 表）」，
> 实测模型为 **10 张**。IM 的 7 张与文档一致。此项待核对后统一口径。

### 2.3 功能清单（42 个端点，前缀 `/api/ledger`）

除「到期周期交易处理」与「财务报告」外，所有端点均按 `/users/{user_id}/...` 隔离，数据严格按 `user_id` 归属。

| 分组 | 端点 | 数量 |
| --- | --- | --- |
| **账户管理** | `POST /users/{uid}/accounts/` 创建　`GET` 列表　`PUT /{id}` 更新　`DELETE /{id}` 删除 | 4 |
| **分类管理** | `POST /users/{uid}/categories/`　`GET`　`PUT /{id}`　`DELETE /{id}` | 4 |
| **地点管理** | `POST /users/{uid}/locations/`　`GET`　`PUT /{id}`　`DELETE /{id}` | 4 |
| **商户管理** | `POST /users/{uid}/merchants/`　`GET`　`PUT /{id}`　`DELETE /{id}` | 4 |
| **人员管理** | `POST /users/{uid}/persons/`　`GET`　`PUT /{id}`　`DELETE /{id}` | 4 |
| **项目管理** | `POST /users/{uid}/projects/`　`GET`　`PUT /{id}`　`DELETE /{id}` | 4 |
| **记账管理** | `POST /users/{uid}/transactions/` 记一笔　`GET` 列表（多维筛选）　`GET /{id}` 详情　`PUT /{id}` 修改　`DELETE /{id}` 删除 | 5 |
| **统计分析** | `GET /users/{uid}/statistics/summary` 财务概览<br>`GET /statistics/category` 按分类统计支出<br>`GET /statistics/monthly` 按月收支趋势<br>`GET /statistics/budget` 项目预算执行率 | 4 |
| **周期性交易** | `POST /users/{uid}/recurring/`　`GET`　`PUT /{id}`　`DELETE /{id}`<br>`POST /recurring/{id}/toggle` 启用/停用<br>`POST /recurring/run-due` 手动触发到期执行 | 6 |
| **财务报告** | `GET /reports/summary?period=weekly\|monthly\|yearly` 生成周期报告（返回 JSON） | 1 |
| **导入导出** | `GET /users/{uid}/export/csv` 导出账单　`POST /users/{uid}/import/csv` 导入账单 | 2 |

### 2.4 核心业务规则

**BR-L1 账户余额自动联动**
创建交易时按类型调整账户余额（`_adjust_balance`）：

| 交易类型 | 余额变动 |
| --- | --- |
| `income` 收入 | `to_account` **+amount** |
| `expense` 支出 | `from_account` **−amount** |
| `transfer` 转账 | `from_account` **−amount**，`to_account` **+amount** |

> 删除/修改交易时会反向回滚余额，保证账户余额与账单流水一致。

**BR-L2 金额精度**
所有金额字段为 `Numeric(15,2)`（精确到分），**禁止 Float**——遵循项目 DB-01 铁律。

**BR-L3 周期性交易**
- 支持 `daily` / `weekly` / `monthly` / `yearly` 四种频率，字段 `next_run` 记录下次执行时间
- 到期后由 `POST /recurring/run-due` 触发（**手动触发，未见定时任务挂载**），自动生成一笔账单并推进 `next_run`
- `is_active` 可停用，`POST /recurring/{id}/toggle` 切换

**BR-L4 财务周期报告**
`generate_financial_report()` 统计区间 `[period_start, period_end]`，与上一周期对比（环比），产出：

- 本期收入 / 支出 / 净收入
- 当前总余额（`SUM(accounts.balance)`）
- 支出 Top5 分类（按三级分类分组，含金额与笔数）
- 报表配置受 `db_ledger_user_report_settings` 控制：是否含图表、是否含同比环比、是否含理财建议
- 推送记录落 `db_ledger_notification_logs`，含 `status` 与 `error_message` 便于重试排查

### 2.5 后台管理（6 端点，前缀 `/api/admin`）

| 端点 | 说明 |
| --- | --- |
| `GET /ledger/bills` | 账单列表（跨用户） |
| `DELETE /ledger/bills/{bill_id}` | 删除账单 |
| `GET /ledger/accounts` | 账户列表（跨用户） |
| `DELETE /ledger/accounts/{account_id}` | 删除账户 |
| `GET /ledger/categories` | 分类列表（跨用户） |
| `DELETE /ledger/categories/{category_id}` | 删除分类 |

前端入口：`admin/src/views/Manage.vue`「账本 · IM 管理」的**账单 / 账户 / 分类**三个 tab。
定位为**运营兜底**——只支持查看与删除，不支持增删改。

---

## 三、模块二：即时通讯（IM）

### 3.1 产品定位

面向平台用户的即时通讯能力，含好友体系、私聊/群聊、富媒体消息、群公告、已读回执与**积分红包**。

### 3.2 数据模型（7 张表 + users 表 4 个补充字段）

| 表名 | 说明 | 关键字段 |
| --- | --- | --- |
| `db_im_chats` | 聊天室（私聊/群聊） | `name` `chat_type` `created_by` `avatar` `description` `announcement` `announcement_at/by` |
| `db_im_messages` | 消息 | `chat_id` `sender_id` `content` `message_type` `file_path/name/size` `edited_at` `is_deleted` |
| `db_im_friendships` | 好友关系 | `requester_id` `addressee_id` `status` |
| `db_im_group_members` | 群成员 | `chat_id` `user_id` `is_admin` `joined_at` |
| `db_im_red_packets` | 红包 | `sender_id` `chat_id` `message_id` `total_amount` `total_count` `remaining_amount` `remaining_count` `blessing_words` `status` `expires_at` |
| `db_im_red_packet_claims` | 红包领取记录 | `red_packet_id` `user_id` `amount` `claimed_at` |
| `db_im_read_receipts` | 已读回执 | `chat_id` `user_id` `last_read_message_id` `updated_at` |

**IM 为 `users` 表补充的 4 个字段**（迁移 `031_im_tables.py` 幂等添加）

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| `avatar` | VARCHAR(255) | 头像 URL |
| `points` | INTEGER DEFAULT 0 | **积分**——红包发放与领取的结算单位 |
| `is_online` | TINYINT(1) | 在线状态 |
| `last_seen` | DATETIME | 最后活跃时间 |

**枚举定义**

| 枚举 | 取值 |
| --- | --- |
| `MessageType` | `text` `image` `file` `voice` `video` `red_packet` `system` |
| `ChatType` | `private` / `group` |
| `FriendStatus` | `pending` 待确认 / `accepted` 已通过 / `blocked` 已拉黑 |
| `RedPacketStatus` | `active` 可领取 / `expired` 已过期 / `finished` 已领完 |

### 3.3 功能清单（29 个 HTTP 端点 + 1 个 WebSocket，前缀 `/api/im`）

| 分组 | 端点 | 数量 |
| --- | --- | --- |
| **好友关系** | `POST /friends/add` 发起添加<br>`GET /friends` 好友列表<br>`POST /friends/accept/{friendship_id}` 接受<br>`GET /friends/pending` 待处理请求<br>`POST /friends/{uid}/block` 拉黑<br>`DELETE /friends/{uid}/block` 解除<br>`GET /friends/blocked` 黑名单 | 7 |
| **会话** | `POST /chats` 创建会话<br>`GET /chats` 我的会话列表<br>`GET /chats/{chat_id}/messages` 历史消息 | 3 |
| **群成员** | `POST /chats/{chat_id}/members` 加人<br>`DELETE /chats/{chat_id}/members/{uid}` 踢人<br>`GET /chats/{chat_id}/members` 成员列表<br>`POST /chats/{chat_id}/leave` 退群 | 4 |
| **群公告** | `PUT /chats/{chat_id}/announcement` 设置<br>`GET /chats/{chat_id}/announcement` 读取 | 2 |
| **消息** | `PUT /messages/{id}` 编辑<br>`DELETE /messages/{id}` 删除<br>`POST /messages/{id}/recall` 撤回<br>`POST /messages/{id}/read` 标记已读<br>`GET /messages/unread-count` 未读数 | 5 |
| **红包** | `POST /red-packets` 发红包<br>`POST /red-packets/{id}/claim` 抢红包<br>`GET /red-packets/{id}/claims` 领取记录 | 3 |
| **用户资料** | `GET /users/me`<br>`PUT /users/me`<br>`GET /users/search` 搜索用户 | 3 |
| **文件** | `POST /upload/file` 上传消息附件 | 1 |
| **健康检查** | `GET /health` | 1 |

### 3.4 WebSocket 实时通信

**连接地址**：`ws://<host>/api/im/ws/chat?token=<user_token>`

- **鉴权**：URL query 传 `token`，查 `users.token`；无 token 或匹配失败立即 `close(1008)`
- **上线**：连接建立时置 `is_online=True`、刷新 `last_seen`
- **离线补偿**：连接后立即推送 `offline_summary`（各会话未读数 + 总数）
- **断线**：`WebSocketDisconnect` 时置 `is_online=False` 并刷新 `last_seen`

**客户端 → 服务端**（`type` 三选一）

| type | 载荷 | 处理 |
| --- | --- | --- |
| `message` | `chat_id` `content` `message_type` `file_path` `file_name` `file_size` | 权限校验 → 落库 → 广播给会话成员 |
| `typing` | `chat_id` | 广播「正在输入」状态 |
| `read` | `chat_id` `message_id` | 更新 `db_im_read_receipts` 已读回执 |

**服务端 → 客户端**

| type | 说明 |
| --- | --- |
| `offline_summary` | 连接时推送，`unread_counts` + `total` |
| 消息广播 | 新消息推送给会话内在线成员 |
| `red_packet_claimed` | 红包被领取时广播：领取人、金额、剩余个数 |

> ⚠️ **连接池铁律（项目硬性红线）**：WS 全生命周期内**绝不跨阶段持有 DB 会话**。
> 鉴权、未读查询、消息落库、成员查询、离线状态更新**各自使用独立的短生命周期 `SessionLocal()`**，
> 会话关闭后再进行网络广播。

### 3.5 红包业务规则（BR-IM1~4）

| 规则 | 说明 |
| --- | --- |
| **BR-IM1 积分结算** | 红包金额单位为**平台积分**（`users.points`，整型），非现金。发红包时 `sender.points -= total_amount` |
| **BR-IM2 24 小时过期** | `expires_at = now + 24h`；领取时若已过期，状态置 `expired` 并拒绝 |
| **BR-IM3 拼手气算法** | 剩余个数 == 1 时领取全部余额；否则 `random.randint(1, remaining_amount - (remaining_count - 1))`，**保证后续每人至少得 1 分**。领取后 `remaining_amount/count` 递减，归零置 `finished` |
| **BR-IM4 防自领** | `sender_id == 领取人` 时拒绝（400 `Cannot claim your own red packet`） |

### 3.6 后台管理（6 端点，前缀 `/api/admin`）

| 端点 | 说明 |
| --- | --- |
| `GET /im/chats` | 会话列表（跨用户） |
| `DELETE /im/chats/{chat_id}` | 删除会话（级联删除消息与成员） |
| `GET /im/friendships` | 好友关系列表（跨用户） |
| `DELETE /im/friendships/{friendship_id}` | 删除好友关系 |
| `GET /im/red-packets` | 红包列表（跨用户） |
| `DELETE /im/red-packets/{red_packet_id}` | 删除红包 |

前端入口：`admin/src/views/Manage.vue` 的**聊天 / 好友 / 红包**三个 tab，仅查看 + 删除。

---

## 四、架构与部署

### 4.1 冻结域（D9）定位

两模块合称 **D9 隔离域**，代码位于 `app/domains/frozen/`：

```
app/domains/frozen/
├── README.md          # 域说明：冻结新需求、开关可整体关闭
├── __init__.py
├── contracts.py       # 对外契约 —— _EXPORTS 为空（刻意设计，不向其它域暴露能力）
├── routers/
│   ├── ledger.py      # 42 端点
│   ├── admin_ledger.py#  6 端点
│   ├── im.py          # 29 端点 + 1 WebSocket
│   └── admin_im.py    #  6 端点
└── services/
    └── im_crud.py     # IM 未读数等复用逻辑
```

**冻结决策依据**（见 `contracts.py` 文档串）：
71 个端点占全站 19%，`im.py` 1,251 行、`ledger.py` 1,086 行，**零测试覆盖**，
维护成本与风险敞口与产出不成比例 → ① 冻结新需求 ② 抽独立子包 ③ 开关可整体关闭 ④ 表前缀隔离。

### 4.2 配置开关

`app/config.py`：

```python
ENABLE_IM     = os.environ.get("ENABLE_IM", "true").strip().lower() in ("1","true","yes","on")
ENABLE_LEDGER = os.environ.get("ENABLE_LEDGER", "true").strip().lower() in ("1","true","yes","on")
```

**默认均为 `true`（保持现状）**。设为 `false` 后对应路由**完全不注册**，端点消失。

### 4.3 挂载方式（`app/main.py`）

```python
# 用户端
if ENABLE_LEDGER:
    app.include_router(frozen_ledger.router, prefix="/api/ledger", tags=["个人账本"])
if ENABLE_IM:
    app.include_router(frozen_im.router,     prefix="/api/im",     tags=["即时通讯"])

# 后台（随各自开关）
if ENABLE_LEDGER:
    app.include_router(frozen_admin_ledger.router, prefix="/api/admin", tags=["管理后台-账本数据"])
if ENABLE_IM:
    app.include_router(frozen_admin_im.router,     prefix="/api/admin", tags=["管理后台-IM数据"])
```

> 路由内部已用 `require_user` 鉴权，**不挂全局 `user_auth_deps`**（避免重复校验）。

### 4.4 架构约束（import-linter 强制）

- 契约 `frozen-sealed`：**D1–D8 任何代码都不得 `from app.domains.frozen...`**，仅组合根 `app/main.py` 豁免
- 其它域需要本域能力时，只能经 `app.domains.frozen.contracts`（当前 `_EXPORTS = {}`，即**不提供任何能力**）
- 违反会在 pre-commit 的 import-linter 钩子中直接失败

### 4.5 数据隔离与迁移

| 项 | 账本 | IM |
| --- | --- | --- |
| 表前缀 | `db_ledger_*` | `db_im_*` |
| 建表迁移 | `app/migrations/versions/030_ledger_tables.py` | `app/migrations/versions/031_im_tables.py` |
| 建表方式 | `Base.metadata.create_all(..., tables=[...])`，幂等 | 同左 |
| 附加动作 | — | 幂等为 `users` 表补 `avatar`/`points`/`is_online`/`last_seen` 四列 |

两前缀使未来**独立部署为单独产品**时的数据拆分成本极低。

---

## 五、已知缺口与风险

| # | 缺口 | 现状 | 影响 |
| --- | --- | --- | --- |
| 1 | **自动化测试 0 覆盖** | `tests/` 无 `test_ledger*.py` / `test_im*.py`；`ROADMAP.md` 明载「IM（29 端点）、账本（42 端点）尚未纳入自动化」 | 83 个端点无任何回归保护，改动即高风险 |
| 2 | **学生端（web）无 UI** | `web/src/views/` 无 LedgerView / IMView；`appOptions.js` 无入口 | 功能只有 API，学生完全看不到。web 中出现的 `ledger` 均为 `/api/pet/ledger`、`/api/diamond/ledger`（宠物币/钻石流水，属 D5/D7），与本模块无关 |
| 3 | **后台只支持查看+删除** | `Manage.vue` 无增删改 | 运营兜底能力有限 |
| 4 | **周期交易无定时触发** | 仅 `POST /recurring/run-due` 手动触发，未见 scheduler 挂载 | 房租/订阅类自动记账实际不会自动执行 |
| 5 | **文档口径偏差** | 07 实施方案记账本 11 表，实测 10 表 | 口径不一致，待核对统一 |
| 6 | **红包积分与钻石体系未打通** | 红包用 `users.points`，交易域用 `diamond_accounts` | 两套虚拟资产并行，存在对账风险 |

---

## 六、附：完整端点速查

### 账本（48 = 42 用户端 + 6 后台）

<details>
<summary>展开</summary>

**账户管理**　`POST|GET /api/ledger/users/{uid}/accounts/`　`PUT|DELETE /api/ledger/users/{uid}/accounts/{id}`
**分类管理**　`POST|GET /api/ledger/users/{uid}/categories/`　`PUT|DELETE .../categories/{id}`
**地点管理**　`POST|GET /api/ledger/users/{uid}/locations/`　`PUT|DELETE .../locations/{id}`
**商户管理**　`POST|GET /api/ledger/users/{uid}/merchants/`　`PUT|DELETE .../merchants/{id}`
**人员管理**　`POST|GET /api/ledger/users/{uid}/persons/`　`PUT|DELETE .../persons/{id}`
**项目管理**　`POST|GET /api/ledger/users/{uid}/projects/`　`PUT|DELETE .../projects/{id}`
**记账管理**　`POST|GET /api/ledger/users/{uid}/transactions/`　`GET|PUT|DELETE .../transactions/{id}`
**统计分析**　`GET /api/ledger/users/{uid}/statistics/{summary|category|monthly|budget}`
**周期交易**　`POST|GET /api/ledger/users/{uid}/recurring/`　`PUT|DELETE .../recurring/{id}`　`POST .../recurring/{id}/toggle`　`POST /api/ledger/recurring/run-due`
**财务报告**　`GET /api/ledger/reports/summary?period=weekly|monthly|yearly`
**导入导出**　`GET /api/ledger/users/{uid}/export/csv`　`POST /api/ledger/users/{uid}/import/csv`
**后台**　`GET|DELETE /api/admin/ledger/{bills|accounts|categories}[/{id}]`

</details>

### IM（36 = 29 用户端 + 1 WebSocket + 6 后台）

<details>
<summary>展开</summary>

**好友**　`POST /api/im/friends/add`　`GET /api/im/friends`　`POST /api/im/friends/accept/{id}`　`GET /api/im/friends/pending`　`POST|DELETE /api/im/friends/{uid}/block`　`GET /api/im/friends/blocked`
**会话**　`POST /api/im/chats`　`GET /api/im/chats`　`GET /api/im/chats/{chat_id}/messages`
**群成员**　`POST /api/im/chats/{chat_id}/members`　`DELETE .../members/{uid}`　`GET .../members`　`POST /api/im/chats/{chat_id}/leave`
**群公告**　`PUT|GET /api/im/chats/{chat_id}/announcement`
**消息**　`PUT|DELETE /api/im/messages/{id}`　`POST /api/im/messages/{id}/recall`　`POST /api/im/messages/{id}/read`　`GET /api/im/messages/unread-count`
**红包**　`POST /api/im/red-packets`　`POST /api/im/red-packets/{id}/claim`　`GET /api/im/red-packets/{id}/claims`
**用户**　`GET|PUT /api/im/users/me`　`GET /api/im/users/search`
**文件**　`POST /api/im/upload/file`
**健康检查**　`GET /api/im/health`
**WebSocket**　`WS /api/im/ws/chat?token=...`
**后台**　`GET|DELETE /api/admin/im/{chats|friendships|red-packets}[/{id}]`

</details>

---

## 七、维护约定

- 本模块处于**冻结状态**，新增需求前须先解冻 D9（改 `.importlinter`、补测试、建前端）。
- 若决定下线：将 `ENABLE_IM` / `ENABLE_LEDGER` 置为 `false` 即可，表数据保留待处置。
- 若决定独立部署：按 `db_im_*` / `db_ledger_*` 前缀整库导出即可，代码已在独立子包内。
- 数字口径以代码实测为准；修改后同步更新本文档与 `docs/INDEX.md`。
