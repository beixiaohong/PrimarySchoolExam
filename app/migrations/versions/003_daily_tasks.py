"""003 新增每日任务表 daily_tasks

背景：新增"每科必做"任务系统——每学科每天必完成 1 项任务，
且每个学科提供多个任务类型可更换。需要一张按 (用户, 日期, 学科)
唯一的三行任务表。
"""
import logging

logger = logging.getLogger("migrations")


def upgrade(db):
    from ...models.daily_task import DailyTask
    DailyTask.__table__.create(bind=db.get_bind(), checkfirst=True)
    logger.info("daily_tasks 表已创建")
