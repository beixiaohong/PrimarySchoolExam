"""家长学习报告测试：GET /api/parent/report

验证多维报告（周/月/30天）聚合 ExamAttempt（分科）/DailyTask/FocusSession/WrongRecord：
- summary 计数与平均分正确
- by_subject 含做题学科
- trend 按天非空
- weak_points 薄弱点归因（关联 question_kp_map → knowledge_points）
"""
from datetime import date, datetime

import pytest

from app.database import SessionLocal
from app.models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from app.models.daily_task import DailyTask
from app.models.focus import FocusSession
from app.models.kp_map import QuestionKpMap
from app.models.knowledge import KnowledgePoint


def test_report_week_aggregates(client):
    """构造本周一次数学考试 + 任务 + 专注 + 一道未掌握错题（带知识点），报告聚合正确"""
    uid = "report_child"
    db = SessionLocal()
    now = datetime.now()
    try:
        # 试卷 + 题目
        exam = ExamRecord(user_id=uid, subject="数学", title="单元测", grade=6,
                          difficulty=3, question_count=1)
        db.add(exam); db.commit(); db.refresh(exam)
        q = Question(exam_id=exam.id, seq=1, subject="数学", category="计算",
                     type_name="填空", question="1+1=?", answer="2")
        db.add(q); db.commit(); db.refresh(q)
        # 一次尝试：满分 100，对 8/总 10
        db.add(ExamAttempt(user_id=uid, exam_id=exam.id, score=80, total=10,
                           correct=8, wrong=2, duration_sec=300, created_at=now))
        # 当日任务完成 + 专注
        db.add(DailyTask(user_id=uid, task_date=date.today(), subject="数学",
                         task_code="r1", title="练习", target=1, progress=1,
                         status="done"))
        db.add(FocusSession(user_id=uid, minutes=30, created_at=now))
        # 未掌握错题 + 知识点归因
        kp = KnowledgePoint(subject="数学", grade=6, unit="加法", title="进位加法")
        db.add(kp); db.commit(); db.refresh(kp)
        db.add(WrongRecord(user_id=uid, question_id=q.id, is_mastered=False,
                           wrong_at=now))
        db.add(QuestionKpMap(question_id=q.id, kp_id=kp.id,
                             source_table="questions", status="active"))
        db.commit()

        r = client.get(f"/api/parent/report?user_id={uid}&range=week")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["range"] == "week"
        s = body["summary"]
        assert s["total_attempts"] >= 1
        assert s["avg_score"] == 80.0, s
        assert s["tasks_done"] >= 1
        assert s["focus_minutes"] >= 30
        # 分科明细含数学
        subs = {x["subject"]: x for x in body["by_subject"]}
        assert "数学" in subs, subs
        assert subs["数学"]["attempts"] >= 1
        # 趋势按天非空
        assert len(body["trend"]) >= 1
        # 薄弱点归因（当前季度窗口内错题 → 命中知识点）
        titles = [w["kp_title"] for w in body["weak_points"]]
        assert "进位加法" in titles, titles
    finally:
        db.close()


def test_report_invalid_range_falls_back(client):
    """非法 range 不报错（回退默认 week）"""
    uid = "report_child2"
    r = client.get(f"/api/parent/report?user_id={uid}&range=garbage")
    assert r.status_code == 200, r.text
    assert r.json()["range"] == "week"
