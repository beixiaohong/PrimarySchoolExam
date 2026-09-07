"""红包过期原路退回（D5 决策配套 / B12）。

现状问题：红包 24h 到期时仅把状态置 `EXPIRED`，**剩余金额不退回发送者**。
改用钻石（真实资产）后这是资金缺口，必须补齐。

本服务扫描 `status=ACTIVE AND expires_at < now` 的红包，把 `remaining_amount`
按毫钻→钻石退回 sender，再置 `EXPIRED`，逐条 commit（同 ledger_recurring 风格）：
单条失败不中断整批，且状态已变更后不会重复命中（幂等）。
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.im import RedPacket, RedPacketStatus, DIAMOND_SCALE

logger = logging.getLogger(__name__)


def expire_red_packets(db: Session) -> dict:
    """退回全部过期红包的剩余金额。

    返回 {"scanned": 命中条数, "refunded": 退回条数, "failed": 失败条数}。
    """
    now = datetime.now(timezone.utc)
    due = db.query(RedPacket).filter(
        RedPacket.status == RedPacketStatus.ACTIVE,
        RedPacket.expires_at < now,
    ).all()

    scanned = len(due)
    refunded = 0
    failed = 0

    for rp in due:
        try:
            remain = int(rp.remaining_amount or 0)
            if remain > 0 and rp.sender_id:
                # 函数内 import：跨域只经 commerce.contracts（import-linter 白名单）
                from app.domains.commerce.contracts import DiamondService
                DiamondService.grant(
                    db, str(rp.sender_id), remain / DIAMOND_SCALE,
                    biz="im_red_packet_refund",
                )
            rp.status = RedPacketStatus.EXPIRED
            db.commit()
            refunded += 1
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("[red_packet] 过期退回失败 rp=%s，已跳过", getattr(rp, "id", "?"))

    return {"scanned": scanned, "refunded": refunded, "failed": failed}
