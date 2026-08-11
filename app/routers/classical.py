"""古诗文背诵模块 API 路由"""
import json
import random
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.classical import ClassicalText, ClassicalProgress, ClassicalDailyLog

router = APIRouter()

# 艾宾浩斯间隔（天）
EBBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30]
# 每天新学篇数
NEW_TEXTS_PER_DAY = 5


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════

class ClassicalTextCreate(BaseModel):
    title: str
    author: str = ""
    dynasty: str = ""
    text_type: str = "poem"  # poem / prose
    grade: int = 3
    content: str  # 全文，行用\n分隔
    tags: str = ""


class ClassicalTextOut(BaseModel):
    id: int
    title: str
    author: str
    dynasty: str
    text_type: str
    grade: int
    content: str
    lines: list
    tags: str


class QuizQuestionOut(BaseModel):
    text_id: int
    title: str
    author: str
    question: str
    answer: str
    context: str  # 上下文提示


class LearnRequest(BaseModel):
    user_id: str
    text_ids: List[int]


class ReviewRequest(BaseModel):
    user_id: str
    results: List[dict]  # [{text_id, correct}]


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _parse_lines(content: str) -> list:
    """将全文按换行分割成行列表，过滤空行"""
    return [line.strip() for line in content.strip().split("\n") if line.strip()]


def _calc_next_review(stage: int, from_date: date) -> date:
    if stage >= len(EBBINGHAUS_INTERVALS):
        return from_date + timedelta(days=30)
    return from_date + timedelta(days=EBBINGHAUS_INTERVALS[stage])


def _get_today_log(db: Session, user_id: str, today: date) -> ClassicalDailyLog:
    log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.learn_date == today
    ).first()
    if not log:
        log = ClassicalDailyLog(user_id=user_id, learn_date=today)
        db.add(log)
        db.commit()
        db.refresh(log)
    return log


def _get_streak(db: Session, user_id: str) -> int:
    logs = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.texts_learned > 0
    ).order_by(ClassicalDailyLog.learn_date.desc()).all()
    if not logs:
        return 0
    streak = 0
    check_date = date.today()
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date
    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


_TRAILING_PUNCT = "，。！？；：、,.!?;:"


def _strip_punct(s: str) -> str:
    """去掉行尾标点，避免与题干模板标点重复"""
    return s.rstrip(_TRAILING_PUNCT)


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


# ═══════════════════════════════════════════════════════════
# 文章管理 API
# ═══════════════════════════════════════════════════════════

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
            tags=t.tags,
        )
        for t in texts
    ]


@router.get("/texts/{text_id}", summary="查看单篇详情")
def get_text(text_id: int, db: Session = Depends(get_db)):
    text = db.query(ClassicalText).filter(ClassicalText.id == text_id).first()
    if not text:
        raise HTTPException(404, "篇目不存在")
    return ClassicalTextOut(
        id=text.id, title=text.title, author=text.author, dynasty=text.dynasty,
        text_type=text.text_type, grade=text.grade, content=text.content,
        lines=json.loads(text.lines_json) if text.lines_json else _parse_lines(text.content),
        tags=text.tags,
    )


# ═══════════════════════════════════════════════════════════
# 出题 / 背诵 API
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# 背诵会话检测：混合题型（基础填空 + 理解型选择），按复习阶段递增理解题占比
# ═══════════════════════════════════════════════════════════

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


@router.get("/session-quiz", summary="背诵会话检测：每篇 3 题混合题型（理解题随复习阶段递增）")
def classical_session_quiz(
    user_id: str = Query(...),
    text_ids: str = Query(..., description="篇目ID，逗号分隔"),
    mode: str = Query("new", description="new=新学 / review=复习"),
    db: Session = Depends(get_db),
):
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
    return {"items": items}


@router.get("/today", summary="获取今日背诵任务")
def get_today_task(
    user_id: str = Query(...),
    grade: int = Query(6),
    db: Session = Depends(get_db),
):
    """获取今日任务：新学篇目 + 待复习篇目"""
    today = date.today()

    # 待复习
    review_progress = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "learning",
        ClassicalProgress.next_review_date <= today,
    ).all()

    review_items = []
    for p in review_progress:
        text = db.query(ClassicalText).filter(ClassicalText.id == p.text_id).first()
        if text:
            review_items.append({
                "text_id": text.id,
                "title": text.title,
                "author": text.author,
                "content": text.content,
                "review_stage": p.review_stage,
                "next_review_date": str(p.next_review_date) if p.next_review_date else None,
            })

    # 新学：不限制每日轮数，每轮按额度返回下一批未背篇目
    # 每轮新背额度由家长配置（默认 NEW_TEXTS_PER_DAY）
    from .tasks import get_daily_quota
    remaining = get_daily_quota(db, user_id, "daily_new_texts")

    new_items = []
    if remaining > 0:
        # 学期解锁：只开「全」+ 当前学期篇目，include_next 预支下学期
        from ..services.semester import current_semester, next_semester
        from .tasks import _load_study_flags
        semesters = ["全", current_semester()]
        if _load_study_flags(db, user_id).get("include_next"):
            semesters.append(next_semester())

        learned_ids = db.query(ClassicalProgress.text_id).filter(
            ClassicalProgress.user_id == user_id
        ).subquery()
        # xsc_bridge：六年级升初衔接，新背批次按 7:3 混入七年级篇目
        flags = _load_study_flags(db, user_id)
        bridge_n = remaining * 3 // 10 if (grade == 6 and flags.get("xsc_bridge")) else 0
        main_n = remaining - bridge_n
        candidates = db.query(ClassicalText).filter(
            ClassicalText.grade <= grade,
            ClassicalText.semester.in_(semesters),
            ~ClassicalText.id.in_(db.query(learned_ids)),
        ).order_by(ClassicalText.grade, ClassicalText.title).limit(main_n).all()
        if bridge_n:
            candidates += db.query(ClassicalText).filter(
                ClassicalText.grade == 7,
                ClassicalText.semester.in_(semesters),
                ~ClassicalText.id.in_(db.query(learned_ids)),
                ClassicalText.id.notin_([t.id for t in candidates]),
            ).order_by(ClassicalText.grade, ClassicalText.title).limit(bridge_n).all()

        for t in candidates:
            new_items.append({
                "text_id": t.id,
                "title": t.title,
                "author": t.author,
                "content": t.content,
                "text_type": t.text_type,
            })

    # 统计
    total = db.query(ClassicalText).filter(ClassicalText.grade <= grade).count()
    learned = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.text_id.in_(
            db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        )
    ).count()
    mastered = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "mastered",
        ClassicalProgress.text_id.in_(
            db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        )
    ).count()

    return {
        "new_texts": new_items,
        "review_texts": review_items,
        "stats": {
            "total": total,
            "learned": learned,
            "mastered": mastered,
            "due_today": len(review_items),
            "new_remaining": remaining,
            "streak_days": _get_streak(db, user_id),
        }
    }


@router.post("/learn", summary="标记篇目已学习")
def mark_texts_learned(req: LearnRequest, db: Session = Depends(get_db)):
    """标记新学的篇目，设置首次复习日期"""
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []

    for tid in req.text_ids:
        existing = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == req.user_id,
            ClassicalProgress.text_id == tid,
        ).first()
        if existing:
            results.append({"text_id": tid, "status": "already_exists"})
            continue

        progress = ClassicalProgress(
            user_id=req.user_id,
            text_id=tid,
            status="learning",
            review_stage=0,
            first_learn_date=today,
            last_review_date=today,
            next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),
            correct_count=1,
            total_reviews=1,
        )
        db.add(progress)
        log.texts_learned += 1
        log.correct_count += 1
        results.append({"text_id": tid, "status": "learned"})

    db.commit()
    return {"updated": len(results), "details": results}


@router.post("/review", summary="提交背诵复习结果")
def submit_review(req: ReviewRequest, db: Session = Depends(get_db)):
    """提交复习结果，更新艾宾浩斯进度"""
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []

    for item in req.results:
        tid = item.get("text_id")
        correct = item.get("correct", False)

        progress = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == req.user_id,
            ClassicalProgress.text_id == tid,
        ).first()
        if not progress:
            results.append({"text_id": tid, "status": "not_found"})
            continue

        progress.total_reviews += 1
        progress.last_review_date = today
        log.texts_reviewed += 1

        if correct:
            progress.correct_count += 1
            log.correct_count += 1
            progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
            progress.next_review_date = _calc_next_review(progress.review_stage, today)
            if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
                progress.status = "mastered"
            results.append({"text_id": tid, "status": "correct", "next_review": str(progress.next_review_date)})
        else:
            progress.wrong_count += 1
            log.wrong_count += 1
            progress.review_stage = 0
            progress.next_review_date = today + timedelta(days=EBBINGHAUS_INTERVALS[0])
            progress.status = "learning"
            results.append({"text_id": tid, "status": "wrong", "next_review": str(progress.next_review_date)})

    db.commit()
    return {"updated": len(results), "details": results}


# ═══════════════════════════════════════════════════════════
# 默写：全对才算通过（前端填空判分），通过后才落库
# ═══════════════════════════════════════════════════════════

class DictateRequest(BaseModel):
    user_id: str
    mode: str = "new"  # new=新学 / review=复习
    text_ids: List[int]


@router.post("/dictate", summary="古诗文默写提交：全对才落库（new=学会 / review=复习推进）")
def dictate_texts(req: DictateRequest, db: Session = Depends(get_db)):
    """默写结果提交（前端随机填空题判分，全对才允许调用本接口）：

    - mode=new：全部默写正确 → 与 /learn 相同落库（建进度 + 今日新学数 +N）
    - mode=review：全部正确 → 按全部 correct 提交复习（记忆曲线推进，达满掌握）
    - text_ids 为空 → 不落库，视为未通过
    """
    if not req.text_ids:
        return {"passed": False, "updated": 0}

    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []

    if req.mode == "new":
        for tid in req.text_ids:
            existing = db.query(ClassicalProgress).filter(
                ClassicalProgress.user_id == req.user_id,
                ClassicalProgress.text_id == tid,
            ).first()
            if existing:
                results.append({"text_id": tid, "status": "already_exists"})
                continue
            progress = ClassicalProgress(
                user_id=req.user_id, text_id=tid,
                status="learning", review_stage=0,
                first_learn_date=today, last_review_date=today,
                next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),
                correct_count=1, total_reviews=1,
            )
            db.add(progress)
            log.texts_learned += 1
            log.correct_count += 1
            results.append({"text_id": tid, "status": "learned"})
        db.commit()
        return {"passed": True, "updated": len(results), "details": results}

    # mode=review：全部按 correct 提交复习（全对才落库，等同 /review 的 correct 分支）
    for tid in req.text_ids:
        progress = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == req.user_id,
            ClassicalProgress.text_id == tid,
        ).first()
        if not progress:
            results.append({"text_id": tid, "status": "not_found"})
            continue
        progress.total_reviews += 1
        progress.last_review_date = today
        log.texts_reviewed += 1
        progress.correct_count += 1
        log.correct_count += 1
        progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
        progress.next_review_date = _calc_next_review(progress.review_stage, today)
        if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
            progress.status = "mastered"
        results.append({"text_id": tid, "status": "correct",
                        "next_review": str(progress.next_review_date)})
    db.commit()
    return {"passed": True, "updated": len(results), "details": results}


@router.get("/stats", summary="古诗文学习统计")
def get_stats(
    user_id: str = Query(...),
    grade: int = Query(6),
    db: Session = Depends(get_db),
):
    today = date.today()
    total = db.query(ClassicalText).filter(ClassicalText.grade <= grade).count()
    all_progress = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.text_id.in_(
            db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        )
    ).all()

    learned = len(all_progress)
    mastered = sum(1 for p in all_progress if p.status == "mastered")
    due_today = sum(
        1 for p in all_progress
        if p.status == "learning" and p.next_review_date and p.next_review_date <= today
    )

    today_log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.learn_date == today,
    ).first()

    return {
        "total": total,
        "learned": learned,
        "mastered": mastered,
        "learning": learned - mastered,
        "due_today": due_today,
        "new_today": today_log.texts_learned if today_log else 0,
        "review_today": today_log.texts_reviewed if today_log else 0,
        "streak_days": _get_streak(db, user_id),
    }
