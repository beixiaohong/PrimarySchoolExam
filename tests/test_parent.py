"""家长功能：密码设置/解锁 + X-Parent-Pwd 守卫 + 试卷题数配置"""

UID = "家长测试生"
PWD = "9966"
HINT_Q = "孩子最爱吃的零食是？"
HINT_A = "薯片"


def _setup(client):
    r = client.post("/api/parent/setup", json={
        "user_id": UID, "password": PWD,
        "hint_question": HINT_Q, "hint_answer": HINT_A,
    })
    assert r.status_code == 200, r.text


def test_status_before_setup(client):
    r = client.get("/api/parent/status", params={"user_id": "未设置用户"})
    assert r.status_code == 200
    assert r.json()["has_password"] is False


def test_guard_rejects_without_password(client):
    """未设置家长密码时敏感接口直接 403"""
    r = client.post("/api/parent/exam-settings", json={
        "user_id": "未设置用户", "math_min": 8,
    })
    assert r.status_code == 403


def test_setup_and_unlock(client):
    _setup(client)
    r = client.get("/api/parent/status", params={"user_id": UID})
    assert r.json()["has_password"] is True
    assert r.json()["hint_question"] == HINT_Q

    # 解锁：错误密码 403，正确密码通过
    r = client.post("/api/parent/unlock",
                    json={"user_id": UID, "password": "0000"})
    assert r.status_code == 403
    r = client.post("/api/parent/unlock",
                    json={"user_id": UID, "password": PWD})
    assert r.status_code == 200


def test_exam_settings_guard(client):
    """试卷题数下限配置：缺头/错头 403，正确头写入成功"""
    _setup_idempotent(client)
    payload = {"user_id": UID, "math_min": 8, "chi_min": 6,
               "eng_min": 7, "difficulty_min": "提高"}

    r = client.post("/api/parent/exam-settings", json=payload)
    assert r.status_code == 403

    r = client.post("/api/parent/exam-settings", json=payload,
                    headers={"X-Parent-Pwd": "0000"})
    assert r.status_code == 403

    r = client.post("/api/parent/exam-settings", json=payload,
                    headers={"X-Parent-Pwd": PWD})
    assert r.status_code == 200, r.text
    assert r.json()["math_min"] == 8
    assert r.json()["difficulty_min"] == "提高"

    # 读回
    r = client.get("/api/parent/exam-settings", params={"user_id": UID})
    assert r.json()["math_min"] == 8
    assert r.json()["eng_min"] == 7


def test_message_flow(client):
    """家长留言 → 孩子查看未读 → 标记已读"""
    r = client.post("/api/parent/message",
                    json={"user_id": UID, "content": "今天也要加油！"})
    assert r.status_code == 200

    r = client.get("/api/parent/messages", params={"user_id": UID})
    assert r.status_code == 200
    body = r.json()
    assert body["unread"] >= 1
    assert any("加油" in m["content"] for m in body["messages"])

    r = client.post("/api/parent/messages/read", json={"user_id": UID})
    assert r.status_code == 200
    r = client.get("/api/parent/messages", params={"user_id": UID})
    assert r.json()["unread"] == 0


def _setup_idempotent(client):
    """已设置过则跳过（测试间共享同一用户）"""
    r = client.get("/api/parent/status", params={"user_id": UID})
    if not r.json()["has_password"]:
        _setup(client)
