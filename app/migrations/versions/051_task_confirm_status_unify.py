"""051 - 统一家长确认状态机命名：task_confirms.status approved → confirmed

背景：任务系统整理后，三套「家长确认」状态机统一为 pending/confirmed/rejected
（TaskConfirm / MakeupUsageLog / ParentCustomTask）。历史存量中 TaskConfirm
曾用 approved，此处做一次幂等数据订正。

MySQL-only 迁移：SQLite（测试环境）由 Base.metadata.create_all 兜底，本脚本跳过。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    # 幂等：只把仍为 approved 的历史行订正为 confirmed（重复执行无匹配行，安全）
    result = db.execute(text(
        "UPDATE task_confirms SET status = 'confirmed' WHERE status = 'approved'"
    ))
    logger.info("051: task_confirms approved → confirmed，订正 %s 行", result.rowcount)
    db.commit()


def downgrade(db):
    # 回滚：把 confirmed 里历史由 approved 转来的行还原（无法区分，按兼容处理：
    # 仅还原 rejected 之外的行有风险，故 downgrade 不做数据还原，仅提示）
    logger.info("051: downgrade 不做数据还原（approved 历史行已并入 confirmed，无法区分）")
