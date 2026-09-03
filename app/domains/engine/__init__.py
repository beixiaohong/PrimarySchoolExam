"""D4 学习引擎域（engine）

职责：掌握度模型、诊断测评、个性化学习路径、遗忘曲线与复习队列。

边界纪律（S1-R）：
- 数据归属：vocab_progress study_errors learning_goals 等；新增 mastery_records diagnostic_sessions learning_paths
- 迁入代码：vocab/ study/ learning_goals.py review_service.py reading_service.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
