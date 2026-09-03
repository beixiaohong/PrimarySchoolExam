"""D5 激励与成长域（engagement）

职责：每日任务双轨、家长自定义任务、补签卡、奖励券/心愿、宠物/成长树/徽章/知识卡、心情打卡、专注钟。

边界纪律（S1-R）：
- 数据归属：daily_tasks custom_tasks reward_coupons pet_profiles coin_ledger 等
- 迁入代码：tasks/ rewards/ goals.py pet.py tree.py badges.py cards.py mood.py focus.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
