"""词组和句子 API 路由

提供英语词组（phrases）与例句（sentences）的增删查，用于背词/造句练习的素材管理。
所有接口只读或管理本地素材表，无需家长密码。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.phrase import Phrase, Sentence
from ..schemas.phrase import PhraseCreate, PhraseOut, SentenceCreate, SentenceOut

router = APIRouter()


# ─── 词组管理 ───────────────────────────────────────────────

@router.get("/phrases", response_model=List[PhraseOut], summary="获取词组列表")
def list_phrases(
    grade: Optional[int] = Query(None, ge=1, le=6),
    type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """分页查询词组列表，支持按年级（<=grade）、类型过滤。

    参数（Query）：grade（1-6，含下限过滤）、type、page（>=1）、page_size（1-200）。
    返回：PhraseOut 列表（按 grade,id 排序）。
    副作用：无（只读）。无需家长密码。
    """
    q = db.query(Phrase)
    if grade:
        q = q.filter(Phrase.grade <= grade)
    if type:
        q = q.filter(Phrase.type == type)
    return q.order_by(Phrase.grade, Phrase.id).offset((page - 1) * page_size).limit(page_size).all()


@router.post("/phrases", response_model=PhraseOut, summary="添加词组")
def create_phrase(data: PhraseCreate, db: Session = Depends(get_db)):
    """新增词组（按 phrase 去重）。

    参数（Body）：grade、phrase、meaning、type。
    返回：新建的 PhraseOut；词组已存在返回 400。
    副作用：写入 phrases 表。无需家长密码。
    """
    existing = db.query(Phrase).filter(Phrase.phrase == data.phrase).first()
    if existing:
        raise HTTPException(400, f"词组已存在：{data.phrase}")
    p = Phrase(grade=data.grade, phrase=data.phrase, meaning=data.meaning, type=data.type)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/phrases/{phrase_id}", summary="删除词组")
def delete_phrase(phrase_id: int, db: Session = Depends(get_db)):
    """删除词组。

    参数（Path）：phrase_id 主键。
    返回：{"message": "已删除"}；不存在返回 404。
    副作用：删除 phrases 表记录。无需家长密码。
    """
    p = db.get(Phrase, phrase_id)
    if not p:
        raise HTTPException(404, "词组不存在")
    db.delete(p)
    db.commit()
    return {"message": "已删除"}


# ─── 句子管理 ───────────────────────────────────────────────

@router.get("/sentences", response_model=List[SentenceOut], summary="获取句子列表")
def list_sentences(
    grade: Optional[int] = Query(None, ge=1, le=6),
    grammar_point: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """分页查询例句列表，支持按年级（<=grade）、语法点（模糊包含）过滤。

    参数（Query）：grade（1-6）、grammar_point、page、page_size（1-200）。
    返回：SentenceOut 列表（按 grade,id 排序）。
    副作用：无（只读）。无需家长密码。
    """
    q = db.query(Sentence)
    if grade:
        q = q.filter(Sentence.grade <= grade)
    if grammar_point:
        q = q.filter(Sentence.grammar_point.contains(grammar_point))
    return q.order_by(Sentence.grade, Sentence.id).offset((page - 1) * page_size).limit(page_size).all()


@router.post("/sentences", response_model=SentenceOut, summary="添加句子")
def create_sentence(data: SentenceCreate, db: Session = Depends(get_db)):
    """新增例句（按 sentence_en 去重）。

    参数（Body）：grade、sentence_en、sentence_cn、type、grammar_point。
    返回：新建的 SentenceOut；例句已存在返回 400。
    副作用：写入 sentences 表。无需家长密码。
    """
    existing = db.query(Sentence).filter(Sentence.sentence_en == data.sentence_en).first()
    if existing:
        raise HTTPException(400, f"句子已存在：{data.sentence_en}")
    s = Sentence(
        grade=data.grade, sentence_en=data.sentence_en,
        sentence_cn=data.sentence_cn, type=data.type,
        grammar_point=data.grammar_point,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/sentences/{sentence_id}", summary="删除句子")
def delete_sentence(sentence_id: int, db: Session = Depends(get_db)):
    """删除例句。

    参数（Path）：sentence_id 主键。
    返回：{"message": "已删除"}；不存在返回 404。
    副作用：删除 sentences 表记录。无需家长密码。
    """
    s = db.get(Sentence, sentence_id)
    if not s:
        raise HTTPException(404, "句子不存在")
    db.delete(s)
    db.commit()
    return {"message": "已删除"}
