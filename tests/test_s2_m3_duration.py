"""S2-M3：提交答案接口持久化单题用时（duration_ms / started_at / seq）。

验收：/api/exam/submit-answers 接受每题上报的 duration_ms 与 started_at，
写入 attempt_answers，且跨会话可查（还原答题过程需要）。
"""

import time

from app.database import SessionLocal
from app.models.exam import (
    ExamRecord, Question, ExamAttempt, AttemptAnswer, WrongRecord,
)


def _cleanup(db, rec_id, qids):
    """按 FK 安全顺序清理：attempt_answers → wrong_records → questions →
    exam_attempts → exam_records。"""
    db.query(AttemptAnswer).filter(
        AttemptAnswer.attempt_id.in_(
            db.query(ExamAttempt.id).filter(ExamAttempt.exam_id == rec_id)
        )).delete(synchronize_session=False)
    db.query(WrongRecord).filter(
        WrongRecord.question_id.in_(qids)).delete(synchronize_session=False)
    db.query(Question).filter(Question.exam_id == rec_id).delete(
        synchronize_session=False)
    db.query(ExamAttempt).filter(ExamAttempt.exam_id == rec_id).delete(
        synchronize_session=False)
    db.query(ExamRecord).filter(ExamRecord.id == rec_id).delete(
        synchronize_session=False)
    db.commit()


def test_s2_m3_submit_persists_timing(client):
    db = SessionLocal()
    rec = ExamRecord(subject="数学", title="S2M3计时卷", grade=6,
                     difficulty="综合", question_count=2)
    db.add(rec)
    db.flush()
    q1 = Question(exam_id=rec.id, seq=1, subject="数学",
                  question="1+1=?", answer="2")
    q2 = Question(exam_id=rec.id, seq=2, subject="数学",
                  question="2+2=?", answer="4")
    db.add(q1)
    db.add(q2)
    db.commit()
    # 在会话关闭前抓出整型主键，避免后续访问 detached 实例触发刷新
    rec_id, q1_id, q2_id = rec.id, q1.id, q2.id
    try:
        started = int(time.time() * 1000) - 5000  # 5 秒前开始作答
        r = client.post("/api/exam/submit-answers", json={
            "user_id": "S2M3计时生",
            "exam_id": rec_id,
            "answers": [
                {"question_id": q1_id, "user_answer": "2",
                 "duration_ms": 3200, "started_at": started},
                {"question_id": q2_id, "user_answer": "故意错",
                 "duration_ms": 1800, "started_at": started + 3200},
            ],
            "duration_sec": 10,  # 满足防刷最低时长
        })
        assert r.status_code == 200, r.text
        body = r.json()

        # 前端回显：每题 duration_ms 透传
        by_q = {res["question_id"]: res for res in body["results"]}
        assert by_q[q1_id]["duration_ms"] == 3200
        assert by_q[q2_id]["duration_ms"] == 1800

        # 跨会话核对：attempt_answers 确实落库了计时字段（在清理前验证）
        db2 = SessionLocal()
        try:
            aas = db2.query(AttemptAnswer).filter(
                AttemptAnswer.question_id.in_([q1_id, q2_id])).all()
            assert len(aas) == 2
            m = {a.question_id: a for a in aas}
            assert m[q1_id].duration_ms == 3200
            assert m[q1_id].seq == 1
            assert m[q1_id].started_at is not None
            assert m[q2_id].duration_ms == 1800
            assert m[q2_id].seq == 2
            assert m[q2_id].started_at is not None
        finally:
            db2.close()
    finally:
        _cleanup(db, rec_id, [q1_id, q2_id])
        db.close()


def test_s2_m3_missing_timing_defaults_zero(client):
    """旧前端不上报计时字段时，duration_ms 默认为 0（未采集），接口不报错。"""
    db = SessionLocal()
    rec = ExamRecord(subject="数学", title="S2M3无计时卷", grade=6,
                     difficulty="综合", question_count=1)
    db.add(rec)
    db.flush()
    q = Question(exam_id=rec.id, seq=1, subject="数学",
                 question="3+3=?", answer="6")
    db.add(q)
    db.commit()
    rec_id, q_id = rec.id, q.id
    try:
        r = client.post("/api/exam/submit-answers", json={
            "user_id": "S2M3无计时生",
            "exam_id": rec_id,
            "answers": [{"question_id": q_id, "user_answer": "6"}],
            "duration_sec": 10,
        })
        assert r.status_code == 200, r.text

        # 跨会话核对：未上报计时 → duration_ms=0、started_at=None、seq=1
        db2 = SessionLocal()
        try:
            aas = db2.query(AttemptAnswer).filter_by(question_id=q_id).all()
            assert len(aas) == 1
            assert aas[0].duration_ms == 0
            assert aas[0].started_at is None
            assert aas[0].seq == 1
        finally:
            db2.close()
    finally:
        _cleanup(db, rec_id, [q_id])
        db.close()
