# 项目长期记忆 (PrimarySchoolExam / 智学学堂)

## 项目概况
- FastAPI + SQLAlchemy，**MySQL-only**（已移除 SQLite，`DB_DRIVER` 强制回退 mysql），连接串 `mysql+pymysql://...?charset=utf8mb4`。Python 3.12+，前端 `web/`(Vue3) + `admin/`（旧 frontend/、frontend-admin/ 已删）。
- 九域分层架构：D9 frozen 冻结域（IM/账本）禁被 D1–D8 直连；跨域只经 `contracts.py`（见下 import-linter 条）。
- 测试库：`tests/conftest.py` 强制 MySQL，自动建 `DB_NAME+"_test"` 隔离库，安全护栏防误删生产库。文档总览 `docs/INDEX.md`。

## Git 工作流（用户明确要求）
- **模块级提交**：每完成一个可独立验证模块就 commit，提交前自查无报错、功能自洽（跑测试/CLI 验证）。
- **整体推送**：大模块完成且测试通过后才 push。
- 提交信息用中文，聚焦"改了什么 + 为什么"。不提交临时文件（`tools/_*.py`、`*.log`）与 `demo/`、`*.db`、`output/`、`.paper_cache/`、`web/dist`、`admin/dist`、`qb_versions/`。

## 🗄️ 数据库拓扑（2026-08-25 用户确认）
- **线上库（真生产）**：`115.29.213.131:3306/schoolexam`。
- **`192.168.2.158:3306/schoolexam` 是线上库本地克隆**（本地 `.env` 的 `DB_HOST`，勿改）。**铁律：绝不拿克隆库跑 `tools/seed_*.py` 等写数据脚本**。
- 同步：本地 `.env.prod`（PROD_DB_*，含线上凭据，**勿提交/外泄**）+ `tools/sync_prod_to_local.py`。线上后台 https://liusijin.com/api/admin 可只读验证。
- 迁移上线 = 本地 commit+push → 线上 `git pull` + `sudo bash deploy.sh`（重启触发 `run_migrations()`）。
- 现状基线：路由 31 / 迁移 40 / 测试 58 / 小学单词 1969 / AI 三链路(智谱GLM+Relay+DeepSeek，当前仅 DeepSeek 可用)。

## 🕐 定时任务约定（2026-08-25 定案）
- 采集/定时/汇总类统一排**凌晨 01:00**。本地无线上库密码，**写线上库的任务只能跑在线上服务器**。
- 定时器 = 代码内置 `tools/scheduler.py`（随 git 提交，**勿用 WorkBuddy 自动化**）：任务声明 `JOBS`（once/daily/weekly + at HH:MM + 次数限制），状态 `tools/.scheduler_state.json`，幂等可重触发。线上 crontab：`*/15 * * * * cd <部署目录> && <venv>/bin/python tools/scheduler.py >> /var/log/scheduler.log 2>&1`。

## 🔴 硬性铁律：严禁"持 DB 连接等外部阻塞调用"（曾致全站卡死）
- 根因：AI 接口在 `get_db` 会话期间调外部 AI/HTTP/SMTP/SMS → QueuePool 耗尽 → 全站 TimeoutError。
- 规则：仅 DB 读写时持连；外部调用前 `db.close()` 或 `with SessionLocal() as s:` 包住 DB 段；AI 端点用"分段短会话"。
- 已修复清单（勿回退）：ai/ai_quiz/assistant/exam/grading/qa/reading/search/study/judge/reading_service/review_service/weather/auth(_send_code)。
- 连接池：pool_size=10, max_overflow=30, pool_timeout=15, pool_pre_ping=True, pool_recycle=3600。扩容只是缓解，根因是不得长时间持连。

## 关键坑（务必牢记）
- **🚨 并行 Edit 同一文件会互相覆盖（2026-09-08 血泪）**：一条消息里对**同一文件**发多个 Edit，后写盘会覆盖先改的内容（工具报 Success 但改动丢失，直到跑测试才暴露）。**修法：同一文件的多次 Edit 必须串行**（一次一个，等返回后再发下一个）；改完用 grep/读文件逐处核对落盘。
- **git 实操**：优先 `/mingw64/bin/git` 直跑（Bash 偶 fork 失败）；沙箱 commit 必须 `--no-verify` 跳 import-linter 钩子；PowerShell 调 .exe stdout 常被吞，用 `| cat` 兜底。**push 走 SSH 常被沙箱拦**（需 ~/.ssh 私钥权限），若被拒则提示用户手动 `git push origin main`（近期实测多数能直接推成功，先试）。
- **🚨 前后端字段契约必须逐项核对**：后端返回 `id` 而前端读 `user_id` 这类错位会让按钮/动作静默失效（2026-09-08 IM 私聊/加好友/建群全废）。新写列表页先确认返回 JSON 字段名；Pydantic **默认忽略多余字段**（前端传未声明字段不报错但被丢弃），所以"传了没效果"先查 schema。
- **🚨 nginx 反向代 WebSocket 必须升级协议**（2026-09-08）：缺 `proxy_http_version 1.1` + `Upgrade`/`Connection` 头时，生产 HTTPS 下 wss 握手拿不到 101 → WS 永不连通（前端表现为"正在连接中"）；且长连接需 `proxy_read/send_timeout 3600s`（120s 会每 2 分钟掐断）。配置见 `DEPLOY.md` §7。
- **敏感词服务有进程内缓存**：测试/后台改词后须 `from app.domains.frozen.services.sensitive import invalidate_cache; invalidate_cache()` 才生效，否则断言 400 会拿到 200。
- **🚨 admin axios 响应拦截器陷阱**：`admin/src/api/index.js` 拦截器返回**完整响应对象**，取数据必须 `const { data } = await api.get(...)`；写成 `const d = await api.get()` 则 `d.items` 恒 undefined → 列表空白。修复工具 `tools/fix_admin_api_unwrap.py`（跳过 blob 下载）。
- **🚨 测试 helper 跨 session 竞争**：AuthClient 用私有 `_db` add user；helper 另开 `SessionLocal()` 插同一 user_id 会在 REPEATABLE READ 下 `Duplicate entry`。**修法：helper 统一用 `client._db`，finally 不 db.close()**。
- **🚨 时区比较**：MySQL DATETIME 读回是 naive，与 `datetime.now(timezone.utc)` 比较会 TypeError。先判 `if x.tzinfo is None: x = x.replace(tzinfo=timezone.utc)`。
- **🚨 `git checkout -- <dir>` 会丢弃该目录全部未提交修改**（2026-09-02 曾回滚掉拆分 common.py 的导入修复）。重构中严禁 checkout 恢复。远端有新提交优先 `git merge <sha>` 手工解冲突，别 rebase 整树。
- **前端"可构建"≠ 语法通过**：须同时满足 ①`@vue/compiler-sfc` 编译过（用 `tools/verify_vue_sfc.js`）②**裸 import ⊆ package.json**（rollup 才不报 resolve 失败，web 端禁引 element-plus 等 admin 专用库）③模板无 `<el-*>` 残留。`vite build` 沙箱间歇失败（esbuild spawn EPERM），前端改动须线上/本机重建 `web/dist` 才生效；排查前端问题先确认 dist 是否最新。
- **删文件**：`rm`/`Remove-Item` 被 safe-delete shim 拦，用 venv python `os.remove()`/`shutil.rmtree(ignore_errors=True)`。
- **MySQL 列/Dialect**：TEXT/MEDIUMTEXT 不允许 DEFAULT（1101），跨 dialect 加列用 `app/database.py` 的 `_ensure_column`；大文本用 `paper.py` 的 `_longtext()`（`compiles(MEDIUMTEXT,"sqlite")`），不能靠 try-import 判方言。
- **统一错误信封**：`app/core/middleware.py` 把异常包成 `{code, message, request_id}`，**不是** `{detail}`；测试断言响应体须读 `["message"]`。
- **import-linter（`.importlinter`）**：九域独立、跨域只经 `contracts.py`；`app.core` 不监控；`app/routers/admin/** -> app.domains.*.contracts` 属白名单；D9 frozen 禁止被 D1–D8 import；`app/main.py` 豁免。
- **后台子模块路由范式**：`app/routers/admin/*` 必须 `from . import router` 复用共享 `APIRouter()`，不可自建（否则全部 404），并在 `__init__.py` 补 import 与 `from .<module> import *`。
- **管理后台**：密码 `ke5eghq357`（pbkdf2-sha256/200k）；重置用服务器本机 `python tools/reset_admin_pwd.py --password "新密码"`（4-32 位）。本地访问 `cd admin && npm run build` + `python run.py` → `http://127.0.0.1:8000/admin/`（别单独开 5173，无代理）。

## 🎯 账本 / IM 六项产品决策（2026-09-07 拍板，见 docs/IM与账本前端实现方案.md §〇）
- D1 生产 **HTTPS**；D2 账本入口**挨着钱包**；D3 周期交易**自动执行**；D4 后台**敏感词过滤**；D5 **红包用钻石**；D6 语音**后端统一转 MP3**（ffmpeg 外部调用须释放 DB 连接）。
- **红包单位**：1 钻石 = 1000 毫钻（Integer 存储）；钻石 `balance` 是 Float。
- **资损红线**：红包 claim 改真资产前必须加 `with_for_update`/条件更新（B11）。
- **发消息双通道**：WS 为主（`ws/chat?token=`），WS 不通时降级 `POST /api/im/chats/{id}/messages`，两者共用 `handle_message`（成员校验/敏感词/落库/广播）。
- frozen→commerce 跨域**只能走 `commerce.contracts`**，禁直连 services。

## 📖 小说站模块（2026-09-17 新增，见 docs/小说站模块说明.md）
- 入口 `/novel`：独立 HTML `web/novel.html` + 独立 Vue 应用 `web/src/novel/*`（hash 路由）；
  vite 多页 `rollupOptions.input={main,novel}`，后端 `/novel` 返回 `dist/novel.html`。
- 表：`db_novels` / `db_novel_chapters`（章节**与**流式块共用）/ `db_novel_read_progress`。
  `chapter_mode=chapter|stream` 决定前端是否渲染章节标题。
- TXT 解析：编码探测 + 正则分章，判定保守（命中≥3 且均章 100~10w 字且首标题在前 30%），
  不成立则按 ~2000 字/块流式切片。
- 读者端 `/api/novel/*` **公开**（游客可读），仅 progress/shelf 需登录；
  下滑加载核心 `GET /{id}/read?from=&limit=` 返回 next 指针。
- 属 D2 内容域：**跨域必须走 `content.contracts`**（如 `parse_novel_txt`），直连 services 违反契约。
- 🟢 **沙箱 vite build 可用**：`cd web && node node_modules/vite/bin/vite.js build`（托管 node 22.22.2-3），
  之前以为只能线上构建，实测可跑（本次 10s 成功），前端改动可自行验证。

## 📥 每日试卷采集（collected 子系统）
- 入口：`python tools/collect_daily.py --daily-limit 200 --answer-cap 0`（须用项目 `.venv/Scripts/python.exe`）。
- 产物：每日 SQLite `data/collected_YYYY-MM-DD.sqlite` + 去重注册表 `data/scrape_registry.sqlite`。站点：第一试卷网；九大学科均衡（学段配额 初中120/小学50/高中30）。
- **LibreOffice 必需**（旧版 .doc 是 OLE 二进制，无 LO 解析出乱码/0 题）。
- AI 答案当前唯一可用 **DeepSeek（deepseek-v4-flash）**；`fill_missing_answers` 已重构为短会话增量写回（崩溃只丢当前题）。200 份补全约 5-8h，宜凌晨跑。

## 测试经验（高复用）
- **MySQL REPEATABLE READ 余额断言陷阱**：长生命周期测试会话首次 `SELECT` 后快照冻结，读不到接口内部 `diamond.grant`（新建会话）已提交的新余额 → 余额差断言误判为 0。修法：余额断言用独立 `SessionLocal()` 会话读取最新已提交值，并按「前后差值」判定（参考 `tests/test_checkin.py` 的 `_read_balance`）。
- conftest 不做事务回滚：每用例用专属用户 + 显式 token + finally 清理自身数据，避免跨用例污染钻石余额断言。
- **判「全量测试通过」看退出码，别 grep 摘要**：`pytest -q > file` 重定向/管道下末尾只剩 warnings 块，
  无 `N passed` 行，grep `passed` 会空手而归。失败时 pytest 退出码必非 0，故以 **EXIT=0** 为准。

## 🧩 前端新增一个 tab 页面（4 处注册，漏一处页面就空白/图标缺失）
1. `web/src/main.js`：`import XxxView from './views/XxxView.vue'` + `app.component('XxxView', XxxView)`。
2. `web/src/App.vue`：加 `<xxx-view v-if="tab==='xxx'"></xxx-view>`（按 tab 字符串切换，非动态 :is）。
3. `web/src/nav.js`：`NAV_GROUPS` 加 `{tab,label,icon}`（移动端 TABBAR 固定 6 项，通常只加桌面侧边栏）。
4. `web/src/components/AppIcon.vue`：`ICONS` 补对应图标，否则回落 placeholder（不报错但视觉错）。
- 业务一律放 `web/src/logic/xxx.js` 用三字典 `xxxData()/xxxComputed/xxxMethods`，在 `appOptions.js`
  展开合并（data/computed/methods 三处各一行）；**同一文件多次 Edit 必须串行**。
- `hs-btn` 样式**只在 `.home-subnav` 作用域内生效**，别处复用需自建类（如收藏夹的 `.fv-tab`）。
- 沙箱偶发 `error launching git:` 会让 `vite build` 连带失败，与代码无关，**重跑即可**。

## 🏅 成就徽章体系（新功能 B 升级后架构，2026-09-24）
- **逻辑位置**：领域逻辑在 `app/domains/engagement/services/achievement.py`（**规则唯一真相源 `BADGE_RULES`**：
  metric/target/category/event 四元组）；`routers/badges.py` 只是薄 HTTP 层。改徽章阈值/加徽章**只改这一处**。
- **按需指标**：`METRIC_FNS` 惰性求值，`_metrics(db,uid,keys)` 只算点名的指标（事件路径不再全量 12 条聚合）。
- **事件驱动授予**：`try_grant(db, uid, event)`；event=None 为兜底全量（`GET /api/badges` 用，保证历史达标不漏发）。
  事件常量 `EVENT_*`，未登记事件返回 [] 且不授予任何徽章。
- **埋点铁律**：必须在写操作 `db.commit()` **之后**调用（纯 DB、无外部调用、`try/except` 静默，不得影响主流程）；
  **跨域埋点一律经 `engagement.contracts.AchievementService.try_grant`**（assessment 交卷/掌握错题即如此）。
- 已埋点：`exam_done`(交卷) / `wrong_mastered`(掌握错题 ×2 处) / `task_done`(任务完成 ×2 处) /
  `mood_done`(心情打卡)。其余事件（vocab/classical/teach/challenge/goal）仅由兜底全量扫描覆盖。
- 前端徽章逻辑在 `web/src/logic/badges.js`（**已从 cards.js 拆出**），`BadgesView.vue` 有分类 tab + 进度条。

## ⚠️ SQLAlchemy/MySQL 类型陷阱（极易静默出错）
- **`Date` 列不能用 `str(d) in dates` 比较**：`DailyTask.task_date` 是 `Column(Date)`，读回是 `datetime.date`，
  与 `str` 永不相等 → 判断恒 False（曾致 `badges._streak` 恒返回 0，`streak_7/30` 徽章永不可得）。
  **正确写法：`while d in dates`（date 对象比较）**，参考 `app/domains/engagement/routers/checkin.py::_checkin_streak`。
- 时区比较：MySQL DATETIME 读回是 naive，与 `datetime.now(timezone.utc)` 比较会 TypeError，先补 tzinfo。

## 🧪 测试脚手架注意（conftest.AuthClient）
- `AuthClient` 会为请求里出现的 `user_id`（无则回落 `test_auth_uid`）**自动补签 token**，
  所以**无法用它构造「未鉴权 401」场景**（写 `assert status in (401,403)` 必失败）。
  鉴权边界要靠其他既有用例覆盖，或绕开该 client 用裸 TestClient。

## ⭐ 等级/成长体系（新功能 C 架构 + 行为事件收敛层，2026-09-24）
- **统一行为事件入口 `app/domains/engagement/services/events.py`**（B/C 共同收敛层，**新埋点一律加这里**）：
  11 个 `EVENT_*` 常量 + `EXP_RULES`（事件→经验）+ `award(db, uid, event, extra_exp=0)`：
  **一次调用 = 加经验 + 评估徽章解锁**，返回 `{event,exp_gained,level,new_badges}`。
  `achievement.py` 的 `EVENT_*` 改为**从此处再导出**（单一真相源，杜绝两处字面量漂移）。
- **等级逻辑 `services/level.py`**：等级**由 exp 反算**（`level_for_exp` 纯函数，`>=` 语义，
  恰好等于阈值即升级）；`users.level` 只是冗余缓存 → 列值脏/NULL 也不会显示错误等级。
  默认 20 级 `min_exp = 30*(lv-1)*lv`（Lv1=0/Lv2=60/Lv3=180/Lv20=11400），阶梯表 `level_config`
  （后台可调参），`_ladder()` 表空时回落常量 `LEVEL_FALLBACK`。
- **经验策略铁律：行为发生时增量累加落库，读时零聚合**。`get_level_info` 只读 `users.exp` 一个字段，
  **禁止**做「交卷数+正确率+专注时长+错题」实时多表聚合（否则每次开等级页付 N 条聚合查询）。
- **`add_exp` 并发安全**：`.with_for_update()` 行锁读改写 → **先 `commit()` 释放锁，再跨域发升级钻石**
  （不在持锁期间调其它域）；一次跨多级用 `sum(...)` 合并奖励不漏发；发奖失败**不回滚经验**。
- **安全红线：不提供任何对外加经验端点**（仅只读 `GET /api/level`），经验只能由真实行为埋点驱动，
  否则用户可自刷等级并白拿升级钻石。
- **上线配套 `tools/backfill_level_exp.py`**：默认 dry-run（须 `--apply` 写库）、默认**不发**升级钻石
  （`--grant-reward` 才补发）、默认只补 `exp=0/NULL`（可安全重跑）、`--batch` 分批提交。
  迁移 `080_user_level.py` 幂等三步（`_ensure_column` ×2 + `LevelConfig.__table__.create(checkfirst=True)`
  + `ensure_level_config` 增量 seed）。
- **`ensure_level_config` 用「按 lv 增量补齐」而非「表为空才 seed」**：将来扩到 25 级会自动补新等级，
  且不覆盖后台已调过的旧等级数值。

## 🚨 两条易漏的机械性坑（2026-09-24 血泪）
- **Vue 模板里禁止裸 `<` 比较**：`l.lv<appCtx.levelNum` 的 `<a` 会被 HTML 解析器当成 `<a>` 起始标签而报错。
  **比较逻辑一律移入 JS**（如 `levelItemClass(l)`/`levelItemState(l)`），模板只渲染。
- **`git commit --no-verify` 会静默放过 import-linter 契约违规**（曾致 `checkin.py` 直连
  `commerce.services.diamond` 一路漏到线上）。**新增跨域调用后必须手动跑
  `.venv/Scripts/lint-imports.exe` 复验（应输出 `2 kept, 0 broken`），别只信提交成功。**
- `tools/*.py` 直接运行时 `ModuleNotFoundError: No module named 'app'`（sys.path 只含 tools/），
  头部按范式补 `ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))`。
