"""管理后台：运营数据分析"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.ai_usage import AIUsageLog, AiQa
from app.models.classical import ClassicalDailyLog
from app.models.diamond import DiamondAccount, DiamondLedger
from app.models.exam import ExamAttempt, WrongRecord
from app.models.makeup_card import MakeupCard
from app.models.parent import ParentMessage
from app.models.pet import CoinLedger
from app.models.sprint4 import ChallengeRecord
from app.models.user import User, VipUser
from app.models.vocab import VocabDailyLog

from . import router
from .common import _require_admin


@router.get("/analytics", summary="运营数据分析（注册/活跃/留存/资产/AI/功能活跃）")
def analytics(db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    today = date.today()
    start7 = datetime.combine(today - timedelta(days=6), datetime.min.time())
    start30 = datetime.combine(today - timedelta(days=29), datetime.min.time())

    total_users = db.query(func.count(User.id)).scalar() or 0
    new_7 = db.query(func.count(User.id)).filter(User.created_at >= start7).scalar() or 0
    new_30 = db.query(func.count(User.id)).filter(User.created_at >= start30).scalar() or 0

    # DAU：近 7 天（按 last_login_date）
    dau_map = dict(db.query(User.last_login_date, func.count(User.id)).filter(
        User.last_login_date >= today - timedelta(days=6)).group_by(
        User.last_login_date).all())
    active_trend = [{"date": (today - timedelta(days=i)).isoformat(),
                     "count": dau_map.get(today - timedelta(days=i), 0)}
                    for i in range(6, -1, -1)]
    dau_today = dau_map.get(today, 0)

    # 注册趋势：近 30 天
    reg_rows = db.query(func.date(User.created_at).label("d"), func.count(User.id)).filter(
        User.created_at >= start30).group_by("d").all()
    reg_map = {str(d): c for d, c in reg_rows}
    registration_trend = [{"date": (today - timedelta(days=i)).isoformat(),
                           "count": reg_map.get((today - timedelta(days=i)).isoformat(), 0)}
                          for i in range(29, -1, -1)]

    # 次留：近 14 天注册用户在注册次日仍活跃的比例
    retention = []
    for i in range(13, -1, -1):
        reg_date = today - timedelta(days=i + 1)
        day_start = datetime.combine(reg_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        reg_n = db.query(func.count(User.id)).filter(
            User.created_at >= day_start, User.created_at < day_end).scalar() or 0
        retained = 0
        if reg_n:
            retained = db.query(func.count(User.id)).filter(
                User.created_at >= day_start, User.created_at < day_end,
                User.last_login_date >= reg_date + timedelta(days=1)).scalar() or 0
        retention.append({"date": reg_date.isoformat(), "registered": reg_n,
                          "retained": retained,
                          "rate": round(retained / reg_n * 100, 1) if reg_n else 0.0})

    vip_count = db.query(func.count(VipUser.user_id)).scalar() or 0

    # 资产总量
    diamond_total = round(float(db.query(func.sum(DiamondAccount.balance)).scalar() or 0), 2)
    coin_total = int(db.query(func.sum(CoinLedger.amount)).scalar() or 0)
    makeup_total = int(db.query(func.sum(MakeupCard.balance)).scalar() or 0)

    # 资产流向
    def _flow(model, col, positive, since):
        q = db.query(func.sum(col)).filter(model.user_id.isnot(None))
        if positive:
            q = q.filter(col > 0)
        else:
            q = q.filter(col < 0)
        q = q.filter(getattr(model, "created_at") >= since)
        val = q.scalar() or 0
        return round(float(val), 2) if positive else round(abs(float(val)), 2)

    asset_flow = {
        "diamond_grant_7d": _flow(DiamondLedger, DiamondLedger.amount, True, start7),
        "diamond_spend_7d": _flow(DiamondLedger, DiamondLedger.amount, False, start7),
        "diamond_grant_30d": _flow(DiamondLedger, DiamondLedger.amount, True, start30),
        "diamond_spend_30d": _flow(DiamondLedger, DiamondLedger.amount, False, start30),
        "coin_grant_7d": int(_flow(CoinLedger, CoinLedger.amount, True, start7)),
        "coin_spend_7d": int(_flow(CoinLedger, CoinLedger.amount, False, start7)),
        "coin_grant_30d": int(_flow(CoinLedger, CoinLedger.amount, True, start30)),
        "coin_spend_30d": int(_flow(CoinLedger, CoinLedger.amount, False, start30)),
    }

    # AI 用量（近 30 天）
    ai_total = db.query(func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= start30).scalar() or 0
    ai_by_feature = [{"feature": f, "count": c} for f, c in db.query(
        AIUsageLog.feature, func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= start30).group_by(AIUsageLog.feature).all()]
    ai_by_provider = [{"provider": p, "count": c} for p, c in db.query(
        AIUsageLog.provider, func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= start30).group_by(AIUsageLog.provider).all()]

    # 各功能活跃（近 30 天）
    def _cnt(model, col, since):
        return db.query(func.count(getattr(model, col))).filter(
            getattr(model, "created_at") >= since).scalar() or 0

    feature_activity = [
        {"name": "做题（试卷）", "count": _cnt(ExamAttempt, "id", start30)},
        {"name": "错题标记", "count": db.query(func.count(WrongRecord.id)).filter(
            WrongRecord.wrong_at >= start30).scalar() or 0},
        {"name": "古诗文背诵", "count": db.query(func.count(ClassicalDailyLog.id)).filter(
            ClassicalDailyLog.learn_date >= today - timedelta(days=29)).scalar() or 0},
        {"name": "背单词", "count": db.query(func.count(VocabDailyLog.id)).filter(
            VocabDailyLog.learn_date >= today - timedelta(days=29)).scalar() or 0},
        {"name": "挑战赛刷题", "count": _cnt(ChallengeRecord, "id", start30)},
        {"name": "AI 对话/讲解", "count": _cnt(AiQa, "id", start30)},
        {"name": "家长留言", "count": _cnt(ParentMessage, "id", start30)},
    ]

    # 活跃榜：按近 30 天做题次数 Top10
    top_users = [{"user_id": u, "count": c} for u, c in db.query(
        ExamAttempt.user_id, func.count(ExamAttempt.id).label("c")).filter(
        ExamAttempt.created_at >= start30).group_by(ExamAttempt.user_id).order_by(
        func.count(ExamAttempt.id).desc()).limit(10).all()]

    return {
        "overview": {
            "total_users": total_users, "new_users_7d": new_7, "new_users_30d": new_30,
            "vip_count": vip_count, "dau_today": dau_today,
            "diamond_total": diamond_total, "coin_total": coin_total, "makeup_total": makeup_total,
        },
        "registration_trend": registration_trend,
        "active_trend": active_trend,
        "retention": retention,
        "asset_flow": asset_flow,
        "ai_usage": {"total_30d": ai_total, "by_feature": ai_by_feature,
                     "by_provider": ai_by_provider},
        "feature_activity": feature_activity,
        "top_users": top_users,
    }


__all__ = ["analytics"]
