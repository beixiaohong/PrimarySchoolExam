"""071 - VIP 到期语义（S4 商城支付闭环）

vip_users 加 expire_at 列：NULL = 永久有效（现有种子名单「诗文、橙子」保持 NULL 不被误伤）。
新购买按叠加续期：expire_at = max(now, 现有 expire_at or now) + timedelta(days=amount)。

基线策略：MySQL-only，幂等（_ensure_column 靠异常兜底跳过已存在列）。
"""
import logging

from app.database import _ensure_column

logger = logging.getLogger("migrations")


def upgrade(db):
    _ensure_column("vip_users", "expire_at", "DATETIME NULL")
    db.commit()
    logger.info("071 VIP 到期语义已就绪（expire_at NULL=永久）")
