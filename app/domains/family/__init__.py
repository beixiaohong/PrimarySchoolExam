"""D6 家长与家校区（family）

职责：家长密码守卫、任务与学习设置、周报留言、答题申诉、同步学。

边界纪律（S1-R）：
- 数据归属：parent_messages exam_min_counts answer_appeals sync_quiz_log
- 迁入代码：parent.py appeal.py sync.py sync_service.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
