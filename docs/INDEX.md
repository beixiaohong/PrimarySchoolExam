# 项目文档总览（INDEX）

> 智学学堂（PrimarySchoolExam）—— 面向小学（含初中）家庭的智能学习平台。
> 本文档是项目文档的「目录」，把分散的说明串成一条清晰的导航线。
> 最后更新：2026-09-02（口径：路由端点 377 / 模型类 85 / 迁移 056 / 测试用例 124）

## 一、文档地图

| 文档 | 定位 | 读者 | 主要内容 |
| --- | --- | --- | --- |
| [README.md](../README.md) | **项目门面 / 快速开始** | 所有人 | 产品定位、功能全景、技术栈、本地启动、测试、常见问题 |
| [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md) | **结构与模块权威清单** | 开发者 | 目录树逐层解读、模块清单、端点分布、迁移清单、代码体量、口径自检命令 |
| [架构说明书](./架构说明书.md) | **架构与关键决策** | 开发者 / 架构 | 系统上下文、分层架构、请求生命周期、数据域划分、10 条关键设计决策、硬性约束与反模式、技术债 |
| [项目说明书](./项目说明书.md) | **「文件 → 作用」速查** | 新成员 / 接手者 | 顶层文件、后端模块清单、前端、测试、运维脚本、高频改动入口 |
| [DEPLOY.md](../DEPLOY.md) | **部署上线指南** | 运维 / 开发者 | 服务器环境、一键部署脚本、前端构建、Nginx/systemd、健康检查 |
| [ROADMAP.md](./ROADMAP.md) | **规划与进度** | 产品 / 开发者 | 版本里程碑、已完成/进行中功能、已知问题与下一步 |

## 二、按场景阅读

- **我想马上跑起来** → 读 `README.md` 的「快速开始」，遇到部署问题再查 `DEPLOY.md`。
- **我要理解系统怎么分层、为什么这样设计** → 读 `架构说明书.md`（含硬性红线，动手前必看）。
- **我要改代码 / 加功能** → 先看 `架构说明书.md` §九「扩展指南」，再到 `PROJECT_STRUCTURE.md` 找模块，最后核对 `ROADMAP.md` 是否在规划内。
- **这个文件是干什么的** → 查 `项目说明书.md`，或直接看文件头的模块 docstring（覆盖率 95%）。
- **我要上线 / 排查环境** → 主看 `DEPLOY.md`，架构疑问回 `架构说明书.md`。

## 三、文档之间的依赖关系

```
README.md（是什么 / 怎么跑）
   │
   ├──► 架构说明书（为什么这样设计 / 哪些红线）──► 项目说明书（文件速查）
   │              │
   │              └──► PROJECT_STRUCTURE.md（内部长什么样）
   │                             │
   │                             └──► DEPLOY.md（怎么放到服务器上）
   │
   └──► ROADMAP.md（将来要变成什么样）
```

- `README.md` 顶部「📚 配套文档」已互链；本文档是其总入口。
- 数字口径（路由数、迁移脚本数、测试用例数、词库规模等）以代码实测为准，
  刷新命令见 `PROJECT_STRUCTURE.md` 文末「口径自检」。

## 四、配套子系统文档

| 子系统 | 文档 | 现状摘要 |
| --- | --- | --- |
| 任务系统 | [tasks-module.md](./tasks-module.md) | 模块收敛在 `app/routers/tasks/` 包内（constants/service/progress/makeup_service + 5 个薄路由），端点 21 条（`/api/tasks/*` 18 + `/api/task-confirm/*` 3）。强制任务按学科整体替换默认；家长自定义任务行 `custom:N` 生命周期自管理 |
| 采集与题库 | `services/paper_crawler.py`、`question_parser.py`、`tools/collect_daily.py` | 采集结果入 `papers` / `paper_questions`，与出题式 `questions` / `exam_records` 解耦；按 `source_url` 去重，富文本以 HTML + base64 图片保存 |
| IM 与账本 | `routers/im.py`、`routers/ledger.py` | 外部模块迁移而来，表名统一 `db_` 前缀隔离；IM 含 WebSocket 端点 |
| 学生端优化 | [user-app-optimization-plan.md](./user-app-optimization-plan.md) | 拆分 `appOptions.js`（3,643 行）为「壳 provide + View inject」 |
| 管理端优化 | [admin-optimization-plan.md](./admin-optimization-plan.md) | 后台功能增强与结构治理 |
| 治理总纲 | [优化建议书.md](./优化建议书.md) | 双系统/重复实现/死代码/上帝文件等混乱点的清理方案 |

## 五、维护约定

- 任何一处数字/口径修改，需同步更新 `README.md`、`PROJECT_STRUCTURE.md`、`项目说明书.md`、`架构说明书.md`，保持「单一事实来源」。
- 新增文档时，在此 INDEX 登记并互链，避免文档孤岛。
- 代码模块必须带中文模块级 docstring（当前 237 个文件中 225 个已覆盖），
  描述「职责 + 设计要点 + 接口清单」，**语义变更时同步更新 docstring**（曾出现 docstring 停留在旧语义的情况）。
