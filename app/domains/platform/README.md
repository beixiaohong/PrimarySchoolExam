# D8 平台与运营域

系统配置、公告、审核工作流、看板与分析、审计日志、搜索、AI 答疑/助手、天气、夜间免打扰。

- 数据归属：system_config admin_operation_logs admin_announcements ai_qa weekly_reports
- 迁入代码：announcement.py search.py qa.py assistant.py ai.py weather.py admin_panel.py quiet_hours.py + 平台类 admin
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
