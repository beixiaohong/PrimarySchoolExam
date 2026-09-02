# 项目文档总览（INDEX）

> 智学学堂（PrimarySchoolExam）—— 小学试卷自动生成与采集系统。
> 本文档是项目文档的「目录」，把分散的说明串成一条清晰的导航线。

## 一、文档地图

| 文档 | 定位 | 读者 | 主要内容 |
| --- | --- | --- | --- |
| [README.md](../README.md) | **项目门面 / 快速开始** | 所有人 | 产品定位、技术栈、目录结构、本地启动、测试、常见问题 |
| [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md) | **架构与模块权威说明** | 开发者 | 目录树逐层解读、数据库表、路由/服务/迁移清单、关键技术决策 |
| [DEPLOY.md](../DEPLOY.md) | **部署上线指南** | 运维 / 开发者 | 服务器环境、一键部署脚本、前端构建、Nginx/systemd、健康检查 |
| [ROADMAP.md](./ROADMAP.md) | **规划与进度** | 产品 / 开发者 | 版本里程碑、已完成/进行中功能、已知问题与下一步 |

## 二、按场景阅读

- **我想马上跑起来** → 读 `README.md` 的「快速开始」，遇到部署问题再查 `DEPLOY.md`。
- **我要改代码 / 加功能** → 先看 `PROJECT_STRUCTURE.md` 找到对应模块，再对照 `ROADMAP.md` 确认是否在规划内。
- **我想了解整体规划** → 直接看 `ROADMAP.md`，需要细节回 `PROJECT_STRUCTURE.md`。
- **我要上线 / 排查环境** → 主看 `DEPLOY.md`，架构疑问回 `PROJECT_STRUCTURE.md`。

## 三、文档之间的依赖关系

```
README.md（是什么 / 怎么跑）
   │
   ├──► PROJECT_STRUCTURE.md（内部长什么样）
   │        │
   │        └──► DEPLOY.md（怎么把它放到服务器上）
   │
   └──► ROADMAP.md（将来要变成什么样）
```

- `README.md` 顶部「📚 配套文档」已互链四份文档；本文档是其总入口。
- 数字口径（路由数、迁移脚本数、测试用例数、词库规模等）四份文档保持一致，
  以代码实测值为准（详见 `PROJECT_STRUCTURE.md` 技术栈表与 `ROADMAP.md` 进度表）。

## 四、配套子系统文档

- **任务系统（每日任务/自定义/补签卡/完成确认）**：见 `docs/tasks-module.md`。
  模块收敛在 `app/routers/tasks/` 包内（constants/service/progress/makeup_service 分层 +
  5 个薄路由文件），端点 21 条（`/api/tasks/*` + `/api/task-confirm/*`）。
  家长确认状态机统一为 `pending/confirmed/rejected`；孩子端自定义任务标注 DEPRECATED 保留待复活。

- **试卷采集与题库（采集式）**：见 `app/services/paper_crawler.py` 与 `app/services/question_parser.py`。
  运行入口为 `tools/collect_papers.py`。采集结果入库到主库 `papers` / `paper_questions` 表，
  试卷以 HTML 富文本（图片 base64 内联）保存，按 `source_url` 去重，已采集过的不再重复采集。
  与原 `questions` / `exam_records`（出题式题库）完全解耦。

## 五、维护约定

- 任何一处数字/口径修改，需同步更新上述四份文档，保持「单一事实来源」。
- 新增文档时，在此 INDEX 登记并互链，避免文档孤岛。
