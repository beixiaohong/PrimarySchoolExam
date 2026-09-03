"""教学进度（课堂同步）相关端点与辅助函数"""
import re
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import router
from app.database import get_db
from app.domains.identity.contracts import ensure_parent_pwd
from app.models.middle import TeachingProgress
from app.models.word import Word, WordBook


class ProgressUpdateRequest(BaseModel):
    """教学进度（课堂同步）更新请求体：记录某科当前词书/单元。"""
    user_id: str
    subject: str = "英语"
    book_id: int = 0
    chapter: str = ""


def _unit_sort_key(u: str):
    """单元数字解析排序：Unit2 < Unit10，非数字排最后"""
    m = re.search(r"\d+", u or "")
    return (0, int(m.group())) if m else (1, u or "")


@router.get("/progress", summary="查询教学进度（每科当前书/单元）")
def get_teaching_progress(user_id: str = Query(...), db: Session = Depends(get_db)):
    """查询教学进度：每科当前词书/单元（课堂同步用）。

    参数（Query）：user_id。
    返回：{items[{subject, book_id, book_name, chapter, updated_at}]}（无则空）。
    副作用：无（只读）。无需家长密码。
    """
    from app.models.middle import TeachingProgress
    rows = db.query(TeachingProgress).filter(TeachingProgress.user_id == user_id).all()
    book_names = {}
    items = []
    for p in rows:
        if p.book_id and p.book_id not in book_names:
            b = db.query(WordBook).filter(WordBook.id == p.book_id).first()
            book_names[p.book_id] = b.name if b else ""
        items.append({
            "subject": p.subject,
            "book_id": p.book_id or 0,
            "book_name": book_names.get(p.book_id, "") if p.book_id else "",
            "chapter": p.chapter or "",
            "updated_at": str(p.updated_at) if p.updated_at else "",
        })
    return {"items": items}


@router.get("/progress/options", summary="教学进度可选册与单元（词书→单元）")
def teaching_progress_options(
    user_id: str = Query(...),
    grade: int = Query(6, description="年级"),
    subject: str = Query("英语", description="学科（当前仅英语有词册单元数据）"),
    db: Session = Depends(get_db),
):
    """教学进度可选册与单元（词书 → 单元，供家长端下拉选择）。

    参数（Query）：user_id、grade、subject（默认英语）。
    返回：{subject, grade, books[{book_id, book_name, semester, units}]}。
    副作用：无（只读）。无需家长密码。
    """
    books = db.query(WordBook).filter(WordBook.grade == grade) \
        .order_by(WordBook.semester.desc(), WordBook.id).all()
    result = []
    for b in books:
        units = [u for (u,) in db.query(Word.unit).filter(
            Word.book_id == b.id, Word.unit != "", Word.unit.isnot(None),
        ).distinct().all()]
        units.sort(key=_unit_sort_key)
        result.append({"book_id": b.id, "book_name": b.name,
                       "semester": b.semester, "units": units})
    return {"subject": subject, "grade": grade, "books": result}


@router.put("/progress", summary="更新教学进度（家长设置，需家长密码）")
def update_teaching_progress(req: ProgressUpdateRequest, request: Request,
                             db: Session = Depends(get_db)):
    """记录某科当前词书/单元；sync_mode 开启后背单词按此 unit 同步"""
    ensure_parent_pwd(db, req.user_id, request)
    from app.models.middle import TeachingProgress
    if not req.subject:
        raise HTTPException(400, "学科不能为空")
    if req.book_id:
        if not db.query(WordBook).filter(WordBook.id == req.book_id).first():
            raise HTTPException(404, "词书不存在")
    prog = db.query(TeachingProgress).filter(
        TeachingProgress.user_id == req.user_id,
        TeachingProgress.subject == req.subject,
    ).first()
    if not prog:
        prog = TeachingProgress(user_id=req.user_id, subject=req.subject)
        db.add(prog)
    prog.book_id = req.book_id
    prog.chapter = req.chapter.strip()
    prog.updated_at = datetime.now()
    db.commit()
    return {"ok": True, "subject": req.subject,
            "book_id": prog.book_id, "chapter": prog.chapter}


__all__ = [
    "ProgressUpdateRequest", "_unit_sort_key",
    "get_teaching_progress", "teaching_progress_options", "update_teaching_progress",
]
