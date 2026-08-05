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
NEW_TEXTS_PER_DAY = 3


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
            "answer": lines[0] if lines else text.content,
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
            question = f"《{text.title}》（{text.author}）：____________，{lines[idx+1]}。"
        elif idx == len(lines) - 1:
            question = f"《{text.title}》（{text.author}）：{lines[idx-1]}，____________。"
        else:
            # 随机给上句或下句
            if random.random() < 0.5:
                question = f"《{text.title}》（{text.author}）：{lines[idx-1]}，____________。"
            else:
                question = f"《{text.title}》（{text.author}）：____________，{lines[idx+1]}。"

        questions.append({
            "text_id": text.id,
            "title": text.title,
            "author": text.author,
            "question": question,
            "answer": line,
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
    count: int = Query(10, description="题目数量", ge=1, le=50),
    db: Session = Depends(get_db),
):
    """从数据库中随机抽取篇目，生成上下句填空题"""
    texts = db.query(ClassicalText).filter(ClassicalText.grade <= grade).all()
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

    # 今日新学
    today_log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.learn_date == today,
    ).first()
    already_new = today_log.texts_learned if today_log else 0
    remaining = max(0, NEW_TEXTS_PER_DAY - already_new)

    new_items = []
    if remaining > 0:
        learned_ids = db.query(ClassicalProgress.text_id).filter(
            ClassicalProgress.user_id == user_id
        ).subquery()
        candidates = db.query(ClassicalText).filter(
            ClassicalText.grade <= grade,
            ~ClassicalText.id.in_(db.query(learned_ids)),
        ).order_by(ClassicalText.grade, ClassicalText.title).limit(remaining).all()

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
