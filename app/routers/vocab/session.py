"""背单词：背诵会话检测（混合题型）"""
import random
import re
from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.word import Word
from app.models.vocab import VocabProgress
from app.models.study_error import StudyError

from . import router
from .common import _career_book_ids


_VOCAB_UNDERSTAND_TYPES = ["meaning_choice", "reverse_choice", "context_fill", "spelling_choice"]


def _vocab_choice_item(w: Word, kind: str, question: str, correct: str,
                       distractors: list, context: str) -> Optional[dict]:
    """组装选择题；干扰项去重后不足则降级选项数，无干扰项则弃用"""
    ds = []
    for d in distractors:
        d = (d or "").strip()
        if d and d != correct and d not in ds:
            ds.append(d)
    if not ds:
        return None
    options = [correct] + random.sample(ds, min(3, len(ds)))
    random.shuffle(options)
    return {
        "word_id": w.id, "word": w.word,
        "kind": "choice", "q_type": kind,
        "question": question, "answer": correct,
        "options": options, "context": context,
    }


def _vocab_distractor_pool(db: Session, book_ids: list, field: str, exclude: str,
                           limit: int = 60) -> list:
    """从同年级词库取干扰项（释义或单词）"""
    col = Word.meaning if field == "meaning" else Word.word
    rows = db.query(col).filter(Word.book_id.in_(book_ids)).all()
    pool = []
    for (v,) in rows:
        v = (v or "").strip()
        if v and v != exclude and v not in pool:
            pool.append(v)
    random.shuffle(pool)
    return pool[:limit]


def _spelling_variants(word: str, n: int = 3) -> list:
    """拼写干扰项：相邻换位/字母替换/删增"""
    letters = "abcdefghijklmnopqrstuvwxyz"
    variants = set()
    w = word.strip()
    if len(w) < 2:
        return []
    for _ in range(60):
        if len(variants) >= n:
            break
        op = random.choice(["swap", "replace", "delete", "insert"])
        s = list(w)
        if op == "swap" and len(s) >= 2:
            i = random.randrange(len(s) - 1)
            s[i], s[i + 1] = s[i + 1], s[i]
        elif op == "replace":
            i = random.randrange(len(s))
            s[i] = random.choice([c for c in letters if c != s[i]])
        elif op == "delete" and len(s) > 2:
            s.pop(random.randrange(len(s)))
        elif op == "insert":
            s.insert(random.randrange(len(s) + 1), random.choice(letters))
        v = "".join(s)
        if v != w:
            variants.add(v)
    return list(variants)[:n]


def _dictate_item(w: Word, variant: int) -> dict:
    """默写题：variant 变换题干措辞，避免同词多道默写题完全一样"""
    if variant == 1 and w.phonetic:
        q = f"根据音标与释义默写单词：{w.phonetic}（{w.meaning}）"
    elif variant == 2:
        q = f"把下面的释义翻译成英文单词：{w.meaning}"
    elif variant == 3 and w.phonetic:
        q = f"只听音标默写单词：{w.phonetic}"
    else:
        q = f"根据释义默写单词：{w.meaning}" \
            + (f"（音标：{w.phonetic}）" if w.phonetic else "")
    return {
        "word_id": w.id, "word": w.word,
        "kind": "fill", "q_type": "dictate",
        "question": q, "answer": w.word, "options": None,
        "context": "服务端判分，忽略大小写",
    }


def _vocab_session_items_for_word(db: Session, w: Word, stage: int,
                                 book_ids: list, sentence_cache: list,
                                 per_word: int = 4) -> list:
    """每词题目数由 per_word 控制（默认 4）：默写+理解混合，默写题干措辞按 variant 区分避免重复。
    per_word=1 时只出 1 道默写题（直接检验单词拼写记忆，任何复习阶段都适用）；
    per_word=4：stage0 2默写+2理解 → stage1-3 1+3 → stage4+ 全理解。"""
    if per_word == 1:
        # 逐词「测一测」：只出 1 道默写填空题，直接检验拼写记忆（不依赖理解题，各阶段均可用）
        return [_dictate_item(w, random.randint(0, 3))]
    if stage <= 0:
        n_dict = 2
    elif stage <= 3:
        n_dict = 1
    else:
        n_dict = 0
    variants = [0, 1, 2, 3]
    random.shuffle(variants)
    items = [_dictate_item(w, v) for v in variants[:n_dict]]
    under_pool = _VOCAB_UNDERSTAND_TYPES[:]
    random.shuffle(under_pool)
    meaning_pool = None
    word_pool = None
    for t in under_pool:
        if len(items) >= 4:
            break
        item = None
        if t == "meaning_choice":
            meaning_pool = meaning_pool or _vocab_distractor_pool(db, book_ids, "meaning", w.meaning)
            item = _vocab_choice_item(
                w, t, f"单词 「{w.word}」 的中文释义是？", (w.meaning or "").strip(),
                meaning_pool, "选择正确释义")
        elif t == "reverse_choice":
            word_pool = word_pool or _vocab_distractor_pool(db, book_ids, "word", w.word)
            item = _vocab_choice_item(
                w, t, f"「{w.meaning}」对应的英文单词是？", (w.word or "").strip(),
                word_pool, "选择正确单词")
        elif t == "context_fill":
            # 从句子库查含该词的句子抠空；无合适句回退释义选择
            pat = re.compile(r"\b" + re.escape(w.word) + r"\b", re.IGNORECASE)
            sents = [s for s in sentence_cache if pat.search(s)]
            if sents:
                sent = random.choice(sents)
                blanked = pat.sub("____", sent, count=1)
                item = _vocab_choice_item(
                    w, t, f"选择正确的单词填入句子：{blanked}", (w.word or "").strip(),
                    word_pool or _vocab_distractor_pool(db, book_ids, "word", w.word),
                    "语境填空")
            else:
                meaning_pool = meaning_pool or _vocab_distractor_pool(db, book_ids, "meaning", w.meaning)
                item = _vocab_choice_item(
                    w, "meaning_choice", f"单词 「{w.word}」 的中文释义是？",
                    (w.meaning or "").strip(), meaning_pool, "选择正确释义")
        elif t == "spelling_choice":
            variants = _spelling_variants(w.word, 3)
            item = _vocab_choice_item(
                w, t, f"「{w.meaning}」的正确拼写是？", (w.word or "").strip(),
                variants, "拼写辨析")
        if item:
            items.append(item)
    # 理解题生成失败时用剩余 variant 的默写题补足 4 题（题干仍尽量区分）
    vi = n_dict
    while len(items) < 4 and vi < len(variants):
        items.append(_dictate_item(w, variants[vi]))
        vi += 1
    while len(items) < 4:
        items.append(_dictate_item(w, 0))
    return items[:max(1, min(per_word, 4))]


@router.get("/session-quiz", summary="背诵会话检测：每词 4 题混合题型（理解题随复习阶段递增）")
def vocab_session_quiz(
    user_id: str = Query(...),
    word_ids: str = Query(..., description="单词ID，逗号分隔"),
    mode: str = Query("new", description="new=新学 / review=复习"),
    grade: int = Query(6),
    mix_errors: bool = Query(False, description="是否混入未掌握的单词错题（每词4题，打 error_id 标记）"),
    per_word: int = Query(4, description="每词题目数：默认4；逐词测一测传1（只出1道默写题）"),
    db: Session = Depends(get_db),
):
    """背诵会话检测：为新学/复习的每个单词生成混合题（默写+理解型），每词题数由 per_word 控制。

    理解题占比随复习阶段递增（stage0: 2默写2理解 → stage1-3: 1默写3理解 → stage4+: 全理解）；
    per_word=1 时每词只出 1 道默写填空题（直接检验拼写记忆，各阶段均适用）。
    选择题干扰项从同年级词库取，拼写题用邻近变体。答案由前端判分。
    参数（Query）：user_id、word_ids（逗号分隔）、mode、grade、per_word。
    返回：{items[每词 per_word 题]};word_ids 空 400、单词不存在 404。
    副作用：无（只读，仅生成题目）。无需家长密码。
    """
    from app.models.phrase import Sentence
    ids = []
    for s in (word_ids or "").split(","):
        s = s.strip()
        if s.isdigit():
            ids.append(int(s))
    if not ids:
        raise HTTPException(400, "word_ids 不能为空")
    words = db.query(Word).filter(Word.id.in_(ids)).all()
    if not words:
        raise HTTPException(404, "单词不存在")
    stages = {}
    if mode != "new":
        for p in db.query(VocabProgress).filter(
                VocabProgress.user_id == user_id,
                VocabProgress.word_id.in_(ids)).all():
            stages[p.word_id] = p.review_stage
    book_ids = _career_book_ids(db, grade, user_id) or [w.book_id for w in words]
    sentence_cache = [s for (s,) in db.query(Sentence.sentence_en).all() if s]
    items = []
    for w in words:
        items.extend(_vocab_session_items_for_word(db, w, stages.get(w.id, 0),
                                                   book_ids, sentence_cache, per_word))

    # 错题混入：拉取少量未掌握的单词错题，生成题并打 error_id 标记，
    # 前端据此在提交时回写「连续答对连击」，满 3 次移除错题本。
    if mix_errors:
        errs = db.query(StudyError).filter(
            StudyError.user_id == user_id,
            StudyError.source_type == "vocab",
            StudyError.is_mastered.is_(False),
        ).order_by(StudyError.wrong_at.desc()).limit(3).all()
        err_ids = [e.source_id for e in errs if e.source_id]
        if err_ids:
            err_words = db.query(Word).filter(Word.id.in_(err_ids)).all()
            emap = {e.source_id: e.id for e in errs}
            for ew in err_words:
                for qi in _vocab_session_items_for_word(db, ew, stages.get(ew.id, 0),
                                                        book_ids, sentence_cache, per_word):
                    qi["error_id"] = emap.get(ew.id)
                    items.append(qi)
    return {"items": items}


__all__ = [
    "_VOCAB_UNDERSTAND_TYPES",
    "_vocab_choice_item",
    "_vocab_distractor_pool",
    "_spelling_variants",
    "_dictate_item",
    "_vocab_session_items_for_word",
    "vocab_session_quiz",
]
