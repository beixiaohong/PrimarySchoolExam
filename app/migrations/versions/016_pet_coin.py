"""016 金币宠物（创意 6）：coin_ledger 金币流水 + pet_profiles 宠物档案

金币来源（行为挂钩）：任务完成 +5、答题每对 1 题 +1（全对 +10）、
错题重做掌握 +3、小老师讲清楚 +10。余额 = coin_ledger.amount 之和。
宠物：喂养（-10 币 / +5 经验）与抚摸（每天 3 次 / +1 经验）升级进化。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    with bind.begin() as conn:
        # 新建金币流水表（行为挂钩，余额=amount 之和）
        conn.execute(text(
            """CREATE TABLE IF NOT EXISTS coin_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(64) NOT NULL,
                amount INTEGER NOT NULL,
                reason VARCHAR(100) NOT NULL,
                created_at DATETIME
            )"""
        ))
        # 新建宠物档案表（喂养/抚摸升级进化）
        conn.execute(text(
            """CREATE TABLE IF NOT EXISTS pet_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(64) NOT NULL UNIQUE,
                pet_key VARCHAR(20) NOT NULL DEFAULT 'qicai',
                level INTEGER NOT NULL DEFAULT 1,
                exp INTEGER NOT NULL DEFAULT 0,
                pats_today INTEGER NOT NULL DEFAULT 0,
                pat_date VARCHAR(10),
                feeds_today INTEGER NOT NULL DEFAULT 0,
                feed_date VARCHAR(10),
                fed_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME
            )"""
        ))
    logger.info("016: coin_ledger / pet_profiles 已建表")
