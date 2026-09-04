"""权益自动履约服务（S4 商城支付闭环）

消费 order.benefit_snapshot 发放权益，成功后 PAID → FULFILLED。
幂等：已 FULFILLED 直接返回；只在 PAID 执行。
失败保持 PAID（钱已收，绝不因发货失败把订单关掉）。

权益分派：
- diamond → DiamondService.grant（同域）
- vip_days → vip_users 叠加续期
- coupon + makeup_card → MakeupService.grant（跨域契约 D5→D7）
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.commerce_order import Order
from app.models.user import VipUser

logger = logging.getLogger("commerce.fulfillment")


def fulfill_order(db: Session, order: Order) -> dict:
    """消费 benefit_snapshot 发放权益，成功后 PAID → FULFILLED。幂等。

    返回 {"ok": True/False, "skipped": bool, "error": str}
    """
    # 幂等：已履约直接返回
    if order.status == "FULFILLED":
        return {"ok": True, "skipped": True}

    # 只处理 PAID 状态
    if order.status != "PAID":
        return {"ok": False, "error": f"订单状态 {order.status} 不可履约（须 PAID）"}

    # 解析 benefit_snapshot
    try:
        benefits = json.loads(order.benefit_snapshot or "[]")
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": f"benefit_snapshot 解析失败: {order.benefit_snapshot!r}"}

    # 逐项发放
    for item in benefits:
        btype = item.get("benefit_type", "")
        bkey = item.get("benefit_key", "")
        amount = int(item.get("amount", 0))
        if amount <= 0:
            continue

        try:
            if btype == "diamond":
                _fulfill_diamond(db, order, amount)
            elif btype == "vip_days":
                _fulfill_vip_days(db, order, amount)
            elif btype == "coupon" and bkey == "makeup_card":
                _fulfill_makeup_cards(db, order, amount)
            else:
                logger.warning("订单 %s 未知权益类型: type=%s key=%s（跳过，不中断）",
                               order.order_no, btype, bkey)
        except Exception as e:
            logger.exception("订单 %s 权益发放失败: %s", order.order_no, e)
            db.rollback()
            return {"ok": False, "error": f"{btype}/{bkey} 发放失败: {e}"}

    # 全部成功 → PAID → FULFILLED
    from app.domains.commerce.services.order_service import OrderService
    try:
        OrderService.transition(
            db, order, "FULFILLED",
            operator_name="system", reason="auto_fulfill",
        )
    except Exception as e:
        logger.exception("订单 %s 状态流转 FULFILLED 失败: %s", order.order_no, e)
        db.rollback()
        return {"ok": False, "error": f"状态流转失败: {e}"}

    logger.info("订单 %s 履约完成：发放 %d 项权益", order.order_no, len(benefits))
    return {"ok": True, "skipped": False}


def _fulfill_diamond(db: Session, order: Order, amount: int) -> None:
    """钻石到账：同域直接调用"""
    from app.domains.commerce.services.diamond import grant
    grant(db, order.user_id, float(amount), reason=f"order_{order.order_no}")


def _fulfill_vip_days(db: Session, order: Order, days: int) -> None:
    """VIP 叠加续期：expire_at = max(now, 现有 expire_at or now) + days"""
    now = datetime.now()
    vip = db.query(VipUser).filter(VipUser.user_id == order.user_id).first()
    if vip is None:
        # 首次开通
        db.add(VipUser(
            user_id=order.user_id,
            note=f"order_{order.order_no}",
            expire_at=now + timedelta(days=days),
        ))
    else:
        # 叠加续期：已过期从今起算，未过期在原到期日上累加
        base = vip.expire_at if (vip.expire_at and vip.expire_at > now) else now
        vip.expire_at = base + timedelta(days=days)
        vip.note = (vip.note or "") + f" +order_{order.order_no}"
    db.flush()


def _fulfill_makeup_cards(db: Session, order: Order, n: int) -> None:
    """补签卡批量发放：走 D5 契约 MakeupService.grant"""
    from app.domains.engagement.contracts import MakeupService
    MakeupService.grant(db, order.user_id, n, reason=f"order_{order.order_no}")
