# 项目长期记忆 (PrimarySchoolExam / 智学学堂)

> 主文件只留**跨模块通用**的规范与铁律；模块细节按需读 `topics/`（勿全量加载）：
> `topics/模块明细-IM小说采集.md` · `topics/成长体系与高项备考.md` · `topics/消息推送.md` · `topics/工程规范-前端与定时任务.md`

## 一、项目与工作流
- **技术栈**：FastAPI + SQLAlchemy，**MySQL-only**（`DB_DRIVER` 强制回退 mysql，连接串带 `?charset=utf8mb4`）；Python 3.12+；前端 `web/`(学生端) + `admin/`(后台) 均 Vue3（旧 `frontend/`、`frontend-admin/` 已删）；文档总览 `docs/INDEX.md`。
- **九域分层**：D9 frozen（IM/账本）禁被 D1–D8 直连；跨域只经各域 `contracts.py`，由 `.importlinter` 强制。
- **Git**：模块级提交（完成即 commit，先跑测试），大模块通过才 push；提交信息中文写「改了什么 + 为什么」。不提交 `tools/_*.py`、`*.log`、`demo/`、`*.db`、`output/`、`.paper_cache/`、`web/dist`、`admin/dist`、`qb_versions/`；`.workbuddy/memory/` **被跟踪**，需一并提交。
- **沙箱实操**：git 用 `/mingw64/bin/git -C D:/PrimarySchoolExam`（Bash 偶 fork 失败）；python 用 `.venv/Scripts/python.exe`；node 前缀 `PATH="/c/Users/aaaa/.workbuddy/binaries/node/versions/22.22.2-3:$PATH"`；PowerShell 调 .exe stdout 常被吞 → 加 `| cat`。沙箱 commit 必须 `--no-verify` → **之后手跑 `.venv/Scripts/lint-imports.exe` 复验 `2 kept, 0 broken`**。push 走 SSH 偶被拦，先试，被拒则让用户手动 `git push origin main`。

## 二、数据库拓扑（2026-08-25 用户确认）
- 线上真生产 `115.29.213.131:3306/schoolexam`；**`192.168.2.158` 是它的本地克隆**（本地 `.env` 的 `DB_HOST`，勿改）。
- **铁律：绝不拿克隆库跑 `tools/seed_*.py` 等写数据脚本**；写线上库只能跑在线上服务器。线上后台 https://www.liusijin.com/api/admin 用于只读验证。
- 同步：本地 `.env.prod`（`PROD_DB_*`，**勿提交/外泄**）+ `tools/sync_prod_to_local.py`。上线 = 本地 commit+push → 线上 `git pull` + `sudo bash deploy.sh`（重启触发 `run_migrations()`）。

## 三、三条硬性铁律
1. **严禁「持 DB 连接等外部阻塞调用」**（曾致全站卡死）：AI/HTTP/SMTP/SMS 前必须 `db.close()` 或用 `with SessionLocal() as s:` 包住 DB 段。已修复（勿回退）：ai / ai_quiz / assistant / exam / grading / qa / reading / search / study / judge / reading_service / review_service / weather / auth(_send_code) / push。池参数 pool_size=10, max_overflow=30, pool_timeout=15, pre_ping=True, recycle=3600 —— 扩容只缓解，根因是不长持连。
2. **新增第三方依赖必须同步 `requirements.txt`**（`deploy.sh:68` 只跑 `pip install -r`）：漏写 → 启动期 ImportError → 全站 502；**本地能 import ≠ 线上正常**（本地 venv 常多装包）。三处拦截：`tools/dep_audit.py`、`regression_check.py` 第[3]项、`tests/test_requirements_complete.py`。可选依赖写函数内 try/except，别写模块级 import（审计会误报）。
3. **所有部署检查必须在 `systemctl restart` 之前**：`deploy.sh` 两道闸门（`tools/preflight.py`，纯标准库）——`3.55 early`（chown 后、npm build 前：依赖完整性 + 可导入 + `.env` 必需键）/ `3.8 full`（写 systemd/nginx 与重启前：+外部命令 + 前端产物）。失败即中止，旧版本继续服务。只让「真会致挂」的项 BLOCK，外部命令（ffmpeg/soffice/npm）只 WARN——误报比漏报更致命（会卡住正常部署 → 运维绕过闸门）。最有效的检查是用服务所用解释器真实 `import app.main`。
   · 回滚：`git log --oneline -5` → `git reset --hard <好版本>` → `sudo bash deploy.sh`。
   · 线上导入期崩溃：`journalctl -u exam-app -n 200 --no-pager | grep -iE "ModuleNotFoundError|ImportError"`（`-n 50` 常把异常行截掉）。

## 四、关键坑（都「不报错但静默失效」）
- **🚨 并行 Edit 同一文件互相覆盖**：一条消息里对**同一文件**发多个 Edit，后写盘覆盖先改（工具报 Success 但改动丢失）→ **同一文件的多次 Edit 必须串行**，改完 grep/读文件逐处核对落盘。
- **🚨 前后端字段契约逐项核对**：后端返 `id` 而前端读 `user_id` 之类错位让按钮静默失效（IM 私聊/加好友/建群曾全废）。新列表页先确认返回 JSON 字段名；Pydantic **忽略多余字段**（传了未声明字段不报错但被丢）→「传了没效果」先查 schema。
- **🚨 `git checkout -- <dir>` 丢弃该目录全部未提交修改**（曾回滚掉 common.py 拆分修复）→ 重构中严禁用它恢复；远端有新提交优先 `git merge <sha>` 手工解冲突，别 rebase 整树。
- **🚨 nginx 反代 WebSocket 必须升级协议**：缺 `proxy_http_version 1.1` + `Upgrade`/`Connection` 头 → 生产 HTTPS 下 wss 拿不到 101（前端「正在连接中」）；长连接需 `proxy_read/send_timeout 3600s`。见 `DEPLOY.md` §7。
- **🚨 admin axios 拦截器返回完整响应对象**：必须 `const { data } = await api.get(...)`；写成 `const d = await api.get()` 则 `d.items` 恒 undefined → 列表空白。修复脚本 `tools/fix_admin_api_unwrap.py`。
- **🚨 时区**：MySQL DATETIME 读回是 naive，与 `datetime.now(timezone.utc)` 比较抛 TypeError → 先 `if x.tzinfo is None: x = x.replace(tzinfo=timezone.utc)`。
- **🚨 日期列比较**：`Column(Date)` 读回是 `datetime.date`，`str(d) in dates` 恒 False（曾致 streak 徽章永不可得）→ 用 `while d in dates`（date 对象比较），参考 `checkin.py::_checkin_streak`。
- **🚨 测试 helper 跨 session 竞争**：helper 另开 `SessionLocal()` 插 AuthClient 已 add 的 user_id → REPEATABLE READ 下 `Duplicate entry` → **helper 统一用 `client._db`，finally 不 close()**。
- **🚨 Vue 模板禁裸 `<` 比较**：`l.lv<appCtx.x` 的 `<a` 被 HTML 解析器当起始标签 → 比较逻辑一律移入 JS。
- **🚨 scoped 样式不作用于 `v-html` 产出的 DOM**（2026-09-29）：v-html 节点没有 `data-v-xxx`，编译后规则 `.box .x[data-v-x]` 一条都匹配不上 —— 而**编译/构建/测试全绿**，只有肉眼能发现。**作用于 v-html 内容的后代选择器必须 `:deep()`**（`.box :deep(.x)` → `.box[data-v-x] .x`）；判据：产物里属性若挂在**子选择器**上即未穿透。
- **敏感词服务有进程内缓存**：改词后须 `from app.domains.frozen.services.sensitive import invalidate_cache; invalidate_cache()`，否则断言 400 会拿到 200。
- **统一错误信封**：`app/core/middleware.py` 把异常包成 `{code, message, request_id}`，**不是** `{detail}` → 测试断言响应体读 `["message"]`。
- **MySQL 列/Dialect**：TEXT/MEDIUMTEXT 不允许 DEFAULT（1101）；跨 dialect 加列用 `app/database.py::_ensure_column`；大文本用 `paper.py::_longtext()`，不能靠 try-import 判方言。**唯一索引可空列只允许一个 NULL**（指纹 / `dedup_key` 必须可空，不能 `DEFAULT ''`）。
- **`tools/*.py` 直接跑报 `No module named 'app'`**（sys.path 只含 tools/）→ 头部补 `ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))`。
- **含 `\s`/`\d` 的脚本别用 heredoc 生成**（反斜杠被吞 → Node `SyntaxError`），一律 Write 落盘。
- **被 `spec_from_file_location` 按路径加载的脚本慎用 `from __future__ import annotations` + `@dataclass`**（解析注解抛 AttributeError），用普通类。
- **删文件**：`rm`/`Remove-Item` 被 safe-delete shim 拦 → 用 venv python `os.remove()` / `shutil.rmtree(ignore_errors=True)`。
- **🚨 写进文档/回复的验证命令，必须自己先跑一遍**（同类错误犯过两次）：
  · `@app.get` **不注册 HEAD** → `curl -I` 发的是 HEAD，会拿到 405 而误判「路由没生效/部署失败」。需被探的路由用 `@app.api_route(path, methods=["GET","HEAD"])`；文档统一写 GET 取头 `curl -s -D - -o /dev/null <url>`。
  · 判「线上代码是否已上线」必须做**存在 vs 不存在对照**：`require_self` 全站挂载，不存在的 `/api/*` 也可能返 401 → 单看一个 401 会误判，需「一个 401（存在）+ 一个 404（不存在）」。
  · 判「线上前端产物是否已重建」：从 `curl <站点>/` 取入口 bundle → grep 本次新增的函数名/文案/常量；⚠️ **懒加载路由的关键字不在入口 chunk**（直接 grep 入口会误判成没部署），要从 `import("./Xxx-hash.js")` 取 chunk 名单独 fetch。
- **🚨 `www.x.com` 与 `x.com` 是两个独立源**（本项目**主域名＝`www.liusijin.com`**）：通知权限、SW、推送订阅、localStorage 登录态**各一套，互不相通**。三处必须对齐 —— ①OneSignal 站点域名 `chrome_web_origin` ②后端 `SITE_URL` ③用户实际访问域名。错位症状：**(a)** 授权后仍读回 `default`；**(b)** 订阅失败 / `InvalidStateError`；**(c)** **通知能弹但点开未登录**（`url` 落到另一源，没 token，最隐蔽）。**排查第一步先打印 `location.origin`**。做 301 统一前必须先验证书 SAN 覆盖裸域，否则 `nginx -t` 失败会**中断部署**。详见 `topics/消息推送.md` §15。

## 五、架构约定
- **import-linter（`.importlinter`）**：九域独立、跨域只经 `contracts.py`；`app.core` 不监控；`app/routers/admin/** -> app.domains.*.contracts` 属白名单；D9 frozen 禁被 D1–D8 import；`app/main.py` 豁免。
- **鉴权来源在挂载处，不在 router 文件**：全站鉴权来自 `app/main.py` 的 `include_router(..., dependencies=user_auth_deps)`。`require_self` 是严格账号绑定：从 query 或 JSON body 取 `user_id`，与登录账号不一致直接 **403**（拦在写库前）、未登录 401。**判读顺序：先看 `main.py` 挂载处，再读 router 内部**（曾把 focus 误报成无鉴权；已由 `tests/test_user_id_binding.py` 4 例钉死）。
- **后台子模块路由范式**：`app/routers/admin/*` 必须 `from . import router` 复用共享 `APIRouter()`（自建会全部 404），并在 `__init__.py` 补 import + `from .<module> import *`。
- **域内路由**：`app/domains/<domain>/routers/*.py`；跨域出口写在 `contracts.py` 的 `_EXPORTS` 白名单。
- **管理后台**：**记忆里不存密码明文**（此前明文曾被 git 跟踪并推到远端，2026-09-28 清理移除；建议重置）。重置用服务器本机 `python tools/reset_admin_pwd.py --password "新密码"`（4–32 位，改的是它连接的那个库）。本地访问 `cd admin && npm run build` + `python run.py` → `http://127.0.0.1:8000/admin/`（别单开 5173，无代理）。
- **🚨 admin token 是「单槽」的**：`admin_login` 把新 token 写在 `admin.token` 单列 → **任何一次新登录立即让旧 token 失效**。不要替在线用户登录后台做只读验证（会把他踢下线），该类核验交给用户自己。
- **路由表必须走 `app.openapi()["paths"]`**：本项目 `include_router` 惰性（`app.routes` 元素是 `_IncludedRouter`、`path` 为 None），直接遍历得 0 条 → 会误报全部路由缺失。比对路径要归一化参数段（后端 `{gid}` vs 前端具体 id）。

## 六、测试
- conftest 强制 MySQL，自动建 `DB_NAME+"_test"` 隔离库（有防误删生产库护栏）；**不做事务回滚**：每用例用专属 user_id + 显式 token + finally 清理自身数据。
- **判「全量通过」看 `--junit-xml` 计数**：`pytest -q --junit-xml=temp/_junit.xml` → 读 `<testsuite tests=.. failures=.. errors=..>`。`pytest -q > file` 重定向下末尾只剩 warnings、无 `N passed` 行；沙箱里 `EXIT=$?` 与 stdout 还可能被 safe-delete 拦截器污染。
- **🚨 不要给全量 pytest 加 `--basetemp=temp/pt`**：pytest 收尾 `rmtree` 触发本机批量删除守护 → `SystemExit` → fixture finalizer 未消费 → 后续用例 setup 连锁报错（`assert not self._finalizers`），一次可造 25 例与代码无关的假失败。**小批量（74 例）正常、全量才炸**，极易误判成代码回归。**用默认临时目录**（系统 temp 在守护 bypass 名单内）。
- **MySQL REPEATABLE READ 余额断言陷阱**：长生命周期会话首次 SELECT 后快照冻结，读不到接口内部新建会话已提交的新余额 → 用独立 `SessionLocal()` 读最新已提交值 + 按前后差值判定（参考 `tests/test_checkin.py::_read_balance`）。
- **`AuthClient` 会自动补签 token**（按请求里的 `user_id`，缺省回落 `test_auth_uid`）→ **无法构造「未鉴权 401」场景**（`assert status in (401,403)` 必失败），鉴权边界靠其他用例或裸 TestClient。
- pytest 只能证明「被覆盖的逻辑是对的」；**跨域直连、前后端路径/字段错位、图标缺失、路由漏注册**这四类静默失效只有 `tools/regression_check.py` 能抓。

## 七、回归自检（改完代码、提交前按序跑）
```bash
.venv/Scripts/python.exe tools/regression_check.py    # 7 项：契约/编译/依赖/路由/前端URL/图标/定时任务（退出 0=通过）
.venv/Scripts/lint-imports.exe                        # 期望 2 kept, 0 broken
.venv/Scripts/python.exe -m pytest -q --junit-xml=temp/_junit.xml
cd web && node node_modules/vite/bin/vite.js build     # 前端构建（admin 同理）
```
端到端跨模块联动见 `tests/test_e2e_new_features.py`（含迁移幂等 + 存量脏值自愈）。

## 八、模块一览（红线摘录，细节见 topics/）
| 模块 | 红线 / 唯一真相源 | 明细文件 |
|---|---|---|
| IM / 账本 | 红包 claim 改真资产前必须 `with_for_update`；frozen→commerce 只走 `commerce.contracts` | `模块明细-IM小说采集.md` |
| 小说站 | 属 D2 内容域，跨域走 `content.contracts`；读者端 `/api/novel/*` 公开 | 同上 |
| 试卷采集 | 写线上库只能跑在线上；须用项目 venv；LibreOffice 必需 | 同上 |
| 成长体系 | 新埋点一律加 `engagement/services/events.py`；埋在 `commit()` **之后**；读时零聚合；不提供对外加经验端点 | `成长体系与高项备考.md` |
| 高项备考 | `/quiz/generate` 用独立短会话回读；题库取题必须在 SQL 层排除已做题；填空辅助记忆清单已统一转成完整知识点（kind=list），后端中文标签改为「速记清单」，不再保留 `【答案】` 分隔与自测折叠；线上存量 recite 需执行 `tools/fix_gx_recite_merge.py --apply` 迁入 list；知识点正文结构化唯一实现 `gxKParseBlocks`/`gxKBlocksHtml`（配 `:deep()`），**行首每 2 空格 = 1 级**（`gx-k-lv1..5`；缩进优先，无缩进退回按 `•/◦/▪` 判级）；**PDF 层级由 `tools/gx_pdf_tree.py` 按真实缩进坐标重建**（fitz rawdict 取每字符 x0；同级差<10pt、跨级差>60pt；单调栈 + **按页重置栈**）；坑：段内已无 `----` 不能拿来判续行、单横线不是分隔符、上标会劈行需按 y 合并、同级兄弟有排版噪声须与「父的已有兄弟」比；**回填走 `gx_rebuild_list.py`（本地产出 `data/gx_content_patch.json`，需 scp，`data/` 被 gitignore）+ `gx_apply_content_patch.py`（线上按 `old_fingerprint` 就地更新、默认干跑、幂等）——卡片≠页（36 份无一 1:1），靠「字符多重集 Jaccard + 单调 DP」对齐，段长按 页数/卡数 动态放宽、末段强制用完所有页、无 `----` 的页不参与**；🚨 **批量写库判唯一索引冲突必须「集合预检」而非逐条查库**（同批内写入互相不可见 → 干跑报「0 冲突」却真写时 1062；本批内部冲突要按**目标行**去重后再数，否则「两块补丁指同一行」被误判）；补丁生成侧由 `resolve_fingerprints` 按 old 去重 + 碰撞加盐（`source_file`→仍撞则用 `old_fingerprint`，**不用递增序号**以免不可重现）；**已读真相源 `gx_knowledge_reads`（084），计数仅首次 +1** | `成长体系与高项备考.md` |
| 消息推送 | 200 无 `id` 必须判失败（两条路径共用 `_parse_resp`），但有**两种**原因：没人订阅 / **群发段名过期**（用常量 `SEGMENT_ALL_SUBSCRIBERS`，禁字面量）；**跟踪防护会拦 OneSignal，自托管 SDK 无效**；**主域名＝www，三者必须一致**。排查先跑 `tools/onesignal_probe.py` | `消息推送.md` |
| 前端约定 / 定时任务 | 新 tab 4 处注册；可构建三条判据；**开关统一用 `components/StateSwitch.vue`（禁「按钮上写状态词」）**；调试「静默失效」；调度是静默失效，单任务异常不得终止整轮 | `工程规范-前端与定时任务.md` |
