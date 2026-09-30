# 项目长期记忆 (PrimarySchoolExam / 智学学堂)

> 主文件只留**跨模块通用**的规范与铁律；模块细节读 `topics/`：`模块明细-IM小说采集.md` · `成长体系与高项备考.md` · `消息推送.md` · `工程规范-前端与定时任务.md`。

## 一、项目与工作流
- **技术栈**：FastAPI + SQLAlchemy，**MySQL-only**（`DB_DRIVER` 强制回退 mysql，连接串带 `?charset=utf8mb4`）；Python 3.12+；前端 `web/`(学生端) + `admin/`(后台) 均 Vue3；文档总览 `docs/INDEX.md`。
- **九域分层**：D9 frozen（IM/账本）禁被 D1–D8 直连；跨域只经各域 `contracts.py`，由 `.importlinter` 强制。
- **Git**：模块级提交（完成即 commit，先跑测试），大模块通过才 push；提交信息中文写「改了什么 + 为什么」。不提交 `tools/_*.py`、`*.log`、`demo/`、`*.db`、`output/`、`.paper_cache/`、`web/dist`、`admin/dist`、`qb_versions/`；`.workbuddy/memory/` **被跟踪**，需一并提交。
- **沙箱实操**：git 用 `/mingw64/bin/git -C D:/PrimarySchoolExam`（Bash 偶 fork 失败）；python 用 `.venv/Scripts/python.exe`；node 前缀 `PATH="/c/Users/aaaa/.workbuddy/binaries/node/versions/22.22.2-3:$PATH"`；PowerShell 调 .exe stdout 常被吞 → 加 `| cat`。沙箱 commit 必须 `--no-verify` → **之后手跑 `.venv/Scripts/lint-imports.exe` 复验 `2 kept, 0 broken`**。push 走 SSH 偶被拦，先试，被拒则让用户手动 `git push origin main`。

## 二、数据库拓扑（2026-08-25 用户确认）
- 线上真生产 `115.29.213.131:3306/schoolexam`；**`192.168.2.158` 是它的本地克隆**（本地 `.env` 的 `DB_HOST`，勿改）。
- **铁律：绝不拿克隆库跑 `tools/seed_*.py` 等写数据脚本**；写线上库只能跑在线上服务器。线上后台 https://www.liusijin.com/api/admin 用于只读验证。
- 同步：本地 `.env.prod`（`PROD_DB_*`，**勿提交/外泄**）+ `tools/sync_prod_to_local.py`。上线 = 本地 commit+push → 线上 `git pull` + `sudo bash deploy.sh`（重启触发 `run_migrations()`）。

## 三、三条硬性铁律
1. **严禁「持 DB 连接等外部阻塞调用」**（曾致全站卡死）：AI/HTTP/SMTP/SMS 前必须 `db.close()` 或用 `with SessionLocal() as s:` 包住 DB 段（池参数只缓解，不长持连才是根因）。
2. **新增第三方依赖必须同步 `requirements.txt`**（`deploy.sh:68` 只跑 `pip install -r`）：漏写 → 启动期 ImportError → 全站 502；**本地能 import ≠ 线上正常**。三处拦截：`tools/dep_audit.py`、`regression_check.py`[3]、`tests/test_requirements_complete.py`。可选依赖写函数内 try/except。
3. **部署检查必须在 `systemctl restart` 之前**：`deploy.sh` 两道闸门（`tools/preflight.py`，纯标准库）`3.55 early` / `3.8 full`；只让「真会致挂」的项 BLOCK，外部命令（ffmpeg/soffice/npm）只 WARN——误报会卡住部署导致运维绕过。最有效的检查＝用服务解释器真实 `import app.main`。回滚：`git log --oneline -5` → `git reset --hard <好版本>` → `sudo bash deploy.sh`。线上导入崩溃排查：`journalctl -u exam-app -n 200 --no-pager | grep -iE "ModuleNotFoundError|ImportError"`。

## 四、关键坑（多「不报错但静默失效」）
- **🚨 并行 Edit 同一文件互相覆盖**：同一文件多次 Edit 必须串行，改完 grep/读文件核对落盘。
- **🚨 前后端字段契约逐项核对**：后端返 `id` 前端读 `user_id` 会静默失效；Pydantic 忽略多余字段 →「传了没效果」先查 schema。
- **🚨 `git checkout -- <dir>` 丢弃该目录全部未提交修改** → 重构严禁用它；远端新提交优先 `git merge <sha>` 解冲突。
- **🚨 nginx 反代 WebSocket 必须升级协议**（`proxy_http_version 1.1` + `Upgrade`/`Connection`），长连接 `proxy_read/send_timeout 3600s`。
- **🚨 admin axios 拦截器返回完整响应对象**：必须 `const { data } = await api.get(...)`。
- **🚨 时区**：MySQL DATETIME 读回 naive，与 `datetime.now(timezone.utc)` 比较抛 TypeError → 先补 tzinfo。
- **🚨 日期列比较**：`Column(Date)` 读回是 `date`，`str(d) in dates` 恒 False → 用 `while d in dates`。
- **🚨 测试 helper 跨 session 竞争**：helper 统一用 `client._db`，finally 不 close()。
- **🚨 Vue 模板禁裸 `<` 比较** → 比较逻辑移入 JS。
- **🚨 scoped 样式不作用于 `v-html` DOM** → 后代选择器必须 `:deep()`。
- **敏感词服务有进程内缓存**：改词后 `invalidate_cache()`。
- **统一错误信封** `{code,message,request_id}`（非 `{detail}`）→ 测试断言读 `["message"]`。
- **MySQL 列**：TEXT/MEDIUMTEXT 不允许 DEFAULT；跨 dialect 加列用 `_ensure_column`；唯一索引可空列只允许一个 NULL。
- **`tools/*.py` 直接跑报 `No module named 'app'`** → 头部补 ROOT 入 sys.path。
- **🚨 写进文档/回复的验证命令必须自己先跑一遍**：`@app.get` 不注册 HEAD（探活用 `curl -s -D - -o /dev/null`）；判线上是否上线需「存在 401 + 不存在 404」对照；判前端产物重建懒加载路由关键字不在入口 chunk。
- **🚨 `www.x.com` 与 `x.com` 两独立源**（主域名＝`www.liusijin.com`）：通知/SW/订阅/localStorage 各一套，三者必须对齐。

## 五、架构约定
- **import-linter**：九域独立、跨域只经 `contracts.py`；D9 frozen 禁被 D1–D8 import；`app/main.py` 豁免。
- **鉴权来源在挂载处**：`app/main.py` 的 `include_router(..., dependencies=user_auth_deps)`；`require_self` 从 query/body 取 `user_id` 与登录账号不一致 → 403、未登录 401。
- **后台子模块路由范式**：`app/routers/admin/*` 必须 `from . import router` 复用共享 `APIRouter()`。
- **域内路由**：`app/domains/<domain>/routers/*.py`；跨域出口写在 `contracts.py` 的 `_EXPORTS` 白名单。
- **🚨 admin token 单槽**：任何新登录立即让旧 token 失效 → 别替在线用户登后台做只读验证。
- **路由表必须走 `app.openapi()["paths"]`**（`include_router` 惰性，直接遍历 `app.routes` 得 0 条）。

## 六、测试
- conftest 强制 MySQL，自动建 `DB_NAME+"_test"` 隔离库（防误删生产护栏）；不做事务回滚，每用例专属 user_id + finally 清理。
- **判全量通过看 `--junit-xml` 计数**：读 `<testsuite tests=.. failures=.. errors=..>`。
- **🚨 全量 pytest 别加 `--basetemp=temp/pt`**：rmtree 触发批量删除守护 → 连锁假失败；用默认临时目录。
- **MySQL REPEATABLE READ 余额断言陷阱**：用独立 `SessionLocal()` 读最新已提交值 + 差值判定。
- **`AuthClient` 自动补签 token** → 无法构造「未鉴权 401」。

## 七、回归自检（改完代码、提交前按序跑）
```bash
.venv/Scripts/python.exe tools/regression_check.py    # 7 项：契约/编译/依赖/路由/前端URL/图标/定时任务（退出 0=通过）
.venv/Scripts/lint-imports.exe                        # 期望 2 kept, 0 broken
.venv/Scripts/python.exe -m pytest -q --junit-xml=temp/_junit.xml
cd web && node node_modules/vite/bin/vite.js build     # 前端构建（admin 同理）
```

## 八、模块一览（红线摘录）
| 模块 | 红线 / 唯一真相源 |
|---|---|
| IM / 账本 | 红包 claim 改真资产前必须 `with_for_update`；frozen→commerce 只走 `commerce.contracts` |
| 小说站 | 属 D2 内容域，跨域走 `content.contracts`；读者端 `/api/novel/*` 公开 |
| 试卷采集 | 写线上库只能跑在线上；须用项目 venv；LibreOffice 必需 |
| 成长体系 | 新埋点一律加 `engagement/services/events.py`；埋在 `commit()` **之后**；读时零聚合；不提供对外加经验端点 |
| 高项备考 | `/quiz/generate` 独立短会话回读；取题库 SQL 层排除已做题；填空速记清单→完整知识点(kind=list)，标签「速记清单」；PDF 层级 `tools/gx_pdf_tree.py` 按真实缩进坐标重建；回填 `gx_rebuild_list.py`(本地 `data/gx_content_patch.json`)+`gx_apply_content_patch.py`(线上按 `old_fingerprint` 就地更新、干跑、幂等)；🚨 批量写库唯一索引冲突须「集合预检」按目标行去重；🚨 随机打乱选项须「先打乱值、再按位置生成字母前缀」；计算题 `gx_calc_gen.py` 参数化(fixed seed 可重现,`--verify`,与真题指纹去重)；已读 `gx_knowledge_reads`,计数仅首次+1 |
| 消息推送 | 200 无 `id` 须判失败（两原因：无人订阅/群发段名过期，用 `SEGMENT_ALL_SUBSCRIBERS`）；跟踪防护会拦 OneSignal；主域名＝www，三者必须一致；排查先跑 `tools/onesignal_probe.py` |
| 前端约定 / 定时任务 | 新 tab 4 处注册；可构建三条判据；开关统一 `components/StateSwitch.vue`；调度单任务异常不得终止整轮 |
