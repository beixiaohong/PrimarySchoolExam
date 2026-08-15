"""古诗文：文章管理（录入 / 列表 / 详情）"""
import json
from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.classical import ClassicalText

from . import router
from .common import (
    ClassicalTextCreate,
    ClassicalTextOut,
    _parse_lines,
    _pinyin_lines,
)


@router.post("/texts", summary="录入古诗文（重复检查）")
def add_classical_text(req: ClassicalTextCreate, db: Session = Depends(get_db)):
    """录入一篇古诗文/文言文，标题重复则拒绝"""
    existing = db.query(ClassicalText).filter(ClassicalText.title == req.title).first()
    if existing:
        raise HTTPException(400, f"篇目「{req.title}」已存在，无法重复录入")

    text = ClassicalText(
        title=req.title,
        author=req.author,
        dynasty=req.dynasty,
        text_type=req.text_type,
        grade=req.grade,
        content=req.content,
        lines_json=json.dumps(_parse_lines(req.content), ensure_ascii=False),
        tags=req.tags,
    )
    db.add(text)
    db.commit()
    db.refresh(text)
    return {"id": text.id, "title": text.title, "lines_count": len(_parse_lines(req.content))}


@router.get("/texts", summary="查看古诗文列表")
def list_texts(
    grade: Optional[int] = Query(None),
    text_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """查看古诗文列表（可按年级上限 / 类型过滤），按年级与标题排序返回全部篇目。

    参数（Query）：grade（仅返回该年级及以下篇目）、text_type（poem/prose 过滤，可空）。
    返回：ClassicalTextOut 列表（含逐行内容、拼音、标签）。无副作用（只读）。无需家长密码。
    """
    query = db.query(ClassicalText)
    if grade:
        query = query.filter(ClassicalText.grade <= grade)
    if text_type:
        query = query.filter(ClassicalText.text_type == text_type)
    texts = query.order_by(ClassicalText.grade, ClassicalText.title).all()
    return [
        ClassicalTextOut(
            id=t.id, title=t.title, author=t.author, dynasty=t.dynasty,
            text_type=t.text_type, grade=t.grade, content=t.content,
            lines=json.loads(t.lines_json) if t.lines_json else _parse_lines(t.content),
            pinyin=_pinyin_lines(t.content),
            tags=t.tags,
        )
        for t in texts
    ]


@router.get("/texts/{text_id}", summary="查看单篇详情")
def get_text(text_id: int, db: Session = Depends(get_db)):
    """查看单篇古诗文详情（含逐行内容、拼音、标签）。

    参数（Path）：text_id。返回：ClassicalTextOut；篇目不存在 404。
    无副作用（只读）。无需家长密码。
    """
    text = db.query(ClassicalText).filter(ClassicalText.id == text_id).first()
    if not text:
        raise HTTPException(404, "篇目不存在")
    return ClassicalTextOut(
        id=text.id, title=text.title, author=text.author, dynasty=text.dynasty,
        text_type=text.text_type, grade=text.grade, content=text.content,
        lines=json.loads(text.lines_json) if text.lines_json else _parse_lines(text.content),
        pinyin=_pinyin_lines(text.content),
        tags=text.tags,
    )


__all__ = [
    "add_classical_text",
    "list_texts",
    "get_text",
]
