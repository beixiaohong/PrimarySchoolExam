# 自动化：每日试卷采集（第一试卷网 → 当日 SQLite）

## 任务目标
每天从第一试卷网(shijuan1.com)抓取约200份"之前没抓过"的试卷，仅最近10年、优先初中→小学→高中、覆盖九大学科；抓取后通过AI补全答案；数据存入**当日独立** SQLite 文件 `data/collected_YYYY-MM-DD.sqlite`（每日一个文件）。

## 本次执行结果（首跑 2026-09-01）
- 完整管线已落地并经端到端验证：采集→LibreOffice转HTML→解析题目→入库→DeepSeek补答案，全链路通过。
- 已确认可用的每日入口：`python tools/collect_daily.py --daily-limit 200 --answer-cap 0`
- 验证样本：8份卷→290题，其中42题带来源答案、其余经DeepSeek补全（实测20/20、60/60调用成功，单题约4.5s）。
- 全量200份任务已在后台启动（首跑 task BnnZAq，后因改为「随采随补」设计而重启为 P8qZ5w），预计数小时（采集~30-50min + 答案补全~5-8h），完成时会通知。

## 设计迭代（首跑后改进）
- 初版：全部采完再统一补答案 → 若中途中断整批卷子无答案，脆弱。
- 改进版（paper_crawler.run_collection）：答案「三段式」随采随补——
  1) 开局先补当日库内已入库但缺答案的卷（断点续传/重启安全）；
  2) 每采完一份卷立即补该卷答案（增量、AI调用期间不持DB连接）；
  3) 结尾再全局 mop-up 兜底。
  因此中断只丢当前卷，已采卷均有答案。
- 重启时：已采卷与注册表均持久化，重启自动跳过、从断点续采续补，无重复劳动。

## 关键实现要点（踩坑/铁律）
- **必须用项目 `.venv`**：`D:\PrimarySchoolExam\.venv\Scripts\python.exe`（自带 sqlalchemy/requests/bs4/lxml/mammoth/pdfplumber/rarfile）。托管版 python3.13 缺依赖，不可用。
- **LibreOffice 必需**：站点试卷多为 `.rar` 内嵌旧版 `.doc`（OLE二进制），无 LO 时转换出乱码、解析0题。已 `winget install TheDocumentFoundation.LibreOffice`。`convert_document_to_html` 优先 LO。
- **AI 提供商路由**：免费链 zhipu/relay 当前**余额耗尽/限流**（429/403），唯一可用是 **DeepSeek（`deepseek-v4-flash`，DEEPSEEK_API_KEY 已配）**。answer_generator 已改为 DeepSeek-only（不回退死链）。
- DeepSeek 原无 timeout 导致偶发>10s被全局10s误杀 → 已在 `ai.py` 给 deepseek 设 `timeout=30`+`retry_on_timeout`，并把超时重试判定扩到 socket.timeout。
- **跨日去重**：每日SQLite是独立文件，不能用库内 source_url 去重（否则每天重抓）。已加持久化注册表 `data/scrape_registry.sqlite`（paper_crawler 的 is_scraped/mark_scraped/count_scraped_today）。`tools/collect_daily.py` 调用前 `seed_registry_from_staging()` 导入历史。
- **连接池铁律**：`fill_missing_answers` 重构为「短会话取题 → 无会话调AI → 每题短会话增量写回」，AI调用期间绝不持DB连接；且增量写保证长任务中途崩溃只丢当前题。
- 采集循环对单份坏卷 try/except 续跑；下载偶发 ConnectionReset 自动跳过该卷。

## 后续/注意
- 每日文件 `data/collected_YYYY-MM-DD.sqlite` 即交付物。
- 若 DeepSeek 限流致连续失败达到阈值，answer_generator 会判定"暂不可用"并放弃本次补全，剩余题留待后续（可重跑 collect_daily 续补）。
- 全量跑完后可 `python tools/collect_daily.py --dry` 看策略，或查 DB 统计。

## 本次执行结果（2026-09-02）
- 入口：`python tools/collect_daily.py --daily-limit 200 --answer-cap 0`（自动化 automation-1786588061378 触发，每日一个 sqlite）。
- 🚨 **阻断：DeepSeek 返回 HTTP 402 "Insufficient Balance"** —— 此前唯一可用 AI 链路额度耗尽，无法生成答案（zhipu/relay 亦早前耗尽/限流）。故今日改以 `--no-fill` 仅采集入库，答案待 DeepSeek 充值后重跑补。
- 进程管理坑：本日发现两个残留 collect_daily 进程（venv + 系统 python3.12 各一）并发写同一 daily sqlite（锁冲突/重复采集风险），已 kill；改由**单一** track 后台任务跑 venv python + `--no-fill`（task `Sca2N0`）。
- 跨日去重正常：注册表累计 256（09-01:188 + 09-02 早段 68，均存于 `collected_2026-09-01.sqlite`；早段因跨午夜标记 day=09-02 但数据落在 09-01 文件，无丢失）。今日新采写 `collected_2026-09-02.sqlite`。
- 状态（采集进行中）：截至记录 `collected_2026-09-02.sqlite` 已入库 12 份/440 题，注册表 09-02 累计 80；目标 ~200 份（约 12 份/分钟）。
- 待完成：等 `Sca2N0` 跑满 ~200 份 → `present_files` 交付 `collected_2026-09-02.sqlite`；DeepSeek 充值后 `python tools/collect_daily.py`（不加 `--no-fill`）补答案。

## 本次执行结果（2026-09-03）
- 入口：`python tools/collect_daily.py --daily-limit 200 --no-fill`（自动化 automation-1786588061378 触发，每日一个 sqlite）。后台任务 `dOwxSA`，日志 `data/collect_2026-09-03.log`。
- 🚨 **AI 仍不可用**：DeepSeek 余额检查 `GET /user/balance` 返回 `is_available:false, total_balance:-0.14 CNY`（HTTP 200），与 09-02 一致；zhipu/relay 亦耗尽。故今日继续 `--no-fill` 仅采集入库，答案待 DeepSeek 充值后补。
- 启动验证：~75s 内入库 8 份/244 题（`collected_2026-09-03.sqlite` 已建，1.36MB），注册表 09-03 累计 8（跨日去重跳过历史 466 条，正常）。速率约 6-8 份/分钟 → 满 200 约 25-33 分钟。
- 无残留采集进程冲突（仅 3 个 WorkBuddy 运行时 main.py 进程）。
- 待完成：等 `dOwxSA` 跑满 ~200 份（完成时通知）→ 校验 `papers`/`paper_questions` 行数、`present_files` 交付 `collected_2026-09-03.sqlite`；并在 memory 末段补最终统计。AI 答案待 DeepSeek 充值后回补（含 09-02 与 09-03 全部未答题）。
- **回补命令（充值后，对任一天库）**：设 `STAGING_DB_URL=sqlite:///<绝对路径>/collected_YYYY-MM-DD.sqlite` 后 `run_collection(once=True, daily_limit=0, fill_answers_after=True)` —— daily_limit=0 跳过采集、开局 `fill_missing_answers()` 补满当日库全部缺答案卷。
