"""012 兑换券任务化：全勤天数要求 + 进度累计 + 核销计数

背景：兑换券此前只有「家长发放 → 孩子线下兑现」的记账语义，无获得门槛、无核销。
本次将券改造为可设置的奖励机制：
- required_days：需要完成几天每日任务（全勤：三科各完成 1 项）才可获得 1 张；
  0 表示即时券（家长添加即获得 1 张，保持旧语义）
- progress_days：当前已累计的全勤天数（达到 required_days 自动清零并 granted+1）
- progress_date：最近一次累计的日期（同一天不重复累计）
- granted_count：孩子累计获得的张数
- redeemed_count：家长已核销的张数（剩余 = granted - redeemed）

旧数据迁移：迁移前已存在且状态为 active 的券视为已下发 1 张（granted=1），
孩子可直接找家长兑现（核销后归零）。
"""
import logging

from sqlalchemy import text
from sqlalchemy import inspect as sa_inspect

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    insp = sa_inspect(bind)
    if "reward_coupons" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("reward_coupons")}
        add = [
            ("required_days", "INTEGER DEFAULT 0"),
            ("progress_days", "INTEGER DEFAULT 0"),
            ("progress_date", "VARCHAR(10)"),
            ("granted_count", "INTEGER DEFAULT 0"),
            ("redeemed_count", "INTEGER DEFAULT 0"),
        ]
        for col, ddl in add:
            if col not in cols:
                db.execute(text(f"ALTER TABLE reward_coupons ADD COLUMN {col} {ddl}"))
                logger.info(f"reward_coupons.{col} 已添加")
        # 旧数据迁移：迁移前已有的 active 券 = 已下发 1 张（即时可用）
        db.execute(text(
            "UPDATE reward_coupons SET granted_count = 1 "
            "WHERE status = 'active' AND required_days = 0 AND granted_count = 0"
        ))
        logger.info("reward_coupons 任务化列已添加，旧 active 券 granted=1")
