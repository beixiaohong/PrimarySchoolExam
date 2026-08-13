"""背单词路由 - 艾宾浩斯记忆曲线"""
import random
import re
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.word import Word, WordBook
from ..models.vocab import VocabProgress, VocabDailyLog
from ..models.study_error import StudyError
from ..schemas.vocab import (
    VocabWordOut, LearnRequest, ReviewRequest,
    VocabStatsOut, TodayTaskOut, VocabProgressOut,
)

router = APIRouter()

# 艾宾浩斯记忆曲线复习间隔（天）
EBBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30]
# 每天新学单词数
NEW_WORDS_PER_DAY = 20


def _get_grade_books(db: Session, grade: int, user_id: Optional[str] = None) -> List[int]:
    """获取指定年级的词库ID：默认只开当前学期，include_next 开启时预支下学期"""
    from .tasks import _load_study_flags
    from ..services.semester import current_semester, next_semester

    semesters = [current_semester()]
    if user_id and _load_study_flags(db, user_id).get("include_next"):
        semesters.append(next_semester())

    books = db.query(WordBook).filter(
        WordBook.grade == grade,
        WordBook.semester.in_(semesters),
    ).all()
    if not books:
        # 兜底：该年级当前学期无册（数据未就绪）时回退全量，避免无词可学
        books = db.query(WordBook).filter(WordBook.grade == grade).all()
    return [b.id for b in books]


def _career_book_ids(db: Session, grade: int, user_id: Optional[str] = None) -> List[int]:
    """整个学生生涯词库（累计统计用）：本年级及以下所有年级；
    当前年级只取不超过当前学期的册（下学期含上下两册），低年级含上下两册。
    实现「每学期把当前阶段词库加进来」——累计学习量不随学期切换而丢失，
    与古诗文模块（ClassicalText.grade <= grade）口径保持一致。"""
    from .tasks import _load_study_flags
    from ..services.semester import current_semester, next_semester

    cur = current_semester()
    books = db.query(WordBook).filter(
        WordBook.grade <= grade,
        or_(WordBook.grade < grade, WordBook.semester <= cur),
    ).all()
    ids = [b.id for b in books]
    if user_id and _load_study_flags(db, user_id).get("include_next"):
        # 预支下学期：把当前年级的下一学期册也纳入累计池
        nxt = next_semester()
        extra = db.query(WordBook.id).filter(
            WordBook.grade == grade, WordBook.semester == nxt
        ).all()
        ids += [r[0] for r in extra]
    if not ids:
        # 兜底：本年级及以下均无册（数据未就绪）时回退当前年级全量
        ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
    return ids


def _sync_unit_filter(db: Session, user_id: str, book_ids: List[int]):
    """课堂同步：sync_mode 开启时返回英语当前进度的 (book_id, unit)，否则 None"""
    from .tasks import _load_study_flags
    if not _load_study_flags(db, user_id).get("sync_mode"):
        return None
    from ..models.middle import TeachingProgress
    prog = db.query(TeachingProgress).filter(
        TeachingProgress.user_id == user_id,
        TeachingProgress.subject == "英语",
    ).first()
    if not prog or not prog.book_id or not prog.chapter:
        return None
    if prog.book_id not in book_ids:
        return None
    return prog.book_id, prog.chapter


def _get_today_log(db: Session, user_id: str, today: date) -> VocabDailyLog:
    """获取或创建今日学习日志"""
    log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date == today
    ).first()
    if not log:
        log = VocabDailyLog(user_id=user_id, learn_date=today)
        db.add(log)
        db.commit()
        db.refresh(log)
    return log


def _calc_next_review(stage: int, from_date: date) -> date:
    """根据复习阶段计算下次复习日期"""
    if stage >= len(EBBINGHAUS_INTERVALS):
        # 已完成所有复习阶段，30天后复查
        return from_date + timedelta(days=30)
    return from_date + timedelta(days=EBBINGHAUS_INTERVALS[stage])


def _get_streak(db: Session, user_id: str) -> int:
    """计算连续学习天数"""
    logs = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.new_words_learned > 0
    ).order_by(VocabDailyLog.learn_date.desc()).all()

    if not logs:
        return 0

    streak = 0
    check_date = date.today()
    # 如果今天还没学，从昨天开始算
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date

    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)

    return streak


@router.get("/today", response_model=TodayTaskOut, summary="获取今日学习任务")
def get_today_words(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    db: Session = Depends(get_db),
):
    """获取今日学习任务：新词 + 待复习词"""
    today = date.today()
    career_ids = _career_book_ids(db, grade, user_id)   # 累计统计：整个学生生涯
    stage_ids = _get_grade_books(db, grade, user_id)    # 新学选材：当前阶段

    if not career_ids:
        return TodayTaskOut(new_words=[], review_words=[], stats={
            "total_words": 0, "learned": 0, "mastered": 0, "due_today": 0
        })

    # 1. 获取待复习词（next_review_date <= today 且 status=learning）
    review_progress = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "learning",
        VocabProgress.next_review_date <= today,
        VocabProgress.word_id.in_(
            db.query(Word.id).filter(Word.book_id.in_(career_ids))
        )
    ).all()

    review_word_ids = [p.word_id for p in review_progress]
    review_words = []
    if review_word_ids:
        words_map = {w.id: w for w in db.query(Word).filter(Word.id.in_(review_word_ids)).all()}
        prog_map = {p.word_id: p for p in review_progress}
        for wid in review_word_ids:
            w = words_map.get(wid)
            p = prog_map.get(wid)
            if w and p:
                review_words.append(VocabWordOut(
                    word_id=w.id, word=w.word, phonetic=w.phonetic or "",
                    pos=w.pos or "", meaning=w.meaning, unit=w.unit or "",
                    difficulty=w.difficulty or 1, is_new=False,
                    review_stage=p.review_stage,
                ))

    # 2. 获取新词（排除已学过的）：不限制每日轮数，每轮按额度返回下一批未学词
    learned_word_ids = db.query(VocabProgress.word_id).filter(
        VocabProgress.user_id == user_id
    ).subquery()

    # 每轮新学额度由家长配置（默认 NEW_WORDS_PER_DAY）
    from .tasks import get_daily_quota
    remaining_new = get_daily_quota(db, user_id, "daily_new_words")

    new_words = []
    if remaining_new > 0:
        # 按难度排序取未学过的词；sync_mode 开启时先按当前 unit 同步，额度不足回退全量
        # 新学选材来自当前阶段词库（stage_ids），不跨低年级
        base_q = db.query(Word).filter(
            Word.book_id.in_(stage_ids),
            ~Word.id.in_(db.query(learned_word_ids))
        )
        from .tasks import _load_study_flags
        flags = _load_study_flags(db, user_id)
        sync = _sync_unit_filter(db, user_id, stage_ids)
        # xsc_bridge：六年级升初衔接，新学批次按 7:3 混入七年级词
        bridge_n = remaining_new * 3 // 10 if (grade == 6 and flags.get("xsc_bridge")) else 0
        main_n = remaining_new - bridge_n

        main_candidates = []
        if sync:
            sync_book_id, sync_unit = sync
            main_candidates = base_q.filter(
                Word.book_id == sync_book_id,
                Word.unit == sync_unit,
            ).order_by(Word.difficulty, Word.id).limit(main_n).all()
        if not sync or len(main_candidates) < main_n:
            main_candidates = base_q.order_by(Word.difficulty, Word.id).limit(main_n).all()

        new_candidates = list(main_candidates)
        if bridge_n:
            bridge_books = db.query(WordBook.id).filter(WordBook.grade == 7)
            new_candidates += db.query(Word).filter(
                Word.book_id.in_(bridge_books),
                ~Word.id.in_(db.query(learned_word_ids)),
            ).order_by(Word.difficulty, Word.id).limit(bridge_n).all()

        for w in new_candidates:
            new_words.append(VocabWordOut(
                word_id=w.id, word=w.word, phonetic=w.phonetic or "",
                pos=w.pos or "", meaning=w.meaning, unit=w.unit or "",
                difficulty=w.difficulty or 1, is_new=True, review_stage=0,
            ))

    # 统计（累计口径：整个学生生涯，career_ids）
    total_words = db.query(Word).filter(Word.book_id.in_(career_ids)).count()
    learned_count = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.word_id.in_(db.query(Word.id).filter(Word.book_id.in_(career_ids)))
    ).count()
    mastered_count = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "mastered",
        VocabProgress.word_id.in_(db.query(Word.id).filter(Word.book_id.in_(career_ids)))
    ).count()

    return TodayTaskOut(
        new_words=new_words,
        review_words=review_words,
        stats={
            "total_words": total_words,
            "learned": learned_count,
            "mastered": mastered_count,
            "due_today": len(review_words),
            "new_remaining": remaining_new,
        }
    )


@router.post("/learn", summary="标记新词已学会")
def mark_words_learned(
    req: LearnRequest,
    db: Session = Depends(get_db),
):
    """标记新词为已学习，设置首次复习日期"""
    today = date.today()
    results = []

    log = _get_today_log(db, req.user_id, today)

    for wid in req.word_ids:
        # 检查是否已有进度
        existing = db.query(VocabProgress).filter(
            VocabProgress.user_id == req.user_id,
            VocabProgress.word_id == wid,
        ).first()

        if existing:
            results.append({"word_id": wid, "status": "already_exists"})
            continue

        # 创建新进度记录
        progress = VocabProgress(
            user_id=req.user_id,
            word_id=wid,
            status="learning",
            review_stage=0,
            first_learn_date=today,
            last_review_date=today,
            next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),  # 1天后复习
            correct_count=1,
            total_reviews=1,
        )
        db.add(progress)
        log.new_words_learned += 1
        log.correct_count += 1
        results.append({"word_id": wid, "status": "learned", "next_review": str(progress.next_review_date)})

    db.commit()
    return {"updated": len(results), "details": results}


@router.post("/review", summary="提交复习结果")
def submit_review(
    req: ReviewRequest,
    db: Session = Depends(get_db),
):
    """提交复习结果，更新艾宾浩斯曲线进度"""
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []

    for item in req.results:
        wid = item.get("word_id")
        correct = item.get("correct", False)

        progress = db.query(VocabProgress).filter(
            VocabProgress.user_id == req.user_id,
            VocabProgress.word_id == wid,
        ).first()

        if not progress:
            results.append({"word_id": wid, "status": "not_found"})
            continue

        progress.total_reviews += 1
        progress.last_review_date = today
        log.words_reviewed += 1

        if correct:
            progress.correct_count += 1
            log.correct_count += 1
            # 答对：推进到下一阶段
            progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
            progress.next_review_date = _calc_next_review(progress.review_stage, today)

            # 达到最高阶段后标记为掌握
            if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
                progress.status = "mastered"

            results.append({
                "word_id": wid, "status": "correct",
                "next_stage": progress.review_stage,
                "next_review": str(progress.next_review_date),
            })
        else:
            progress.wrong_count += 1
            log.wrong_count += 1
            # 答错：回退到第一阶段重新开始
            progress.review_stage = 0
            progress.next_review_date = today + timedelta(days=EBBINGHAUS_INTERVALS[0])
            progress.status = "learning"

            results.append({
                "word_id": wid, "status": "wrong",
                "reset_to_stage": 0,
                "next_review": str(progress.next_review_date),
            })

    db.commit()
    return {"updated": len(results), "details": results}


# ═══════════════════════════════════════════════════════════
# 背诵会话检测：混合题型（默写 + 理解型），理解题随复习阶段递增
# ═══════════════════════════════════════════════════════════

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
    from ..models.phrase import Sentence
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


# ═══════════════════════════════════════════════════════════
# 听写（默写）：全对才算通过，通过后才落库
# ═══════════════════════════════════════════════════════════

class DictateItem(BaseModel):
    word_id: int
    answer: str = ""


class DictateRequest(BaseModel):
    user_id: str
    mode: str = "new"  # new=新学 / review=复习
    results: List[DictateItem]


@router.post("/dictate", summary="单词听写判分：逐词存储（做对记录进度，做错进错题本）")
def dictate_words(req: DictateRequest, db: Session = Depends(get_db)):
    """默写判分（规则：逐词判分，做对即记录进度，做错不记录）：

    - 判分忽略大小写与首尾空白（如 Apple/apple 均正确）
    - mode=new：拼写正确 → 建/保留进度记录（今日新学数 +1）；错误词不记录，返回供前端进错题本
    - mode=review：拼写正确 → 推进该词记忆曲线；错误词不记录
    - 返回 saved(已记录的 word_id 列表)、wrong(错词及正确答案)、updated(记录数)、passed(是否全对)
      这样前端无需「整批从头重来」：做对的即时保存，做错的进入错题本后续巩固。
    """
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    saved: list = []
    wrong: list = []

    for it in req.results:
        w = db.query(Word).filter(Word.id == it.word_id).first()
        key = (w.word or "").strip().lower() if w else ""
        ans = (it.answer or "").strip().lower()
        if not w or ans != key:
            wrong.append({"word_id": it.word_id, "correct": False,
                          "correct_answer": w.word if w else ""})
            continue
        # 拼写正确 → 记录进度（按词独立落库）
        if req.mode == "new":
            existing = db.query(VocabProgress).filter(
                VocabProgress.user_id == req.user_id,
                VocabProgress.word_id == it.word_id,
            ).first()
            if not existing:
                progress = VocabProgress(
                    user_id=req.user_id, word_id=it.word_id,
                    status="learning", review_stage=0,
                    first_learn_date=today, last_review_date=today,
                    next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),
                    correct_count=1, total_reviews=1,
                )
                db.add(progress)
                log.new_words_learned += 1
            log.correct_count += 1
        else:
            progress = db.query(VocabProgress).filter(
                VocabProgress.user_id == req.user_id,
                VocabProgress.word_id == it.word_id,
            ).first()
            if not progress:
                # 复习但无进度记录：跳过记录（不计为错），避免误入错题本
                continue
            progress.total_reviews += 1
            progress.last_review_date = today
            progress.correct_count += 1
            progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
            progress.next_review_date = _calc_next_review(progress.review_stage, today)
            if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
                progress.status = "mastered"
            log.words_reviewed += 1
            log.correct_count += 1
        saved.append(it.word_id)

    db.commit()
    return {"passed": len(wrong) == 0, "saved": saved, "wrong": wrong,
            "updated": len(saved)}


@router.get("/stats", response_model=VocabStatsOut, summary="用户词汇学习统计")
def get_vocab_stats(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    db: Session = Depends(get_db),
):
    """获取用户词汇学习统计（累计口径：整个学生生涯）"""
    today = date.today()
    book_ids = _career_book_ids(db, grade, user_id)

    if not book_ids:
        return VocabStatsOut(
            total_words=0, learned_count=0, mastered_count=0, learning_count=0,
            new_today=0, review_today=0, due_today=0, streak_days=0, total_learned_all_time=0,
        )

    word_ids_subq = db.query(Word.id).filter(Word.book_id.in_(book_ids))

    total_words = db.query(Word).filter(Word.book_id.in_(book_ids)).count()

    all_progress = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.word_id.in_(word_ids_subq)
    ).all()

    learned_count = len(all_progress)
    mastered_count = sum(1 for p in all_progress if p.status == "mastered")
    learning_count = learned_count - mastered_count

    # 今日数据
    today_log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date == today
    ).first()
    new_today = today_log.new_words_learned if today_log else 0
    review_today = today_log.words_reviewed if today_log else 0

    # 今日待复习
    due_today = sum(
        1 for p in all_progress
        if p.status == "learning" and p.next_review_date and p.next_review_date <= today
    )

    streak = _get_streak(db, user_id)

    # 累计学习总数（不限年级）
    total_all_time = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id
    ).count()

    return VocabStatsOut(
        total_words=total_words,
        learned_count=learned_count,
        mastered_count=mastered_count,
        learning_count=learning_count,
        new_today=new_today,
        review_today=review_today,
        due_today=due_today,
        streak_days=streak,
        total_learned_all_time=total_all_time,
    )


@router.get("/progress", summary="查看单词学习进度列表")
def get_progress(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    status: Optional[str] = Query(None, description="过滤状态: learning/mastered"),
    db: Session = Depends(get_db),
):
    """查看用户所有单词的学习进度（累计口径：整个学生生涯）"""
    book_ids = _career_book_ids(db, grade, user_id)
    if not book_ids:
        return []

    query = db.query(VocabProgress, Word).join(
        Word, VocabProgress.word_id == Word.id
    ).filter(
        VocabProgress.user_id == user_id,
        Word.book_id.in_(book_ids),
    )

    if status:
        query = query.filter(VocabProgress.status == status)

    query = query.order_by(VocabProgress.updated_at.desc())
    rows = query.all()

    return [
        VocabProgressOut(
            word_id=prog.word_id,
            word=w.word,
            meaning=w.meaning,
            status=prog.status,
            review_stage=prog.review_stage,
            next_review_date=prog.next_review_date,
            correct_count=prog.correct_count,
            wrong_count=prog.wrong_count,
            total_reviews=prog.total_reviews,
        )
        for prog, w in rows
    ]


@router.get("/history", summary="查看历史学习日志")
def get_history(
    user_id: str = Query(..., description="用户名"),
    days: int = Query(30, description="查询天数"),
    db: Session = Depends(get_db),
):
    """查看最近N天的学习日志"""
    start_date = date.today() - timedelta(days=days)
    logs = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date >= start_date,
    ).order_by(VocabDailyLog.learn_date.desc()).all()

    return [
        {
            "date": str(log.learn_date),
            "new_words": log.new_words_learned,
            "reviewed": log.words_reviewed,
            "correct": log.correct_count,
            "wrong": log.wrong_count,
        }
        for log in logs
    ]
