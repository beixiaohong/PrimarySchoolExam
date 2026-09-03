"""知识卡图鉴（创意 13）：掌握的知识点自动点亮 + 每日抽卡

零新表设计：卡片 = 现有学习内容（单词/古诗文/题型），
已掌握（mastered/练习过）即点亮收集。抽卡 = 从未点亮卡片中随机抽取展示，
鼓励孩子去学习未收集的内容。
"""
import random

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, random_order

router = APIRouter(tags=["cards"])

MAX_PER_CAT = 40  # 每类最多展示卡片数


def _cat_cards(db: Session, user_id: str) -> list:
    """返回三类卡片：{key, name, emoji, total, collected, cards:[{id,title,sub,desc,emoji,collected}]}"""
    cats = []

    # ── 单词卡 ──
    from app.models.vocab import VocabProgress
    from app.models.word import Word
    collected = set()
    for (wid,) in db.query(VocabProgress.word_id).filter(
            VocabProgress.user_id == user_id,
            VocabProgress.status == "mastered").limit(MAX_PER_CAT).all():
        collected.add(wid)
    words = db.query(Word).filter(Word.id.in_(collected)).all() if collected else []
    wmap = {w.id: w for w in words}
    w_cards = [{
        "id": w.id, "title": w.word, "sub": f"{w.pos or ''} {w.meaning or ''}".strip(),
        "desc": f"单词 {w.meaning or ''}".strip(), "emoji": "🔤", "collected": True,
    } for w in words]
    cats.append({"key": "word", "name": "单词卡", "emoji": "🔤", "total": len(w_cards),
                 "collected": len(w_cards), "cards": w_cards})

    # ── 古诗文卡 ──
    from app.models.classical import ClassicalProgress, ClassicalText
    cids = [r[0] for r in db.query(ClassicalProgress.text_id).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "mastered").limit(MAX_PER_CAT).all()]
    texts = db.query(ClassicalText).filter(ClassicalText.id.in_(cids)).all() if cids else []
    t_cards = [{
        "id": t.id, "title": t.title, "sub": f"{t.dynasty or ''}·{t.author or ''}",
        "desc": (t.content or "").split("。")[0][:24] + ("。…" if t.content and len(t.content) > 24 else ""),
        "emoji": "📜", "collected": True,
    } for t in texts]
    cats.append({"key": "classical", "name": "古诗文卡", "emoji": "📜", "total": len(t_cards),
                 "collected": len(t_cards), "cards": t_cards})

    # ── 题型卡（练习过的题型点亮）──
    from app.models.exam import Question
    from app.models.problem_type import ProblemType
    done_types = {r[0] for r in db.query(Question.type_code).filter(
        Question.type_code.isnot(None)).distinct().limit(MAX_PER_CAT).all()}
    types = db.query(ProblemType).filter(ProblemType.code.in_(done_types)).all() if done_types else []
    p_cards = [{
        "id": t.id, "title": t.name or t.code, "sub": f"题型 · {t.description or ''}"[:20],
        "desc": (t.description or "已练习过的题型").strip()[:30],
        "emoji": "🧮", "collected": True,
    } for t in types[:MAX_PER_CAT]]
    cats.append({"key": "type", "name": "题型卡", "emoji": "🧮", "total": len(p_cards),
                 "collected": len(p_cards), "cards": p_cards})

    return cats


@router.get("", summary="知识卡图鉴：已收集的知识卡（掌握即点亮）")
def get_cards(user_id: str = Query(...), db: Session = Depends(get_db)):
    """知识卡图鉴：返回已收集的知识卡（掌握即点亮）。

    查询参数：user_id；无需家长密码。
    返回：{total, collected, categories:[{key,name,emoji,total,collected,cards:[{id,title,sub,desc,emoji,collected}]}]}。
    副作用：只读，无写库。每类最多展示 MAX_PER_CAT(40) 张。
    """
    cats = _cat_cards(db, user_id)
    total = sum(c["total"] for c in cats)
    collected = sum(c["collected"] for c in cats)
    return {"total": total, "collected": collected, "categories": cats}


@router.get("/draw", summary="抽知识卡：随机 3 张未收集的知识点（今日新知）")
def draw_cards(user_id: str = Query(...), db: Session = Depends(get_db)):
    """从「尚未收集」的知识点中随机抽 3 张，作为今日新知引导学习。
    单词/古诗文取未掌握的；题型取未练习过的。
    """
    from app.models.vocab import VocabProgress
    from app.models.word import Word
    from app.models.classical import ClassicalProgress, ClassicalText
    from app.models.exam import Question
    from app.models.problem_type import ProblemType

    pool = []

    # 未掌握单词（最多取 200 个随机样本）
    mastered_ids = {r[0] for r in db.query(VocabProgress.word_id).filter(
        VocabProgress.user_id == user_id, VocabProgress.status == "mastered").all()}
    all_words = db.query(Word).order_by(random_order()).limit(200).all()
    pool += [{"title": w.word, "sub": f"{w.pos or ''} {w.meaning or ''}".strip()[:20],
              "emoji": "🔤", "desc": f"还差一步就掌握的单词「{w.word}」，去背单词里找找它吧！"}
             for w in all_words if w.id not in mastered_ids]

    # 未掌握古诗文
    mastered_texts = {r[0] for r in db.query(ClassicalProgress.text_id).filter(
        ClassicalProgress.user_id == user_id, ClassicalProgress.status == "mastered").all()}
    all_texts = db.query(ClassicalText).order_by(random_order()).limit(100).all()
    pool += [{"title": t.title, "sub": f"{t.dynasty or ''}·{t.author or ''}",
              "emoji": "📜", "desc": f"古诗文《{t.title}》还没有点亮，去背诵中心看看吧！"}
             for t in all_texts if t.id not in mastered_texts]

    # 未练习题型
    done_types = {r[0] for r in db.query(Question.type_code).distinct().all()}
    all_types = db.query(ProblemType).order_by(random_order()).limit(60).all()
    pool += [{"title": t.name or t.code, "sub": "题型", "emoji": "🧮",
              "desc": f"题型「{t.name or t.code}」还没有练过，试试新题型吧！"}
             for t in all_types if t.code not in done_types]

    if not pool:
        return {"cards": [], "all_collected": True}
    picked = random.sample(pool, min(3, len(pool)))
    return {"cards": picked, "all_collected": False}
