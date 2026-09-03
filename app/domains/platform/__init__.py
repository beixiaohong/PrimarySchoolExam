"""D8 平台与运营域（platform）

职责：系统配置、公告、审核工作流、看板与分析、审计日志、搜索、AI 答疑/助手、天气、夜间免打扰。

边界纪律（S1-R）：
- 数据归属：system_config admin_operation_logs admin_announcements ai_qa weekly_reports
- 迁入代码：announcement.py search.py qa.py assistant.py ai.py weather.py admin_panel.py quiet_hours.py + 平台类 admin
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
