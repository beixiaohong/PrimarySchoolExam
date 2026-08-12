"""采集式题库的刷题抽题服务

从 paper_questions（采集试卷解析出的单题）按「年级 + 学科 + 题型」随机抽题，
供后续「刷题系统」使用。与原有 questions/exam_records（出题式题库）完全解耦。

设计要点：
- grade / subject / qtype 三个维度从 PaperQuestion 自身冗余列筛选，不依赖 JOIN papers。
- 随机排序使用 database.random_order()（方言兼容：SQLite random() / MySQL rand()）。
- 只负责「抽题 + 统计」，判分逻辑复用 routers.exam._check_answer（保持去重/容错判题一致）。
"""
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import random_order
from ..models.paper import PaperQuestion


def random_paper_questions(
    db: Session,
    grade: Optional[str] = None,
    subject: Optional[str] = None,
    qtype: Optional[str] = None,
    limit: int = 10,
    exclude_ids: Optional[List[int]] = None,
) -> List[PaperQuestion]:
    """从采集题库随机抽题。

    参数：
      grade:   年级字符串，如 "一年级" / "初三" / "中考"
      subject: 学科字符串，如 "数学" / "语文"
      qtype:   题型 choice / fill_blank / qa
      limit:   抽取数量（内部裁剪到 1~50）
      exclude_ids: 排除的题目 id 列表（避免一次练习重复出题）
    返回：PaperQuestion 列表（已随机排序）。
    """
    limit = max(1, min(int(limit), 50))
    q = db.query(PaperQuestion)
    if grade:
        q = q.filter(PaperQuestion.grade == grade)
    if subject:
        q = q.filter(PaperQuestion.subject == subject)
    if qtype:
        q = q.filter(PaperQuestion.qtype == qtype)
    if exclude_ids:
        q = q.filter(PaperQuestion.id.notin_(exclude_ids))
    return q.order_by(random_order()).limit(limit).all()


def get_paper_questions_by_ids(db: Session, ids: List[int]) -> Dict[int, PaperQuestion]:
    """按 id 批量取题，返回 {id: PaperQuestion}，供提交判分时回查标准答案。"""
    if not ids:
        return {}
    rows = db.query(PaperQuestion).filter(PaperQuestion.id.in_(ids)).all()
    return {r.id: r for r in rows}


def count_paper_questions(
    db: Session,
    grade: Optional[str] = None,
    subject: Optional[str] = None,
    qtype: Optional[str] = None,
) -> int:
    """统计采集题库（按筛选条件）的题目数量，用于前端展示题库规模。"""
    q = db.query(func.count(PaperQuestion.id))
    if grade:
        q = q.filter(PaperQuestion.grade == grade)
    if subject:
        q = q.filter(PaperQuestion.subject == subject)
    if qtype:
        q = q.filter(PaperQuestion.qtype == qtype)
    return int(q.scalar() or 0)


def collection_stats(db: Session) -> dict:
    """采集题库规模统计：总量 + 各学科/年级分布，便于前端展示与 M7 验证。"""
    total = count_paper_questions(db)
    by_subject = {}
    rows = db.query(PaperQuestion.subject, func.count(PaperQuestion.id)).group_by(
        PaperQuestion.subject
    ).all()
    for subj, cnt in rows:
        by_subject[subj or "(未标注)"] = int(cnt)
    by_grade = {}
    rows = db.query(PaperQuestion.grade, func.count(PaperQuestion.id)).group_by(
        PaperQuestion.grade
    ).all()
    for g, cnt in rows:
        by_grade[g or "(未标注)"] = int(cnt)
    return {"total": total, "by_subject": by_subject, "by_grade": by_grade}
