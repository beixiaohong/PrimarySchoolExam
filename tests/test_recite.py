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


def test_review_carries_over_when_not_reviewed(client):
    """需求1回归：背诵中心当日没复习的词，次日继续出现在复习队列（不会被丢弃/提前推出）。

    机制：复习只在真正提交 /review 时才推进 next_review_date；
    选取条件是 next_review_date <= today（含逾期），故未复习的词会一直滞留。
    """
    from datetime import date, timedelta
    from app.database import SessionLocal
    from app.models.word import Word, WordBook
    from app.models.vocab import VocabProgress

    uid = "复习跨天生"
    _set_quota(client, uid, "daily_new_words", 2)

    db = SessionLocal()
    try:
        # 造一本 6 年级词库与一个单词（落在 career 池内）
        book = WordBook(grade=6, semester="上", name="跨天回归册", word_count=1)
        db.add(book)
        db.flush()
        w = Word(book_id=book.id, word="carryover", phonetic="/k/",
                 pos="v.", meaning="延续", unit="U1", difficulty=1)
        db.add(w)
        db.flush()
        # 该词本应在昨天复习（已逾期），且今天一直没复习
        prog = VocabProgress(
            user_id=uid, word_id=w.id, status="learning", review_stage=1,
            first_learn_date=date.today() - timedelta(days=5),
            last_review_date=date.today() - timedelta(days=5),
            next_review_date=date.today() - timedelta(days=1),  # 昨天到期未复习
            correct_count=2, total_reviews=2,
        )
        db.add(prog)
        db.commit()

        # 今天拉取 → 逾期词必须出现在复习队列（证明从昨天延续到今天）
        r = client.get("/api/vocab/today", params={"user_id": uid})
        assert r.status_code == 200, r.text
        review_ids = [x["word_id"] for x in r.json()["review_words"]]
        assert w.id in review_ids, "逾期未复习的词应从到期日延续到今日复习队列"
        # 再次拉取（不提交复习）→ 仍在队列，没有被消费掉
        r2 = client.get("/api/vocab/today", params={"user_id": uid})
        assert w.id in [x["word_id"] for x in r2.json()["review_words"]]
    finally:
        db.query(VocabProgress).filter_by(user_id=uid).delete()
        db.query(Word).filter_by(word="carryover").delete()
        db.query(WordBook).filter_by(name="跨天回归册").delete()
        db.commit()
        db.close()


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
    # 同一词的 4 题题干不得完全相同（默写/理解混合）
    for wid in word_ids:
        qs = [it["question"] for it in items if it["word_id"] == wid]
        assert len(set(qs)) > 1, "同词 4 题题干不应完全一样"


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
