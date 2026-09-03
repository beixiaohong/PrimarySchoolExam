"""阅读理解专项 + 多 AI 校对测试（mock AI，验证抽篇/判分/审核队列）

- 抽篇：按年级返回篇目，下发时隐藏答案与参考要点
- 客观题即时判分（支持字母/文本）
- 主观题走 AI 判分（ratio → 得分）
- 管理后台多 AI 校对：run → conflict 队列 → 人工 resolve
"""
import json

import pytest

from app.database import SessionLocal
from app.models.reading import ReadingPassage
from app.models.middle import MiddleQuestion

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"


PASSAGE = {
    "subject": "英语",
    "grade": 7,
    "semester": "全",
    "title": "M3 Test Passage",
    "passage": "This is a test passage for reading.",
    "questions_json": json.dumps([
        {"type": "choice", "question": "Q1?", "options": ["A. x", "B. y", "C. z", "D. w"],
         "answer": "B. y", "points": [], "score": 5},
        {"type": "choice", "question": "Q2?", "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
         "answer": "C. 3", "points": [], "score": 5},
        {"type": "short", "question": "Q3?", "options": [],
         "answer": "参考要点答案", "points": ["要点1", "要点2"], "score": 10},
    ]),
    "review_status": "pending",
}


@pytest.fixture
def passage_id():
    db = SessionLocal()
    try:
        # 幂等：先清空同 学科+年级 的所有篇目（含种子行与上次运行残留），
        # 保证本次新建的篇目必然出现在抽篇结果内——接口按 id 升序取前 limit=5，
        # 若共享测试库残留 5+ 篇同年级篇目，新篇会被截断导致断言失败。
        db.query(ReadingPassage).filter(
            ReadingPassage.subject == PASSAGE["subject"],
            ReadingPassage.grade == PASSAGE["grade"],
        ).delete()
        p = ReadingPassage(**PASSAGE)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


@pytest.fixture
def mock_reading_ai(monkeypatch):
    calls = {}

    def fake(user_id, system, user, max_tokens=800, history=None):
        calls.setdefault("n", 0)
        calls["n"] += 1
        if "ratio" in system:
            return {"text": json.dumps({"ratio": 1.0, "comment": "完整覆盖要点"}),
                    "prompt_tokens": 10, "completion_tokens": 20, "model": "glm-4.7"}
        return {"text": "ok", "prompt_tokens": 10, "completion_tokens": 20, "model": "glm-4.7"}

    monkeypatch.setattr("app.domains.platform.services.ai.chat_for", fake)
    return calls


def test_reading_passages_hide_answer(client, passage_id):
    r = client.get("/api/reading/passages", params={"subject": "英语", "grade": 7})
    assert r.status_code == 200, r.text
    d = r.json()
    assert any(p["id"] == passage_id for p in d["passages"])
    p = next(p for p in d["passages"] if p["id"] == passage_id)
    assert "answer" not in p["questions"][0]
    assert "points" not in p["questions"][0]
    assert p["questions"][0]["options"] == ["A. x", "B. y", "C. z", "D. w"]


def test_reading_submit_correct(client, passage_id, mock_reading_ai):
    r = client.post("/api/reading/submit", json={
        "user_id": "r_u1", "passage_id": passage_id,
        "answers": [
            {"qid": 0, "user_answer": "B. y"},
            {"qid": 1, "user_answer": "C"},
            {"qid": 2, "user_answer": "学生完整作答，覆盖要点1和要点2。"},
        ],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["max_score"] == 20.0
    assert d["total_score"] == 20.0
    # 主观题按 ratio=1 得满分
    short = d["detail"][2]
    assert short["type"] == "short"
    assert short["earned"] == 10.0


def test_reading_submit_wrong_choice(client, passage_id, mock_reading_ai):
    r = client.post("/api/reading/submit", json={
        "user_id": "r_u2", "passage_id": passage_id,
        "answers": [
            {"qid": 0, "user_answer": "A"},
            {"qid": 1, "user_answer": "D. 4"},
            {"qid": 2, "user_answer": "部分作答"},
        ],
    })
    assert r.status_code == 200
    d = r.json()
    # 两道客观错 → 0；主观 ratio=1 → 10
    assert d["total_score"] == 10.0


def test_reading_submit_invalid_passage(client, mock_reading_ai):
    r = client.post("/api/reading/submit", json={
        "user_id": "r_u3", "passage_id": 999999,
        "answers": [{"qid": 0, "user_answer": "x"}]})
    assert r.status_code == 400


@pytest.fixture
def admin_token(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture
def pending_question_id():
    db = SessionLocal()
    try:
        q = MiddleQuestion(
            subject="物理", grade=8, type="choice",
            question="M3 review question?",
            options_json=json.dumps(["A. x", "B. y"]),
            answer="A. x", analysis="", unit="八年级上·机械运动",
            review_status="pending",
        )
        db.add(q)
        db.commit()
        db.refresh(q)
        return q.id
    finally:
        db.close()


def test_admin_reviews_run_conflict_resolve(client, admin_token, pending_question_id):
    h = {"Authorization": f"Bearer {admin_token}"}

    # mock 双供应商：zhipu 通过、relay 不通过 → 分歧 conflict
    def fake_chat(user_id, system, user, max_tokens=800, provider=None, history=None):
        verdict = "fail" if provider == "relay" else "pass"
        return {"text": json.dumps({"verdict": verdict, "comment": f"{provider}意见"}),
                "prompt_tokens": 8, "completion_tokens": 16, "model": "glm-4.7"}

    import app.domains.engine.services.review_service as rs
    import app.domains.platform.services.ai as ai_svc
    orig = ai_svc.chat_with
    ai_svc.chat_with = fake_chat
    try:
        r = client.post("/api/admin/reviews/run", json={"limit": 10}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reviewed"] >= 1
        assert body["conflict"] >= 1

        # 队列中应包含该条
        r2 = client.get("/api/admin/reviews", params={"status": "conflict"}, headers=h)
        assert r2.status_code == 200
        items = r2.json()["items"]
        assert any(it["content_id"] == pending_question_id for it in items)

        # 人工采纳
        r3 = client.post("/api/admin/reviews/resolve", json={
            "content_type": "middle_question", "content_id": pending_question_id,
            "verdict": "approved"}, headers=h)
        assert r3.status_code == 200
        assert r3.json()["review_status"] == "approved"
    finally:
        ai_svc.chat_with = orig
