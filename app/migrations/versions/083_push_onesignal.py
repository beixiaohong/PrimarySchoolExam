"""083 - 推送通知（OneSignal Web Push）建表

三条推送链路所需的三张表全部新建，`create_all(checkfirst=True)` 幂等：

    push_subscriptions  订阅设备（OneSignal subscription_id 唯一；external_id = users.user_id）
    push_prefs          逐场景偏好开关（缺行 = 全部开启）
    push_logs           发送记录（dedup_key 唯一索引做「同事件当天只发一次」）

**dedup_key 必须可空**：MySQL 唯一索引允许多个 NULL，但只允许一个空串。
即时推送（IM 私信、后台群发）不参与去重，写 NULL；若给 DEFAULT ''，
第二条即时推送就会撞唯一键而发不出去（与 082 的 fingerprint 同一类坑）。
所以补列时不能给 DEFAULT，索引在建表之后单独探测创建。

本迁移不写种子数据 —— 推送密钥（ONESIGNAL_APP_ID / ONESIGNAL_REST_API_KEY）
走管理后台「三方配置」在线填写（写入 system_config 表），或放 .env；
两者都为空时推送整体降级为「不发送」，不影响任何既有功能。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")

# (表名, 列名, MySQL 列定义)
# 本次为全新三表，无需补列；后续给 push_* 加字段时在此登记即可
# （_ensure_column 幂等，列已存在会跳过）。
_COLUMNS = []

# (表名, 索引名, 列, 是否唯一)
_INDEXES = [
    ("push_subscriptions", "ux_push_subscription_sid", ["subscription_id"], True),
    ("push_subscriptions", "ix_push_subscription_user", ["user_id", "revoked_at"], False),
    ("push_prefs", "ux_push_pref_user", ["user_id"], True),
    # dedup_key 可空 → 多个 NULL 不冲突；唯一性只作用于非空值
    ("push_logs", "ux_push_log_dedup", ["dedup_key"], True),
    ("push_logs", "ix_push_log_user_time", ["user_id", "created_at"], False),
    ("push_logs", "ix_push_log_event_time", ["event", "created_at"], False),
]


def _table_exists(db, table: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": table}).scalar()
    return (row or 0) > 0


def _index_exists(db, table: str, name: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :n"
    ), {"t": table, "n": name}).scalar()
    return (row or 0) > 0


def _column_exists(db, table: str, name: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": name}).scalar()
    return (row or 0) > 0


def upgrade(db):
    from app.database import _ensure_column
    from app.models.push import PushLog, PushPref, PushSubscription

    # 1) 建表（checkfirst 幂等：已存在则跳过，不会动既有数据）
    for model in (PushSubscription, PushPref, PushLog):
        try:
            model.__table__.create(bind=db.get_bind(), checkfirst=True)
            logger.info("083: 表 %s 已就绪", model.__tablename__)
        except Exception as e:                       # noqa: BLE001
            logger.warning("083: 建表 %s 失败（已跳过）：%s", model.__tablename__, e)

    # 2) 补列（本次为空，_COLUMNS 留给后续加字段时登记）
    for table, col, ddl in _COLUMNS:
        if _column_exists(db, table, col):
            continue
        if not _table_exists(db, table):
            logger.info("083: 跳过 %s.%s（表不存在）", table, col)
            continue
        _ensure_column(table, col, ddl)

    # 3) 建索引（必须在建表/补列之后；唯一索引失败只告警不阻断启动）
    for table, name, cols, unique in _INDEXES:
        if _index_exists(db, table, name):
            continue
        try:
            db.execute(text("CREATE %sINDEX %s ON %s (%s)"
                            % ("UNIQUE " if unique else "", name, table, ", ".join(cols))))
            logger.info("083: 已创建索引 %s ON %s(%s)", name, table, ", ".join(cols))
        except Exception as e:                       # noqa: BLE001
            logger.warning("083: 创建索引 %s 失败（已跳过）：%s", name, e)
            try:
                db.rollback()
            except Exception:                        # noqa: BLE001
                pass
    db.commit()
    logger.info("083 推送通知表已就绪")
