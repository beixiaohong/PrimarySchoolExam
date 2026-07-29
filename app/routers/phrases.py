"""词组和句子 API 路由"""
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
    q = db.query(Phrase)
    if grade:
        q = q.filter(Phrase.grade <= grade)
    if type:
        q = q.filter(Phrase.type == type)
    return q.order_by(Phrase.grade, Phrase.id).offset((page - 1) * page_size).limit(page_size).all()


@router.post("/phrases", response_model=PhraseOut, summary="添加词组")
def create_phrase(data: PhraseCreate, db: Session = Depends(get_db)):
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
    p = db.query(Phrase).get(phrase_id)
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
    q = db.query(Sentence)
    if grade:
        q = q.filter(Sentence.grade <= grade)
    if grammar_point:
        q = q.filter(Sentence.grammar_point.contains(grammar_point))
    return q.order_by(Sentence.grade, Sentence.id).offset((page - 1) * page_size).limit(page_size).all()


@router.post("/sentences", response_model=SentenceOut, summary="添加句子")
def create_sentence(data: SentenceCreate, db: Session = Depends(get_db)):
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
    s = db.query(Sentence).get(sentence_id)
    if not s:
        raise HTTPException(404, "句子不存在")
    db.delete(s)
    db.commit()
    return {"message": "已删除"}
