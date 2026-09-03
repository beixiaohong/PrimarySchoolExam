"""古诗文：出题 / 背诵会话检测（混合题型）"""
import random
from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.classical import ClassicalText, ClassicalProgress
from app.models.study_error import StudyError

from . import router
from .common import (
    _parse_lines,
    _strip_punct,
    _pinyin_lines,
    _TRAILING_PUNCT,
)


def _generate_quiz_from_text(text: ClassicalText, count: int = 1) -> list:
    """从一篇古诗文中生成填空题"""
    lines = _parse_lines(text.content)
    if len(lines) < 2:
        # 只有一行，做整句填空
        return [{
            "text_id": text.id,
            "title": text.title,
            "author": text.author,
            "question": f"《{text.title}》（{text.author}）：____________。",
            "answer": _strip_punct(lines[0]) if lines else text.content,
            "context": f"请填写《{text.title}》的完整内容",
        }]

    questions = []
    available_indices = list(range(len(lines)))
    random.shuffle(available_indices)

    for idx in available_indices[:count]:
        line = lines[idx]
        # 构建上下文
        context_parts = []
        if idx > 0:
            context_parts.append(f"上句：{lines[idx-1]}")
        if idx < len(lines) - 1:
            context_parts.append(f"下句：{lines[idx+1]}")
        context = "，".join(context_parts) if context_parts else "无上下文"

        # 根据位置生成不同题型
        if idx == 0:
            question = f"《{text.title}》（{text.author}）：____________，{_strip_punct(lines[idx+1])}。"
        elif idx == len(lines) - 1:
            question = f"《{text.title}》（{text.author}）：{_strip_punct(lines[idx-1])}，____________。"
        else:
            # 随机给上句或下句
            if random.random() < 0.5:
                question = f"《{text.title}》（{text.author}）：{_strip_punct(lines[idx-1])}，____________。"
            else:
                question = f"《{text.title}》（{text.author}）：____________，{_strip_punct(lines[idx+1])}。"

        questions.append({
            "text_id": text.id,
            "title": text.title,
            "author": text.author,
            "question": question,
            "answer": _strip_punct(line),
            "context": context,
        })

    return questions


# 基础题型（填空/默写类）与理解型题型
_CLASSICAL_FILL_TYPES = ["fill_next", "keyword_fill", "first_char_fill"]
_CLASSICAL_UNDERSTAND_TYPES = ["choice_next", "order_choice", "author_choice"]
_CLASSICAL_FUNC_CHARS = set("的了是在不与和而之乎者也兮其于以则乃为")


def _all_classical_lines(db: Session) -> list:
    """全库诗句行池（选择类干扰项用）"""
    pool = []
    for (content,) in db.query(ClassicalText.content).all():
        pool.extend(_parse_lines(content or ""))
    return pool


def _build_choice_item(text: ClassicalText, kind: str, question: str,
                       correct: str, distractors: list, context: str) -> Optional[dict]:
    """组装选择题；干扰项去重后不足则降级选项数，完全无干扰项则弃用该题"""
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
        "text_id": text.id, "title": text.title, "author": text.author,
        "kind": "choice", "q_type": kind,
        "question": question, "answer": correct,
        "options": options, "context": context,
    }


def _gen_choice_next(db, text, lines, line_pool):
    """上下句选择：给上句，4 选 1 选下句"""
    if len(lines) < 2:
        return None
    idx = random.randrange(len(lines) - 1)
    correct = _strip_punct(lines[idx + 1])
    ds = [l for l in lines if l != lines[idx + 1]]
    if len(ds) < 3:
        ds += [l for l in line_pool if l != lines[idx + 1]]
    return _build_choice_item(
        text, "choice_next",
        f"《{text.title}》：「{_strip_punct(lines[idx])}」的下一句是？",
        correct, [_strip_punct(l) for l in ds], "选出正确的下句")


def _gen_order_choice(db, text, lines, line_pool):
    """排序选择：短诗整篇/长诗连续 4 行片段，打乱后选正确顺序"""
    if len(lines) < 4:
        return None
    seg = lines if len(lines) <= 6 else lines[random.randrange(len(lines) - 3):][:4]
    correct_str = " → ".join(_strip_punct(l) for l in seg)
    seen = {correct_str}
    ds = []
    for _ in range(40):
        sh = seg[:]
        random.shuffle(sh)
        s = " → ".join(_strip_punct(l) for l in sh)
        if s not in seen:
            seen.add(s)
            ds.append(s)
        if len(ds) >= 3:
            break
    return _build_choice_item(
        text, "order_choice",
        f"《{text.title}》下列哪一个是正确的顺序？",
        correct_str, ds, "选出诗句的正确排列")


def _gen_author_choice(db, text, lines, line_pool):
    """作者/朝代选择：干扰项取全库去重值"""
    ask_dynasty = bool(text.dynasty and text.dynasty.strip()) and random.random() < 0.5
    if ask_dynasty:
        correct = text.dynasty.strip()
        pool = [d.strip() for d, in db.query(ClassicalText.dynasty).distinct().all() if d and d.strip()]
        question = f"《{text.title}》（{text.author or '佚名'}）是哪个朝代的作品？"
    else:
        correct = text.author.strip() if text.author else "佚名"
        pool = [a.strip() for a, in db.query(ClassicalText.author).distinct().all() if a and a.strip()]
        first_line = _strip_punct(lines[0]) if lines else text.title
        question = f"「{first_line}」出自《{text.title}》，其作者是？"
    return _build_choice_item(text, "author_choice", question, correct,
                              [v for v in pool if v != correct], "文学常识选择")


def _gen_keyword_fill(db, text, lines, line_pool):
    """关键字填空：抠掉行内关键字（非首字/非标点/非虚词），答案为完整句"""
    cands = []
    for line in lines:
        body = _strip_punct(line)
        positions = [i for i, ch in enumerate(body)
                     if i > 0 and ch not in _TRAILING_PUNCT and ch not in _CLASSICAL_FUNC_CHARS]
        if positions:
            cands.append((body, positions))
    if not cands:
        return None
    body, positions = random.choice(cands)
    idx = random.choice(positions)
    blanked = body[:idx] + "＿" + body[idx + 1:]
    return {
        "text_id": text.id, "title": text.title, "author": text.author,
        "kind": "fill", "q_type": "keyword_fill",
        "question": f"《{text.title}》（{text.author}）：{blanked}。",
        "answer": body, "options": None,
        "context": f"填入空缺的字，写出完整诗句（答案不含标点）",
    }


def _gen_first_char_fill(db, text, lines, line_pool):
    """首字填空：只给首字，填完整句"""
    cands = [_strip_punct(l) for l in lines if len(_strip_punct(l)) >= 3]
    if not cands:
        return None
    body = random.choice(cands)
    return {
        "text_id": text.id, "title": text.title, "author": text.author,
        "kind": "fill", "q_type": "first_char_fill",
        "question": f"《{text.title}》（{text.author}）：{body[0]}＿＿＿＿＿＿",
        "answer": body, "options": None,
        "context": "根据首字提示默写完整诗句（答案不含标点）",
    }


_CLASSICAL_TYPE_GENERATORS = {
    "fill_next": lambda db, text, lines, pool: _generate_quiz_from_text(text, 1)[0]
    if _parse_lines(text.content) else None,
    "keyword_fill": _gen_keyword_fill,
    "first_char_fill": _gen_first_char_fill,
    "choice_next": _gen_choice_next,
    "order_choice": _gen_order_choice,
    "author_choice": _gen_author_choice,
}


def _session_quiz_for_text(db: Session, text: ClassicalText, stage: int,
                           line_pool: list) -> list:
    """每篇 3 题：stage 0-1 = 2 基础+1 理解；stage 2-3 = 1+2；stage 4+ 全理解"""
    if stage <= 1:
        n_fill, n_under = 2, 1
    elif stage <= 3:
        n_fill, n_under = 1, 2
    else:
        n_fill, n_under = 0, 3
    fill_pool = _CLASSICAL_FILL_TYPES[:]
    under_pool = _CLASSICAL_UNDERSTAND_TYPES[:]
    random.shuffle(fill_pool)
    random.shuffle(under_pool)
    plan = fill_pool[:n_fill] + under_pool[:n_under]
    lines = _parse_lines(text.content)
    items = []
    for t in plan:
        gen = _CLASSICAL_TYPE_GENERATORS.get(t)
        if not gen:
            continue
        try:
            item = gen(db, text, lines, line_pool)
        except Exception:
            item = None
        if item:
            item.setdefault("kind", "fill")
            item.setdefault("q_type", t)
            item.setdefault("options", None)
            items.append(item)
    return items


@router.get("/quiz", summary="随机生成古诗文填空题")
def generate_quiz(
    grade: int = Query(6, description="年级"),
    text_id: Optional[int] = Query(None, description="指定篇目ID（不填则随机全库）"),
    count: int = Query(10, description="题目数量", ge=1, le=50),
    db: Session = Depends(get_db),
):
    """从数据库中随机抽取篇目，生成上下句填空题"""
    q = db.query(ClassicalText).filter(ClassicalText.grade <= grade)
    if text_id:
        q = q.filter(ClassicalText.id == text_id)
    texts = q.all()
    if not texts:
        raise HTTPException(404, f"暂无{grade}年级及以下的古诗文数据")

    questions = []
    attempts = 0
    while len(questions) < count and attempts < count * 3:
        text = random.choice(texts)
        lines = _parse_lines(text.content)
        if len(lines) >= 1:
            qs = _generate_quiz_from_text(text, 1)
            questions.extend(qs)
        attempts += 1

    return questions[:count]


@router.get("/session-quiz", summary="背诵会话检测：每篇 3 题混合题型（理解题随复习阶段递增）")
def classical_session_quiz(
    user_id: str = Query(...),
    text_ids: str = Query(..., description="篇目ID，逗号分隔"),
    mode: str = Query("new", description="new=新学 / review=复习"),
    mix_errors: bool = Query(False, description="是否混入未掌握的古诗文错题（每篇3题，打 error_id 标记）"),
    db: Session = Depends(get_db),
):
    """背诵会话检测：为新学/复习的每篇古诗文生成 3 道混合题（基础+理解型，理解题占比随复习阶段递增）。

    参数（Query）：user_id、text_ids（逗号分隔的篇目 ID）、mode（new=新学 / review=复习）、
                  mix_errors（是否混入未掌握的古诗文错题，每篇 3 题并打 error_id 标记）。
    返回：{items[每篇 3 题]}；text_ids 为空 400、篇目不存在 404。
    副作用：只读（仅生成题目，不落库）。无需家长密码。
    """
    ids = []
    for s in (text_ids or "").split(","):
        s = s.strip()
        if s.isdigit():
            ids.append(int(s))
    if not ids:
        raise HTTPException(400, "text_ids 不能为空")
    texts = db.query(ClassicalText).filter(ClassicalText.id.in_(ids)).all()
    if not texts:
        raise HTTPException(404, "篇目不存在")
    stages = {}
    if mode != "new":
        for p in db.query(ClassicalProgress).filter(
                ClassicalProgress.user_id == user_id,
                ClassicalProgress.text_id.in_(ids)).all():
            stages[p.text_id] = p.review_stage
    line_pool = _all_classical_lines(db)
    items = []
    for t in texts:
        items.extend(_session_quiz_for_text(db, t, stages.get(t.id, 0), line_pool))

    # 错题混入：拉取少量未掌握的古诗文错题，生成题并打 error_id 标记，
    # 前端据此在提交时回写「连续答对连击」，满 3 次移除错题本。
    if mix_errors:
        errs = db.query(StudyError).filter(
            StudyError.user_id == user_id,
            StudyError.source_type == "classical",
            StudyError.is_mastered.is_(False),
        ).order_by(StudyError.wrong_at.desc()).limit(3).all()
        err_ids = [e.source_id for e in errs if e.source_id]
        if err_ids:
            err_texts = db.query(ClassicalText).filter(ClassicalText.id.in_(err_ids)).all()
            emap = {e.source_id: e.id for e in errs}
            for et in err_texts:
                for qi in _session_quiz_for_text(db, et, stages.get(et.id, 0), line_pool):
                    qi["error_id"] = emap.get(et.id)
                    items.append(qi)
    return {"items": items}


__all__ = [
    "_generate_quiz_from_text",
    "_CLASSICAL_FILL_TYPES",
    "_CLASSICAL_UNDERSTAND_TYPES",
    "_CLASSICAL_FUNC_CHARS",
    "_all_classical_lines",
    "_build_choice_item",
    "_gen_choice_next",
    "_gen_order_choice",
    "_gen_author_choice",
    "_gen_keyword_fill",
    "_gen_first_char_fill",
    "_CLASSICAL_TYPE_GENERATORS",
    "_session_quiz_for_text",
    "generate_quiz",
    "classical_session_quiz",
]
