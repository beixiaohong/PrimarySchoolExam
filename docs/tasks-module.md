# 任务系统模块说明（app/routers/tasks）

> 智学学堂「每日任务」子系统 —— 3 强制 + 3 可选双轨制、自定义任务、补签卡、完成确认。
> 本文档描述 **2026-09 整理后**的模块结构（原 832 行单文件 `common.py` 已拆分为分层包）。

## 一、模块总览

任务系统代码全部收敛在 `app/routers/tasks/` 包内，对外路由统一为
`/api/tasks/*` 与 `/api/task-confirm/*`（与整理前完全一致，调用方零影响）。

| 文件 | 职责 | 说明 |
| --- | --- | --- |
| `constants.py` | 常量与纯函数 | 学科、强制任务表、可选任务池、可配置项、配额键、目标上下限、工具函数 |
| `service.py` | 底层可复用小函数 | 设置读取、学习开关、今日任务行保障、全勤/连续天数、补签卡余额/发放、payload 组装 |
| `progress.py` | 进度计算 | 单任务进度、今日任务可行性、可选新卷、单词/古诗文完成度 |
| `makeup_service.py` | 补签卡业务操作层 | 用卡补签、家长确认/拒绝、待确认列表（一次业务操作粒度） |
| `settings.py` | 配置端点 | GET/POST `/api/tasks/settings` |
| `daily.py` | 今日任务端点 | GET `/api/tasks/daily`、孩子提交、家长确认、claim |
| `makeup.py` | 补签卡端点（薄路由） | `/api/tasks/makeup/use\|balance\|confirm\|pending` |
| `custom.py` | 自定义任务端点 | 孩子端 `/custom`（**DEPRECATED**）+ 家长端 `/custom-task` |
| `confirm.py` | 完成确认端点 | `/api/task-confirm/create\|list\|resolve`（原独立模块迁入） |
| `__init__.py` | 包入口 | 定义共享 `router`、触发子模块注册、挂载 custom、导出 confirm_router |

分层原则：

```
路由层（薄壳：参数解析 + 鉴权 + 转发）
   │  settings.py / daily.py / makeup.py / custom.py / confirm.py
   ▼
业务层（一次操作粒度，可复用）
   │  makeup_service.py（补签卡业务）
   ▼
底层函数（小函数粒度，跨端点复用）
      service.py / progress.py / constants.py
```

## 二、业务规则

### 双轨制（3 强制 + 3 可选）

- **强制任务**：每科 1 条固定（数学练习 / 古诗文背诵 / 学单词），三科全完成 = 当天全勤。
- **可选任务**：系统每日从任务池随机抽 3 条，全部完成奖励 1 张补签卡；不可更换。
- 家长可在「任务设置」调整目标数/启用开关/强制任务搭配（`MANDATORY_CHOICES`）、
  背诵/单词每日配额（`QUOTA_KEYS`）、学习开关（`STUDY_FLAG_KEYS`）。

### 补签卡

- **获得**：完成当天全部可选任务 → 原子发放（`_grant_makeup_card`，按 `last_grant_date` 去重防刷）。
- **使用**：补签某天（立即生效，默认 confirmed）或补签任意每日任务（走 pending 待家长确认）。
- **状态机**：`pending → confirmed / rejected`；reject 退卡（余额 +1、已用 -1）。
- 连续天数统计把「已生效补签」视为全勤日（`_streak` / `_has_makeup_card`）。

### 完成确认（task-confirm）

- 孩子完成背诵等任务后提交 `/create` → 生成 `pending` 记录（同类型当天去重）。
- 家长在首页「完成确认」区块通过 `/resolve` 确认（`confirm`）或拒绝（`reject`，必填理由）。
- **状态机与补签卡统一**：`pending → confirmed / rejected`（2026-09 由 approved 改名，见 051 迁移）。

### 自定义任务（两套，务必分清）

| | 家长端 `/custom-task`（现行） | 孩子端 `/custom`（**DEPRECATED**） |
| --- | --- | --- |
| 模型 / 表 | `ParentCustomTask` / `parent_custom_tasks` | `CustomTask` / `custom_tasks` |
| 注入 | 每日任务强制/可选区（target 夹到 1-50） | 独立列表，家长确认 |
| 现状 | 家长「任务设置」使用 | 前端零引用、表 0 行，保留待复活 |
| 新需求 | **一律走这里** | 不使用 |

## 三、数据模型

| 表 | 模型 | 说明 |
| --- | --- | --- |
| `daily_tasks` | `DailyTask` | 每日任务行（pending/done/pending_confirm） |
| `parent_task_settings` | — | 家长任务配置 JSON（targets/enabled/mandatory/quotas/study_flags） |
| `makeup_cards` | `MakeupCard` | 补签卡余额（每用户一条） |
| `makeup_usage_log` | `MakeupUsageLog` | 补签卡使用记录（pending/confirmed/rejected） |
| `task_confirms` | `TaskConfirm` | 完成确认（pending/confirmed/rejected，reject_reason） |
| `custom_tasks` | `CustomTask` | 孩子端自定义（DEPRECATED） |
| `parent_custom_tasks` | `ParentCustomTask` | 家长自定义（active 软删、task_type） |

## 四、端点清单（21 条）

```
GET/POST /api/tasks/settings
GET      /api/tasks/daily
POST     /api/tasks/daily/child_submit
POST     /api/tasks/daily/makeup_complete
POST     /api/tasks/daily/claim
POST     /api/tasks/makeup/use
GET      /api/tasks/makeup/balance
POST     /api/tasks/makeup/confirm
GET      /api/tasks/makeup/pending
POST/GET /api/tasks/custom                （孩子端，DEPRECATED）
POST     /api/tasks/custom/confirm
POST     /api/tasks/custom/reject
POST/GET /api/tasks/custom-task
PUT/DELETE /api/tasks/custom-task/{task_id}
POST     /api/task-confirm/create
GET      /api/task-confirm/list
POST     /api/task-confirm/resolve
```

## 五、整理变更记录（2026-09）

| 提交 | 内容 |
| --- | --- |
| `3e3e1dc` | 标注孩子端自定义任务为 DEPRECATED（保留代码待复活） |
| `4186860` | 路由文件归并到 tasks 包内（custom/confirm），URL 不变 |
| `fac851a` | 拆分 832 行 common.py → constants/service/progress |
| `4edd6f8` | 修复导入链 + 消除 `from .common import *` 通配导入（显式具名导入） |
| `3ed6c4b` | 统一家长确认状态机（approved → confirmed）+ 051 迁移 |
| `4c55fb4` | 补签卡业务抽离到独立 makeup_service.py |

> 整理原则：死代码（孩子端 CustomTask）**保留但标注废弃**，不删除；后续任何删除前先查引用。
