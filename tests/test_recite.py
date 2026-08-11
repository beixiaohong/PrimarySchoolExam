"""背诵中心：取消每日上限（多轮） + session-quiz 理解型出题"""

PARENT_PWD = "8888"


def _ensure_parent_pwd(client, uid):
    r = client.get("/api/parent/status", params={"user_id": uid})
    if not r.json()["has_password"]:
        r = client.post("/api/parent/setup", json={
            "user_id": uid, "password": PARENT_PWD,
            "hint_question": "测试密保？", "hint_answer": "测试答案",
        })
        assert r.status_code == 200


def _set_quota(client, uid, key, val):
    _ensure_parent_pwd(client, uid)
    r = client.post("/api/tasks/settings", json={
        "user_id": uid, "settings": {"quotas": {key: val}},
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text


def test_vocab_multi_round_no_daily_cap(client):
    """背单词不设每日轮数：学满一轮额度后 /today 仍返回下一批新词"""
    uid = "多轮单词生"
    _set_quota(client, uid, "daily_new_words", 3)

    # 第一轮：按额度返回 3 个新词，剩余额度恒等于额度
    r = client.get("/api/vocab/today", params={"user_id": uid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"]["new_remaining"] == 3
    first = [w["word_id"] for w in body["new_words"]]
    assert len(first) == 3

    # 学完这一轮
    r = client.post("/api/vocab/learn", json={"user_id": uid, "word_ids": first})
    assert r.status_code == 200, r.text

    # 第二轮：仍返回 3 个新词，且是下一批（不与第一轮重复）
    r = client.get("/api/vocab/today", params={"user_id": uid})
    body = r.json()
    assert body["stats"]["new_remaining"] == 3
    second = [w["word_id"] for w in body["new_words"]]
    assert len(second) == 3
    assert set(second).isdisjoint(set(first)), "第二轮应是未学过的下一批新词"


def test_classical_multi_round_no_daily_cap(client):
    """背古诗文不设每日轮数：背满一轮额度后 /today 仍返回下一批篇目"""
    uid = "多轮古诗生"
    _set_quota(client, uid, "daily_new_texts", 2)

    r = client.get("/api/classical/today", params={"user_id": uid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"]["new_remaining"] == 2
    first = [t["text_id"] for t in body["new_texts"]]
    assert len(first) == 2

    r = client.post("/api/classical/learn", json={"user_id": uid, "text_ids": first})
    assert r.status_code == 200, r.text

    r = client.get("/api/classical/today", params={"user_id": uid})
    body = r.json()
    assert body["stats"]["new_remaining"] == 2
    second = [t["text_id"] for t in body["new_texts"]]
    assert len(second) == 2
    assert set(second).isdisjoint(set(first)), "第二轮应是未背过的下一批篇目"


def test_vocab_session_quiz_count(client):
    """单词 session-quiz：新学模式每词 4 题，每题有答案，选择题带选项"""
    uid = "单词检测生"
    r = client.get("/api/vocab/today", params={"user_id": uid})
    words = r.json()["new_words"]
    assert words, "种子数据应含六年级单词"
    word_ids = [w["word_id"] for w in words[:2]]

    r = client.get("/api/vocab/session-quiz", params={
        "user_id": uid, "word_ids": ",".join(map(str, word_ids)),
        "mode": "new", "grade": 6,
    })
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 4 * len(word_ids), "每词应出 4 题"
    for it in items:
        assert it.get("question")
        assert it.get("answer") not in (None, "")
        if it.get("options"):
            # 选择题：正确答案必须在选项内
            assert it["answer"] in it["options"]


def test_classical_session_quiz_count(client):
    """古诗文 session-quiz：新学模式每篇至多 3 题，每题有答案"""
    uid = "古诗检测生"
    r = client.get("/api/classical/today", params={"user_id": uid})
    texts = r.json()["new_texts"]
    assert texts, "种子数据应含古诗文篇目"
    text_ids = [t["text_id"] for t in texts[:2]]

    r = client.get("/api/classical/session-quiz", params={
        "user_id": uid, "text_ids": ",".join(map(str, text_ids)), "mode": "new",
    })
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "应能生成检测题"
    # 每篇不超过 3 题，总数不超过 3 * 篇数
    assert len(items) <= 3 * len(text_ids)
    for it in items:
        assert it.get("question")
        assert it.get("answer") not in (None, "")
        if it.get("options"):
            assert it["answer"] in it["options"]


def test_vocab_session_quiz_empty_ids_rejected(client):
    uid = "单词检测生"
    r = client.get("/api/vocab/session-quiz", params={
        "user_id": uid, "word_ids": "", "mode": "new",
    })
    assert r.status_code == 400
    r = client.get("/api/classical/session-quiz", params={
        "user_id": uid, "text_ids": "", "mode": "new",
    })
    assert r.status_code == 400
