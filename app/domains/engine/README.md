# D4 学习引擎域

掌握度模型、诊断测评、个性化学习路径、遗忘曲线与复习队列。

- 数据归属：vocab_progress study_errors learning_goals 等；新增 mastery_records diagnostic_sessions learning_paths
- 迁入代码：vocab/ study/ learning_goals.py review_service.py reading_service.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
