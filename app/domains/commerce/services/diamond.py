"""钻石服务：余额查询、扣费、充值、初始赠送

扣费规则：1 万 token = 1 钻石，保留 2 位小数。
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.diamond import DiamondAccount, DiamondLedger

logger = logging.getLogger("diamond")

TOKENS_PER_DIAMOND = 10000  # 1 万 token = 1 钻石
# 注册赠送：新用户首次查询余额自动赠送 10 钻石（额外钻石通过「购买」手动充值，1 元 = 1 钻石）
REGISTRATION_GIFT = 10.0


def get_balance(db: Session, user_id: str) -> float:
    """查询用户钻石余额（不存在则自动创建并赠送注册赠送钻石）"""
    acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == user_id).first()
    if not acc:
        acc = DiamondAccount(user_id=user_id, balance=REGISTRATION_GIFT)
        db.add(acc)
        db.flush()
        # 记录赠送明细
        db.add(DiamondLedger(
            user_id=user_id, amount=REGISTRATION_GIFT, balance_after=REGISTRATION_GIFT,
            reason="initial_grant",
        ))
        db.commit()
        return REGISTRATION_GIFT
    return acc.balance


def calc_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """根据 token 用量计算钻石消耗（1 万 token = 1 钻石，保留 2 位小数）"""
    total_tokens = prompt_tokens + completion_tokens
    cost = round(total_tokens / TOKENS_PER_DIAMOND, 2)
    return cost


def deduct(db: Session, user_id: str, amount: float, reason: str = "", ref_id: int = 0) -> bool:
    """扣除钻石，返回是否成功（余额不足返回 False）"""
    if amount <= 0:
        return True
    acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == user_id).first()
    if not acc:
        # 首次扣费，先创建账户并赠送
        get_balance(db, user_id)
        acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == user_id).first()
    if acc.balance < amount:
        return False
    acc.balance = round(acc.balance - amount, 2)
    acc.updated_at = datetime.now()
    db.add(DiamondLedger(
        user_id=user_id, amount=-amount, balance_after=acc.balance,
        reason=reason, ref_id=ref_id,
    ))
    db.commit()
    return True


def grant(db: Session, user_id: str, amount: float, reason: str = "admin_grant") -> float:
    """充值钻石，返回新余额"""
    acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == user_id).first()
    if not acc:
        acc = DiamondAccount(user_id=user_id, balance=0.0)
        db.add(acc)
        db.flush()
    acc.balance = round(acc.balance + amount, 2)
    acc.updated_at = datetime.now()
    db.add(DiamondLedger(
        user_id=user_id, amount=amount, balance_after=acc.balance,
        reason=reason,
    ))
    db.commit()
    return acc.balance


def check_and_deduct(db: Session, user_id: str, prompt_tokens: int, completion_tokens: int,
                      reason: str = "", ref_id: int = 0) -> dict:
    """检查余额并扣费，返回 {"ok": bool, "cost": float, "balance": float, "error": str}"""
    cost = calc_cost(prompt_tokens, completion_tokens)
    if cost <= 0:
        return {"ok": True, "cost": 0, "balance": get_balance(db, user_id), "error": ""}
    balance = get_balance(db, user_id)
    if balance < cost:
        return {"ok": False, "cost": cost, "balance": balance,
                "error": f"钻石不足（需要 {cost}，余额 {balance}）"}
    ok = deduct(db, user_id, cost, reason=reason, ref_id=ref_id)
    new_balance = get_balance(db, user_id)
    return {"ok": ok, "cost": cost, "balance": new_balance,
            "error": "" if ok else "钻石不足"}


def grant_all_existing(db: Session, amount: float = REGISTRATION_GIFT) -> int:
    """为所有现有用户赠送钻石（幂等：已有账户的不重复赠送）"""
    from app.models.user import User
    users = db.query(User).all()
    count = 0
    for u in users:
        acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == u.user_id).first()
        if not acc:
            acc = DiamondAccount(user_id=u.user_id, balance=amount)
            db.add(acc)
            db.flush()
            db.add(DiamondLedger(
                user_id=u.user_id, amount=amount, balance_after=amount,
                reason="existing_user_grant",
            ))
            count += 1
    db.commit()
    return count
