# D5 激励与成长域

每日任务双轨、家长自定义任务、补签卡、奖励券/心愿、宠物/成长树/徽章/知识卡、心情打卡、专注钟。

- 数据归属：daily_tasks custom_tasks reward_coupons pet_profiles coin_ledger 等
- 迁入代码：tasks/ rewards/ goals.py pet.py tree.py badges.py cards.py mood.py focus.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
