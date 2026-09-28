# 消息推送（OneSignal Web Push）接入说明

> 面向：后端 / 前端开发与运维
> 最后更新：2026-09-28
> 相关代码：`app/domains/platform/services/push.py`、`app/domains/platform/routers/push.py`、
> `app/domains/platform/routers/admin_push.py`、`app/models/push.py`、
> `web/src/logic/push.js`、`web/public/OneSignalSDKWorker.js`、`admin/src/views/Push.vue`
> 部署步骤：见 `DEPLOY.md` §16

---

## 1. 定位

推送是继**邮件**（`send_email`）、**短信**（`send_sms`）之后的**第三条通知通道**，
挂在 D8 平台域下，与它们同构：`push_configured()` 判定可用性 + `send_*()` 尽力而为、
失败不影响主流程。

它解决的是「用户不在网站上时怎么被叫回来」：浏览器 Web Push 由 OneSignal 负责送达，
本系统只做三件事 —— **订阅登记、偏好管理、按外部 ID 定向下发**。

| 能力 | 说明 |
|---|---|
| 用户设备订阅 | 登录后自动绑定 `external_id = user_id`，登出解绑（公共电脑不留痕） |
| 四类场景 | 学习提醒（作业/打卡/复习）、私信离线提醒、公告与站内信、考试与成绩 |
| 用户自主控制 | 设备开关 + 逐场景开关 + 免打扰时段，全在「设置 → 通知设置」 |
| 后台群发 | 全体 / 按年级 / 指定用户，含预览式二次确认与发送记录 |
| 事件联动 | 公告发布可勾选「同时推送」；IM 消息对方离线时自动提醒 |
| 降级安全 | 未配置密钥 → 不加载 SDK、不发请求、字段全隐藏，功能不受影响 |

---

## 2. 架构与跨域规则

```
                         ┌──────────────────────────────┐
  web/src/logic/push.js ─┤ /api/push/*   用户端（订阅/偏好/自测）
                         └──────────────┬───────────────┘
                                        │
  admin/src/views/Push.vue ── /api/admin/push/*  （群发/状态/日志）
                                        │
                            ┌───────────▼────────────┐
                            │ D8 platform · push.py  │  唯一出口
                            │  · 偏好过滤/去重/限额   │
                            │  · OneSignal REST 调用  │
                            └───────────┬────────────┘
                                        │ HTTP（不持 DB 连接）
                              api.onesignal.com/notifications
                                        ▲
   frozen(IM) / assessment(成绩) ───────┘
        经 platform.contracts 反向调用
```

**跨域铁律**（`.importlinter` 强制）：

- 其它域（如 D9 frozen 的 IM、D3 assessment 的成绩）**只能**经
  `app.domains.platform.contracts` 调用，禁止 import `platform.services.push`。
  契约已导出：`send_push` / `notify_user` / `notify_users` / `send_per_user_dedup` /
  `push_configured` 以及 `EVENT_*` 六个事件常量。
- 事件常量必须用契约导出的字面量，不要自己拼字符串 —— 它们同时决定
  走哪个偏好开关、是否占每日额度。
- `frozen` 域可以 import 别人的 contracts（白名单允许），但不能被别人 import。

---

## 3. 数据模型（迁移 `083_push_onesignal.py`）

| 表 | 关键字段 | 设计理由 |
|---|---|---|
| `push_subscriptions` | `subscription_id`(唯一)、`user_id`、`platform`、`device_type`、`browser`、`opted_in`、`revoked_at` | 解绑与统计必须落到**每条订阅**：一个用户可能有手机+电脑多个订阅，登出若不按 `subscription_id` 精确解除，旧设备会继续收到推送（隐私问题）。`platform` 预留 `miniapp`/`app` —— 接小程序时只多一种取值，不用改表 |
| `push_prefs` | `enable_study` / `enable_im` / `enable_announce` / `enable_exam`、`quiet_start` / `quiet_end` | 缺行 = 全部开启（避免注册时写一行）。推送是**打扰型**能力，没有偏好开关会把用户推向「浏览器层屏蔽全部通知」，一旦如此今后任何推送都送不到，且我方无从感知 |
| `push_logs` | `dedup_key`(唯一,可空)、`event`、`user_id`、`ok`、`http_status`、`error` | 审计 + 幂等。即时推送写 NULL；定时/事件类占用去重键 |

> ⚠️ **`dedup_key` 必须可空**：MySQL 唯一索引允许多个 NULL，但只允许一个空串。
> 若给 `DEFAULT ''`，第二条不参与去重的推送就会撞唯一键而发不出去（与 082 的 `fingerprint` 同坑）。
> 同理，**失败时不写 `dedup_key`** —— 否则失败一次的定时提醒当天再也补发不出去。

---

## 4. 端点

### 4.1 用户端 `/api/push`（挂 `user_auth_deps`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/config` | 前端初始化：`enabled` / `app_id` / `safari_web_id` / `events` / 我的偏好 |
| POST | `/subscribe` | 上报 `subscription_id`（同一 ID 二次上报按更新处理，换账号会改写归属） |
| POST | `/unsubscribe` | 解绑当前设备或全部设备（登出必调） |
| GET | `/status` | 我的偏好 + 有效设备数 |
| GET/PUT | `/prefs` | 读 / 改偏好（未传字段不动；非法时段归一为「不启用」） |
| POST | `/test` | 给自己发一条测试推送，按 `reason` 给出可操作的中文提示 |

这些端点用 `require_user` 取**当前登录用户**，不采信前端传来的 `user_id` ——
否则「传别人的 user_id 就能给别人推消息 / 改他偏好」。

### 4.2 后台 `/api/admin/push`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/status` | 登录管理员 | 通道是否就绪 + 订阅/用户数 + 事件类型（**不回传任何密钥片段**） |
| POST | `/send` | `announcement:manage`（高危，记审计） | 群发：`target=all` 走分段广播；`user`/`grade` 走 `external_id` 定向 |
| POST | `/test` | `announcement:manage` | 给指定用户发测试（排查端到端） |
| GET | `/logs` | 登录管理员 | 最近发送记录（含失败原因） |

权限**沿用运营组的 `announcement:manage`**，没有新造权限点 ——
RBAC 严格模式下新权限点默认无人拥有，会出现「功能上线了但谁也点不动」的静默故障。

### 4.3 系统

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/OneSignalSDKWorker.js` | Service Worker（根路径托管，见 §6） |

---

## 5. 发送链路与四条不变量

```python
send_to_users(user_ids, title, body, url="", event="", data=None, dedup_key="")
# 1) 短会话：去重检查 + 偏好过滤 + 免打扰 + 每日限额   ← 会话在这里关闭
# 2) 会话之外：requests.post(api.onesignal.com/notifications)
# 3) 新短会话：写发送日志（成功写 dedup_key，失败不写）
```

**四条不变量（改动前务必先读）**：

1. **不持 DB 连接做外部调用**。本模块自己开短会话；调用方**不得**把请求级 `db` 传进来。
   发公告的场景是特例：`create_announcement` 在 `commit` 后显式 `db.close()` 再推送
   （历史上曾因持连等外部调用耗尽 QueuePool 导致全站超时）。
2. **永不抛异常**：对外函数失败只记日志、返回 `{ok: False, reason}`。
   受众筛选（要读 DB）单独用 try 兜住，DB 异常也不能把业务主流程炸掉。
3. **200 但没有消息 id = 失败**。OneSignal 用「没有 id」表示靶向受众里没有有效订阅。
   早期实现把它当成功，会出现「提示已发送、用户永远收不到」的假成功 ——
   现单独返回 `reason=no_subscription`（排查方向与密钥错误完全不同）。
4. **不阻塞事件循环**：IM 里调用时走 `asyncio.create_task(asyncio.to_thread(...))`，
   否则 1~10s 的 HTTP 会加在消息响应上。

### 请求体形状

```json
{
  "app_id": "<ONESIGNAL_APP_ID>",
  "target_channel": "push",
  "include_aliases": { "external_id": ["<user_id>", "..."] },
  "headings": { "en": "标题", "zh-Hans": "标题" },
  "contents": { "en": "正文", "zh-Hans": "正文" },
  "url": "https://liusijin.com/#/home",
  "data": { "event": "study", "kind": "daily_reminder" }
}
```
Header：`Authorization: Key <REST_API_KEY>`（不是 Bearer）。
单请求 `external_id` 上限 20000，代码按 `BATCH_SIZE=1000` 分批。

### 两个发送函数怎么选

| 函数 | 场景 | 去重方式 |
|---|---|---|
| `send_to_users` | 一批人共用同一事件（定时提醒、公告） | 单一 `dedup_key` |
| `send_per_user_dedup` | **每人一个独立去重键**（IM：`im:{uid}:{chat}:{date}`） | 先查已发集合，再批量发，逐人落键 |
| `send_to_all` | 后台全体群发 | 分段广播，不枚举用户、不过滤偏好 |

`send_per_user_dedup` 存在的理由：群里连发 20 条消息时，离线成员不该收到 20 条推送，
但去重键含用户与会话，无法用单一 `dedup_key` 表达；同时它仍是**一次 HTTP 覆盖多人**，
不会退化成逐个请求。

---

## 6. Service Worker（最容易踩的部署坑）

**为什么需要后端专门托管**：部署形态是 nginx `location /` 全量反代给 FastAPI，
`web/dist` 不作为静态目录暴露（只单独挂了 `/assets`、`/qr`）。而 Service Worker
的作用域 = 文件所在目录，只有放在**根路径**才能覆盖全站，所以必须能在
`https://域名/OneSignalSDKWorker.js` 访问到。

```
web/public/OneSignalSDKWorker.js   ──Vite 构建拷贝──▶  web/dist/OneSignalSDKWorker.js
                                                             │
                          app/main.py: GET /OneSignalSDKWorker.js（优先读 dist）
                                                             │
                                        缺失时返回 ONESIGNAL_WORKER_FALLBACK（内联兜底）
```

响应头：`Content-Type: application/javascript`、`Service-Worker-Allowed: /`、
**`Cache-Control: no-store`**。no-store 是必须的 —— OneSignal 明确要求 worker 不可长期缓存，
否则 SDK 升级后老客户端仍跑旧 worker，表现为「后端已更新、老用户收不到推送」。

验证：`curl -I https://liusijin.com/OneSignalSDKWorker.js` → 200 + `application/javascript`。

---

## 7. 前端接入（`web/src/logic/push.js`）

三条设计约束：

1. **SDK 懒加载**：只有 `/api/push/config` 返回 `enabled=true` 才注入 OneSignal 脚本。
   通道未配置时零第三方请求 —— 否则控制台持续报错，用户以为功能坏了，其实只是后台没填密钥。
2. **登录后才 `OneSignal.login()`**：游客状态绝不调用，否则订阅被绑到空/错误的
   `external_id`，之后该设备收不到任何定向推送。
3. **失败全静默**：推送是增量能力，任何一步失败都不得影响登录、答题等主流程。

生命周期挂载点（漏一处就会出现「刷新后收不到」这类诡异现象）：

| 时机 | 调用 | 位置 |
|---|---|---|
| 登录成功 | `pushInit()` | `logic/auth.js` 的 `onLoginOk` |
| **刷新页面恢复会话** | `pushInit()` | `logic/appOptions.js` 的 `mounted`（不走 onLoginOk） |
| 登出 | `pushTeardown()` | `logic/appOptions.js` 的 `logout` |

设置页入口：`web/src/views/SettingsView.vue` 的「通知设置」分组 ——
设备开关、四个场景开关、免打扰时段、发送测试推送。通道未配置时显示说明行而非空白，
避免用户翻遍设置页也找不到开关。

业务逻辑按项目约定放 `logic/push.js`（`pushData()` / `pushComputed` / `pushMethods` 三字典），
在 `appOptions.js` 的 data/computed/methods 各展开一行。

---

## 8. 四类触发点

| 场景 | 触发位置 | 事件 | 说明 |
|---|---|---|---|
| 学习提醒 | `tools/push_daily_reminder.py`（调度器 **19:00**） | `study` | 扫「近 7 天活跃」用户：今天有未完成任务 → 提醒剩几项；今天没签到但有连续记录 → 防断签 |
| 私信离线提醒 | `frozen/routers/im.py::handle_message`（落库广播之后） | `im` | 只推给**没有 WebSocket 连接**的成员；逐人去重，同一会话当天每人一条 |
| 公告 / 成绩 | `platform/routers/admin_panel.py::create_announcement`（勾选「同时推送」） | `announce` | 公告 commit + `db.close()` 后下发；按受众走分段或定向 |
| 后台群发 | `admin/src/views/Push.vue` → `/api/admin/push/send` | `broadcast` | 二级确认；`grade` 目标单次上限 5000 人 |
| 自测 | 设置页「发送测试推送」/ 后台测试 | `test` | 排查端到端链路 |

> **定时任务刻意不排凌晨 01:00**（与项目其它采集/汇总类不同）：推送必须在用户活跃时段
> 才有意义，凌晨推等于不推。19:00 是学生做作业高峰。该时刻与 `check_quiet_hours`
> 不冲突 —— 宵禁只拦答题类接口，推送走的是 OneSignal 对外 HTTP，不经过那些端点。

---

## 9. 防打扰四道闸

| 闸 | 实现 | 备注 |
|---|---|---|
| 设备开关 | 浏览器未授权 → 没有订阅 | 用户可在 SDK 层关闭 |
| 场景偏好 | `_PREF_FIELD` 映射，关掉的类别**不放行到 HTTP** | 无偏好行 = 全开 |
| 免打扰时段 | `in_quiet_hours`，跨零点区间反向判断 | **不复用** `check_quiet_hours`：后者是未成年人护眼宵禁（拦接口），语义不同 |
| 每人每日上限 | `DAILY_CAP = 8`，仅自动事件受限 | 公告/群发不占额度，否则一条公告就能吃光额度，真实提醒全被吞 |

---

## 10. 配置

密钥走**管理后台「三方配置 → 消息推送」**（写入 `system_config`，60 秒生效，无需重启），
或写 `.env`（后台值优先）。`app/config.py` 不含这些常量 —— 与 `MAIL_*`、`SMS_*` 保持同一风格。

| 键 | 说明 |
|---|---|
| `ONESIGNAL_APP_ID` | App ID，会下发到前端（本就公开） |
| `ONESIGNAL_REST_API_KEY` | REST API Key，**机密**；以 `KEY` 结尾 → 后台展示自动脱敏 |
| `ONESIGNAL_SAFARI_WEB_ID` | 可空；不填则 Safari 收不到 |
| `PUSH_ENABLED` | `false` 一键停推（比逐个清空密钥安全，便于灰度回滚） |
| `SITE_URL` | 可选；推送 `url` 的站点根地址，默认 `https://liusijin.com` |

---

## 11. 测试（`tests/test_push.py`，33 例）

| 分组 | 覆盖 |
|---|---|
| 降级 | 未配置时 `push_configured()` False、`/config` 回 false、发送**零 HTTP 请求** |
| 纯函数 | `abs_url` 补全、`in_quiet_hours`（跨零点/未启用/非法值/起止相同）、`pref_allows` |
| 订阅 | 上报 upsert 幂等（换账号改写归属）、解绑、设备计数 |
| 偏好 | 读写回环、未传字段不动、非法时段归一为空 |
| 发送 | `external_id` 定向 + push 通道 + `Key` 鉴权头、日志落库、dedup 去重、偏好关闭、免打扰、每日上限（公告不受限）、200 无 id 判失败、HTTP 错误留痕、逐人去重、分段广播 |
| 端点 | 自测成功/未配置提示、SW 路由 MIME 与 no-store 与 scope、后台状态/群发/定向/未配置 400 |

打桩方式：`monkeypatch.setattr(push, "requests", _FakeRequests)` 与
`monkeypatch.setattr(push.sysconfig, "get", lambda key, default="": cfg.get(key, default))`。

---

## 12. 运维排查速查

```bash
# 通道与订阅概况（后台页也有）
curl -s -H "Authorization: Bearer <admin_token>" https://liusijin.com/api/admin/push/status

# SW 是否可达
curl -I https://liusijin.com/OneSignalSDKWorker.js

# 最近失败记录
#   后台 → 消息推送 → 最近发送记录（error 列给出 OneSignal 原始错误）

# 定时提醒任务（线上）
<venv>/bin/python tools/push_daily_reminder.py --dry-run   # 先看会推给谁
```

| 现象 | 处理 |
|---|---|
| 「没有找到有效订阅」 | 用户未授权；HTTP 页面浏览器不提供通知 API，必须 HTTPS；iOS 需「添加到主屏幕」；微信内置浏览器不支持 |
| 401 | 密钥与 App ID 不属于同一 OneSignal 应用（最常见），或密钥已轮换 |
| 后台「通道未配置」 | 密钥未填或 `PUSH_ENABLED=false` |
| 200 无 id | 受众里没有有效订阅（代码判定为失败并记 `no_subscription`） |
| 同一天没收到定时提醒 | `dedup_key` 当天已用过（正常幂等），或该用户被偏好/免打扰/日限挡住 |
