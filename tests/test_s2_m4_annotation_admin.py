"""S2-M4：后台知识点标注工作台接口（/api/admin/content/*）。

验收：7 个接口在管理员鉴权下可用，且经 content.contracts 触达标注服务；
标注写接口落库可被跨会话核对。
"""

import pytest

from app.database import SessionLocal
from app.models.exam import ExamRecord, Question, ExamAttempt, AttemptAnswer
from app.models.knowledge import KnowledgePoint
from app.models.kp_map import QuestionKpMap

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


_MARK = "__S2M4__"


def _seed(db):
    rec = ExamRecord(subject="数学", title=f"{_MARK}卷", grade=7,
                     difficulty="综合", question_count=1)
    db.add(rec)
    db.flush()
    q = Question(exam_id=rec.id, seq=1, subject="数学",
                 question=f"{_MARK}1+1=?", answer="2")
    db.add(q)
    db.flush()
    kp = KnowledgePoint(subject="数学", grade=7, unit=f"{_MARK}U",
                        title=f"{_MARK}知识点", parent_id=0, code=f"{_MARK}")
    db.add(kp)
    db.commit()
    return rec.id, q.id, kp.id


def _cleanup(db, rec_id, q_id, kp_id):
    db.query(QuestionKpMap).filter_by(question_id=q_id).delete(
        synchronize_session=False)
    db.query(Question).filter(Question.exam_id == rec_id).delete(
        synchronize_session=False)
    db.query(ExamAttempt).filter(ExamAttempt.exam_id == rec_id).delete(
        synchronize_session=False)
    db.query(ExamRecord).filter(ExamRecord.id == rec_id).delete(
        synchronize_session=False)
    db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).delete(
        synchronize_session=False)
    db.commit()


def test_m4_kp_tree_and_create(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    # 新增知识点
    r = client.post("/api/admin/content/kp", headers=h, json={
        "subject": "数学", "grade": 7, "unit": "M4单元",
        "title": "M4树知识点", "summary": "s",
    })
    assert r.status_code == 200, r.text
    kp_id = r.json()["id"]
    assert kp_id > 0
    # 知识点树可查
    r = client.get("/api/admin/content/kp/tree", headers=h,
                   params={"subject": "数学"})
    assert r.status_code == 200, r.text
    tree = r.json()["tree"]
    assert isinstance(tree, list)
    assert any(t["id"] == kp_id for t in tree)


def test_m4_annotation_queue_and_submit(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    db = SessionLocal()
    rec_id, q_id, kp_id = _seed(db)
    try:
        # 队列含该未标注题（按页遍历确认成员，规避 100 封顶）
        found = False
        page = 1
        while True:
            r = client.get("/api/admin/content/annotation/queue", headers=h,
                           params={"source_table": "questions", "page": page,
                                   "page_size": 100})
            assert r.status_code == 200, r.text
            body = r.json()
            if any(i["question_id"] == q_id for i in body["items"]):
                found = True
                break
            if page * 100 >= body["total"]:
                break
            page += 1
        assert found, f"未标注题 q_id={q_id} 未出现在队列"

        # 提交标注
        r = client.post("/api/admin/content/annotation", headers=h, json={
            "source_table": "questions", "question_id": q_id,
            "kp_ids": [kp_id],
        })
        assert r.status_code == 200, r.text
        assert r.json()["added"] >= 1

        # 跨会话核对：question_kp_map 落库
        db2 = SessionLocal()
        try:
            maps = db2.query(QuestionKpMap).filter_by(question_id=q_id).all()
            assert len(maps) >= 1
            assert any(m.kp_id == kp_id for m in maps)
        finally:
            db2.close()
    finally:
        _cleanup(db, rec_id, q_id, kp_id)
        db.close()


def test_m4_annotation_stats_and_import(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    db = SessionLocal()
    rec_id, q_id, kp_id = _seed(db)
    try:
        # 批量导入标注
        rows = [{
            "source_table": "questions", "question_id": q_id,
            "kp_id": kp_id, "is_primary": 1, "weight": 1.0,
        }]
        r = client.post("/api/admin/content/annotation/import", headers=h,
                        json={"rows": rows})
        assert r.status_code == 200, r.text
        assert r.json()["added"] >= 1

        # 统计：标注数 >= 1
        r = client.get("/api/admin/content/annotation/stats", headers=h,
                       params={"source_table": "questions"})
        assert r.status_code == 200, r.text
        stats = r.json()
        assert stats["annotated"] >= 1
        assert stats["coverage"] > 0
    finally:
        _cleanup(db, rec_id, q_id, kp_id)
        db.close()


def test_m4_ai_predict_returns_list(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    # AI 关闭时返回空列表（不报错）；开启时返回建议
    r = client.post("/api/admin/content/annotation/ai-predict", headers=h,
                    json={"question_text": "计算 12 乘以 8 的结果"})
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["predictions"], list)


def test_m4_requires_admin_token(client):
    # 无 token → 401
    r = client.get("/api/admin/content/kp/tree")
    assert r.status_code == 401
