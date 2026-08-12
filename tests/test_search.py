"""搜题 API 测试：题库命中 / AI 降级 / 缓存命中 / 限频 / 错题本去重 / 历史

AI 调用一律 mock（不依赖真实 API key），符合 task-607 第 9 节验收要求。
"""
import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.exam import ExamRecord, Question


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_question(db, text, subject="数学", answer="300"):
    exam = ExamRecord(user_id="seed", subject=subject, title="测试卷",
                      grade=6, question_count=1)
    db.add(exam)
    db.flush()
    q = Question(exam_id=exam.id, seq=1, subject=subject, question=text,
                  answer=answer, options_json="[]")
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def _mock_ai(monkeypatch, text="【思路】先算速度和…【解答】300千米【举一反三】类似题"):
    calls = {"n": 0}

    def fake_chat(user_id, system, user, max_tokens=800, history=None):
        calls["n"] += 1
        return {"text": text, "provider": "zhipu", "model": "glm-4.7",
                "prompt_tokens": 10, "completion_tokens": 20}

    import app.services.ai as ai_svc
    monkeypatch.setattr(ai_svc, "chat_for", fake_chat)
    return calls


def test_ask_library_hit(client, db_session):
    q = _add_question(
        db_session,
        "甲乙两车同时从两地相向而行，甲车每小时行60千米，乙车每小时行40千米，3小时相遇。两地相距多少千米？",
        answer="300",
    )
    resp = client.post("/api/search/ask", json={
        "user_id": "u1",
        "question_text": "甲乙两车同时从两地相向而行，甲车每小时行60千米，乙车每小时行40千米，3小时相遇。两地相距多少千米？",
        "subject": "数学",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["hit"] is True
    assert data["question_id"] == q.id
    assert data["answer"] == "300"
    assert data["diamond_cost"] == 0


def test_ask_ai_fallback_and_cache(client, monkeypatch):
    calls = _mock_ai(monkeypatch)
    body = {
        "user_id": "u2",
        "question_text": "一个水池有进水管和出水管，单开进水管6小时注满，单开出水管10小时放完，同时开两管几小时注满？",
    }
    r1 = client.post("/api/search/ask", json=body)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["hit"] is False
    assert d1["cached"] is False
    assert "思路" in d1["ai_text"]
    assert d1["diamond_cost"] >= 0
    assert calls["n"] == 1

    # 二次相同题 → 缓存命中，不再调用 AI
    r2 = client.post("/api/search/ask", json=body)
    assert r2.status_code == 200
    assert r2.json()["cached"] is True
    assert calls["n"] == 1


def test_ask_force_ai_skips_library(client, db_session, monkeypatch):
    calls = _mock_ai(monkeypatch)
    q = _add_question(
        db_session,
        "直角三角形两条直角边分别为3和4，斜边是多少？",
        answer="5",
    )
    # 普通搜索应命中题库
    r0 = client.post("/api/search/ask", json={
        "user_id": "u_force", "question_text": "直角三角形两条直角边分别为3和4，斜边是多少？",
        "subject": "数学",
    })
    assert r0.json()["hit"] is True

    # force_ai 应跳过题库命中，走 AI 讲解
    r1 = client.post("/api/search/ask", json={
        "user_id": "u_force", "question_text": "直角三角形两条直角边分别为3和4，斜边是多少？",
        "subject": "数学", "force_ai": True,
    })
    assert r1.status_code == 200
    assert r1.json()["hit"] is False
    assert calls["n"] == 1


def test_ask_rate_limit(client, monkeypatch):
    _mock_ai(monkeypatch)
    uid = "rate_user"
    text = "一个关于行程问题的独特题目XYZ123，求甲的速度？"
    statuses = []
    for _ in range(6):
        r = client.post("/api/search/ask", json={"user_id": uid, "question_text": text})
        statuses.append(r.status_code)
    # 限频 5 次/分钟：前 5 次 200，第 6 次 400
    assert statuses.count(400) >= 1


def test_to_wrong_dedup(client):
    body = {"user_id": "u3", "question": "某题题干X去重测试", "answer": "42",
            "explanation": "解析内容"}
    r1 = client.post("/api/search/to-wrong", json=body)
    assert r1.status_code == 200
    assert r1.json()["added"] is True
    r2 = client.post("/api/search/to-wrong", json=body)
    assert r2.status_code == 200
    assert r2.json()["added"] is False


def test_history(client, monkeypatch):
    _mock_ai(monkeypatch)
    client.post("/api/search/ask", json={
        "user_id": "u4", "question_text": "唯一题目ABC用于历史回看测试",
    })
    r = client.get("/api/search/history", params={"user_id": "u4"})
    assert r.status_code == 200
    items = r.json()
    assert any("唯一题目ABC用于历史回看测试" in it["question"] for it in items)
