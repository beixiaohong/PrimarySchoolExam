"""订单状态机与编排（S4-M3 / 07 §5.2.2 / D7）

状态机唯一入口 `OrderService.transition()`：校验合法性 → 并发安全 UPDATE → 写支付流水 → 写审计 → 提交。

状态图（ALLOWED_TRANSITIONS）：
- PENDING_PAYMENT → {PAID, PENDING_APPROVAL, CLOSED}
- PENDING_APPROVAL → {PAID, PENDING_PAYMENT}（审批通过 / 驳回）
- PAID → {FULFILLED, REVERSED}
- FULFILLED → {REFUNDING, REVERSED}
- REFUNDING → {REFUNDED, FULFILLED}
- CLOSED / REFUNDED / REVERSED 为终态

关键约束（07 §5.2.2）：
- 并发安全：`SELECT ... FOR UPDATE` 取当前状态 + `UPDATE ... WHERE id=? AND status=?` 受影响行数判定；
- 幂等：外部流水号以 pay_transactions.external_no 唯一索引兜底；
- 事务边界：状态变更 + 流水 + 审计同一事务；通知/埋点（本期无）在提交后异步；
- 铁律：核销流程无外部调用；若未来接自动支付，查单/回调验签须在释放 DB 会话后进行；
- 超时关单：scan_expired_orders 批量关单（定时任务每 5 分钟，S4 定时规范）。
"""
import json
import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy import text

from app.domains.commerce.services.payment.factory import get_gateway
from app.models.admin import AdminOperationLog
from app.models.commerce_order import Order
from app.models.commerce_payment import PayTransaction
from app.models.commerce_product import Product, ProductBenefit

# 状态机：from_status -> 允许的 to_status 集合
ALLOWED_TRANSITIONS = {
    "PENDING_PAYMENT": {"PAID", "PENDING_APPROVAL", "CLOSED"},
    "PENDING_APPROVAL": {"PAID", "PENDING_PAYMENT"},   # 审批通过 / 驳回
    "PAID": {"FULFILLED", "REVERSED"},
    "FULFILLED": {"REFUNDING", "REVERSED"},
    "REFUNDING": {"REFUNDED", "FULFILLED"},
    # CLOSED / REFUNDED / REVERSED 为终态
}

_TERMINAL = {"CLOSED", "REFUNDED", "REVERSED"}

# 支付相关动作才写 pay_transactions（核销/审批/退款/冲正）
_PAYMENT_ACTIONS = {"CONFIRM", "APPROVE", "REFUND", "REVERSE"}


class OrderTransitionError(Exception):
    """状态流转非法或并发冲突。"""


def is_transition_allowed(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


def _gen_order_no(now: datetime) -> str:
    rand = "".join(secrets.choice(string.digits) for _ in range(6))
    return now.strftime("%Y%m%d%H%M%S") + rand


def _status_fields(to_status: str, now: datetime, reason: str) -> dict:
    f = {"status": to_status, "updated_at": now}
    if to_status == "PAID":
        f["paid_at"] = now
    elif to_status == "FULFILLED":
        f["fulfilled_at"] = now
    elif to_status == "CLOSED":
        f["closed_at"] = now
        f["close_reason"] = reason or "closed"
    return f


def _fallback_external_no(action: str, order_id) -> str:
    return f"{action.lower()}_{order_id}_{int(datetime.now().timestamp())}"


def _write_tx(db, order, action: str, payload, operator_id, operator_name,
              ip: str, user_agent: str) -> None:
    """写支付流水（核心资金留痕）。external_no 唯一约束由 DB 强制，重复则 IntegrityError。"""
    external_no = (payload.external_no or "") if payload else ""
    if not external_no:
        external_no = _fallback_external_no(action, order.id)
    received = int(getattr(payload, "received_fen", order.amount_fen) or order.amount_fen)
    db.add(PayTransaction(
        order_id=order.id,
        order_no=order.order_no,
        gateway="manual",
        action=action,
        amount_fen=int(order.amount_fen or 0),
        received_fen=received,
        external_no=external_no,
        channel=getattr(payload, "channel", "") or "",
        evidence_url=getattr(payload, "evidence_url", "") or "",
        evidence_hash=getattr(payload, "evidence_hash", "") or "",
        operator_id=operator_id,
        operator_name=operator_name or "",
        ip=ip or "",
        user_agent=user_agent or "",
        reason=getattr(payload, "remark", "") or "",
    ))


def _write_audit(db, operator_name: str, action: str, target: str, detail: str,
                amount_fen, ip: str, user_agent: str) -> None:
    db.add(AdminOperationLog(
        admin=operator_name or "system",
        action=action,
        target=target,
        detail=detail,
        ip=ip or "",
        user_agent=user_agent or "",
        amount_fen=amount_fen,
        target_type="order",
    ))


class OrderService:
    """订单状态机与编排的唯一对外入口（无状态静态方法）。"""

    @staticmethod
    def create_order(db, *, user_id: str, product: Product, benefits,
                     idempotency_key: str = "", client_ip: str = "",
                     user_agent: str = "", consent_rule_version: str = "") -> Order:
        """下单：固化 benefit_snapshot（JSON），状态 PENDING_PAYMENT，超时 = 创建+24h。

        幂等：同 (user_id, idempotency_key) 已存在则直接返回既有订单（避免重复下单）。
        """
        if idempotency_key:
            existing = db.query(Order).filter_by(
                user_id=user_id, idempotency_key=idempotency_key).first()
            if existing:
                return existing

        now = datetime.now()
        order_no = _gen_order_no(now)
        snapshot = json.dumps(
            [{"benefit_type": b.benefit_type, "benefit_key": b.benefit_key,
              "amount": int(b.amount)} for b in benefits],
            ensure_ascii=False,
        )
        order = Order(
            order_no=order_no,
            user_id=user_id,
            product_id=product.id,
            product_sku=product.sku,
            product_name=product.name,
            amount_fen=int(product.price_fen or 0),
            benefit_snapshot=snapshot,
            idempotency_key=idempotency_key or f"nokey_{order_no}",
            consent_rule_version=consent_rule_version,
            expire_at=now + timedelta(hours=24),
            client_ip=client_ip or "",
            user_agent=user_agent or "",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def transition(db, order, to_status: str, *, operator_id=None,
                   operator_name: str = "", ip: str = "", user_agent: str = "",
                   reason: str = "", action: str = None, payload=None) -> Order:
        """状态流转唯一入口：并发安全 + 写流水 + 写审计，单事务提交。"""
        now = datetime.now()
        # 临界区加锁取当前状态，防止核销竞态
        cur = db.query(Order).filter(Order.id == order.id).with_for_update().first()
        if cur is None:
            raise OrderTransitionError("订单不存在")

        from_status = cur.status
        if not is_transition_allowed(from_status, to_status):
            raise OrderTransitionError(
                f"非法状态流转：{from_status} -> {to_status}")

        # 并发安全：仅当 DB 中状态仍为 from_status 时才更新（受影响行数判定）
        n = (db.query(Order)
             .filter(Order.id == order.id, Order.status == from_status)
             .update(_status_fields(to_status, now, reason)))
        if n != 1:
            raise OrderTransitionError("并发冲突：订单状态已被其他请求变更")

        # 写支付流水（仅支付相关动作）
        if action in _PAYMENT_ACTIONS and payload is not None:
            _write_tx(db, cur, action, payload, operator_id, operator_name, ip, user_agent)

        # 写审计（有操作人时）
        if operator_name:
            _write_audit(db, operator_name,
                         _audit_action(action, to_status),
                         cur.order_no,
                         f"{from_status} -> {to_status}" + (f"：{reason}" if reason else ""),
                         amount_fen=int(cur.amount_fen or 0), ip=ip, user_agent=user_agent)

        db.commit()
        db.refresh(cur)
        return cur

    @staticmethod
    def confirm_payment(db, order, payload, *, operator_id=None,
                        operator_name: str = "", ip: str = "", user_agent: str = "") -> Order:
        """人工核销：先经网关校验 BR-M0-2-05 网关层项，再流转 PENDING_* -> PAID。"""
        res = get_gateway().confirm(order, payload)
        if not res.ok:
            raise OrderTransitionError(res.message)
        return OrderService.transition(
            db, order, "PAID", operator_id=operator_id, operator_name=operator_name,
            ip=ip, user_agent=user_agent, action="CONFIRM", payload=payload)

    @staticmethod
    def approve(db, order, *, approver_id=None, approver_name: str = "",
                ip: str = "", user_agent: str = "", payload=None) -> Order:
        """大额审批通过：PENDING_APPROVAL -> PAID（审批人非核销人，BR-M0-2-04）。"""
        p = payload or _empty_payload()
        if not p.external_no:
            p.external_no = _fallback_external_no("APPROVE", order.id)
        return OrderService.transition(
            db, order, "PAID", operator_id=approver_id, operator_name=approver_name,
            ip=ip, user_agent=user_agent, action="APPROVE", payload=p)

    @staticmethod
    def refund(db, order, amount_fen: int, *, operator_id=None,
               operator_name: str = "", ip: str = "", user_agent: str = "",
               reason: str = "") -> Order:
        """发起退款：FULFILLED -> REFUNDING（实际退款完成由后台置 REFUNDED）。"""
        p = _empty_payload()
        p.external_no = _fallback_external_no("REFUND", order.id)
        p.received_fen = int(amount_fen or order.amount_fen or 0)
        p.remark = reason
        return OrderService.transition(
            db, order, "REFUNDING", operator_id=operator_id, operator_name=operator_name,
            ip=ip, user_agent=user_agent, action="REFUND", payload=p, reason=reason)

    @staticmethod
    def cancel(db, order, *, reason: str = "user_cancel") -> Order:
        """用户取消：PENDING_PAYMENT / PENDING_APPROVAL -> CLOSED。"""
        if order.status not in ("PENDING_PAYMENT", "PENDING_APPROVAL"):
            raise OrderTransitionError(f"当前状态 {order.status} 不可取消")
        return OrderService.transition(db, order, "CLOSED", reason=reason)

    @staticmethod
    def scan_expired_orders(db, now: datetime = None, batch: int = 100) -> int:
        """超时关单扫描：PENDING_PAYMENT 且 expire_at < now -> CLOSED(timeout)。

        定时任务每 5 分钟调用（S4 定时规范）；批量更新避免长事务。
        """
        now = now or datetime.now()
        n = (db.query(Order)
             .filter(Order.status == "PENDING_PAYMENT", Order.expire_at < now)
             .update({
                 Order.status: "CLOSED",
                 Order.closed_at: now,
                 Order.close_reason: "timeout",
                 Order.updated_at: now,
             }, synchronize_session=False))
        db.commit()
        return n


def _empty_payload():
    from app.domains.commerce.services.payment.gateway import ConfirmPayload
    return ConfirmPayload(external_no="")


def _audit_action(action: str, to_status: str) -> str:
    if action == "CONFIRM":
        return "order:confirm_payment"
    if action == "APPROVE":
        return "order:approve"
    if action == "REFUND":
        return "order:refund"
    if action == "REVERSE":
        return "order:reverse"
    return f"order:transition:{to_status.lower()}"
