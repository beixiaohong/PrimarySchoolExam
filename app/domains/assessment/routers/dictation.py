"""听写磨耳朵（创意 25）：TTS 朗读 + 孩子听写判分

朗读由前端浏览器 speechSynthesis 完成（免音频资源）；
后端提供听写题库与判分激励（全对 +3 金币）。
单词来源：当日新学/复习优先，不足补未掌握；古诗文来源：篇目名句。
"""
import random

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, random_order

router = APIRouter(tags=["dictation"])

DICTATION_PAID = 3  # 全对奖励金币


@router.get("/words", summary="听写单词列表（当日优先，最多 count 个）")
def dictation_words(user_id: str = Query(...), count: int = Query(10, ge=3, le=20),
                    db: Session = Depends(get_db)):
    """听写单词列表（当日优先，最多 count 个）。

    查询参数：user_id, count(3~20)；无需家长密码。
    返回：{items:[{id, word, meaning, pos, book}]}。
    副作用：只读，无写库。取词优先级：当日到期复习词(learning 且 next_review<=今天) → 未学过新词 → 全库随机，最后打乱。
    """
    from datetime import date

    from app.models.vocab import VocabProgress
    from app.models.word import Word

    today = date.today()
    picked = []

    # 1) 当日到期复习词（status=learning 且 next_review_date <= 今天）
    due_ids = [r[0] for r in db.query(VocabProgress.word_id).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "learning",
        VocabProgress.next_review_date <= today,
    ).limit(count * 3).all()]
    if due_ids:
        picked = db.query(Word).filter(Word.id.in_(due_ids)).limit(count).all()

    # 2) 不足 → 未学过的新词
    if len(picked) < count:
        known = {r[0] for r in db.query(VocabProgress.word_id).filter(
            VocabProgress.user_id == user_id).limit(500).all()}
        if known:
            extra = db.query(Word).filter(~Word.id.in_(known)).order_by(random_order()).limit(count - len(picked)).all()
        else:
            extra = db.query(Word).order_by(random_order()).limit(count - len(picked)).all()
        picked += list(extra)

    # 3) 仍不足 → 全部词库随机
    if len(picked) < count:
        picked += db.query(Word).order_by(random_order()).limit(count - len(picked)).all()

    random.shuffle(picked)
    return {"items": [{"id": w.id, "word": w.word, "meaning": w.meaning or "",
                       "pos": w.pos or "", "book": w.book.name if w.book else ""}
                      for w in picked[:count]]}


@router.get("/texts", summary="古诗文听写句子（随机篇目名句）")
def dictation_texts(user_id: str = Query(...), count: int = Query(5, ge=1, le=10),
                    grade: int = Query(6), db: Session = Depends(get_db)):
    """古诗文听写句子（随机篇目名句）。

    查询参数：user_id, count(1~10), grade；无需家长密码。
    返回：{items:[{id, title, author, sentence, full}]}（每篇取首句，最多 count*2 篇里筛出 count 条）。
    副作用：只读，无写库。优先从已学篇目取，无则全库。
    """
    from app.models.classical import ClassicalProgress, ClassicalText

    learned_ids = {r[0] for r in db.query(ClassicalProgress.text_id).filter(
        ClassicalProgress.user_id == user_id).limit(200).all()}
    if learned_ids:
        texts = db.query(ClassicalText).filter(ClassicalText.id.in_(learned_ids)).all()
    else:
        texts = db.query(ClassicalText).all()
    if len(texts) < count:
        texts = db.query(ClassicalText).all()
    random.shuffle(texts)

    items = []
    for t in texts[:count * 2]:
        sentence = _first_sentence(t.content or "")
        if not sentence:
            continue
        items.append({
            "id": t.id, "title": t.title, "author": f"{t.dynasty or ''}·{t.author or ''}",
            "sentence": sentence, "full": (t.content or ""),
        })
        if len(items) >= count:
            break
    return {"items": items}


def _first_sentence(content: str) -> str:
    """取篇目第一句（去掉标点），无内容返回空"""
    text = content.strip()
    if not text:
        return ""
    for sep in ("。", "！", "？", "；"):
        idx = text.find(sep)
        if idx > 0:
            return text[:idx]
    return text[:30]


class DictationRewardReq(BaseModel):
    user_id: str
    correct: int
    total: int


@router.post("/reward", summary="听写全对奖励 +3 金币")
def dictation_reward(req: DictationRewardReq, db: Session = Depends(get_db)):
    """全对（correct == total 且 total > 0）→ 金币 +3；否则不发放"""
    if req.total <= 0 or req.correct < req.total:
        return {"ok": True, "granted": 0}
    from app.domains.engagement.contracts import _grant_coins
    _grant_coins(db, req.user_id, DICTATION_PAID, "听写全对")
    db.commit()
    return {"ok": True, "granted": DICTATION_PAID}
