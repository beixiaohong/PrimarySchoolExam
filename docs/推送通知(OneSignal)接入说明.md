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
  "url": "https://www.liusijin.com/#/home",
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

验证（用 GET，不要用 `curl -I` —— 那发的是 HEAD）：

```bash
curl -s -D - -o /dev/null https://www.liusijin.com/OneSignalSDKWorker.js | head -8
```
→ 200 + `application/javascript` + `no-store` + `Service-Worker-Allowed: /`。
（路由已同时注册 HEAD，`curl -I` 现在也能返回 200；但 GET 形式在任何版本上都成立，故文档统一用它。）

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
| `SITE_URL` | 可选；推送 `url` 的站点根地址，默认 `https://www.liusijin.com` |

---

## 11. 测试

### 11.1 自动化回归（不需要 OneSignal 账号，沙箱即可跑）

`tests/test_push.py`，33 例：

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

### 11.2 发送目标预演（仍不需要 OneSignal 账号）

只想确认「会推给谁、内容对不对」，不想真发，用 dry-run：

```bash
# 线上（写库任务只能在线上跑；本地克隆库只能看，别拿来判线上真实名单）
<venv>/bin/python tools/push_daily_reminder.py --dry-run --limit 50
```

输出形如 `[push-reminder] 2026-09-28 命中 N 人（active<=7 天）` + 每人一行 `uid | 标题`，
末尾 `dry-run：未实际发送`。**这一步不走网络、不写库**，纯读。

---

### 11.3 真机端到端验收（唯一能证明「用户真能收到」的方式）

自动化测试全部打桩，证明的是「组装出的请求体是对的」；**收没收到只有真浏览器能证明**。
按下面顺序走，任何一步不过都对应一个明确的 reason（见 11.4 对照表）。

> ⚠️ 前提：必须 HTTPS 域名（生产 `liusijin.com`）。**HTTP 页面浏览器不提供通知 API**；
> `localhost` 是唯一例外（`push.js` 已传 `allowLocalhostAsSecureOrigin`，但还需在
> OneSignal 控制台把该源加入允许列表，且本地库是克隆库，测完别当成线上配置）。
> iOS Safari 必须先把站点「添加到主屏幕」才支持 Web Push；微信内置浏览器不支持。

**① 后端就绪**

```bash
# 迁移是否已跑（应有 3 张 push_* 表）
#   ⚠️ 本地没有线上库密码，这条必须在**线上服务器**上执行，别在本地连 115.29.213.131
ssh <线上> "cd <部署目录> && mysql -u <user> -p schoolexam -e \
  \"SHOW TABLES LIKE 'push_%'; SELECT * FROM schema_migrations WHERE version LIKE '083%';\""
#   或更省事：venv/bin/python -c \"from app.migrations.runner import run_migrations; run_migrations()\"（幂等，已应用则秒过）

# SW 是否可达（必须 200 + application/javascript + no-store）
#   用 GET 取响应头：curl -I 发的是 HEAD，旧版本路由只注册了 GET 会返回 405，容易误判
curl -s -D - -o /dev/null https://www.liusijin.com/OneSignalSDKWorker.js | head -8

# 通道是否就绪（后台页也有；密钥不回传明文）
curl -s -H "Authorization: Bearer <admin_token>" https://www.liusijin.com/api/admin/push/status
#   期望 configured.app_id=true、configured.rest_api_key=true、enabled=true
```

**② 浏览器侧绑定**（这一步最容易出错，重点看 `external_id` 有没有绑上）

1. 用 **HTTPS** 打开 https://www.liusijin.com 并**登录**（游客不调 `OneSignal.login()`，
   没登录就授权的话订阅不会绑到 `user_id` → 后面必报 `no_subscription`）。
2. 浏览器弹通知授权 → **允许**。（已被拒过的话不会再弹，去站点设置里改）
3. F12 控制台逐条确认：

```js
OneSignal.User.PushSubscription.id        // 应为订阅 id 字符串，非 null
OneSignal.User.PushSubscription.optedIn   // 应为 true
OneSignal.User.externalId                 // 应等于你的 user_id  ← 绑定成功的关键判据
```

4. Application → Service Workers：`OneSignalSDKWorker.js` 状态应为 **activated**、scope `/`。

**③ 点自测按钮**

设置页 →「🔔 消息推送」→ **发送测试推送**（等价 `POST /api/push/test`）。
成功返回 `{"ok":true,"message":"已发送，请查看系统通知（约 1-3 秒）"}`，
应在 1~3 秒内看到系统级通知。**注意是系统通知，不是页面内的 toast**——
页面开着时浏览器可能不弹横幅，去桌面通知中心看。

**④ 后台定向/群发**

后台 →「消息推送」：先看 status 卡片上的已订阅设备数/用户数（**为 0 就是没人成功订阅**，
先去 ② 排查），再用指定 `user_id` 发测试，最后试群发。
发送记录表会给每次的 `ok / http_status / error`。

**⑤ 落库核对**（确认绑定与审计真的写进去了）

```sql
SELECT user_id, subscription_id, platform, opted_in, revoked_at
  FROM push_subscriptions ORDER BY id DESC LIMIT 10;

SELECT event, ok, http_status, recipients, error, dedup_key, created_at
  FROM push_logs ORDER BY id DESC LIMIT 10;
```

`push_logs` 最关键的两个字段：`ok=0` 时看 `error`（OneSignal 原始错误），
`dedup_key` 为 NULL 表示这条不参与去重（即时推送正常如此）。

---

### 11.4 线上验收：与本地测试的三处差异

线上已天然满足 HTTPS（本地是靠 `allowLocalhostAsSecureOrigin` 绕过的），但下面三处**必须区别对待**。

**① 凭据是两份，不会自己同步**

本地 `.env` 里有密钥 **不代表**线上有 —— 线上服务器的 `.env` 是独立的一份。两条填法：

| 方式 | 生效 | 说明 |
|---|---|---|
| 线上 `.env` 加 `ONESIGNAL_APP_ID` / `ONESIGNAL_REST_API_KEY` | 需 `systemctl restart` | 改文件、要重启 |
| 后台「系统配置 → 消息推送」在线填 | **60 秒内自动生效，无需重启** | `system_config` 表优先级高于 `.env` |

判断线上到底配好没有，**直接看后台「消息推送」页的 status 卡片**（`configured.app_id` /
`configured.rest_api_key` / `enabled`），不要去猜 `.env`。该卡片只回传「是否已配置」，不回传明文。

**② 查库只能在线上服务器上做**

本地没有线上库密码，`115.29.213.131` 从本地连不上：

```bash
ssh <线上> "cd <部署目录> && mysql -u <user> -p schoolexam -e \
  \"SELECT user_id, subscription_id, opted_in, revoked_at FROM push_subscriptions ORDER BY id DESC LIMIT 5;\""
```

**③ 迁移与前端产物都由部署流程产出，没有「单独跑一下」的捷径**

- 建表：`deploy.sh` 重启时 `lifespan` 自动 `run_migrations()`（幂等）→ 3 张 `push_*` 表；
- 前端：新的设置卡片与新后台页**必须重建 `web/dist`、`admin/dist`**，否则线上页面里根本没有推送开关
  —— 表现为「翻遍设置页找不到推送」，而接口其实一切正常。

**线上验收最小清单**

```bash
# 1) SW 可达（200 + application/javascript + no-store + Service-Worker-Allowed: /）
curl -s -D - -o /dev/null https://www.liusijin.com/OneSignalSDKWorker.js | head -8

# 2) 代码是否真的上线了 —— 必须做「存在 vs 不存在」对照
curl -s -o /dev/null -w "%{http_code}\n" https://www.liusijin.com/api/push/prefs          # 期望 401（路由在，待登录）
curl -s -o /dev/null -w "%{http_code}\n" https://www.liusijin.com/api/push/zzz-not-exist  # 期望 404（路由不在）
```

> 🚨 **第 2 条是判别「代码有没有真上线」的可靠手法**：只看一个 401 会被骗 ——
> 若全局鉴权中间件对一切 `/api/*` 兜底（本项目 `require_self` 就是全站挂载的），
> 那么**不存在的路由也会返回 401**。必须拿一个肯定不存在的路径做对照，
> 一个 401 + 一个 404 才能证明路由确实注册了。本方法在 2026-09-28 的线上探测中实测有效。

浏览器侧步骤与 11.3 完全一致（HTTPS 打开站点 → **先登录** → 授权 → 设置页「发送测试推送」），
线上不需要任何额外配置；后台定向与群发也在同一套流程里。

---

### 11.5 失败对照表（按接口返回的 `reason` 定位）

| reason | 含义 | 怎么修 |
|---|---|---|
| `not_configured` | 后台未填 APP_ID / REST_API_KEY，或 `PUSH_ENABLED=false` | 后台「系统配置 → 消息推送」填齐后等 60 秒 |
| `no_subscription` | 靶向受众无有效订阅（含 HTTP 200 但无 `id`） | 按 ② 逐条查：没登录 / 没点允许 / `externalId` 为空 / 授权后没刷新页面 |
| `http_error` | OneSignal 返回非 2xx | 多为 **401：Key 与 App ID 不属于同一应用**，或 Key 已轮换 |
| `request_failed` | 请求根本没发出去 | 线上出网/防火墙；看应用日志 |
| `duplicate` | 当天该去重键已发过 | 正常幂等，不是故障（定时提醒一天只发一条） |
| `no_recipient` | 过滤后无人可发 | 偏好关闭 / 免打扰时段 / 每日上限 8 条用尽 |

> 排查顺序建议：**先看 `reason`，再看 `push_logs.error`，最后才查代码**。
> 「没收到」和「发送失败」是两件事——`ok=1` 但用户没收到，属于浏览器侧
> （免打扰/系统通知被关/勿扰模式/多设备只在一台上授权），不属于后端问题。

---

## 12. 运维排查速查

**排查第 0 步：先确认前端的推送脚本有没有被浏览器拦掉**。若用户说「从来没见到过授权提示」，
大概率不是后端问题，而是浏览器把 OneSignal 当广告追踪器阻止了加载 —— 见 **§13**（含放行步骤）。

**排查第一步：先分清「配置错」与「没人订阅」**。后台日志只显示「失败」，
但这两类原因的处理方向完全相反（一个去改密钥、一个去让用户授权），必须先分开。
探测工具直接问 OneSignal 侧要事实：

```bash
# 只读：App 概览 + 订阅构成 + 最近通知触达数（不发任何推送，不打印密钥）
python tools/onesignal_probe.py
# 线上：cd /home/PrimarySchoolExam && venv/bin/python tools/onesignal_probe.py
```

判据：

| 探测结果 | 结论 | 动作 |
|---|---|---|
| `订阅构成` 里**没有 Web**（只有 Email/移动端，或为空） | **没人订阅** | 让用户登录后点「允许通知」；**别去改密钥** |
| HTTP 401 | 配置错 | 核对 Key 与 App ID 是否属于**同一个** OneSignal 应用 |
| `Web 平台域名` ≠ 本站地址 | OneSignal 侧站点 URL 配错 | 改成本站域名后重新授权 |
| 群发 0 人，但**定向推送成功** | **分段名已过期**（不是没人订阅） | 按下方「案例二」核对段名，别去查订阅 |

> **案例一：真的没人订阅（2026-09-28）** —— 线上后台群发与测试推送全部失败，
> `reason=no_subscription`。探测显示域名正确、Web 平台已启用、`push_configured()=True`，
> 但**订阅总数 1 且构成是 `{'Email': 1}`** —— 一个 Web Push 订阅都没有，属「没人订阅」。
> ⚠️ 这类 Email/移动端订阅**不能**用于 Web Push，所以段推送同样发不到，也返回 200 无 `id`。
>
> 同一次还暴露了一个代码缺陷：`send_to_all`（段推送）漏了「200 无 `id` = 无有效订阅」
> 的判定，导致后台显示「结果=失败、错误=空」而接口却回「已广播」，两头矛盾且无从排查。
> 现已抽成 `_parse_resp()` 由两条发送路径共用（`_send_once` / `send_to_all`）。

> **案例二：分段名过期（当天第二次踩坑，⚠️ 更隐蔽）**
>
> 用户订阅成功后，**定向推送已经能触达**（后台日志 `触达订阅 1 / 成功`，拿到消息 id），
> 但**后台群发仍然 0 人**。根因不是订阅，而是代码里写死的分段名 **已被 OneSignal 改名**：
>
> | 旧名（曾写死在代码里） | App 内**实际存在**的 6 个预置段（实测） |
> |---|---|
> | `Subscribed Users` | `Total Subscriptions`、`Active Subscriptions`、`Inactive Subscriptions`、`Engaged Subscriptions`、`All SMS Subscriptions`、`All Email Subscriptions` |
>
> OneSignal 把预置段从「用户（Users）」维度改成了「订阅（Subscriptions）」维度。
> 引用一个**不存在的段**时，接口**返回 200 却不带 `id`** → 被 `_parse_resp` 判成
> `no_subscription` → 提示「还没人授权通知」，而真相是「段名过期」。**同一个错误码、
> 两种完全不同的原因**，这是本次排查最绕的地方。
>
> 现状：段名已抽为常量 `push.SEGMENT_ALL_SUBSCRIBERS`（含核对手册注释），
> 并有 `test_broadcast_segment_name_is_pinned` 钉住它；`no_subscription` 的返回文案
> 也已改成**两种原因并列提示**，不再只喊「没人订阅」。
>
> **核对段名的只读命令**（群发 0 人时的第一步，先跑它再看订阅）：
>
> ```bash
> # 列出全部段名
> curl -s -H "Authorization: Key $ONESIGNAL_REST_API_KEY" \
>   https://api.onesignal.com/apps/$ONESIGNAL_APP_ID/segments
>
> # 查某段实际人数（<segment_id> 换成上一步拿到的 id）
> curl -s -H "Authorization: Key $ONESIGNAL_REST_API_KEY" \
>   https://api.onesignal.com/apps/$ONESIGNAL_APP_ID/segments/<segment_id>
> # 实测：Total Subscriptions → {"subscriber_count": 3}（2 Email + 1 Web）
> #       Active Subscriptions → {"subscriber_count": 2}
> ```

```bash
# 通道与订阅概况（后台页也有）
curl -s -H "Authorization: Bearer <admin_token>" https://www.liusijin.com/api/admin/push/status

# SW 是否可达（GET 取响应头；别用 curl -I，HEAD 在旧版路由会 405）
curl -s -D - -o /dev/null https://www.liusijin.com/OneSignalSDKWorker.js | head -8

# 最近失败记录
#   后台 → 消息推送 → 最近发送记录（error 列给出 OneSignal 原始错误）

# 定时提醒任务（线上）
<venv>/bin/python tools/push_daily_reminder.py --dry-run   # 先看会推给谁
```

| 现象 | 处理 |
|---|---|
| 「没有找到有效订阅」 | **先用 `tools/onesignal_probe.py` 确认 OneSignal 侧有没有 Web 订阅**（见上）；若确实没有：用户未授权、或授权时未登录导致绑定不上账号。另外 HTTP 页面浏览器不提供通知 API（必须 HTTPS）；iOS 需「添加到主屏幕」；微信内置浏览器不支持 |
| 401 | 密钥与 App ID 不属于同一 OneSignal 应用（最常见），或密钥已轮换 |
| 后台「通道未配置」 | 密钥未填或 `PUSH_ENABLED=false` |
| 200 无 id | 受众里没有有效订阅（两条发送路径均已判定为失败并记 `no_subscription`） |
| 结果=失败但错误列空白 | 2026-09-28 前 `send_to_all` 的缺陷，已修；历史记录仍可能是空的，看 `push_logs.http_status`（200 = 无订阅者） |
| 同一天没收到定时提醒 | `dedup_key` 当天已用过（正常幂等），或该用户被偏好/免打扰/日限挡住 |

---

## 13. 浏览器跟踪防护会把 OneSignal 拦掉（2026-09-28 定位，重要）

### 13.1 事实：OneSignal 在跟踪防护列表里属于「广告」

Microsoft Edge 的跟踪防护**直接使用 disconnect.me 的开源 Tracker Protection 列表**做分类
（Edge 官方文档 *Tracking prevention in Microsoft Edge*）。在该列表中：

```
分类 Advertising → 公司条目 OneSignal → 归属域名 onesignal.com
```

`cdn.onesignal.com`（SDK 脚本、SW 的 importScripts 目标）与 `api.onesignal.com`
（拉配置 / 注册订阅 / 上报 external_id）都是它的子域，按 Edge 的后缀匹配规则
（最多回溯 4 层标签）**都会被判定为广告追踪器**。

### 13.2 Edge 各防护级别对「广告」类的处置（官方表）

| 级别 | Advertising | Analytics | Content | Fingerprinting | Social |
|---|---|---|---|---|---|
| 基本 Basic | – | – | – | 阻止存储+加载 | – |
| **均衡 Balanced（默认）** | **仅阻止存储** | – | 仅阻止存储 | 阻止存储+加载 | 仅阻止存储 |
| 严格 Strict | **阻止存储 + 阻止加载** | 阻止存储+加载 | 仅阻止存储 | 阻止存储+加载 | 阻止存储+加载 |

（– = 不拦；「阻止加载」= 请求在到达网络之前就被丢弃）

这解释了两件事：

- **默认「均衡」的用户仍能订阅**：广告类只被挡 localStorage/IndexedDB，脚本本身照常下载。
- **「严格」的用户彻底收不到**：`cdn.onesignal.com` 被阻止加载 → `window.OneSignal` 永不出现
  → 前端**连授权提示都不会弹**（不是用户点了拒绝，而是根本没机会问）
  → 后端所有推送必然 `no_subscription`。

同样效果的还有：Firefox「严格」跟踪保护、uBlock Origin / AdGuard 等拦截扩展、
Brave Shields，以及企业终端的策略强制。

### 13.3 🚫 一条走过的弯路：自托管 SDK 资源**解决不了**这个问题

直觉是「把 `OneSignalSDK.page.es6.js` 下载到自己域名、SW 改成
`importScripts('/OneSignalSDK.sw.js')`」就能绕过拦截。**分析后否掉了**：

- 静态脚本换成第一方确实能加载；
- 但 SDK 运行期仍必须请求 **`api.onesignal.com`**（拉配置、注册订阅、上报 external_id），
  它与 `cdn.onesignal.com` 同属 `onesignal.com` 实体 → Strict 下照样**阻止加载**
  → 订阅仍然建不起来。

也就是说，自托管只能骗过「按 URL 匹配」的静态拦截，骗不过「按域名清单」的跟踪防护，
反而多背两个需要手动跟进版本升级的第三方文件。**不要走这条路。**

> 附带发现：v16 的 `OneSignalSDK.page.js` 只是 590 字节的 loader，内部**硬编码**了
> `https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.es6.js?v=160610`，
> 所以连 loader 本身也没法自托管。

### 13.4 让用户放行（可照抄的步骤）

| 浏览器 | 操作 |
|---|---|
| **Edge** | 设置 → 隐私、搜索和服务 → **跟踪防护** → 「例外」→ 添加本站域名（须带 `https://`，如 `https://www.liusijin.com`）；或点地址栏左侧的锁形图标 → 「跟踪器」→ **允许此站点上的跟踪器**。若级别是「严格」，也可临时改回默认的「均衡」 |
| **Chrome** | 默认不拦第三方脚本加载；若装了 uBlock/AdGuard，在扩展里放行即可 |
| **Firefox** | 地址栏盾牌图标 → 关闭「此网站的增强跟踪保护」；或设置 → 隐私 → 把本站加入例外 |
| **拦截扩展** | uBlock Origin / AdGuard 等对当前站点关闭，或把 `onesignal.com` 加入允许清单 |

放行后**必须做两步**才生效：

1. 强制刷新页面（`Ctrl+Shift+R`）；
2. 若此前 SW 注册失败过，先清掉坏状态：DevTools → Application → Service Workers →
   **Unregister**，再刷新。

### 13.5 怎么确认「确实被拦了」

1. **界面**：设置页「🔔 消息推送」的状态会直接显示
   **「推送脚本未能加载（多为浏览器跟踪防护/广告拦截）」** —— 前端在 SDK 注入处加了
   10 秒超时兜底（脚本被拦时 `onerror` **不保证触发**，没有超时就会永远停在「未开启」，
   用户和我们什么都看不出来）。
2. **DevTools Console**：出现 `Tracking Prevention blocked access to storage for <URL>`
   或 `Tracking Prevention blocked a resource load for ...`（Edge 官方给的判据）。
3. **DevTools Network**：`cdn.onesignal.com/...page.es6.js` 显示为 `(blocked:other)` 或无响应。

### 13.6 影响面与后续选择

| 人群 | OneSignal 方案能否触达 |
|---|---|
| Chrome 默认 / Edge 均衡 / Safari | ✅ 可以（仍需用户点「允许」） |
| Edge 严格、Firefox 严格、装了拦截扩展、企业策略终端 | ❌ 完全不可用 |

直觉上「改成本站第一方 Web Push」可以根治——自建 Service Worker + 标准 VAPID 订阅，投递到
`fcm.googleapis.com` / `updates.push.services.mozilla.com` / Apple 这些**不在追踪器清单里**的端点。

> ⚠️ **但 2026-09-28 的全链路实测推翻了这条路**：它只在 **Edge / Firefox / Safari** 上成立，
> **Chrome 与 Opera 永久不行**——投递由**服务器**发起，而线上服务器到 `fcm.googleapis.com`
> 被网络阻断（Google 系整体不可达）。详见 **§14**（含已实测跑通的 Edge 路线与两个必踩的坑）。
>
> **结论：保持 OneSignal。** 它的投递在自家海外服务器上，恰好绕过这个限制，覆盖面反而最大。

---

## 14. 自建原生 Web Push 的可行性（2026-09-28 全链路实测，备案）

> 本节是**备案材料**：万一 OneSignal 不可用（服务中断、又被某浏览器拦、成本变化），
> 照这里的事实链可以直接判断「值不值得自建、能覆盖谁、第一步改什么」，不必重新摸索。
> 触发本次实测的起因是 §13 的跟踪防护问题——但结论是**不该自建**。

### 14.1 决定性事实：各浏览器推送端点的可达性

Web Push 的**订阅端点由浏览器硬编码**，网站无法选择。所以「服务器能不能投递」取决于
**服务器到那个端点域名的网络通不通**。实测（同一台线上阿里云服务器）：

| 投递端点 | 归属浏览器 | 线上服务器 | 沙箱（国内本地） | 判据 |
|---|---|---|---|---|
| `fcm.googleapis.com` | **Chrome / 国产 Chromium** | ❌ 超时 `exit=124` | ❌ 重置 `exit=56` | DNS 正常（216.239.x.x），**TCP 层阻断** |
| `*.notify.windows.com` | **Edge（Windows）** | ✅ `404` | ✅ `404` | 404 = TLS+HTTP 往返成功，只是路径不对 |
| `updates.push.services.mozilla.com` | Firefox | ✅ `406` | ✅ `406` | 同上 |
| `web.push.apple.com` | Safari / iOS | ✅ `405` | ✅ `405` | 同上 |
| `push.opera.com` | Opera | ❌ | ❌ `56` | 同上 |

- 🚨 **认知修正**：Edge 的 Web Push 端点**不是 FCM，而是微软自家的 WNS**（`*.notify.windows.com`）。
  Edge 有 `ForceBuiltInPushMessagingClient` 策略（用内置 WNS 客户端连 WNS），这条链路独立于 Google。
  很多人（包括本文档初版）以为 Chromium 系全走 FCM，是错的。
- `www.google.com`、`www.googleapis.com` **同样不可达** → 不是 FCM 被特判，是**服务器出网到 Google 整体被阻断**。

**判「通不通」的方法**：404/405/406 这类「应用层错误码」= **网络是通的**；只有超时/连接重置才是不可达。

### 14.2 覆盖面：OneSignal 反而更大

| 路线 | Chrome | Edge | Firefox | Safari | 依赖第三方 |
|---|---|---|---|---|---|
| **OneSignal**（现状） | ✅ | ✅ | ✅ | ✅ | 是 |
| 自建原生 Web Push | ❌ **服务器发不出去** | ✅ | ✅ | ✅ | 否 |

自建方案卡在一个死结上：**Chrome 的订阅端点是 FCM，而服务器到 FCM 被阻断**。
浏览器侧能不能到 FCM 是用户自己的事，而「投递」这一步由服务器发起，救不了。

> 附带一个容易混淆的点：用户浏览器实测 `fcm.googleapis.com` 返回 **403**（不是网络错误），
> 说明**用户侧**能连 FCM（该用户疑似走代理）。但**普通家长不开代理时，Chrome 连订阅都建不起来**——
> 这也可能是 OneSignal 后台长期「零 Web 订阅」的另一半原因（与 §13 的跟踪防护并列）。
> **Chrome / Opera 用户的 Web Push 在国内无论用谁家服务都发不出去**，换服务商救不了。

### 14.3 已实测跑通的 Edge 路线（HTTP 201）

在隔离环境装 `pywebpush`（2.5.0）后向用户真实 Edge 端点投递，**一次 400、补头后 201**：

```
X-WNS-STATUS: received
X-WNS-NOTIFICATIONSTATUS: received
X-WNS-MSG-ID: 6F6A9A307A1FBDD5
```

`received` 是 WNS 的明确回执 → **服务器 → WNS → 设备** 链路成立，无需任何中转/代理/出海通道。
补充经验：**Edge 无需保持浏览器打开即可收到；Firefox 必须开着浏览器**。

### 14.4 🚨 两个必须记住的坑

1. **发到 WNS 必须带 `x-wns-cache-policy` 头**，否则返回**裸 400 且响应体为空**，
   真因只写在响应头里（`X-WNS-ERROR-DESCRIPTION: "Ttl value conflicts with X-WNS-Cache-Policy."`）。
   规则：`ttl == 0` → `no-cache`；`ttl > 0` → `cache`。写法 `webpush(..., headers={"x-wns-cache-policy": "no-cache"})`。
   参考 pywebpush issue #162。
2. **同一个源下只能存在一个推送订阅**：用临时 VAPID 密钥建的订阅会与 OneSignal 的密钥冲突，
   之后 OneSignal 订阅会报 `InvalidStateError`。**验证完必须退订**：
   ```js
   const r = await navigator.serviceWorker.getRegistration();
   const s = await r.pushManager.getSubscription();
   if (s) await s.unsubscribe();
   ```

### 14.5 若将来真要启用，缺口清单

- **自有 Service Worker**：现有挂的是 OneSignal 的 SW，它只认自家格式的 payload；
  自建需自己的 SW（`push` 事件 → `showNotification`），并复用本站 SW 路由的
  `Cache-Control: no-store` + `Service-Worker-Allowed: /`（见 §6）。
- **订阅登记**：现有 `push_subscriptions` 存的是 OneSignal player id，需扩列或新增表存
  `endpoint` + `p256dh` + `auth`（即 `subscription.toJSON()` 的形态）。
- **投递层**：新增 `pywebpush` 依赖 → ⚠️ **必须同步 `requirements.txt`**，否则线上启动即
  `ModuleNotFoundError`（铁律 2）；VAPID 密钥对需持久化进配置（**不要** commit 私钥）。
- **Chrome 用户无解**：`grep` 得再干净也没用——这部分受众要么继续走 OneSignal，
  要么用「页面打开时的站内实时提醒」兜底（复用现有 WebSocket 通道 + `Notification` API，
  零第三方依赖、不受跟踪防护拦截，还能覆盖微信内置浏览器里的家长）。

---

## 15. 域名一致性：`www` 与非 `www` 是两个源（务必先读）

### 15.1 事实

浏览器把 `https://www.liusijin.com` 与 `https://liusijin.com` 当作**两个完全独立的网站**。
凡与「源」（origin）绑定的东西**各自一套**：

| 项目 | 是否按源隔离 |
|---|---|
| 通知权限（`Notification.permission`） | ✅ 各一套 |
| Service Worker 注册 | ✅ 各一套 |
| **推送订阅**（`pushManager.subscribe`） | ✅ 各一套 |
| 登录态（localStorage 里的 token） | ✅ 各一套 |
| Cookie | ✅ 各一套 |

### 15.2 必须对齐的三处

| 位置 | 要求 |
|---|---|
| OneSignal 后台的站点域名（`chrome_web_origin`） | 与用户**实际访问**的 origin 一致 |
| 后端 `SITE_URL`（推送 `url` 字段的来源，见 §10） | 同上；未配置时用代码默认值 |
| 用户授权/订阅所在的那个源 | 同上 |

**当前决策（2026-09-28）**：主域名定为 **`www.liusijin.com`** —— 它与 nginx 证书目录
（`/etc/letsencrypt/live/www.liusijin.com/`）和 `deploy.sh` 的证书路径一致。
OneSignal 后台、`push.py` 的 `SITE_URL` 默认值、本文档全部示例已统一为带 `www`。

### 15.3 三个典型症状与真实原因

| 症状 | 原因 |
|---|---|
| 设置里明明改成「允许」，页面仍读回 `default` | 改的权限落到了**另一个源**上 |
| 订阅失败 / 报 `InvalidStateError` | OneSignal origin 与当前页面 origin 不一致 |
| 通知能弹出，**点开却是未登录** | 推送 `url` 指向了另一个源（那边 localStorage 没有 token） |

第三行是最隐蔽的：**推送看起来很成功，用户体验却是断的**。

### 15.4 排查第一步

**先打印 `location.origin`，不要凭域名想象。** 本次故障就是靠这一行定位的：

```js
console.log(location.origin);   // 期望 https://www.liusijin.com
```

### 15.5 彻底消除双源（可选，须先做前置检查）

现状：`deploy.sh` 生成的 nginx 配置把 `server_name` 写成了 `${DOMAIN} ${DOMAIN_WWW}`，
**两个域名都直接服务、互不重定向**，所以双源并存。要彻底解决，可在 nginx 里把裸域 301 到 www。

⚠️ **前置检查（必做）**：证书必须同时覆盖两个域名，否则 `nginx -t` 失败会中断部署：

```bash
sudo openssl x509 -in /etc/letsencrypt/live/www.liusijin.com/fullchain.pem -noout -text \
  | grep -A1 "Subject Alternative Name"
# 需同时有 DNS:www.liusijin.com 与 DNS:liusijin.com；缺一个先补：
#   sudo certbot --nginx -d www.liusijin.com -d liusijin.com
```

确认后再加裸域跳转：

```nginx
# 443：裸域 → www（证书路径按上一步的实际结果填）
server {
    listen 443 ssl http2;
    server_name liusijin.com;
    ssl_certificate     /etc/letsencrypt/live/www.liusijin.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.liusijin.com/privkey.pem;
    return 301 https://www.liusijin.com$request_uri;
}
```

> ⚠️ **做 301 前想清楚代价**：跳转会**作废另一个源上已有的授权与订阅**，那些设备要重新授权一次。
> 目前真实 Web 订阅数接近 0，是迁移成本最低的时机；若将来已有较多用户订阅，更稳妥的做法是
> **保持双源、只确保 OneSignal 与 `SITE_URL` 指向同一侧**，并接受「两侧都授权过的用户收到两份」
> 这点少量噪声。
>
> 另一个替代方案是**改 OneSignal 与代码去跟随非 www**（把上面三处改成 `liusijin.com`）——
> 但那样与 nginx 证书目录的命名就分家了，不推荐。
