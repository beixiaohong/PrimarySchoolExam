"""学期目标倒计时：分数 / 消灭错题 / 背诵 三类目标（goal_items 表，005 迁移已建）

current 自动计算：
- score：最近 10 次练习平均分
- wrong：累计消灭错题数（试卷错题 + 学习错题已掌握）
- recite：累计背诵古诗文篇数
目标到期自动归档；最多同时 2 个进行中（PRD P1：同时 ≤2 个）。
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db

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
        from ..models.exam import ExamAttempt
        from ..models.exam import ExamRecord
        q = db.query(ExamAttempt).join(
            ExamRecord, ExamAttempt.exam_id == ExamRecord.id
        ).filter(ExamAttempt.user_id == user_id)
        if subject:  # 分数目标按学科统计，避免其他学科做题记录混入
            q = q.filter(ExamRecord.subject == subject)
        rows = q.order_by(ExamAttempt.id.desc()).limit(10).all()
        return round(sum(a.score or 0 for a in rows) / len(rows)) if rows else 0
    if kind == "wrong":
        from ..models.exam import WrongRecord
        from ..models.study_error import StudyError
        n1 = db.query(WrongRecord).filter(
            WrongRecord.user_id == user_id, WrongRecord.is_mastered.is_(True)).count()
        n2 = db.query(StudyError).filter(
            StudyError.user_id == user_id, StudyError.is_mastered.is_(True)).count()
        return n1 + n2
    if kind == "recite":
        from ..models.classical import ClassicalDailyLog
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
        "days_left": days_left, "status": g.status,
        "daily_step": daily_step,
        "achieved": current >= g.target,
    }


@router.get("", summary="进行中目标列表（含自动计算进度与倒计时）")
def list_goals(user_id: str = Query(...), db: Session = Depends(get_db)):
    from ..models.reward import GoalItem
    rows = db.query(GoalItem).filter(
        GoalItem.user_id == user_id, GoalItem.status.in_(("active", "done")),
    ).order_by(GoalItem.id.desc()).all()
    return {"goals": [_goal_out(db, g) for g in rows]}


@router.post("", summary="新建目标（同时最多 2 个进行中）")
def create_goal(req: GoalReq, db: Session = Depends(get_db)):
    from ..models.reward import GoalItem
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
                 target=target, deadline=deadline, status="active")
    db.add(g)
    db.commit()
    return _goal_out(db, g)


class GoalActionReq(BaseModel):
    user_id: str


@router.post("/{gid}/done", summary="标记目标达成")
def done_goal(gid: int, req: GoalActionReq, db: Session = Depends(get_db)):
    from ..models.reward import GoalItem
    g = db.query(GoalItem).filter(GoalItem.id == gid).first()
    if not g or g.user_id != req.user_id:
        raise HTTPException(404, "目标不存在")
    g.status = "done"
    db.commit()
    return _goal_out(db, g)


@router.post("/{gid}/archive", summary="移除目标")
def archive_goal(gid: int, req: GoalActionReq, db: Session = Depends(get_db)):
    from ..models.reward import GoalItem
    g = db.query(GoalItem).filter(GoalItem.id == gid).first()
    if not g or g.user_id != req.user_id:
        raise HTTPException(404, "目标不存在")
    g.status = "archived"
    db.commit()
    return {"ok": True}
