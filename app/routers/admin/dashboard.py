"""管理后台：仪表盘"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.ai_usage import AIUsageLog
from app.models.diamond import DiamondLedger
from app.models.user import User, VipUser

from . import router
from .common import _require_admin


@router.get("/dashboard", summary="仪表盘（注册趋势/日活/AI 用量/钻石消耗）")
def dashboard(db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    """仪表盘汇总：总用户数、VIP 数、近 30 天注册趋势、近 7 天日活、近 7 天 AI 用量与钻石消耗/发放。

    参数：db / admin：依赖注入。
    返回：含 total_users / vip_count / registration_trend / active_trend / ai_usage_7d / diamond_spend_7d / diamond_grant_7d 的字典。
    副作用：只读查询。
    """
    today = date.today()
    total_users = db.query(func.count(User.id)).scalar() or 0

    # 注册趋势：近 30 天
    reg_start = datetime.combine(today - timedelta(days=29), datetime.min.time())
    reg_rows = db.query(
        func.date(User.created_at).label("d"), func.count(User.id)
    ).filter(User.created_at >= reg_start).group_by("d").all()
    reg_map = {str(d): c for d, c in reg_rows}
    registration_trend = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "count": reg_map.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(29, -1, -1)
    ]

    # 日活（近似：last_login_date 在当日的新登录用户数）近 7 天
    dau_map = dict(db.query(User.last_login_date, func.count(User.id)).filter(
        User.last_login_date >= today - timedelta(days=6)
    ).group_by(User.last_login_date).all())
    active_trend = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "count": dau_map.get(today - timedelta(days=i), 0)}
        for i in range(6, -1, -1)
    ]

    # AI 用量与钻石消耗：近 7 天
    week_start = datetime.combine(today - timedelta(days=6), datetime.min.time())
    ai_usage = db.query(func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= week_start).scalar() or 0
    diamond_spend = db.query(func.sum(DiamondLedger.amount)).filter(
        DiamondLedger.created_at >= week_start, DiamondLedger.amount < 0).scalar() or 0.0
    diamond_grant = db.query(func.sum(DiamondLedger.amount)).filter(
        DiamondLedger.created_at >= week_start, DiamondLedger.amount > 0).scalar() or 0.0

    return {
        "total_users": total_users,
        "vip_count": db.query(func.count(VipUser.user_id)).scalar() or 0,
        "registration_trend": registration_trend,
        "active_trend": active_trend,
        "ai_usage_7d": ai_usage,
        "diamond_spend_7d": round(abs(diamond_spend), 2),
        "diamond_grant_7d": round(diamond_grant, 2),
    }


__all__ = ["dashboard"]
