"""奖励闭环：家长兑换券 + 孩子心愿单

表（005 迁移已建）：
- reward_coupons：家长创建的兑换券（kind: cartoon/snack/sticker/toy/outing/custom）
- wish_items：孩子心愿单。状态机：
    pending（孩子创建，待家长确认）→ active（确认后进行中）
    → progress 达 target 自动 pending_redeem（待兑现）→ redeemed（家长确认兑现，周报数据源）
  任意非 redeemed 状态可 archive 移除。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()

COUPON_KINDS = {"cartoon": "动画时间", "snack": "零食券", "sticker": "贴纸券",
                "toy": "玩具券", "outing": "外出券", "custom": "自定义"}


class CouponReq(BaseModel):
    user_id: str
    title: str
    kind: str = "custom"
    max_per_month: int = 2


class WishReq(BaseModel):
    user_id: str
    title: str
    target: int = 10


class ToggleReq(BaseModel):
    user_id: str


class ParentNoteReq(BaseModel):
    user_id: str
    note: str = ""


def _coupon_out(c):
    return {
        "id": c.id, "title": c.title, "kind": c.kind,
        "kind_label": COUPON_KINDS.get(c.kind, "自定义"),
        "max_per_month": c.max_per_month, "used_count": c.used_count,
        "status": c.status,
    }


def _wish_out(w):
    return {
        "id": w.id, "title": w.title, "progress": w.progress, "target": w.target,
        "status": w.status, "created_at": str(w.created_at)[:10] if w.created_at else "",
    }


# ═══════════════════ 兑换券 ═══════════════════

@router.get("/overview", summary="孩子侧奖励总览：可用券 + 进行中心愿 + 本周兑现数")
def rewards_overview(user_id: str, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon, WishItem
    coupons = db.query(RewardCoupon).filter(
        RewardCoupon.user_id == user_id, RewardCoupon.status == "active",
    ).order_by(RewardCoupon.id.asc()).all()
    wish = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status.in_(("pending", "active", "pending_redeem")),
    ).order_by(WishItem.id.desc()).first()
    # 本周兑现数
    from datetime import timedelta, date
    week_ago = datetime.combine(date.today() - timedelta(days=7), datetime.min.time())
    redeemed = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status == "redeemed",
        WishItem.updated_at >= week_ago,
    ).count()
    return {
        "coupons": [_coupon_out(c) for c in coupons],
        "wish": _wish_out(wish) if wish else None,
        "redeemed_7d": redeemed,
    }


@router.get("/parent-panel", summary="家长侧管理面板：全部兑换券 + 全部待处理心愿")
def parent_panel(user_id: str, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon, WishItem
    coupons = db.query(RewardCoupon).filter(
        RewardCoupon.user_id == user_id,
    ).order_by(RewardCoupon.id.desc()).all()
    wishes = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status.in_(("pending", "active", "pending_redeem")),
    ).order_by(WishItem.id.desc()).all()
    return {
        "coupons": [_coupon_out(c) for c in coupons],
        "wishes": [_wish_out(w) for w in wishes],
    }


@router.post("/coupon", summary="家长创建兑换券")
def create_coupon(req: CouponReq, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "券名不能为空")
    if req.kind not in COUPON_KINDS:
        raise HTTPException(400, f"券类型只能是 {list(COUPON_KINDS)}")
    max_n = max(1, min(12, req.max_per_month or 2))
    c = RewardCoupon(user_id=req.user_id, title=title[:100], kind=req.kind,
                     max_per_month=max_n, status="active")
    db.add(c)
    db.commit()
    return _coupon_out(c)


@router.post("/coupon/{cid}/toggle", summary="家长启用/停用兑换券")
def toggle_coupon(cid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon
    c = db.query(RewardCoupon).filter(RewardCoupon.id == cid,
                                      RewardCoupon.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "兑换券不存在")
    c.status = "active" if c.status != "active" else "archived"
    db.commit()
    return _coupon_out(c)


# ═══════════════════ 心愿单 ═══════════════════

@router.post("/wish", summary="孩子创建心愿（待家长确认；同时仅 1 个进行中）")
def create_wish(req: WishReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "心愿不能为空")
    active = db.query(WishItem).filter(
        WishItem.user_id == req.user_id,
        WishItem.status.in_(("active", "pending", "pending_redeem")),
    ).first()
    if active:
        raise HTTPException(400, "已有进行中的心愿，完成或移除后才能换新的")
    target = max(1, min(100, req.target or 10))
    w = WishItem(user_id=req.user_id, title=title[:100], target=target,
                 progress=0, status="pending")
    db.add(w)
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/confirm", summary="家长确认心愿开始进行")
def confirm_wish(wid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(WishItem.id == wid,
                                  WishItem.user_id == req.user_id).first()
    if not w:
        raise HTTPException(404, "心愿不存在")
    if w.status != "pending":
        raise HTTPException(400, "只有待确认的心愿可以开始")
    w.status = "active"
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/redeem", summary="家长确认兑现心愿")
def redeem_wish(wid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(WishItem.id == wid,
                                  WishItem.user_id == req.user_id).first()
    if not w:
        raise HTTPException(404, "心愿不存在")
    if w.status != "pending_redeem":
        raise HTTPException(400, "心愿还没完成，先完成再兑现哦")
    w.status = "redeemed"
    w.updated_at = datetime.now()
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/archive", summary="移除心愿（已兑现的记录保留）")
def archive_wish(wid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(WishItem.id == wid,
                                  WishItem.user_id == req.user_id).first()
    if not w:
        raise HTTPException(404, "心愿不存在")
    if w.status == "redeemed":
        raise HTTPException(400, "已兑现的心愿是荣誉记录，不能移除")
    w.status = "archived"
    db.commit()
    return _wish_out(w)


def inc_active_wish_progress(db: Session, user_id: str, n: int = 1):
    """每日任务完成时调用：进行中心愿 progress +n，达标自动转待兑现"""
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(
        WishItem.user_id == user_id, WishItem.status == "active",
    ).order_by(WishItem.id.desc()).first()
    if not w:
        return None
    w.progress = (w.progress or 0) + n
    if w.progress >= w.target:
        w.progress = w.target
        w.status = "pending_redeem"
    w.updated_at = datetime.now()
    db.commit()
    return _wish_out(w)


# ═══════════════════ 家长寄语 ═══════════════════

@router.get("/parent-note", summary="获取最近一周周报的家长寄语")
def get_parent_note(user_id: str, db: Session = Depends(get_db)):
    from ..models.ai_usage import WeeklyReport
    r = db.query(WeeklyReport).filter(
        WeeklyReport.user_id == user_id,
    ).order_by(WeeklyReport.week_start.desc()).first()
    return {"note": getattr(r, "parent_note", "") if r else ""}


@router.post("/parent-note", summary="家长写入寄语（保存到最近周报）")
def save_parent_note(req: ParentNoteReq, db: Session = Depends(get_db)):
    from ..models.ai_usage import WeeklyReport
    note = (req.note or "").strip()[:200]
    r = db.query(WeeklyReport).filter(
        WeeklyReport.user_id == req.user_id,
    ).order_by(WeeklyReport.week_start.desc()).first()
    if not r:
        # 没有周报时先建一条占位（本周）
        from datetime import date, timedelta
        monday = date.today() - timedelta(days=date.today().weekday())
        r = WeeklyReport(user_id=req.user_id, week_start=monday, content_json="{}",
                         status="pending")
        db.add(r)
        db.flush()
    r.parent_note = note
    db.commit()
    return {"note": note}
