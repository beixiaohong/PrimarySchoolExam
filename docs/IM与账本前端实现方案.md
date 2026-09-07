# IM 与账本「前端 + 后台管理」功能说明文档

> **文档定位**：实现前的**需求基线与技术设计**，不含代码实现。
> 目标：为已冻结的 D9 域（个人账本 + 即时通讯）补齐**学生端 Web 页面**与**后台管理能力**。
> 编写日期：2026-09-07　状态：**已确认（6 项决策已拍板，可进入开发）**
> 关联文档：[IM与账本功能产品文档](./IM与账本功能产品文档.md)（现状规格）

---

## 〇、决策记录（2026-09-07 已确认）

| # | 议题 | **决策** | 对方案的影响 |
| --- | --- | --- | --- |
| D1 | 生产环境是否 HTTPS | **是** | ✅ 解除 R3 阻塞，`getUserMedia` 录音可正常上线，语音功能纳入本期 |
| D2 | 账本入口导航位置 | **挨着钱包** | 归入「成长与激励」组，紧邻 `wallet` 之后 |
| D3 | 周期交易是否自动执行 | **需要** | ⬆️ B7 由「可选/二期」升级为**本期必需**，需新增全量扫描脚本 + 挂载 `tools/scheduler.py` |
| D4 | 后台是否做敏感词过滤 | **需要** | 🆕 新增 G7 缺口与 B8/B9/B10 后端改动：词库表、实时拦截、命中审计、后台词库管理 |
| D5 | 红包积分与钻石是否打通 | **红包使用钻石** | 🔄 红包资产由 `users.points` 改为 **钻石体系**，涉及单位换算、退款、跨域调用（见 §4.6） |
| D6 | 语音是否后端统一转码 | **需要** | 🆕 新增 B2′：上传后统一转 MP3，需服务器部署 ffmpeg（见 §4.4） |

> 决策后的完整后端改动清单见 **§五**（B1–B12），实施计划已同步调整为 **§七**。

---

## 一、背景与现状

### 1.1 后端已具备（无需重写）

| 模块 | 用户端 API | 后台 API | 实时通道 |
| --- | --- | --- | --- |
| 账本 ledger | 42 端点（`/api/ledger/*`） | 6 端点（`/api/admin/ledger/*`） | — |
| IM | 29 端点（`/api/im/*`） | 6 端点（`/api/admin/im/*`） | WebSocket `/api/im/ws/chat?token=` |

数据模型完备（账本 10 表 / IM 7 表）、业务规则清晰（余额联动、拼手气红包、已读回执等），
详见 [IM与账本功能产品文档](./IM与账本功能产品文档.md)。

### 1.2 当前缺口（本次要补的）

| # | 缺口 | 现状 | 本次目标 |
| --- | --- | --- | --- |
| G1 | **学生端（web）无任何页面** | `web/src/views/` 无 LedgerView / IMView；`nav.js` 无入口 | 新增 2 个一级页面 |
| G2 | **无文件上传能力** | 全仓 `web/src` 零 `FormData`/`upload` 调用 | 图片 + 语音上传 |
| G3 | **无录音能力** | 无 `MediaRecorder`/`getUserMedia` | 语音消息录制 |
| G4 | **后端上传白名单无音频** | `ALLOWED_MIME_TYPES` 仅 image/pdf/office，**无 `audio/*`** | 补音频 MIME |
| G5 | **后台仅查看+删除** | `Manage.vue` 6 tab，无增删改、无统计 | 升级为完整管理 |
| G6 | **零自动化测试** | 无 `test_ledger*` / `test_im*` | 本期补关键路径冒烟 |
| G7 | **无内容安全过滤**（D4 决策新增） | 全仓无敏感词模块，消息即发即存 | 词库 + 实时拦截 + 命中审计 |
| G8 | **周期交易不会自动执行**（D3 决策新增） | 仅 `POST /recurring/run-due` 手动触发，且**按当前登录用户** | 全量扫描脚本 + 定时调度 |
| G9 | **语音格式不统一**（D6 决策新增） | 浏览器原生 webm/mp4 各异，原样存储 | 后端统一转码 MP3 |

---

## 二、目标与非目标

### 2.1 本期目标（In Scope）

**账本**
- ✅ 快速记账：支出 / 收入 / 转账三种类型
- ✅ 六维度挂接：分类、账户、地点、商户、人员、项目
- ✅ 账单列表：多维筛选 + 分页
- ✅ 分析看板：收支概览、分类占比、月度趋势、项目预算执行率
- ✅ 账户管理：增删改查 + 余额展示
- ✅ 分类管理：三级分类维护
- ✅ 周期交易：**自动执行**（每日凌晨调度，D3）+ 手动补跑
- ✅ 后台：跨用户账单查询、统计看板、数据维护

**IM**
- ✅ 单聊（私聊）
- ✅ 群聊（建群、加人、踢人、退群、群公告、群成员）
- ✅ 消息类型：**文字、图片、语音**（明确不含音视频通话；语音由后端统一转码 MP3，D6）
- ✅ 好友体系：添加、接受、好友列表、拉黑/解除
- ✅ 实时收发：WebSocket 长连接 + 断线重连
- ✅ 已读回执 + 未读数
- ✅ 消息撤回 / 编辑 / 删除
- ✅ **内容安全**：敏感词实时拦截 + 命中审计 + 后台词库维护（D4）
- ✅ 红包：以**钻石**为资产（D5），发 / 抢 / 领取记录 / 过期原路退回
- ✅ 后台：会话/消息审计、好友关系、红包管理、敏感词管理

### 2.2 非目标（Out of Scope）

| 项 | 原因 |
| --- | --- |
| 音视频通话 | 用户明确排除；且需 WebRTC/信令服务，成本量级不同 |
| 移动端 App / 小程序 | 本期仅 Web（含移动端响应式） |
| 消息漫游多端同步 | 单端已读回执即可满足 |
| 红包 / 钻石提现 | D5 决策后红包走钻石，钻石是平台内虚拟资产（AI 扣费用），**非现金、不支持提现** |
| 账本多人协作账 | 数据模型按 `user_id` 隔离，不支持共享账本 |
| AI 自动记账 / 语音识别记账 | 后期可选，本期人工录入 |
| 解冻 D9 域 | 前端为**新增**而非改造域内逻辑；后端仅补必要的音频 MIME（G4） |

---

## 三、账本功能设计

### 3.1 页面结构

新增 `web/src/views/LedgerView.vue`，采用项目既有的 **「壳 provide + View inject」** 模式：

```
LedgerView.vue
├── Tab 1：记一笔      —— 快速记账表单
├── Tab 2：账单         —— 列表 + 多维筛选
├── Tab 3：分析         —— 统计看板（4 张卡）
└── Tab 4：设置         —— 账户 / 分类 / 地点 / 商户 / 人员 / 项目管理
```

**接入点改动清单**

| 文件 | 改动 |
| --- | --- |
| `web/src/views/LedgerView.vue` | **新增**：`inject: ['appCtx']`，业务逻辑放 `web/src/logic/ledger.js` |
| `web/src/logic/ledger.js` | **新增**：账本专属逻辑（mixin 展开到 App 实例，与 `appOptions.js` / `parent.js` 同构） |
| `web/src/App.vue` | 加 `<ledger-view v-if="tab==='ledger'"></ledger-view>` |
| `web/src/main.js` | `app.component('LedgerView', LedgerView)` |
| `web/src/nav.js` | 「成长与激励」组中**紧随 `wallet` 之后**插入 `{ tab: 'ledger', label: '记账本', icon: 'ledger' }`（D2 决策：挨着钱包）；`AppIcon.vue` 补 `ledger` 图标 |
| `web/src/AppIcon.vue` | 新增 `ledger` 内联 SVG（与 `wallet` 同风格） |

> 📌 **移动端不进 TabBar**：`TABBAR` 固定 6 项已满，账本仅从侧边栏进入，避免挤压既有入口。
> 具体插入位置（`web/src/nav.js:38` 的 `wallet` 之后）：
> ```js
> { tab: 'wallet', label: '钱包', icon: 'wallet' },
> { tab: 'ledger', label: '记账本', icon: 'ledger' },   // ← 新增
> ```

> ⚠️ 遵循既有约定：View 自身**零业务 data/methods**，全部委托 `appCtx`。

### 3.2 Tab 1 · 记一笔

**表单字段**

| 字段 | 控件 | 必填 | 说明 |
| --- | --- | --- | --- |
| 交易类型 | 三选一按钮组：支出 / 收入 / 转账 | ✅ | 决定后续字段显示 |
| 金额 | 数字输入（单位：元，两位小数） | ✅ | 提交时 ×100 转分 |
| 分类 | 级联选择（一级 > 二级 > 三级） | ✅ | 按类型过滤 `category_type` |
| 账户 | 下拉（支出/转账=付款账户；收入=收款账户） | ✅ | 转账时显示**两个**下拉 |
| 地点 | 下拉（可空）+ 「+ 新建」 | — | |
| 商户 | 下拉（可空）+ 「+ 新建」 | — | |
| 人员 | 下拉（可空）+ 「+ 新建」 | — | |
| 项目 | 下拉（可空） | — | 选后实时提示该项目预算执行率 |
| 备注 | 文本 | — | |
| 交易时间 | 日期时间选择器，默认当前 | ✅ | |

**交互要点**
- 金额输入用 `AntiCheatInput.vue`（项目既有组件，防 IME 联想）
- 常用分类做「最近使用」快捷区（本地 `localStorage` 缓存最近 6 个）
- 提交成功后：Toast 提示 + 清空表单（保留类型）+ 刷新账户余额
- 转账类型下 `from_account` / `to_account` 不可相同，前端校验

**调用**：`POST /api/ledger/users/{user_id}/transactions/`
> `user_id` 取 `appCtx.user`；后端自动联动账户余额（BR-L1）。

### 3.3 Tab 2 · 账单

- **筛选栏**：时间范围（本月/上月/近 3 月/自定义）、类型、分类、账户、项目、金额区间、关键词（备注）
- **列表**：日期分组，每行显示 分类标签 / 金额（支出红、收入绿）/ 账户 / 备注 / 时间
- **操作**：编辑（跳转记一笔预填）、删除（二次确认 + 余额回滚说明）
- **分页**：每页 20，滚动加载

**调用**：`GET /api/ledger/users/{user_id}/transactions/`（筛选参数按后端现有 query 传）

### 3.4 Tab 3 · 分析

四张卡片，图表**手写 SVG + CSS**（项目无图表库，`web/package.json` 仅 vue/vue-router/pinia/html2canvas；
现有 `StatsView.vue` 即用 `.progress` + `width:%` 实现，保持风格一致）：

| 卡片 | 数据来源 | 呈现 |
| --- | --- | --- |
| **收支概览** | `GET /statistics/summary` | 4 个数字块：本期收入 / 支出 / 结余 / 总余额；支出红、收入绿（中国习惯） |
| **分类占比** | `GET /statistics/category` | 手写 SVG 环形图（Top 6 + 其他），下方图例含金额与占比 |
| **月度趋势** | `GET /statistics/monthly` | 手写 SVG 双柱图（收入/支出），近 6–12 个月，支持 hover 显示数值 |
| **预算执行** | `GET /statistics/budget` | 每个项目一行：名称 / 预算 / 已用 / 进度条；超支标红 |

**交互**
- 顶部周期切换：本月 / 近 3 月 / 本年 / 自定义
- 环形图扇区点击 → 跳转到账单列表并按该分类筛选
- 空数据态：引导「去记一笔」

### 3.5 Tab 4 · 设置

六个子区块，均为标准「列表 + 新增/编辑/删除」：

账户（含余额） / 分类（三级） / 地点 / 商户 / 人员 / 项目（含预算）

**周期性交易**（D3 决策：**本期纳入，自动执行**）

前端：列表展示（名称 / 金额 / 频率 / 启用开关 / **上次执行** / **下次执行**）+ 手动「立即补跑」按钮 + 执行失败提示。

> ⚠️ **关键实现约束**：现有 `POST /recurring/run-due`（`ledger.py:925`）依赖
> `current_user` 登录态，**只处理调用者本人的到期交易**，调度器无法直接调用它。

**后端配套（详见 §五 B7/B8）**

1. 在 frozen 域内新增**领域服务函数** `run_due_recurring_all(db)`：遍历全量
   `RecurringTransaction`（`is_active=True AND next_run <= now`），逐条生成 Bill、
   调用既有 `_adjust_balance` 联动余额、推进 `next_run`。
   - **复用**现有 `_adjust_balance` / `_advance_next_run`，不重写业务规则
   - **幂等**：执行后 `next_run` 即被推进，重复执行不会重复生成账单
   - 单条失败跳过并记日志，不中断整批
2. 新增脚本 `tools/run_due_recurring.py`：开一次短会话调用上述函数，打印
   `{scanned, processed, failed}` 供 crontab 日志排查。
3. `tools/scheduler.py` 的 `JOBS` 追加（遵循项目约定：批量任务排凌晨）：

```python
{
    "name": "ledger_recurring_daily",
    "kind": "daily",
    "at": "01:00",
    "valid_from": "2026-09-08",
    "valid_until": None,
    "max_runs": None,
    "weekday": None,
    "command": ["tools/run_due_recurring.py"],
    "timeout": 600,
},
```

> 线上 crontab 已 `*/15` 分钟轮询 `tools/scheduler.py`，新增任务无需改 crontab。

### 3.6 后台管理（admin）

现有 `admin/src/views/Manage.vue`「账本 · IM 管理」仅 6 个只读+删除 tab。
**升级方案**：拆为两个独立页面。

**新增 `admin/src/views/LedgerAdmin.vue`**

| Tab | 内容 | 新增端点需求 |
| --- | --- | --- |
| 数据看板 | 平台账本总览：用户数、账单数、总收支、活跃趋势 | 需新增统计端点 |
| 账单管理 | 跨用户查询（按用户/时间/类型/金额筛选）+ 查看 + 删除 | 现有 6 端点 |
| 账户管理 | 跨用户账户列表 + 删除 | 现有 6 端点 |
| 分类管理 | 分类列表 + 删除 | 现有 6 端点 |
| **用户账本** | 输入 user_id 查看该用户完整账本（只读穿透） | 复用现有端点 |

**新增 `admin/src/views/ImAdmin.vue`**

| Tab | 内容 | 新增端点需求 |
| --- | --- | --- |
| 会话管理 | 会话列表（类型/成员数/创建者）+ 查看消息 + **解散会话** | 现有 6 端点 |
| **消息审计** | 按关键词/用户/时间检索消息；**违规消息删除**（内容治理刚需） | **需新增消息检索端点** |
| **敏感词库**（D4） | 词库 CRUD（增/改/停用/删）+ 按分类筛选 + 批量导入 | **需新增词库端点** |
| **命中记录**（D4） | 命中列表（用户/词/原文/动作/时间）+ 按用户聚合统计 + Top 词排行 | **需新增命中查询端点** |
| 好友关系 | 好友关系列表 + 删除 | 现有 6 端点 |
| 红包管理 | 红包列表（**钻石**金额/状态/过期）+ 领取记录 + 删除 + **手动退回** | 现有 6 端点 + 退回端点 |
| **用户封禁** | 按 user_id 禁用 IM 发言能力 | **需新增封禁字段/端点** |

> 后台页面必须遵循 [axios 解包约定](./../.workbuddy/memory/MEMORY.md)：
> `const { data } = await api.get(...)`，**不可** `const d = await api.get(...)`。

---

## 四、IM 功能设计

### 4.1 页面结构

新增 `web/src/views/ImView.vue`，三栏布局（桌面端）/ 单栏堆叠（移动端）：

```
┌─────────────┬──────────────────────────┬──────────────┐
│ 会话列表     │  消息区                    │  群信息/好友  │
│ (ChatList)  │  (MessagePane)            │  (SidePanel) │
│             │                           │              │
│ · 搜索框     │  ┌────────────────────┐   │  群聊：      │
│ · 会话项     │  │ 消息气泡流          │   │  · 成员列表  │
│   头像/名称  │  │ (文字/图片/语音)     │   │  · 群公告    │
│   最后消息   │  └────────────────────┘   │  · 退出群聊  │
│   未读角标   │  ┌────────────────────┐   │              │
│             │  │ 输入区：文本/图片/语音│   │  私聊：      │
│ Tab:        │  └────────────────────┘   │  · 好友资料  │
│ 消息 | 好友  │                           │  · 拉黑      │
└─────────────┴──────────────────────────┴──────────────┘
```

**接入点改动清单**

| 文件 | 改动 |
| --- | --- |
| `web/src/views/ImView.vue` | **新增**：`inject: ['appCtx']` |
| `web/src/logic/im.js` | **新增**：IM 业务逻辑 + WebSocket 客户端封装 |
| `web/src/components/im/ChatList.vue` | 会话列表 |
| `web/src/components/im/MessagePane.vue` | 消息流 |
| `web/src/components/im/MessageInput.vue` | 输入区（文本/图片/语音） |
| `web/src/components/im/VoiceBubble.vue` | 语音消息气泡（播放 + 时长 + 波形） |
| `web/src/App.vue` | 加 `<im-view v-if="tab==='im'"></im-view>` |
| `web/src/main.js` | 全局注册上述组件 |
| `web/src/nav.js` | 建议「我的」组**首位**：`{ tab: 'im', label: '消息', icon: 'im', badge: 'im' }`（带未读角标，需显眼）；`AppIcon.vue` 补 `im` 图标 |
| `web/src/AppIcon.vue` | 新增 `im` 内联 SVG |

> ❓ IM 入口位置本次未决策，上面为**建议值**（消息带未读数，宜放在显眼处）。
> 若希望与「钱包/账本」同组，可改放「成长与激励」组；开工前确认一次即可。

### 4.2 单聊（私聊）

**发起路径**
1. 好友 Tab → 点击好友 → 进入/创建私聊
2. 搜用户（`GET /api/im/users/search`）→ 加好友（`POST /api/im/friends/add`）→ 对方接受后开聊

**好友状态流转**

```
（无）──add──▶ pending ──accept──▶ accepted
                  │                    │
                  └──(拒绝/删除)        └──block──▶ blocked ──unblock──▶ 解除
```

**私聊会话**：`POST /api/im/chats` 传 `chat_type=private` + 成员；
前端需做「与同一好友只存在一个私聊会话」的本地去重。

### 4.3 群聊

| 能力 | 操作 | 端点 |
| --- | --- | --- |
| 建群 | 选好友 → 设群名/头像/简介 | `POST /api/im/chats`（`chat_type=group`） |
| 加人 | 群信息面板 → 添加成员 | `POST /api/im/chats/{id}/members` |
| 踢人 | 成员列表 → 移除（**仅群管理员**） | `DELETE /api/im/chats/{id}/members/{uid}` |
| 退群 | 群信息面板底部 | `POST /api/im/chats/{id}/leave` |
| 群公告 | 管理员编辑，成员只读 | `PUT` / `GET /api/im/chats/{id}/announcement` |
| 成员列表 | 右侧面板，标注管理员 | `GET /api/im/chats/{id}/members` |

**权限规则**：`GroupMember.is_admin` 决定踢人、改公告、改群名权限；前端按此禁用按钮。

### 4.4 消息类型（文字 / 图片 / 语音）

| 类型 | 前端实现 | 上传 | 后端现状 |
| --- | --- | --- | --- |
| **文字** `text` | 输入框 + Enter 发送 / Shift+Enter 换行 | 否 | ✅ 就绪 |
| **图片** `image` | `<input type="file" accept="image/*">`；**Canvas 压缩**（长边 ≤1600px，质量 0.8）后上传 | `POST /api/im/upload/file`（FormData） | ✅ 就绪（jpeg/png/gif/webp，≤10MB） |
| **语音** `voice` | `MediaRecorder` 录制 → Blob → 上传 | `POST /api/im/upload/file`（FormData） | ❌ 需补 `audio/*` MIME + **统一转码 MP3（D6）** |

**语音消息细节**

| 项 | 方案 |
| --- | --- |
| 录音 API | `navigator.mediaDevices.getUserMedia({audio:true})` + `MediaRecorder` |
| 前端产物 | 优先 `audio/webm`（Chrome/Edge/Firefox）；Safari 降级 `audio/mp4`；以 `Blob.type` 上报 |
| 时长限制 | 最长 **60 秒**，到时自动停止；最短 1 秒，过短提示「说话时间太短」 |
| 交互 | 按住说话 / 上滑取消发送 / 松手发送；录制中显示计时与音量波形 |
| 后端转码（D6） | 统一转 **MP3**（单声道 44.1kHz / 64kbps），落盘 `.mp3`，库里 `file_path` 指向转码后文件 |
| 时长取值 | 以服务端 `ffprobe` 解析为准；转码不可用时回退前端上报的 `duration_ms` |
| 播放 | 气泡显示时长 + 播放按钮 + 简易波形条；点击播放，同列表互斥（同时只播一条） |
| 降级策略 | ffmpeg 缺失或转码失败 → **原样保存**原格式并在响应中带 `transcoded: false`；前端照常发送，`<audio>` 原生可播 webm/mp4，功能不中断 |
| 后端改动 | `ALLOWED_MIME_TYPES` 增加 `audio/webm` `audio/mp4` `audio/mpeg` `audio/ogg` `audio/wav`；音频单独限 **2MB**（转码前）/ 转码后约 480KB/60s |

**转码流程（必须遵守持连铁律）**

```
上传接口
 ├─ 1) 校验 MIME/大小 → 写临时文件                    [无 DB 会话]
 ├─ 2) 开短会话：登记消息/附件记录（status=processing）→ db.close()
 ├─ 3) 调 ffmpeg 子进程转码 + ffprobe 取时长           [⚠️ 外部阻塞，绝不持连]
 └─ 4) 再开短会话：回填 file_path / duration / size → commit
```

> 🚨 **项目红线**：ffmpeg 是外部阻塞调用，**绝不允许**在 `get_db` 会话期间执行
> （历史教训：持连做外部调用导致 QueuePool 耗尽、全站卡死，见 `267c32c`）。
> 必须按上面「分段短会话」模式落地。

**部署依赖**

- 服务器安装：`apt install -y ffmpeg`（需在 `deploy.sh` 中检测，缺失时打印醒目告警）
- 配置项：新增 `FFMPEG_PATH`（默认 `ffmpeg`），便于自定义路径
- 可选：`FFMPEG_TIMEOUT`（默认 15s），超时走降级分支

> ✅ **HTTPS 已确认（D1）**：生产为 HTTPS，`getUserMedia` 安全上下文满足，录音可正常上线。

**消息操作**

| 操作 | 规则 | 端点 |
| --- | --- | --- |
| 撤回 | 仅发送者，**2 分钟内**；气泡替换为「XX 撤回了一条消息」 | `POST /api/im/messages/{id}/recall` |
| 编辑 | 仅发送者，仅文本；气泡标注「已编辑」 | `PUT /api/im/messages/{id}` |
| 删除 | 仅发送者（自己侧不可见） | `DELETE /api/im/messages/{id}` |

> 「2 分钟内」为产品建议值，后端 `recall` 当前未做时限校验——若需强制，属后端改动。

### 4.5 实时通信（WebSocket）

**连接**：`ws(s)://<host>/api/im/ws/chat?token=<localStorage.zx_token>`

**客户端状态机**

```
disconnected ──connect──▶ connecting ──open──▶ connected
                              │                    │
                              └──fail──▶ retrying（指数退避 1s/2s/4s/8s，上限 30s）
                                             connected ──close/error──▶ retrying
```

**客户端 → 服务端**

| type | 载荷 | 触发 |
| --- | --- | --- |
| `message` | `chat_id` `content` `message_type` `file_path` `file_name` `file_size` | 发送任意消息 |
| `typing` | `chat_id` | 输入中（节流 3s 一次） |
| `read` | `chat_id` `message_id` | 进入会话 / 消息可见 |

**服务端 → 客户端**

| type | 处理 |
| --- | --- |
| `offline_summary` | 连接即推：`unread_counts` + `total` → 更新未读角标 |
| 消息广播 | 追加到对应会话消息流；若不在当前会话则未读 +1 |
| `red_packet_claimed` | 更新红包剩余个数；自己领取则刷新**钻石余额**（D5） |

**前端工程要点**
- 单例连接：封装在 `web/src/logic/im.js`，App 级维护，**不要**每个组件各建一条
- 页面切走不主动断开（保持在线态），应用卸载/登出才 `close`
- 心跳：每 30s 发一次 `typing` 或空 ping，防代理超时断连
- **乐观发送**：消息先上屏（status=sending），收到广播/回执后置为 sent；失败标红并提供重试
- 断线期间发送的消息进入本地队列，重连后按序补发

### 4.6 红包（D5 决策：资产由积分改为**钻石**）

#### 4.6.1 单位定义（关键）

| 系统 | 类型 | 单位 | 说明 |
| --- | --- | --- | --- |
| 红包表 `db_im_red_packets.total_amount` | `Integer` | **毫钻（mDM）** | 1 钻石 = **1000 毫钻**；保持整型，拼手气拆分精确求和 |
| 钻石账户 `diamond_accounts.balance` | `Float` | 钻石（2 位小数） | 既有体系，AI 扣费用 |

**换算**：`钻石 = total_amount / 1000`；`毫钻 = 钻石 × 1000`。
前端输入/展示一律用**钻石**（如 `1.00 钻石`），提交前 ×1000 转毫钻，回显时 ÷1000。

> 选「毫钻」而非直接改 Float 的理由：拼手气红包需把总额拆成 N 份且**各份之和必须精确等于总额**，
> 浮点会产生 0.01 级别的缺口；整型拆分可严格配平（沿用现有「最后一个领剩余全部」逻辑）。
> 也便于与项目既有的「金额用整型、禁止 Float」铁律对齐。

#### 4.6.2 发红包

- 入口：输入区「+」→ 红包 → 填**总钻石数** / 个数 / 祝福语 → `POST /api/im/red-packets`
- 前端校验：钻石余额充足（`GET /api/diamond/balance`）、个数 ≥1、**每份 ≥ 0.001 钻石（1 毫钻）**
- 服务端流程：
  1. `DiamondService.charge(db, uid, total_amount/1000, biz="im_red_packet", ref_id=<packet_id>)`
     —— ⚠️ 必须经 `app.domains.commerce.contracts` 调用（frozen → D7 跨域，`import-linter`
     白名单 `app.domains.** -> app.domains.*.contracts` 允许；**禁止**直连 `services/diamond.py`）
  2. 扣款成功再落 `RedPacket` 记录与红包消息；失败返回「钻石余额不足」，不产生脏数据
  3. `expires_at = now + 24h`（沿用 BR-IM2）

#### 4.6.3 抢红包

- 点击红包气泡 → `POST /api/im/red-packets/{id}/claim` → 展示抢到的钻石数
- 已过期 / 已领完 / **自己发的不可领**（BR-IM4）→ 按钮置灰并提示
- 入账：`DiamondService.grant(db, uid, claim_amount/1000, biz="im_red_packet_claim")`

> 🚨 **并发缺陷（必须修，见 §五 B11）**：现有 `claim` 逻辑是「读红包 → 判断剩余 → 扣减 → 写回」，
> **全程无行锁**，多人同时抢最后一个会超发。改用真资产（钻石）后属于**资损风险**。
> 修法：对 `RedPacket` 行加 `with_for_update()` 后再判断/扣减；或改为条件更新
> `UPDATE ... SET remaining_count = remaining_count - 1 WHERE id=? AND remaining_count > 0`
> 并按影响行数判定成败。

#### 4.6.4 过期原路退回（新增）

现状：24h 到期仅把状态置 `EXPIRED`，**剩余金额不退回发送者**。改用钻石后必须补：

- 新增服务函数 `expire_red_packets(db)`：扫描 `status=ACTIVE AND expires_at < now`，
  将 `remaining_amount` 通过 `DiamondService.grant(..., biz="im_red_packet_refund")` 退回 sender，
  状态置 `EXPIRED`，并记录退回流水
- 挂载调度器：`JOBS` 追加 `im_red_packet_expire`，`daily / at 01:10`（与账本周期交易错峰）
- 幂等：状态变更为 `EXPIRED` 后不再命中扫描条件

#### 4.6.5 对账与展示

- 对账口径以**红包表整型毫钻为准**：`已领之和 + 退回 + 剩余 == total_amount`
- `diamond_ledger` 落 Float 明细，`reason` 新增三值：`im_red_packet` / `im_red_packet_claim` / `im_red_packet_refund`
- 领取记录：`GET /api/im/red-packets/{id}/claims` → 头像 / 昵称 / **钻石数** / 时间
- 前端统一展示为钻石（如 `+0.52 钻石`），不再出现「积分」字样

#### 4.6.6 存量数据处理

上线前先查 `SELECT COUNT(*) FROM db_im_red_packets;`：
- 若 **0 行**（预期，IM 未启用过）→ 无需迁移，直接改字段语义
- 若有数据 → 需补迁移脚本：按「1 积分 = 1 毫钻」折算，或直接作废并退回（视业务决定）

> `users.points` 不再被红包使用；其余用途（如有）保持不变，本次不动。

### 4.7 内容安全 · 敏感词过滤（D4 决策新增）

面向小学生的产品，IM 是 UGC 入口，必须具备基础内容防线。

#### 4.7.1 词库模型

新增表（frozen 域内，IM 专属）：

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `db_im_sensitive_words` | `id` `word` `level` `category` `is_active` `created_at` `updated_at` | 词库；`level`: `reject`（拒绝发送）/ `replace`（替换为 `***`） |
| `db_im_sensitive_hits` | `id` `user_id` `chat_id` `word` `raw_content` `action` `created_at` | 命中记录，供后台审计与统计 |

#### 4.7.2 过滤范围与时机

| 输入面 | 是否过滤 | 备注 |
| --- | --- | --- |
| 单聊/群聊**文本消息** | ✅ | 主要场景 |
| 群名称 / 群公告 / 群简介 | ✅ | 建群、改公告时 |
| 红包祝福语 | ✅ | 发红包时 |
| 昵称 | ✅（可选） | 复用词库，建议一期先不动（影响面大） |
| 图片 | ❌ | 需图像识别，超出本期 |
| 语音 | ❌ | 需 ASR，超出本期；风险由「撤回 + 举报 + 人工审计」兜底 |

> ⚠️ **双通道都必须拦截**：REST `POST /api/im/messages` 与 **WebSocket `message` 帧**
> 是两条独立写入路径，只拦 REST 会被 WS 绕过。过滤函数须抽到领域服务层，两处共同调用。

#### 4.7.3 处理策略

- `level=reject`（**默认**）：拒绝发送，返回明确提示「消息包含不当内容，请修改后重试」，**不入库**
- `level=replace`：替换为等长 `***` 后入库，并记命中
- 命中即写 `db_im_sensitive_hits`（短会话，异步/事后写均可，不阻塞发送主流程）
- 连续命中可触发临时禁言（可选，二期）

#### 4.7.4 性能与实现

- 词库加载：模块级缓存（首次加载 + `is_active` 变更时失效），**不要每条消息查库**
- 匹配算法：词库量 < 1000 时简单遍历 `in` 即可；超过则上 DFA/Aho-Corasick
- 检测为纯 CPU 操作，可在 DB 会话内执行（不构成外部阻塞调用，不违反持连铁律）

#### 4.7.5 前端表现

- 发送被拒：输入框下方红色提示 + 保留已输入内容（不清空）
- 被替换：正常上屏，内容已打码
- 前端**不做**本地词库校验（词库需服务端可控、可热更新），仅展示服务端返回的错误

### 4.8 后台管理（admin）

见 §3.6 的 `ImAdmin.vue`。核心增量是**消息审计**（内容合规刚需）、**用户封禁**与**敏感词库维护**。

---

## 五、需改动的后端（按决策更新）

### 5.1 改动清单

| # | 改动 | 文件 | 必要性 | 来源 |
| --- | --- | --- | --- | --- |
| B1 | `ALLOWED_MIME_TYPES` 补 `audio/webm` `audio/mp4` `audio/mpeg` `audio/ogg` `audio/wav` | `frozen/routers/im.py:1206` | **必需** | G4 |
| B2 | 音频单独限流 2MB（现统一 10MB） | 同上 | 建议 | G4 |
| B3 | **语音统一转码 MP3**：ffmpeg 子进程 + ffprobe 取时长 + 降级分支 + `FFMPEG_PATH` 配置 | `frozen/routers/im.py`（上传接口） | **必需** | D6 / G9 |
| B4 | 服务器部署 ffmpeg（`deploy.sh` 检测并告警） | `deploy.sh` | **必需** | D6 |
| B5 | 后台消息检索端点（关键词/用户/时间） | `admin_im.py` 新增 | **必需** | 消息审计 |
| B6 | 后台账本统计端点（平台维度） | `admin_ledger.py` 新增 | 建议 | 数据看板 |
| B7 | IM 用户禁言字段与端点 | `im.py` + users 表 | 建议 | 治理 |
| B8 | `recall` 时限校验（2 分钟） | `im.py` | 可选 | AC-I6 |
| B9 | **周期交易全量扫描** `run_due_recurring_all(db)` + `tools/run_due_recurring.py` + `JOBS` 任务 | `frozen/services/`、`tools/scheduler.py` | **必需** | D3 / G8 |
| B10 | **红包改用钻石**：毫钻单位换算、`DiamondService.charge/grant`（**经 `commerce.contracts`**） | `frozen/routers/im.py:415-555` | **必需** | D5 |
| B11 | **红包并发行锁**（`with_for_update` 或条件更新） | 同 B10 | **必需（资损）** | D5 |
| B12 | **红包过期原路退回** + `JOBS` 任务 `im_red_packet_expire` | `frozen/services/`、`tools/scheduler.py` | **必需** | D5 |
| B13 | `diamond_ledger.reason` 扩三值：`im_red_packet` / `_claim` / `_refund` | `models/diamond.py` 注释 + 常量 | 建议 | D5 |
| B14 | **敏感词过滤**：2 张表 + 过滤服务 + REST/WS 双通道接入 | `frozen/models`、`frozen/services/` | **必需** | D4 / G7 |
| B15 | **敏感词后台端点**：词库 CRUD + 命中记录查询 + 统计 | `admin_im.py` 新增 | **必需** | D4 |
| B16 | 迁移 `062_im_sensitive.py`（建 2 张表 + 内置基础词库） | `app/migrations/versions/` | **必需** | D4 |

### 5.2 必跑校验

| 项 | 说明 |
| --- | --- |
| `import-linter` | B10/B12 会让 frozen 域 import `app.domains.commerce.contracts`。白名单 `app.domains.** -> app.domains.*.contracts` 允许该边；**但禁止直连 `services/diamond.py`**。改完必须跑 `lint-imports` 确认 `frozen-sealed` 与域独立契约均通过 |
| 持连铁律 | B3（ffmpeg）与 B12（退回）均含外部/批处理逻辑，须用「分段短会话」，**不得**在 `get_db` 会话内执行 |
| 迁移上线 | 新表随 `deploy.sh` 重启时 `run_migrations()` 自动执行，无需手工 |

> B1–B16 均属**冻结域内的增量补充**，不改动既有业务规则（余额联动、已读回执、红包拆分算法保持不变）。
> 其中 **B11（并发锁）与 B14（敏感词）是上线前的硬门槛**——前者是资损风险，后者是内容合规风险。

---

## 六、技术约束与风险

| # | 约束 / 风险 | 应对 |
| --- | --- | --- |
| R1 | **web 端无图表库** | 手写 SVG + CSS，与 `StatsView.vue` 风格一致；不引入依赖 |
| R2 | **web 端无上传/录音能力** | 从零实现 `FormData` 上传与 `MediaRecorder` 录音，抽为可复用工具 |
| R3 | ~~HTTPS 依赖（`getUserMedia`）~~ | ✅ **已解除（D1 确认生产为 HTTPS）**，录音可正常上线 |
| R4 | **audio 格式跨浏览器不一致** | 以 `Blob.type` 上报，后端按 MIME 存；播放端用 `<audio>` 原生兼容 |
| R5 | **WS 持有 DB 连接（项目红线）** | 后端现有实现已用短会话；前端不得在 WS 回调中触发长事务 |
| R6 | **账本数据按 user_id 隔离** | 前端统一取 `appCtx.user`；后台穿透查询需留审计日志 |
| R7 | **冻结域 import 约束** | 前端不受限；后端改动（B1–B5）须保持不向 D1–D8 暴露能力 |
| R8 | **零测试覆盖** | 本期至少补：账本 CRUD+统计、IM 发消息+上传、WS 连接 冒烟用例 |
| R9 | **移动端适配** | IM 三栏在 <768px 退化为「列表 → 会话」两级堆叠 |
| R10 | **未读数一致性** | 以服务端 `offline_summary` 为准，本地增量仅作 UI 乐观更新 |
| R11 | **ffmpeg 部署依赖**（D6） | 服务器需 `apt install -y ffmpeg`；`deploy.sh` 增加检测与醒目告警；缺失时走降级分支（原样存储），**功能不中断** |
| R12 | **红包资损**（D5） | B11 行锁为硬门槛；上线前用并发用例验证「N 人抢 M 个」不超发；上线后定期跑对账 SQL |
| R13 | **敏感词误杀**（D4） | 学习场景易误拦（如数学/生物用语）；词库需人工审校，**建议先 `replace` 观察一周再切 `reject`**；命中记录可复盘 |
| R14 | **周期任务漏执行 / 重复执行**（D3） | 靠 `next_run` 推进天然幂等；单条失败跳过不中断整批；日志输出 `scanned/processed/failed`；调度状态记 `tools/.scheduler_state.json` |
| R15 | **跨域调用合规**（D5） | frozen → commerce 必须走 `commerce.contracts`，改完跑 `lint-imports`；直连 `services/diamond.py` 会触发契约失败 |

---

## 七、实施计划（按决策调整为七期）

| 期 | 内容 | 交付物 | 前置后端项 | 依赖 |
| --- | --- | --- | --- | --- |
| **P1** | 账本 · 记账 + 账单 | `LedgerView.vue`（Tab1/2）、`logic/ledger.js`、导航接入（紧邻钱包） | — | 无 |
| **P2** | 账本 · 分析 + 设置 + 周期交易 | Tab3 分析（手写 SVG）、Tab4 六维管理、周期交易 UI | **B9**（全量扫描 + 脚本 + JOBS） | P1 |
| **P3** | IM · 文字 + 单聊 + 群聊 + **敏感词** | `ImView.vue` 三栏、WS 客户端、好友体系、过滤接入 | **B14 / B16**（词库表 + 过滤服务 + 迁移） | 无 |
| **P4** | IM · 图片 + 语音 | 上传/录音组件、语音气泡、WS 状态机完善 | **B1 / B2 / B3 / B4**（音频 MIME + 转码 + ffmpeg） | P3 |
| **P5** | IM · 红包（钻石） | 发/抢/记录/退回展示 | **B10 / B11 / B12 / B13**（换算 + 行锁 + 退回） | P3 |
| **P6** | 后台管理增强 | `LedgerAdmin.vue` / `ImAdmin.vue`（含敏感词库、命中记录） | **B5 / B6 / B7 / B15** | P2 + P3 |
| **P7** | 测试补齐 | `tests/test_ledger_web.py`、`tests/test_im_web.py`、红包并发用例 | — | P1–P5 |

**并行建议**

- **P3 可与 P1/P2 并行**（不同模块、不同文件，无冲突）
- P4 依赖 P3 的 WS 与消息流；P5 依赖 P3 的消息气泡框架
- **P6 建议紧跟 P3**：敏感词库要有后台维护入口，否则词库只能改库，运营不可持续

**上线顺序硬门槛**

- P3 完成前不得开放 IM 入口（无敏感词过滤 = 内容合规风险）
- P5 完成前不得开放红包入口（无行锁 = 资损风险）
- 建议用 `ENABLE_IM` / `ENABLE_LEDGER` 开关分模块灰度：账本可先全量，IM 待 P5 完成再开

---

## 八、验收标准

### 账本
- [ ] AC-L1 记一笔（支出/收入/转账）后，对应账户余额正确变动，账单列表可见
- [ ] AC-L2 转账时付款/收款账户均正确变动，且两者不可相同
- [ ] AC-L3 账单按时间/类型/分类/账户/项目筛选结果正确
- [ ] AC-L4 分析页四张卡数据与筛选周期一致；分类占比合计 100%
- [ ] AC-L5 项目预算执行率超支标红
- [ ] AC-L6 金额全程整型分，无浮点误差（如 0.1+0.2 场景）
- [ ] AC-L7 六维设置页增删改查均生效
- [ ] AC-L8 移动端（375px）布局不破版
- [ ] AC-L9 **周期交易到期自动生成账单**，`next_run` 按频率正确推进（D3）
- [ ] AC-L10 调度任务**重复执行不产生重复账单**（幂等），单条失败不中断整批
- [ ] AC-L11 账本入口出现在「成长与激励」组、`wallet` 正后方（D2）

### IM
- [ ] AC-I1 单聊可收发文字消息，延迟 < 1s
- [ ] AC-I2 群聊可建群/加人/踢人/退群/改公告，权限按 `is_admin` 生效
- [ ] AC-I3 图片消息可发送并正确展示（含压缩）
- [ ] AC-I4 语音消息可录制（≤60s）、上传、播放，时长显示正确
- [ ] AC-I5 断网重连后自动恢复，未读数与服务端一致
- [ ] AC-I6 消息撤回（2 分钟内）/编辑/删除行为符合预期
- [ ] AC-I7 红包以**钻石**发放：总额/份数与毫钻换算正确（1 钻石 = 1000 毫钻），剩余实时更新，不可自领（D5）
- [ ] AC-I7a **并发 N 人抢 M 个红包不超发**，最后一个领取者拿到全部剩余（B11 行锁验证）
- [ ] AC-I7b 24h 过期后剩余钻石**原路退回**发送者，且只退一次（幂等）
- [ ] AC-I7c 对账校验：`已领之和 + 退回 + 剩余 == total_amount`（整型毫钻，无浮点误差）
- [ ] AC-I8 未读角标在进入会话后清零
- [ ] AC-I9 同时只播放一条语音
- [ ] AC-I10 移动端退化为两级堆叠，体验可用
- [ ] AC-I11 语音上传后服务端返回 **MP3**，Chrome / Safari 均可播放（D6）
- [ ] AC-I12 **ffmpeg 缺失时语音仍可发送**（降级原样存储），前端不报错
- [ ] AC-I13 含敏感词消息被拦截，**REST 与 WebSocket 双通道均生效**（D4）
- [ ] AC-I14 敏感词命中记录落库，后台「命中记录」页可见
- [ ] AC-I15 语音转码全程未长时间持有 DB 连接（连接池无 Timeout 告警）

### 后台
- [ ] AC-A1 账本后台可按用户/时间/类型筛选并查看/删除账单
- [ ] AC-A2 IM 后台可检索消息并删除违规内容
- [ ] AC-A3 所有后台列表均有数据（无 axios 解包错误导致的空表）
- [ ] AC-A4 后台操作写入审计日志
- [ ] AC-A5 **敏感词库可增/改/停用/删除**，停用后立即不再拦截（D4）
- [ ] AC-A6 命中记录可按用户 / 时间 / 词查询，Top 词统计正确

### 工程
- [ ] AC-E1 新增/修改文件符合「壳 provide + View inject」模式
- [ ] AC-E2 `import-linter` 通过
- [ ] AC-E3 关键路径冒烟用例通过（账本 CRUD、IM 发消息、WS 连接、红包并发）
- [ ] AC-E4 `deploy.sh` 重建 `web/dist` 与 `admin/dist` 后功能生效
- [ ] AC-E5 服务器已安装 **ffmpeg**，`deploy.sh` 检测结果通过（D6）
- [ ] AC-E6 `import-linter` 通过：frozen → commerce 仅走 `contracts`，无直连（D5）

---

## 九、遗留待定事项（低阻塞，开工前确认即可）

原 6 项议题已于 2026-09-07 全部拍板（见 §〇）。以下为**新衍生、尚未定**的小项：

| # | 事项 | 建议 | 影响 |
| --- | --- | --- | --- |
| 1 | **IM 入口导航位置**（本次未问） | 「我的」组首位，带未读角标 | 低：仅 `nav.js` 一行位置 |
| 2 | **敏感词默认策略**：先 `replace` 还是直接 `reject` | 先 `replace` 观察一周，再切 `reject`（防误杀） | 中：影响用户体验与词库审校节奏 |
| 3 | **昵称是否纳入敏感词过滤** | 一期不做（影响面大，存量昵称需清洗） | 低 |
| 4 | **存量红包数据**如何处理 | 上线前查 `db_im_red_packets` 行数；预期 0 行，无需迁移 | 低 |
| 5 | **红包最小单位**：0.001 钻石是否够用 | 若运营希望更小，可改 1 钻石 = 10000 单位（字段仍 Integer） | 低：仅换算常量 |
| 6 | **内置基础词库来源** | 需运营/合规提供初始词表；技术侧提供批量导入接口 | 中：影响 P3 能否验收 |

> 以上均不阻塞 P1（账本记账 + 账单）开工。
