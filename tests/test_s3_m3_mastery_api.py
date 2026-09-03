"""S3-M3 验证：掌握度用户端接口（07 §4.3）

覆盖 GET /api/mastery/overview、/heatmap、/kp/{kp_id}、POST /recompute：
- overview 按学科聚合正确；
- heatmap 返回 学科×知识点 结构；
- kp 单点详情 + 缺失返回 exists=False；
- recompute 端点 200 且返回 recomputed_kps（无数据时为 0）；
- recompute 经 monkeypatch 注入作答后真正 UPSERT mastery_records（写路径）。

读取类用例直接 seed mastery_records（无 FK 负担）；recompute 写路径用 monkeypatch 注入
build_answer_records，避免 ExamRecord→Question→ExamAttempt→AttemptAnswer 长 FK 链。
计算正确性本身已由 test_s3_m2_mastery_algo.py 单测覆盖。
"""
from datetime import datetime

from app.database import SessionLocal
from app.domains.engine.services import mastery_store
from app.domains.engine.services.mastery import AnswerRecord
from app.models.knowledge import KnowledgePoint
from app.models.mastery import MasteryRecord


def _seed_recs(db, user_id="test_auth_uid"):
    db.query(MasteryRecord).filter_by(user_id=user_id).delete()
    db.query(KnowledgePoint).filter(KnowledgePoint.id.in_([72001, 72002, 72003])).delete()
    db.commit()
    db.add(KnowledgePoint(id=72001, subject="数学", grade=7, unit="", title="加法(s3)",
                          parent_id=0, status="active", textbook_ver=""))
    db.add(KnowledgePoint(id=72002, subject="数学", grade=7, unit="", title="减法(s3)",
                          parent_id=0, status="active", textbook_ver=""))
    db.add(KnowledgePoint(id=72003, subject="英语", grade=7, unit="", title="时态(s3)",
                          parent_id=0, status="active", textbook_ver=""))
    db.commit()
    db.add(MasteryRecord(user_id=user_id, kp_id=72001, subject="数学", grade=7, mastery=85,
                        level="已掌握", answer_count=5, correct_count=5, correct_rate=1.0,
                        avg_duration_ms=9000, last_answer_at=datetime.now(), correct_streak=5,
                        confidence=0.8, algo_version="v1"))
    db.add(MasteryRecord(user_id=user_id, kp_id=72002, subject="数学", grade=7, mastery=50,
                        level="薄弱", answer_count=3, correct_count=1, correct_rate=0.33,
                        avg_duration_ms=9000, last_answer_at=datetime.now(), correct_streak=0,
                        confidence=0.3, algo_version="v1"))
    db.add(MasteryRecord(user_id=user_id, kp_id=72003, subject="英语", grade=7, mastery=30,
                        level="未掌握", answer_count=2, correct_count=0, correct_rate=0.0,
                        avg_duration_ms=0, last_answer_at=datetime.now(), correct_streak=0,
                        confidence=0.1, algo_version="v1"))
    db.commit()


def _cleanup(db, user_id="test_auth_uid"):
    db.query(MasteryRecord).filter_by(user_id=user_id).delete()
    db.query(KnowledgePoint).filter(KnowledgePoint.id.in_([72001, 72002, 72003])).delete()
    db.commit()


def test_s3_m3_overview_aggregates(client):
    db = SessionLocal()
    _seed_recs(db)
    try:
        r = client.get("/api/mastery/overview")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["overall"]["total"] == 3
        assert data["overall"]["mastered"] == 1
        assert data["overall"]["weak"] == 1
        assert data["overall"]["unknown"] == 1
        assert "数学" in data["subjects"] and data["subjects"]["数学"]["total"] == 2
        assert data["subjects"]["数学"]["avg_mastery"] == 68  # round((85+50)/2)=68
    finally:
        _cleanup(db)
        db.close()


def test_s3_m3_heatmap_structure(client):
    db = SessionLocal()
    _seed_recs(db)
    try:
        r = client.get("/api/mastery/heatmap")
        assert r.status_code == 200, r.text
        hm = r.json()
        assert "数学" in hm["subjects"] and "英语" in hm["subjects"]
        maths = {row["kp_id"]: row for row in hm["subjects"]["数学"]}
        assert maths[72001]["mastery"] == 85 and maths[72001]["level"] == "已掌握"
    finally:
        _cleanup(db)
        db.close()


def test_s3_m3_kp_detail_and_missing(client):
    db = SessionLocal()
    _seed_recs(db)
    try:
        r = client.get("/api/mastery/kp/72001")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["exists"] is True
        assert d["mastery"] == 85 and d["level"] == "已掌握"
        assert d["subject"] == "数学" and d["title"] == "加法(s3)"
        assert "basis" in d

        r2 = client.get("/api/mastery/kp/999999")
        assert r2.status_code == 200, r2.text
        assert r2.json()["exists"] is False
    finally:
        _cleanup(db)
        db.close()


def test_s3_m3_recompute_endpoint_ok(client):
    """端点 200，返回 recomputed_kps（int，无真实作答时为 0）。"""
    r = client.post("/api/mastery/recompute")
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["recomputed_kps"], int)
    assert d["algo_version"]


def test_s3_m3_recompute_writes_records(client, monkeypatch):
    """monkeypatch 注入作答后，recompute_user_mastery 真正 UPSERT mastery_records。"""
    db = SessionLocal()
    db.query(MasteryRecord).filter_by(user_id="s3m3_u").delete()
    db.query(KnowledgePoint).filter_by(id=71001).delete()
    db.commit()
    db.add(KnowledgePoint(id=71001, subject="数学", grade=7, unit="", title="加法(s3m3)",
                          parent_id=0, status="active", textbook_ver=""))
    db.commit()
    kp_id = 71001

    def fake_build(db, user_id, limit=1000):
        return {kp_id: [
            AnswerRecord(answered_at=datetime(2026, 9, 1), is_correct=True,
                         duration_ms=10000, difficulty=4, kp_id=kp_id),
            AnswerRecord(answered_at=datetime(2026, 9, 2), is_correct=True,
                         duration_ms=8000, difficulty=4, kp_id=kp_id),
        ]}

    monkeypatch.setattr(mastery_store, "build_answer_records", fake_build)
    try:
        n = mastery_store.recompute_user_mastery(db, "s3m3_u")
        assert n == 1
        mr = db.query(MasteryRecord).filter_by(
            user_id="s3m3_u", kp_id=kp_id).first()
        assert mr is not None
        assert mr.mastery >= 70          # 全对近期 → 基本掌握及以上
        assert mr.level in ("基本掌握", "已掌握")
        assert mr.subject == "数学"      # 学科冗余回填
        assert mr.confidence > 0
    finally:
        db.query(MasteryRecord).filter_by(user_id="s3m3_u").delete()
        db.query(KnowledgePoint).filter_by(id=kp_id).delete()
        db.commit()
        db.close()
