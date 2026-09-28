# 模块明细（一）：IM/账本 · 小说站 · 试卷采集

> 从 `MEMORY.md` 拆出（2026-09-28）。主文件只留跨模块通用的规范与铁律，模块细节放这里。

## 十、IM / 账本（细节见 `docs/IM与账本前端实现方案.md` §〇）
- 六项产品决策：D1 生产 **HTTPS**；D2 账本入口**挨着钱包**；D3 周期交易**自动执行**；D4 后台**敏感词过滤**；D5 **红包用钻石**；D6 语音**后端统一转 MP3**（ffmpeg 外部调用须释放 DB 连接）。
- **红包单位**：1 钻石 = 1000 毫钻（Integer 存储）；钻石 `balance` 是 Float。**资损红线**：红包 claim 改真资产前必须加 `with_for_update`/条件更新。
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
- 产物：每日 SQLite `data/collected_YYYY-MM-DD.sqlite` + 去重注册表 `data/scrape_registry.sqlite`；站点第一试卷网；九大学科均衡（学段配额 初中120 / 小学50 / 高中30）。
- **LibreOffice 必需**（旧版 .doc 是 OLE 二进制，无 LO 解析出乱码/0 题）。
- AI 答案当前唯一可用 **DeepSeek（deepseek-v4-flash）**；`fill_missing_answers` 已重构为短会话增量写回（崩溃只丢当前题）。200 份补全约 5-8h，宜凌晨跑。
