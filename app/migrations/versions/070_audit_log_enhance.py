"""070 - 审计日志增强（S1-B7 / 07-技术实施方案 §3.2.9）

admin_operation_logs 补列：ip / user_agent / amount_fen / target_type / extra_json。
基线策略：MySQL-only，幂等（_ensure_column 靠异常兜底跳过已存在列）。

补列定义约定（DB-05：TEXT 列无 DEFAULT，故 TEXT 列一律 nullable，由写入路径填 ""）：
- ip           VARCHAR(64)  NOT NULL DEFAULT ''   （来源 IP）
- user_agent   TEXT         NULL                   （来源 UA；TEXT 不允许 DEFAULT）
- amount_fen   INT          NULL                   （涉及金额，分；无则空）
- target_type  VARCHAR(32)  NOT NULL DEFAULT ''    （对象类型：user/config/asset/vip/order...）
- extra_json   TEXT         NULL                   （扩展上下文 JSON；TEXT 不允许 DEFAULT）

迁移不触达数据（审计/交易表禁止物理删除，亦不回填历史行；历史行缺列取 NULL 即可）。
"""
import logging

from app.database import _ensure_column

logger = logging.getLogger("migrations")


def upgrade(db):
    # 来源 IP：VARCHAR 允许 DEFAULT，NOT NULL 对存量行安全（填 ''）
    _ensure_column("admin_operation_logs", "ip", "VARCHAR(64) NOT NULL DEFAULT ''")
    # 来源 UA：TEXT 不允许 DEFAULT，按可空补列（写入路径恒填 ''，不会落 NULL）
    _ensure_column("admin_operation_logs", "user_agent", "TEXT")
    # 涉及金额（分）：可空
    _ensure_column("admin_operation_logs", "amount_fen", "INT NULL")
    # 对象类型：VARCHAR 允许 DEFAULT
    _ensure_column("admin_operation_logs", "target_type", "VARCHAR(32) NOT NULL DEFAULT ''")
    # 扩展上下文 JSON：TEXT 不允许 DEFAULT，按可空补列
    _ensure_column("admin_operation_logs", "extra_json", "TEXT")
    db.commit()
    logger.info("070 审计日志增强列已就绪（ip/user_agent/amount_fen/target_type/extra_json）")
