"""学期目标倒计时：分数 / 消灭错题 / 背诵 三类目标（goal_items 表，005 迁移已建）

current 自动计算：
- score：最近 10 次练习平均分
- wrong：累计消灭错题数（试卷错题 + 学习错题已掌握）
- recite：累计背诵古诗文篇数
目标到期自动归档；最多同时 2 个进行中（PRD P1：同时 ≤2 个）。
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter()

KINDS = {"score": "分数目标", "wrong": "消灭错题", "recite": "背诵目标"}


class GoalReq(BaseModel):
    user_id: str
    kind: str
    target: int = 90
    deadline: str = ""  # YYYY-MM-DD
    subject: str = ""


def _current(db: Session, user_id: str, kind: str, subject: str = "") -> int:
    if kind == "score":
        from app.models.exam import ExamAttempt
        from app.models.exam import ExamRecord
        q = db.query(ExamAttempt).join(
            ExamRecord, ExamAttempt.exam_id == ExamRecord.id
        ).filter(ExamAttempt.user_id == user_id)
        if subject:  # 分数目标按学科统计，避免其他学科做题记录混入
            q = q.filter(ExamRecord.subject == subject)
        rows = q.order_by(ExamAttempt.id.desc()).limit(10).all()
        return round(sum(a.score or 0 for a in rows) / len(rows)) if rows else 0
    if kind == "wrong":
        from app.models.exam import WrongRecord
        from app.models.study_error import StudyError
        n1 = db.query(WrongRecord).filter(
            WrongRecord.user_id == user_id, WrongRecord.is_mastered.is_(True)).count()
        n2 = db.query(StudyError).filter(
            StudyError.user_id == user_id, StudyError.is_mastered.is_(True)).count()
        return n1 + n2
    if kind == "recite":
        from app.models.classical import ClassicalDailyLog
        rows = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id).all()
        # 只累计"新背"篇数：复习/重复学习不重复计数，避免进度虚高
        return sum(r.texts_learned or 0 for r in rows)
    return 0


def _goal_out(db: Session, g) -> dict:
    current = _current(db, g.user_id, g.kind, g.subject)
    days_left = (g.deadline - date.today()).days if g.deadline else None
    # 每日小步：剩余进度 ÷ 剩余天数（有截止日且未达成时才有意义）
    daily_step = None
    if days_left and days_left > 0 and current < g.target:
        import math
        daily_step = max(1, math.ceil((g.target - current) / days_left))
    return {
        "id": g.id, "kind": g.kind, "kind_label": KINDS.get(g.kind, g.kind),
        "title": g.title, "subject": g.subject,
        "target": g.target, "current": min(current, g.target),
        "raw_current": current, "pct": round(min(current / g.target, 1) * 100) if g.target else 0,
        "deadline": str(g.deadline) if g.deadline else None,
        "validity_days": getattr(g, 'validity_days', None),
        "days_left": days_left, "status": g.status,
        "daily_step": daily_step,
        "achieved": current >= g.target,
    }


def _goal_window_days(g) -> int:
    """取目标有效期天数：优先存储的 validity_days，缺失时按 旧deadline-创建日 回算（至少 1 天）。"""
    vd = getattr(g, 'validity_days', None)
    if vd and vd > 0:
        return vd
    dl = getattr(g, 'deadline', None)
    ca = getattr(g, 'created_at', None)
    if dl and ca:
        span = (dl - ca.date()).days
        if span > 0:
            return span
    return 1


def _reset_impossible_goals(db: Session, user_id: str):
    """「有效期 + 重置」规则（学期目标）：

    保守判定（避免误判可完成的任务）：假设每天最多推进 1 个单位，
      days_needed = target - current
    若 days_remaining(=deadline-今天) < days_needed → 铁定无法按期完成：
      仅顺延 deadline = 今天 + 原有效期天数，保留已累积的真实进度
      （目标进度是真实成就，如已消灭的错题数，故不清零；如需强制清零可再调整）。
    """
    from app.models.reward import GoalItem
    today = date.today()
    rows = db.query(GoalItem).filter(
        GoalItem.user_id == user_id, GoalItem.status == "active",
        GoalItem.deadline != None, GoalItem.deadline >= today,
    ).all()
    changed = False
    for g in rows:
        current = _current(db, g.user_id, g.kind, g.subject)
        if current >= g.target:
            continue
        days_remaining = (g.deadline - today).days
        days_needed = max(0, (g.target or 0) - current)  # 保守：≤1 单位/天
        if days_remaining < days_needed:
            window = _goal_window_days(g)
            g.validity_days = window
            g.deadline = today + timedelta(days=window)
            changed = True
    if changed:
        db.commit()


@router.get("", summary="进行中目标列表（含自动计算进度与倒计时）")
def list_goals(user_id: str = Query(...), db: Session = Depends(get_db)):
    """进行中目标列表（含自动计算的进度与倒计时）。

    查询参数：user_id；无需家长密码。
    返回：{goals:[{id, kind, kind_label, title, subject, target, current, pct, deadline, days_left, status, daily_step, achieved}]}。
    副作用：只读，无写库。current 按 kind 实时聚合（score 取最近 10 次均分 / wrong 累计掌握错题 / recite 累计新背篇数）。
    """
    from app.models.reward import GoalItem
    _reset_impossible_goals(db, user_id)  # 惰性执行「必然完成不了→顺延 deadline」
    rows = db.query(GoalItem).filter(
        GoalItem.user_id == user_id, GoalItem.status.in_(("active", "done")),
    ).order_by(GoalItem.id.desc()).all()
    return {"goals": [_goal_out(db, g) for g in rows]}


@router.post("", summary="新建目标（同时最多 2 个进行中）")
def create_goal(req: GoalReq, db: Session = Depends(get_db)):
    """新建目标（同时最多 2 个进行中）。

    请求：{user_id, kind=score/wrong/recite, target(夹取1~1000), deadline?, subject?}；无需家长密码。
    返回：目标对象（见 _goal_out）。
    副作用：校验 kind 合法、进行中目标数 < 2（超限拒绝）；解析截止日（须晚于今天）；
            自动生成标题，写 goal_items(status=active) 并落库。
    """
    from app.models.reward import GoalItem
    if req.kind not in KINDS:
        raise HTTPException(400, f"kind 只能是 {list(KINDS)}")
    target = max(1, min(1000, req.target))
    active = db.query(GoalItem).filter(
        GoalItem.user_id == req.user_id, GoalItem.status == "active").count()
    if active >= 2:
        raise HTTPException(400, "进行中的目标最多 2 个，先完成或移除再添加")
    deadline = None
    if req.deadline:
        try:
            deadline = date.fromisoformat(req.deadline)
        except ValueError:
            raise HTTPException(400, "截止日期格式应为 YYYY-MM-DD")
        if deadline <= date.today():
            raise HTTPException(400, "截止日期要在今天之后")
    titles = {
        "score": f"{req.subject or '数学'}平均分冲到 {target} 分",
        "wrong": f"消灭 {target} 道错题",
        "recite": f"背诵 {target} 篇古诗文",
    }
    g = GoalItem(user_id=req.user_id, kind=req.kind,
                 title=titles[req.kind], subject=req.subject,
                 target=target, deadline=deadline,
                 validity_days=(deadline - date.today()).days if deadline else None,
                 status="active")
    db.add(g)
    db.commit()
    return _goal_out(db, g)


class GoalActionReq(BaseModel):
    user_id: str


@router.post("/{gid}/done", summary="标记目标达成")
def done_goal(gid: int, req: GoalActionReq, db: Session = Depends(get_db)):
    """标记目标达成（status=done）。路径参数 gid；请求：{user_id}。仅本人目标可操作，否则 404。
    副作用：更新 goal_items.status=done 并落库。"""
    from app.models.reward import GoalItem
    g = db.query(GoalItem).filter(GoalItem.id == gid).first()
    if not g or g.user_id != req.user_id:
        raise HTTPException(404, "目标不存在")
    g.status = "done"
    db.commit()
    return _goal_out(db, g)


@router.post("/{gid}/archive", summary="移除目标")
def archive_goal(gid: int, req: GoalActionReq, db: Session = Depends(get_db)):
    """移除目标（status=archived）。路径参数 gid；请求：{user_id}。仅本人目标可操作，否则 404。
    副作用：更新 goal_items.status=archived 并落库（保留记录，不删除）。"""
    from app.models.reward import GoalItem
    g = db.query(GoalItem).filter(GoalItem.id == gid).first()
    if not g or g.user_id != req.user_id:
        raise HTTPException(404, "目标不存在")
    g.status = "archived"
    db.commit()
    return {"ok": True}
