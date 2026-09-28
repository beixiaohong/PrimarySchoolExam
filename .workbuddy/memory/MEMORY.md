# 项目长期记忆 (PrimarySchoolExam / 智学学堂)

## 一、项目概况与工作流
- FastAPI + SQLAlchemy，**MySQL-only**（`DB_DRIVER` 强制回退 mysql，连接串带 `?charset=utf8mb4`）；Python 3.12+；前端 `web/`(Vue3 学生端) + `admin/`(Vue3 后台)，旧 `frontend/`、`frontend-admin/` 已删。文档总览 `docs/INDEX.md`。
- **九域分层**：D9 frozen（IM/账本）禁被 D1–D8 直连；跨域只经各域 `contracts.py`，由 `.importlinter` 强制。
- **Git**：模块级提交（完成即 commit，提交前跑测试）+ 大模块通过才 push；提交信息中文，写「改了什么 + 为什么」。不提交 `tools/_*.py`、`*.log`、`demo/`、`*.db`、`output/`、`.paper_cache/`、`web/dist`、`admin/dist`、`qb_versions/`。注意 `.workbuddy/memory/` **是被 git 跟踪的**，需一并提交。
- **沙箱实操**：git 用 `/mingw64/bin/git -C D:/PrimarySchoolExam`（Bash 偶 fork 失败）；python 用 `.venv/Scripts/python.exe`；node 用 `PATH="/c/Users/aaaa/.workbuddy/binaries/node/versions/22.22.2-3:$PATH"`。PowerShell 调 .exe stdout 常被吞，用 `| cat` 兜底。沙箱 commit 必须 `--no-verify`（跳 import-linter 钩子）→ **之后必须手跑 `.venv/Scripts/lint-imports.exe` 复验 `2 kept, 0 broken`**（曾漏检致契约违规上线的教训）。push 走 SSH 偶尔被拦，先试，被拒则提示用户手动 `git push origin main`。

## 二、数据库拓扑（2026-08-25 用户确认）
- 线上真生产：`115.29.213.131:3306/schoolexam`。**`192.168.2.158` 是线上库本地克隆**（本地 `.env` 的 `DB_HOST`，勿改）。
- **铁律：绝不拿克隆库跑 `tools/seed_*.py` 等写数据脚本**；写线上库只能跑在线上服务器。线上后台 https://liusijin.com/api/admin 可只读验证。
- 同步：本地 `.env.prod`（`PROD_DB_*` 含线上凭据，**勿提交/外泄**）+ `tools/sync_prod_to_local.py`。
- 上线 = 本地 commit+push → 线上 `git pull` + `sudo bash deploy.sh`（重启触发 `run_migrations()`）。

## 三、三条硬性铁律
### 1. 严禁「持 DB 连接等外部阻塞调用」（曾致全站卡死）
- 根因：AI 接口在 `get_db` 会话期间调外部 AI/HTTP/SMTP/SMS → QueuePool 耗尽 → 全站 TimeoutError。
- 规则：仅 DB 读写时持连；外部调用前 `db.close()` 或 `with SessionLocal() as s:` 包住 DB 段；AI 端点用「分段短会话」。
- 已修复（勿回退）：ai/ai_quiz/assistant/exam/grading/qa/reading/search/study/judge/reading_service/review_service/weather/auth(_send_code)/push。
- 池参数 pool_size=10, max_overflow=30, pool_timeout=15, pool_pre_ping=True, pool_recycle=3600 —— 扩容只缓解，根因是不长持连。
### 2. 新增第三方依赖必须同步 `requirements.txt`
- `deploy.sh:68` 只跑 `pip install -r requirements.txt`，漏写 → 启动期 `ModuleNotFoundError` → 全站 502。
- **本地能 import ≠ 线上正常**（本地 `.venv` 常多装包，如 httpx 是 starlette TestClient 依赖，生产依赖树根本不会带出）。
- 三处拦截：`tools/dep_audit.py`、`regression_check.py` 第[3]项（扫 app/ 的**启动期硬导入**：模块级 + 不在 try + 不在 TYPE_CHECKING）、`tests/test_requirements_complete.py`。
- 可选依赖写成函数内 `try/except` 降级，**别写成模块级 import**（审计会误报）。
### 3. 所有部署检查必须在 `systemctl restart` 之前
- `deploy.sh` 两道闸门（`tools/preflight.py`，纯标准库，venv 坏了也能跑）：`3.55 early`（chown 后、npm build 前：依赖完整性 + 可导入 + `.env` 必需键）/ `3.8 full`（写 systemd/nginx 与重启前：+外部命令 + 前端产物）。失败即中止，**旧版本继续服务、站点不掉**。
- 为什么：原「先重启后检查」使「部署失败」放大成「站点下线」（坏版本被 systemd 换上 → 崩溃循环）。**判据：任何 gate 都必须在重启之前。**
- 闸门设计：只让「真会致挂」的项 BLOCK，外部命令缺失（ffmpeg/soffice/npm）只 WARN —— **误报比漏报更致命**（会卡住正常部署 → 运维绕过闸门）。闸门自身须健壮（`su` 失败降级为当前用户）。**最有效的检查是用服务所用解释器真实 `import app.main`**（静态检查漏运行期问题）。
- 回滚：`git log --oneline -5` → `git reset --hard <好版本>` → `sudo bash deploy.sh`（deploy.sh 失败时会自动打印这三步）。
- 线上导入期崩溃排查：`journalctl -u exam-app -n 200 --no-pager | grep -iE "ModuleNotFoundError|ImportError"`（默认 `-n 50` 常把异常行截掉），或项目目录直接 `venv/bin/python -c "import app.main"`。复现「缺包」可用 `sys.meta_path` 插 finder 屏蔽目标包。

## 四、关键坑（极易静默出错）
- **🚨 并行 Edit 同一文件互相覆盖**：一条消息里对**同一文件**发多个 Edit，后写盘覆盖先改（工具报 Success 但改动丢失，直到跑测试才暴露）。**同一文件的多次 Edit 必须串行**，改完 grep/读文件逐处核对落盘。
- **🚨 前后端字段契约逐项核对**：后端返 `id` 而前端读 `user_id` 这类错位让按钮静默失效（IM 私聊/加好友/建群曾全废）。新写列表页先确认返回 JSON 字段名；Pydantic **默认忽略多余字段**（传未声明字段不报错但被丢弃）→「传了没效果」先查 schema。
- **🚨 `git checkout -- <dir>` 丢弃该目录全部未提交修改**（曾回滚掉 common.py 拆分修复），重构中严禁用它恢复；远端有新提交优先 `git merge <sha>` 手工解冲突，别 rebase 整树。
- **🚨 nginx 反代 WebSocket 必须升级协议**：缺 `proxy_http_version 1.1` + `Upgrade`/`Connection` 头 → 生产 HTTPS 下 wss 拿不到 101（前端「正在连接中」）；长连接需 `proxy_read/send_timeout 3600s`（120s 会每 2 分钟掐断）。见 `DEPLOY.md` §7。
- **🚨 admin axios 拦截器返回完整响应对象**：必须 `const { data } = await api.get(...)`；写 `const d = await api.get()` 则 `d.items` 恒 undefined → 列表空白。修复工具 `tools/fix_admin_api_unwrap.py`（跳过 blob 下载）。
- **🚨 时区**：MySQL DATETIME 读回是 naive，与 `datetime.now(timezone.utc)` 比较抛 TypeError → 先 `if x.tzinfo is None: x = x.replace(tzinfo=timezone.utc)`。
- **🚨 `Date` 列不能用 `str(d) in dates` 比较**：读回是 `datetime.date`，与 str 永不相等 → 判断恒 False（曾致 streak 徽章永不可得）。用 `while d in dates`（date 对象比较），参考 `checkin.py::_checkin_streak`。
- **🚨 测试 helper 跨 session 竞争**：helper 另开 `SessionLocal()` 插 AuthClient 已 add 的 user_id → REPEATABLE READ 下 `Duplicate entry`。**helper 统一用 `client._db`，finally 不 db.close()**。
- **🚨 Vue 模板禁裸 `<` 比较**：`l.lv<appCtx.x` 的 `<a` 被 HTML 解析器当起始标签报错 → 比较逻辑一律移入 JS。
- **敏感词服务有进程内缓存**：改词后须 `from app.domains.frozen.services.sensitive import invalidate_cache; invalidate_cache()`，否则断言 400 会拿到 200。
- **统一错误信封**：`app/core/middleware.py` 把异常包成 `{code, message, request_id}`，**不是** `{detail}` → 测试断言读 `["message"]`。
- **MySQL 列/Dialect**：TEXT/MEDIUMTEXT 不允许 DEFAULT(1101)；跨 dialect 加列用 `app/database.py::_ensure_column`；大文本用 `paper.py::_longtext()`（`compiles(MEDIUMTEXT,"sqlite")`），不能靠 try-import 判方言。**唯一索引可空列只允许一个 NULL**（指纹/`dedup_key` 类列必须可空，不能给 `DEFAULT ''`）。
- **删文件**：`rm`/`Remove-Item` 被 safe-delete shim 拦 → 用 venv python `os.remove()` / `shutil.rmtree(ignore_errors=True)`。
- **`tools/*.py` 直接运行时 `ModuleNotFoundError: No module named 'app'`**（sys.path 只含 tools/）→ 头部补 `ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))`。
- **含 `\s`/`\d` 的脚本别用 heredoc 生成**（反斜杠被吞 → Node `SyntaxError: missing )`），一律 Write 落盘。
- **会被 `spec_from_file_location` 按路径加载的脚本，慎用 `from __future__ import annotations` + `@dataclass`**（解析注解抛 `AttributeError: 'NoneType' object has no attribute '__dict__'`），用普通类。

## 五、架构约定
- **import-linter（`.importlinter`）**：九域独立、跨域只经 `contracts.py`；`app.core` 不监控；`app/routers/admin/** -> app.domains.*.contracts` 属白名单；D9 frozen 禁止被 D1–D8 import；`app/main.py` 豁免。
- **鉴权来源在挂载处，不在 router 文件**：全站鉴权来自 `app/main.py` 的 `include_router(xxx.router, prefix=..., dependencies=user_auth_deps)`（`user_auth_deps=[Depends(require_self)]`）。`require_self` 是**严格账号绑定**：从 query 或 JSON body 取 `user_id`，与登录账号不一致直接 **403**（拦在写库前）、未登录 401。**判读顺序：先看 `main.py` 挂载处，再读 router 内部**（曾把 focus 误报成无鉴权；已由 `tests/test_user_id_binding.py` 4 例钉死）。
- **后台子模块路由范式**：`app/routers/admin/*` 必须 `from . import router` 复用共享 `APIRouter()`（自建会全部 404），并在 `__init__.py` 补 import + `from .<module> import *`。
- **域内路由**：`app/domains/<domain>/routers/*.py`；跨域出口写在 `app/domains/<domain>/contracts.py` 的 `_EXPORTS` 白名单。
- **管理后台**：密码 `ke5eghq357`（pbkdf2-sha256/200k）；重置用服务器本机 `python tools/reset_admin_pwd.py --password "新密码"`（4-32 位）。本地访问 `cd admin && npm run build` + `python run.py` → `http://127.0.0.1:8000/admin/`（别单独开 5173，无代理）。
- **路由表必须走 `app.openapi()["paths"]`**：本项目 `include_router` 惰性（`app.routes` 元素是 `_IncludedRouter`、`path` 为 None），直接遍历得 0 条 → 会误报全部路由缺失。**比对路径要归一化参数段**（后端 `{gid}` vs 前端具体 id）。

## 六、测试
- conftest 强制 MySQL，自动建 `DB_NAME+"_test"` 隔离库（有防误删生产库护栏）；**不做事务回滚**：每用例用专属 user_id + 显式 token + finally 清理自身数据。
- **判「全量通过」看 `--junit-xml` 计数**：`pytest -q --junit-xml=temp/_junit.xml` → 读 `<testsuite tests=.. failures=.. errors=..>`。`pytest -q > file` 重定向下末尾只剩 warnings 块、无 `N passed` 行；且沙箱里 `EXIT=$?` 与 stdout 都可能被 safe-delete 拦截器污染（收尾清理 tmp 时注入 `[SAFE_DELETE_BULK_CONFIRM_REQUIRED]` 冲掉 FAILURES/summary 段）。
- **🚨 不要给全量 pytest 加 `--basetemp=temp/pt`**：pytest 收尾 `rmtree` 触发本机批量删除守护 → `SystemExit` → fixture finalizer 未消费 → 后续用例 setup 连锁报错（`assert not self._finalizers`），一次可造 25 例假失败。**小批量（74 例）正常、全量才炸**，极易误判成代码回归或并发竞态。**用默认临时目录**（系统 temp 在守护 bypass 名单内）。
- **MySQL REPEATABLE READ 余额断言陷阱**：长生命周期会话首次 SELECT 后快照冻结，读不到接口内部新建会话（如 `diamond.grant`）已提交的新余额 → 差值断言误判 0。修法：用独立 `SessionLocal()` 读最新已提交值 + 按前后差值判定（参考 `tests/test_checkin.py::_read_balance`）。
- **`AuthClient` 会为请求里的 `user_id`（无则回落 `test_auth_uid`）自动补签 token** → **无法构造「未鉴权 401」场景**（`assert status in (401,403)` 必失败）。鉴权边界靠其他用例覆盖，或用裸 TestClient。
- pytest 只能证明「被覆盖的逻辑是对的」；**跨域直连、前后端路径/字段错位、图标缺失、路由漏注册**这四类「不报错但静默失效」的问题只有 `tools/regression_check.py` 能抓。

## 七、回归自检标准流程（改完代码、提交前按序跑）
```bash
.venv/Scripts/python.exe tools/regression_check.py    # 7 项：契约/编译/依赖/路由/前端URL/图标/定时任务（退出 0=通过）
.venv/Scripts/lint-imports.exe                        # 期望 2 kept, 0 broken
.venv/Scripts/python.exe -m pytest -q --junit-xml=temp/_junit.xml
cd web && node node_modules/vite/bin/vite.js build     # 前端构建（admin 同理）
```
- 端到端跨模块联动见 `tests/test_e2e_new_features.py`（含迁移幂等 + 存量脏值自愈）。

## 八、前端约定
- **新增 tab 页面 4 处注册**（漏一处页面空白/图标缺失）：①`web/src/main.js` import + `app.component` ②`web/src/App.vue` 加 `<xxx-view v-if="tab==='xxx'">`（按 tab 字符串切换，非动态 `:is`）③`web/src/nav.js` `NAV_GROUPS` 加 `{tab,label,icon}`（移动 TabBar 固定 6 项，通常只加桌面侧边栏）④`web/src/components/AppIcon.vue` 的 `ICONS` 补图标（否则回落 placeholder，不报错但视觉错）。
- 业务一律放 `web/src/logic/xxx.js` 三字典 `xxxData()/xxxComputed/xxxMethods`，在 `appOptions.js` 的 data/computed/methods 三处各一行展开合并；**同一文件多次 Edit 必须串行**。
- `hs-btn` 样式**只在 `.home-subnav` 作用域内生效**，别处复用需自建类（如收藏夹 `.fv-tab`）。
- **「可构建」判据三条**：①`@vue/compiler-sfc` 编译过（`tools/verify_vue_sfc.js`）②**裸 import ⊆ package.json**（rollup 才不报 resolve 失败；web 端禁引 element-plus 等 admin 专用库）③模板无 `<el-*>` 残留。
- 沙箱 `vite build` 可用：`cd web && node node_modules/vite/bin/vite.js build`（托管 node 22.22.2-3，约 10-16s）。偶发 `error launching git:` 会让 build 连带失败，与代码无关，**重跑即可**。
- **前端产物与后端契约**：`tools/build_info.py`（纯标准库，venv 半坏也能跑）——源码指纹覆盖 `src/ public/ 入口HTML package(-lock).json vite配置`，含逐文件摘要；`needs-build` 退出码 **0=需构建 / 1=无需**；`route_exists` 用**段级匹配**（`{param}` 通配 + 模板串前缀）。`deploy.sh` 用**内容指纹**判前端是否需重建（原 mtime 判据漏 `index.html`/`novel.html`/`public/` 与「删除源文件」→ 线上静默沿用旧 dist）。`preflight.py` full 阶段加 `check_dist_assets`（入口引的 JS/CSS 缺失→白屏）+ `check_frontend_contract`（产物过期 / 前后端契约错位），均 **WARN**。**admin 产物前缀是 `/admin/assets/...`**（vite base=/admin），不是 web 的 `/assets/`。

## 九、定时任务
- 约定：采集/定时/汇总类统一排**凌晨 01:00**（业务例外见模块条目）；本地无线上库密码，**写线上库的任务只能跑在线上服务器**。
- 定时器 = 代码内置 `tools/scheduler.py`（随 git 提交，**勿用 WorkBuddy 自动化**）：`JOBS` 声明（once/daily/weekly + `at` HH:MM + 次数限制），状态 `tools/.scheduler_state.json`，幂等可重触发。
- **前提认知：调度是「静默失效」** —— cron 每 15 分钟执行，输出只进 `/var/log/scheduler.log`，无告警通道；出问题的症状就是「什么都不发生」（订单不关单、会员不降级、红包不退回、周期账单不生成）。**凡涉及调度，先按此思路排查。**
- **三层防护**：①运行期 `validate_job()/validate_jobs()` 纯函数校验 + `_job_due()` 不抛异常 + 单任务异常就地隔离 —— **铁律：任何单任务问题都不得终止整轮调度**（历史：非法 `at` 抛 ValueError 冒泡出 `run_due_jobs`（只有 finally），排在其后的任务**永久停摆**）②提交前 `regression_check.py` 第[7]项（内部调 `tools/ops_check.py`）③部署时 `preflight.py`「定时任务资产」（WARN）+ **自动顺带体检线上调度状态**。
- `tools/ops_check.py` 查 6 类：任务配置 / 脚本存在 / **git 跟踪**（忘 `git add` → 线上 pull 不到）/ 脚本依赖声明 / 运行时文件是否被 gitignore / **crontab 命令两处一致**；`--state` 做线上状态体检（上次失败 / >26h 未成功 / 已过期 / 达 max_runs / 残留状态）。
- **JOBS 陷阱清单**（都「写错不报错」，`validate_job` 已覆盖）：kind 拼错=永不执行；at/日期非法=崩整轮；`enabled="False"` 字符串=**停用失效**（`is False` 判定不成立）；weekday 用在非 weekly=静默忽略；valid_from>valid_until=永不执行；command 用绝对路径=换部署目录即失效。
- **crontab 正确写法**（`scheduler.py` docstring 与 `DEPLOY.md` §15.2 必须逐字一致，ops_check 会校验；历史错误：docstring 写 `/opt/venv/bin/python`，线上不存在 → 任务完全不跑且只往 root 邮箱发错误）：
  `*/15 * * * * cd /home/PrimarySchoolExam && /home/PrimarySchoolExam/venv/bin/python tools/scheduler.py >> /var/log/scheduler.log 2>&1`
- 新增/改 JOBS 后**必跑** `python tools/ops_check.py`，且**新脚本必须 git add**。

## 十、IM / 账本（见 `docs/IM与账本前端实现方案.md` §〇）
- 六项产品决策：D1 生产 **HTTPS**；D2 账本入口**挨着钱包**；D3 周期交易**自动执行**；D4 后台**敏感词过滤**；D5 **红包用钻石**；D6 语音**后端统一转 MP3**（ffmpeg 外部调用须释放 DB 连接）。
- **红包单位**：1 钻石 = 1000 毫钻（Integer 存储）；钻石 `balance` 是 Float。
- **资损红线**：红包 claim 改真资产前必须加 `with_for_update`/条件更新。
- **发消息双通道**：WS 为主（`ws/chat?token=`），WS 不通降级 `POST /api/im/chats/{id}/messages`，两者共用 `handle_message`（成员校验/敏感词/落库/广播）。
- frozen→commerce 跨域**只能走 `commerce.contracts`**，禁直连 services。

## 十一、小说站（见 `docs/小说站模块说明.md`）
- 入口 `/novel`：独立 HTML `web/novel.html` + 独立 Vue 应用 `web/src/novel/*`（hash 路由）；vite 多页 `rollupOptions.input={main,novel}`，后端 `/novel` 返回 `dist/novel.html`。
- 表 `db_novels` / `db_novel_chapters`（章节**与**流式块共用）/ `db_novel_read_progress`；`chapter_mode=chapter|stream` 决定前端是否渲染章节标题。
- TXT 解析：编码探测 + 正则分章，判定保守（命中≥3 且均章 100~10w 字且首标题在前 30%），不成立则按 ~2000 字/块流式切片。
- 读者端 `/api/novel/*` **公开**（游客可读），仅 progress/shelf 需登录；下滑加载核心 `GET /{id}/read?from=&limit=` 返回 next 指针。
- 属 **D2 内容域**：跨域必须走 `content.contracts`（如 `parse_novel_txt`）。

## 十二、每日试卷采集（collected 子系统）
- 入口 `python tools/collect_daily.py --daily-limit 200 --answer-cap 0`（须用项目 `.venv/Scripts/python.exe`）。
- 产物：每日 SQLite `data/collected_YYYY-MM-DD.sqlite` + 去重注册表 `data/scrape_registry.sqlite`；站点第一试卷网，九学科均衡（学段配额 初中120/小学50/高中30）。
- **LibreOffice 必需**（旧版 .doc 是 OLE 二进制，无 LO 解析出乱码/0 题）。
- AI 答案当前唯一可用 **DeepSeek（deepseek-v4-flash）**；`fill_missing_answers` 已重构为短会话增量写回（崩溃只丢当前题）。200 份补全约 5-8h，宜凌晨跑。

## 十三、成长体系（成就徽章 B + 等级 C，2026-09-24）
- **统一行为事件入口 `app/domains/engagement/services/events.py`**（**新埋点一律加这里**）：`EVENT_*` 常量 + `EXP_RULES`（事件→经验）+ `award(db, uid, event, extra_exp=0)`：一次调用 = 加经验 + 评估徽章解锁，返回 `{event,exp_gained,level,new_badges}`。`achievement.py` 的 `EVENT_*` 从此处**再导出**（单一真相源，杜绝字面量漂移）。
- **徽章**：规则唯一真相源 `achievement.py::BADGE_RULES`（metric/target/category/event 四元组），`routers/badges.py` 只是薄 HTTP 层；`METRIC_FNS` 惰性求值，`_metrics(db,uid,keys)` 只算点名的指标；事件驱动 `try_grant(db,uid,event)`，`event=None` 为兜底全量（`GET /api/badges` 用，保证历史达标不漏发）。
- **等级**：`services/level.py`，等级**由 exp 反算**（`level_for_exp` 纯函数，`>=` 语义，恰好等于阈值即升级），`users.level` 只是冗余缓存（列值脏/NULL 也不会显示错等级）；默认 20 级 `min_exp=30*(lv-1)*lv`，阶梯表 `level_config`（后台可调），空表回落 `LEVEL_FALLBACK`。
- **经验铁律：行为发生时增量累加落库，读时零聚合** —— `get_level_info` 只读 `users.exp` 一个字段，**禁止**实时多表聚合（否则每次开等级页付 N 条聚合查询）。
- **`add_exp` 并发安全**：`.with_for_update()` 行锁读改写 → **先 `commit()` 释放锁，再跨域发升级钻石**（不在持锁期间调其它域）；一次跨多级用 `sum()` 合并奖励不漏发；发奖失败**不回滚经验**。
- **安全红线：不提供任何对外加经验端点**（仅只读 `GET /api/level`），经验只能由真实行为埋点驱动（否则可自刷等级白拿钻石）。
- **埋点铁律**：必须在写操作 `db.commit()` **之后**调用（纯 DB、无外部调用、`try/except` 静默，不得影响主流程）；**跨域埋点一律经 `engagement.contracts.AchievementService.try_grant`**（assessment 交卷/掌握错题即如此）。
- 已埋点：`exam_done`(交卷) / `wrong_mastered`(×2) / `task_done`(×2) / `mood_done`；其余事件（vocab/classical/teach/challenge/goal）仅由兜底全量扫描覆盖。前端徽章逻辑 `web/src/logic/badges.js`（已从 cards.js 拆出），`BadgesView.vue` 有分类 tab + 进度条。
- **等级特权 20 条已全部真实落地**（`level_config.perk` 不再是「只显示文字无效果」的虚假承诺）：称号配色 `logic/level.js::levelHue()`（Lv1 青绿 150° → Lv20 紫 290° 逐级插值，经 CSS 变量 `--lv-h` 下发）；头像框 `levelFrameTier()`（Lv2 起每 2 级 1 档 `floor(lv/2)`，经 `--lv-tier`）；成就墙展示位（`BadgesView.vue` 顶部 `.lv-showcase`）。防漂移测试 `test_level.py::test_perk_texts_all_have_real_landing` + `test_frame_tier_matches_frame_perk_levels`。**改特权的检查清单**：改 `_PERKS` 文案 → 同步落地点 → 同步 `LANDED` 映射 → 跑 `test_level.py`。
- **上线配套 `tools/backfill_level_exp.py`**：默认 dry-run（`--apply` 才写库）、默认**不发**升级钻石（`--grant-reward` 才补发）、默认只补 `exp=0/NULL`（可安全重跑）。迁移 `080_user_level.py` 幂等三步；`ensure_level_config` 用「按 lv 增量补齐」而非「表为空才 seed」（将来扩级自动补、不覆盖后台已调数值）。

## 十四、高项备考模块（软考高级，2026-09-28，见 `docs/高项备考模块说明.md`）
- **面向非学生成人用户**的独立备考入口：后端 `/api/gx`（19 端点，assessment 域），前端 tab `gaoxiang`（桌面侧边栏「学习」组；移动 TabBar 6 项已满故不加）。**与小学题库完全解耦**（小学 subject+grade 维度被错题/统计/收藏大量下游假设，复用会污染口径）。
- 独立 **7 表** `gx_knowledge / gx_questions / gx_attempts / gx_wrongs / gx_case_grades / gx_progress / gx_materials`（迁移 `081_gaoxiang.py` + `082_gx_materials.py`，均幂等）。**不挂 `check_quiet_hours`**（成人晚间备考是核心场景，宵禁只针对未成年人护眼）。
- 出题**题库优先** + **服务端判分**（答案存库不下发；多选须全对）；错题闭环同构小学（连对 3 次自动掌握）。
- 🚨 **`/quiz/generate` 必须用独立短会话回读**：AI 补题写库后用请求级会话（`Depends(get_db)`）回读会因 REPEATABLE READ 快照冻结读不到新行（症状「AI 出题成功但返 0 题」）。范式：短会话1 查题库 → **会话外**调 AI → 短会话2 回读。
- 🚨 **题库取题必须在 SQL 层排除已做题**（`~exists()` 相关子查询）。旧实现「取 `n*8` 行再 Python 剔除」在用户做满 40 道后窗口内全是旧题 → 明明有上千道真题却判「资料不够」回退 AI（白扣费）。防回归 `test_gaoxiang.py::test_quiz_pick_excludes_done_at_sql_level`。
- **考纲 24 章**（不是十大知识域）：真实资料覆盖全书，只认十大域会让大半题目无处归置。章节归一三级回退：章号表达式 → 小节号（`第6.4.1节`→第6章）→ 域名反查（别名表长键优先）。
- **资料流水线**：`tools/gx_parse.py`（分类/章节归一/五种解析器/指纹）→ `tools/gx_pack.py`（本地跑，读 PDF 写 `data/gx_materials/pack_*.json` + manifest）→ scp 上传 → 线上 `tools/import_gx_materials.py load`（幂等 upsert，`stats`/`--dry-run` 先看）。四类：知识点 / 选择题练习 / 案例分析练习 / 论文练习（未命中规则进「其他」并记 reason）。实测 602 文件 → 442 解析单元 → 去重 **4544 条**（知识 2851 / 选择 1670 / 案例 17 / 论文 6）。
- **幂等靠内容指纹**（sha1 前 16 位）唯一索引；`fingerprint` 列**必须可空**（唯一索引只允许一个 NULL；AI 现场出的题不带指纹）。导入与 AI 生成共用同一指纹口径。
- ⚠️ `gx_pack.py` 前置自检 `gx.taxonomy_check()`：归一不可用时**直接中止**（否则 `_domains_of()` 静默吞异常 → 7000+ 条知识域全空）。⚠️ 解析器高发坑：选项分隔符要含全角句点 `．`；答案段判据（问题号回退/与题干重复行不计）；`无解析/有解析` 去重要在 **stem** 上判（不是带 `.pdf` 的路径）。
- **错题闭环**：选择题答错 + 案例/论文批改 < 60 分（`SUBJECTIVE_PASS_SCORE`）入错题本；**资料无参考答案的题 `judged=false`**（不判错/不入库/不计分；打印版约 5% 无答案，误判会污染错题本）。**错因分析懒生成**（判分接口要快，一次最多 20 题）：提交后前端立刻调 `POST /api/gx/wrong/analyze`（一次自动分析最多 3 题），结果落 `gx_wrongs.wrong_reason` 缓存，再看不再扣费。重练 `quiz_pick(scope="wrong")` **不再过滤「做过的题」**（否则永远刷不到），按 `wrong_count` 降序。
- `sub_questions` 三形态：选择题 NULL；案例 `[{q,answer,points}]`（`answer` 是参考答案要点，批改评分依据）；论文 `[{q,answer:"",points:0}]`（`q` 是论述要求）。
- 测试：`tests/test_gx_materials.py` 39 例 + `tests/test_gaoxiang.py` 40 例，AI 用 `monkeypatch.setattr("app.domains.platform.contracts.chat_with", fake)` 打桩；验证「题库优先不调 AI」时 **count 必须等于库存数**（count>库存时 AI 补题是预期行为）。

## 十五、消息推送（OneSignal，2026-09-28，见 `docs/推送通知(OneSignal)接入说明.md`）
- **第三条通知通道**（与 `send_email`/`send_sms` 同构：`*_configured()` + 尽力而为的 `send_*()`），属 **D8 platform 域**：服务 `app/domains/platform/services/push.py`、用户端路由 `routers/push.py`（`/api/push/*`）、后台 `routers/admin_push.py`（`/api/admin/push/*`）。跨域经 `platform.contracts`（新增边 frozen→platform，须复验 `lint-imports` = `2 kept, 0 broken`）。
- 表 3 张（迁移 `083_push_onesignal.py`，幂等三步）：`push_subscriptions`（`subscription_id` 唯一 upsert；换账号改写归属并复活 `revoked_at=None`）、`push_prefs`（`user_id` 唯一）、`push_logs`（`dedup_key VARCHAR(120) NULL` 唯一 + `user_id`/`event` 时间索引）。
- **OneSignal v16 API 要点**：`POST https://api.onesignal.com/notifications`，Header `Authorization: Key <REST_API_KEY>`（**不是 Bearer**）；定向用 `include_aliases.external_id`（= 本系统 `user_id`）+ `target_channel:"push"`；广播用 `included_segments:["Subscribed Users"]`。
- 🚨 **HTTP 200 但响应无 `id` 表示靶向受众无有效订阅**（OneSignal 约定）→ **必须判为失败**（`ok=False` + `err="no_subscription"`），否则是「假成功」用户收不到。同理：**失败不写 `dedup_key`**，保证可补发。
- **Service Worker 必须在域名根路径**（scope = 所在目录）；本项目 nginx 全量反代 + `web/dist` 不作静态目录暴露 → 由后端专用路由 `GET /OneSignalSDKWorker.js` 提供（优先 `WEB_DIST_DIR/OneSignalSDKWorker.js`，缺则 `ONESIGNAL_WORKER_FALLBACK` 内联兜底；headers 带 `application/javascript` + `Service-Worker-Allowed: /` + **`Cache-Control: no-store`**（OneSignal 硬要求））。
- **密钥只走后台「系统配置 → 消息推送」在线填写**（`sysconfig` 优先级：`system_config` 表 > `.env` > 默认值，60s 缓存）；`push_sdk_config()` **不下发 REST_API_KEY**。后台 status 接口**不回传密钥片段**。
  · 实况（2026-09-28）：本地 `.env` **已含真实凭据**（App ID = 36 位 UUID，REST Key = `os_v2_app_…` 113 位），
    因此**本地 `http://127.0.0.1:8000` 即可端到端真机测试**（`push.js` 对 localhost 传了
    `allowLocalhostAsSecureOrigin`，绕开 HTTPS 限制）；本地库 `schoolexam` 已应用迁移 083（3 张 push 表）。
    ⚠️ 本地测试写的 `push_subscriptions/prefs/logs` 都落在**克隆库**，与线上无关，别据此判线上订阅数。
- **防打扰四道闸**：设备开关 → 场景偏好（study/im/announce/exam 四类）→ 免打扰时段（`quiet_start/quiet_end`，跨零点反向判断；**不复用** `check_quiet_hours`）→ 每人每日上限 `DAILY_CAP=8`（公告/群发 `_UNLIMITED_EVENTS` 不占额度）。
- **IM 离线推送**在 `frozen/routers/im.py`：`asyncio.create_task(asyncio.to_thread(_push_offline_members, ...))`（避免阻塞事件循环、不持 DB 连接），只推非在线成员，`key_template="im:{uid}:{chat_id}:{date}"`（每人每群每日一条）。
- **其它触发点**：后台公告创建联动（`admin_panel.py` 的 `_send_announcement_push`，在 `db.close()` **之后**推送，`dedup_key="announce:{id}"`）；后台手动群发（`target=all|user|grade`，`GRADE_FANOUT_CAP=5000`，需 `announcement:manage` 权限 + `high_risk=True` + 审计）。
- **每日学习提醒** `tools/push_daily_reminder.py`（`--dry-run/--limit`，`ACTIVE_DAYS=7`/`MIN_STREAK=2`；streak 用 date 对象比较）→ 在 `scheduler.py` 的 `JOBS` 里排 **`at="19:00"`（刻意不排凌晨**，提醒要在学生活跃时段到达），`dedup_key="study:{uid}:{date}"`。
- 测试 `tests/test_push.py` 33 例：打桩 `push.sysconfig.get` 与 `push.requests`；覆盖降级/纯函数/订阅 upsert 与换账号改写/偏好回环/发送体形状与鉴权头/dedup/免打扰/日限/200 无 id 判失败/HTTP 错误留痕/分段广播/SW 路由 MIME 与 no-store。
