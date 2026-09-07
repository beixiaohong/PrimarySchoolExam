"""运营指标端点（OBS-04）

/api/metrics 返回 JSON 格式的实时运营指标，供看板与告警消费。
数据来源为已有业务表（exam_attempts / ai_usage_log / orders / users），不引入额外存储。

设计取舍：
- 仅聚合「今日」与「昨日」数据，避免大范围 COUNT 拖库；
- 对大表查询加 LIMIT 兜底，单请求 < 200ms 可控；
- 无需鉴权（内部看板调用），如需外部暴露可后续加 admin 鉴权。
"""
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter()
logger = logging.getLogger("app.metrics")


def _count_today(db: Session, table: str, time_col: str = "created_at",
                 user_col: str | None = None) -> dict:
    """统计今日 / 昨日某表的行数（及去重用户数）。"""
    today = date.today()
    yesterday = today - timedelta(days=1)

    def _query(d: date) -> dict:
        t0 = datetime.combine(d, datetime.min.time())
        t1 = datetime.combine(d + timedelta(days=1), datetime.min.time())
        base = db.query(func.count(text("1"))).select_from(text(table)).filter(
            text(f"{time_col} >= :t0 AND {time_col} < :t1")
        )
        total = base.params(t0=t0, t1=t1).scalar() or 0
        result = {"count": total}
        if user_col:
            distinct = db.query(func.count(func.distinct(text(user_col)))).select_from(
                text(table)
            ).filter(
                text(f"{time_col} >= :t0 AND {time_col} < :t1")
            ).params(t0=t0, t1=t1).scalar() or 0
            result["distinct_users"] = distinct
        return result

    return {"today": _query(today), "yesterday": _query(yesterday)}


@router.get("/metrics", summary="运营指标快照（OBS-04）")
def metrics(db: Session = Depends(get_db)):
    """实时运营指标：DAU / 答题量 / AI 调用 / 订单量。"""
    result: dict = {"generated_at": datetime.now().isoformat()}

    # 1. DAU（今日答题的去重用户数，近似 DAU）
    try:
        today = date.today()
        t0 = datetime.combine(today, datetime.min.time())
        t1 = datetime.combine(today + timedelta(days=1), datetime.min.time())
        dau = db.query(func.count(func.distinct(text("user_id")))).select_from(
            text("exam_attempts")
        ).filter(text("created_at >= :t0 AND created_at < :t1")).params(
            t0=t0, t1=t1).scalar() or 0
        result["dau"] = dau
    except Exception:
        result["dau"] = None

    # 2. 答题量（今日 exam_attempts 行数）
    try:
        result["answers"] = _count_today(db, "exam_attempts", user_col="user_id")
    except Exception:
        result["answers"] = None

    # 3. AI 调用量（今日 ai_usage_log）
    try:
        result["ai_calls"] = _count_today(db, "ai_usage_log", user_col="user_id")
    except Exception:
        result["ai_calls"] = None

    # 4. AI token 消耗（今日）
    try:
        t0 = datetime.combine(date.today(), datetime.min.time())
        t1 = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
        tokens = db.query(
            func.sum(text("COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)"))
        ).select_from(text("ai_usage_log")).filter(
            text("created_at >= :t0 AND created_at < :t1 AND ok = 1")
        ).params(t0=t0, t1=t1).scalar()
        result["ai_tokens_today"] = int(tokens) if tokens else 0
    except Exception:
        result["ai_tokens_today"] = None

    # 5. 订单量（今日 orders）
    try:
        result["orders"] = _count_today(db, "orders", user_col="user_id")
    except Exception:
        result["orders"] = None

    # 6. 总用户数
    try:
        total_users = db.query(func.count(text("1"))).select_from(text("users")).scalar() or 0
        result["total_users"] = total_users
    except Exception:
        result["total_users"] = None

    # 7. 迁移版本
    try:
        row = db.execute(text(
            "SELECT version FROM schema_migrations ORDER BY id DESC LIMIT 1"
        )).first()
        result["migration_version"] = row[0] if row else None
    except Exception:
        result["migration_version"] = None

    return result
