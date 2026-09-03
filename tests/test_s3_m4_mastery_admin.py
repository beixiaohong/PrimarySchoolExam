"""S3-M4：后台掌握度查询接口（/api/admin/mastery/*，07 §4.3）

验收：mastery:view_all 查任意用户矩阵、content:view 查覆盖率报表；无 token → 401。
"""
import pytest
from datetime import datetime

from app.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.models.mastery import MasteryRecord

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _seed(db, user_id="s3m4_u"):
    db.query(MasteryRecord).filter_by(user_id=user_id).delete()
    db.query(KnowledgePoint).filter(KnowledgePoint.id.in_([73001, 73002])).delete()
    db.commit()
    db.add(KnowledgePoint(id=73001, subject="数学", grade=7, unit="", title="加法(m4)",
                          parent_id=0, status="active", textbook_ver=""))
    db.add(KnowledgePoint(id=73002, subject="英语", grade=7, unit="", title="时态(m4)",
                          parent_id=0, status="active", textbook_ver=""))
    db.commit()
    db.add(MasteryRecord(user_id=user_id, kp_id=73001, subject="数学", grade=7, mastery=80,
                        level="已掌握", answer_count=4, correct_count=4, correct_rate=1.0,
                        avg_duration_ms=9000, last_answer_at=datetime.now(), correct_streak=4,
                        confidence=0.7, algo_version="v1"))
    db.add(MasteryRecord(user_id=user_id, kp_id=73002, subject="英语", grade=7, mastery=40,
                        level="薄弱", answer_count=2, correct_count=1, correct_rate=0.5,
                        avg_duration_ms=9000, last_answer_at=datetime.now(), correct_streak=0,
                        confidence=0.2, algo_version="v1"))
    db.commit()


def _cleanup(db, user_id="s3m4_u"):
    db.query(MasteryRecord).filter_by(user_id=user_id).delete()
    db.query(KnowledgePoint).filter(KnowledgePoint.id.in_([73001, 73002])).delete()
    db.commit()


def test_s3_m4_mastery_user_matrix(client, admin_token):
    db = SessionLocal()
    _seed(db)
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = client.get("/api/admin/mastery/users/s3m4_u", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user_id"] == "s3m4_u"
        assert d["overall"]["total"] == 2
        assert d["overall"]["mastered"] == 1
        assert "数学" in d["subjects"] and "英语" in d["subjects"]
        assert d["subjects"]["数学"][0]["kp_id"] == 73001
    finally:
        _cleanup(db)
        db.close()


def test_s3_m4_mastery_coverage(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/admin/mastery/coverage", headers=headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "total_kp" in d and "annotated_kp" in d
    assert "coverage" in d and "by_subject" in d
    assert isinstance(d["total_kp"], int)
    assert 0.0 <= d["coverage"] <= 1.0


def test_s3_m4_no_token_401(client):
    r = client.get("/api/admin/mastery/coverage")
    assert r.status_code in (401, 403), r.text
    r2 = client.get("/api/admin/mastery/users/anyone")
    assert r2.status_code in (401, 403), r2.text
