"""作文批改与简答判分测试（mock AI 调用，验证评分卡结构/落库/简答分档）"""
import json

import pytest

from app.database import SessionLocal
from app.models.essay import EssayGrade


ESSAY_JSON = json.dumps({
    "total": 24, "dims": {"内容": 8, "结构": 6, "语言": 6, "卷面": 4},
    "highlights": ["比喻生动", "首尾呼应"],
    "improvements": ["可补充具体事例", "个别错别字需改正"],
    "upgraded": "春风轻抚，柳枝如碧玉垂落。",
})

SHORT_JSON = json.dumps({
    "points": [
        {"point": "点明时间", "score": 2, "comment": "完整"},
        {"point": "写出景物", "score": 1, "comment": "部分"},
    ],
    "total": 3, "comment": "整体不错",
})


@pytest.fixture
def mock_ai(monkeypatch):
    calls = {}

    def fake(user_id, system, user, max_tokens=800, history=None):
        # 根据 system 内容区分作文/简答（简化：用 max_tokens 难以区分，这里返回作文结构）
        text = ESSAY_JSON if "作文批改" in system else SHORT_JSON
        calls.setdefault("n", 0)
        calls["n"] += 1
        return {"text": text, "prompt_tokens": 12, "completion_tokens": 30}

    monkeypatch.setattr("app.services.ai.chat_for", fake)
    return calls


def test_grade_essay_card_and_persist(client, mock_ai):
    r = client.post("/api/ai/grade-essay", json={
        "user_id": "e1", "subject": "语文", "grade": 8, "topic": "春天",
        "content": "春天的风轻轻吹过，柳树发芽了。",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stage"] == "初中"
    assert d["max_score"] == 50
    card = d["card"]
    assert card["total"] == 24
    assert set(card["dims"].keys()) == {"内容", "结构", "语言", "卷面"}
    assert len(card["highlights"]) == 2
    assert len(card["improvements"]) == 2
    # 落库可回看
    db = SessionLocal()
    try:
        rows = db.query(EssayGrade).filter_by(user_id="e1").all()
        assert len(rows) == 1
        assert json.loads(rows[0].score_json)["total"] == 24
    finally:
        db.close()


def test_grade_essay_primary_scale(client, mock_ai):
    r = client.post("/api/ai/grade-essay", json={
        "user_id": "e2", "subject": "英语", "grade": 5,
        "content": "My weekend was fun.",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["stage"] == "小学"
    assert d["max_score"] == 15


def test_grade_essay_rate_limit(client, mock_ai):
    for _ in range(3):
        r = client.post("/api/ai/grade-essay", json={
            "user_id": "e3", "subject": "语文", "grade": 6, "content": "x"})
        assert r.status_code == 200
    # 第 4 次应被限频
    r4 = client.post("/api/ai/grade-essay", json={
        "user_id": "e3", "subject": "语文", "grade": 6, "content": "x"})
    assert r4.status_code == 429


def test_grade_essay_invalid_length(client, mock_ai):
    r = client.post("/api/ai/grade-essay", json={
        "user_id": "e4", "subject": "语文", "grade": 6,
        "content": "x" * 801})
    assert r.status_code == 400


def test_grade_short_answer(client, mock_ai):
    r = client.post("/api/ai/grade-short-answer", json={
        "user_id": "s1", "question": "描写春天",
        "reference_points": ["点明时间", "写出景物"],
        "user_answer": "春天来了，花开了。",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["max_score"] == 4
    assert d["total"] == 3
    assert len(d["points"]) == 2
    assert d["points"][0]["score"] == 2
