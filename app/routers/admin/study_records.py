"""管理后台：用户学习记录"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.ai_usage import AiQa, WeeklyReport
from app.models.classical import ClassicalDailyLog
from app.models.exam import ExamAttempt, WrongRecord
from app.models.makeup_card import MakeupUsageLog
from app.models.parent import ParentMessage
from app.models.sprint4 import ChallengeRecord
from app.models.user import User
from app.models.vocab import VocabDailyLog

from . import router
from .common import _require_admin


# 行为 → 表映射（核心表聚合；听写/搜题当前无逐用户日志表，前端会标注「未记录」）
#   做题   → exam_attempts
#   错题   → wrong_records
#   背诵   → classical_daily_log
#   背单词 → vocab_daily_log
#   刷题   → challenge_records
#   AI对话 → ai_qa（qa 问答 / explain 讲解）
#   家长记录 → parent_messages（家长留言）/ weekly_reports（成长周报）/ makeup_usage_log（补签，家长确认）

STUDY_CATS = {
    "exam": "做题", "wrong": "错题", "classical": "背诵", "vocab": "背单词",
    "challenge": "刷题", "ai": "AI对话", "parent": "家长记录",
}


@router.get("/users/{user_id}/study-records",
            summary="查询用户学习记录（做题/错题/背诵/背单词/刷题/AI对话/家长记录）")
def user_study_records(user_id: str, category: str = "all", page: int = 1, page_size: int = 30,
                       db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    uid = user_id.strip()
    if not db.query(User).filter(User.user_id == uid).first():
        raise HTTPException(404, "用户不存在")
    want = lambda c: category in ("all", c)

    events = []
    if want("exam"):
        for r in db.query(ExamAttempt).filter(ExamAttempt.user_id == uid).all():
            events.append({
                "time": r.created_at, "category": "exam", "category_name": "做题",
                "summary": f"完成试卷（得分 {r.score}/100，答对 {r.correct}/{r.total}，用时 {r.duration_sec}s）",
                "detail": f"exam_id={r.exam_id}",
            })
    if want("wrong"):
        for r in db.query(WrongRecord).filter(WrongRecord.user_id == uid).all():
            events.append({
                "time": r.wrong_at, "category": "wrong", "category_name": "错题",
                "summary": f"标记错题（题目 #{r.question_id}）{'· 已掌握' if r.is_mastered else ''}",
                "detail": f"练习 {r.practice_count} 次；错因：{r.cause or '未填'}",
            })
    if want("classical"):
        for r in db.query(ClassicalDailyLog).filter(ClassicalDailyLog.user_id == uid).all():
            d = r.learn_date
            events.append({
                "time": datetime.combine(d, datetime.min.time()), "category": "classical",
                "category_name": "背诵",
                "summary": f"古诗文学习（新学 {r.texts_learned} · 复习 {r.texts_reviewed} · 对 {r.correct_count}/错 {r.wrong_count}）",
                "detail": f"日期 {d}",
            })
    if want("vocab"):
        for r in db.query(VocabDailyLog).filter(VocabDailyLog.user_id == uid).all():
            d = r.learn_date
            events.append({
                "time": datetime.combine(d, datetime.min.time()), "category": "vocab",
                "category_name": "背单词",
                "summary": f"背单词（新学 {r.new_words_learned} · 复习 {r.words_reviewed} · 对 {r.correct_count}/错 {r.wrong_count}）",
                "detail": f"日期 {d}",
            })
    if want("challenge"):
        for r in db.query(ChallengeRecord).filter(ChallengeRecord.user_id == uid).all():
            kind_cn = "口算" if r.kind == "math" else ("单词速答" if r.kind == "word" else r.kind)
            events.append({
                "time": r.created_at, "category": "challenge", "category_name": "刷题",
                "summary": f"限时挑战赛（{kind_cn}）：答对 {r.correct}/{r.total}",
                "detail": f"challenge_id={r.id}",
            })
    if want("ai"):
        for r in db.query(AiQa).filter(AiQa.user_id == uid).all():
            qtype = "讲解" if r.q_type == "explain" else "问答"
            events.append({
                "time": r.created_at, "category": "ai", "category_name": "AI对话",
                "summary": f"AI{qtype}：{(r.question or '')[:60]}{'…' if r.question and len(r.question) > 60 else ''}",
                "detail": f"供应商 {r.provider or '-'}",
            })
    if want("parent"):
        for r in db.query(ParentMessage).filter(ParentMessage.user_id == uid).all():
            events.append({
                "time": r.created_at, "category": "parent", "category_name": "家长记录",
                "summary": f"家长留言：{(r.content or '')[:60]}",
                "detail": f"{'已读' if r.read_at else '未读'}" + (f" · {r.created_at.strftime('%Y-%m-%d %H:%M')}" if r.created_at else ""),
            })
        for r in db.query(WeeklyReport).filter(WeeklyReport.user_id == uid).all():
            events.append({
                "time": r.created_at, "category": "parent", "category_name": "家长记录",
                "summary": f"成长周报（{r.week_start}）状态：{r.status}",
                "detail": f"家长寄语：{r.parent_note or '（无）'}",
            })
        for r in db.query(MakeupUsageLog).filter(MakeupUsageLog.user_id == uid).all():
            events.append({
                "time": r.used_at, "category": "parent", "category_name": "家长记录",
                "summary": f"补签卡使用（目标日 {r.target_date}）状态：{r.status}",
                "detail": f"关联任务 task_id={r.task_id}",
            })

    events.sort(key=lambda e: e["time"] or datetime.min, reverse=True)
    counts = {c: sum(1 for e in events if e["category"] == c) for c in STUDY_CATS}
    total = len(events)
    start = max(0, (page - 1) * page_size)
    items = events[start:start + page_size]
    # 时间格式化
    for e in items:
        e["time"] = e["time"].strftime("%Y-%m-%d %H:%M") if e["time"] else ""
    return {"total": total, "page": page, "page_size": page_size,
            "counts": counts, "items": items}


__all__ = ["STUDY_CATS", "user_study_records"]
