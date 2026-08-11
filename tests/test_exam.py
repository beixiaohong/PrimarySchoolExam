"""试卷生成与在线做题：生成 Word → 题目入库 → 交卷判分 → 错题落库"""

USER = "试卷测试生"


def _seed_attempt(db, uid, subject, answered_correct, answered_wrong, blanks):
    """造一次交卷记录：answered_* 为实际作答题数，blanks 为空题数"""
    from app.models.exam import ExamRecord, Question, ExamAttempt, AttemptAnswer
    rec = ExamRecord(subject=subject, title=f"{uid}-{subject}", grade=6,
                     difficulty="综合", question_count=answered_correct + answered_wrong + blanks)
    db.add(rec)
    db.flush()
    qids = []
    for i in range(answered_correct + answered_wrong + blanks):
        q = Question(exam_id=rec.id, seq=i + 1, subject=subject,
                     type_code="calc_int_basic", type_name="整数四则运算",
                     question=f"题{i}", answer="42")
        db.add(q)
        db.flush()
        qids.append(q.id)
    attempt = ExamAttempt(user_id=uid, exam_id=rec.id, score=0,
                          total=len(qids), correct=answered_correct,
                          wrong=answered_wrong)
    db.add(attempt)
    db.flush()
    idx = 0
    for _ in range(answered_correct):
        db.add(AttemptAnswer(attempt_id=attempt.id, question_id=qids[idx],
                             user_answer="42", is_correct=True))
        idx += 1
    for _ in range(answered_wrong):
        db.add(AttemptAnswer(attempt_id=attempt.id, question_id=qids[idx],
                             user_answer="错", is_correct=False))
        idx += 1
    for _ in range(blanks):
        db.add(AttemptAnswer(attempt_id=attempt.id, question_id=qids[idx],
                             user_answer="", is_correct=False))
        idx += 1
    db.commit()
    return attempt.id


def test_auto_difficulty_tiers(client):
    """自动定档：按最近交卷平均分划档（>=80拔高/70-80提高/60-70综合/<60基础）"""
    from app.database import SessionLocal
    from app.routers.exam import _auto_difficulty
    db = SessionLocal()
    try:
        # 全对 → 拔高
        uid = "难度档拔高生"
        _seed_attempt(db, uid, "数学", 8, 0, 0)
        assert _auto_difficulty(db, uid, "数学") == "拔高"
        # 7 对 3 错 → 70 分 → 提高
        uid = "难度档提高生"
        _seed_attempt(db, uid, "数学", 7, 3, 0)
        assert _auto_difficulty(db, uid, "数学") == "提高"
        # 65 分 → 综合
        uid = "难度档综合生"
        _seed_attempt(db, uid, "数学", 13, 7, 0)
        assert _auto_difficulty(db, uid, "数学") == "综合"
        # 50 分 → 基础
        uid = "难度档基础生"
        _seed_attempt(db, uid, "数学", 5, 5, 0)
        assert _auto_difficulty(db, uid, "数学") == "基础"
        # 无任何记录 → 默认综合
        assert _auto_difficulty(db, "难度档无记录生", "数学") == "综合"
    finally:
        db.close()


def test_auto_difficulty_ignores_blanks(client):
    """平均分口径：去掉未作答的空题，不被空题拉低；整卷空题不计入平均"""
    from app.database import SessionLocal
    from app.routers.exam import _auto_difficulty
    db = SessionLocal()
    try:
        # 作答题全对但有大量空题：若空题计入会 40 分(基础)，正确口径应为 100 分(拔高)
        uid = "难度去空题生"
        _seed_attempt(db, uid, "数学", 2, 0, 3)
        assert _auto_difficulty(db, uid, "数学") == "拔高"
        # 整卷空题的记录不计入平均：另加一次全空卷，仍应只看有效那次
        _seed_attempt(db, uid, "数学", 0, 0, 5)
        assert _auto_difficulty(db, uid, "数学") == "拔高"
    finally:
        db.close()


def test_wrong_type_quota_distribution(client):
    """错题题型配额：按错题数占比分配 n30 题量，总数 == n30，仅限合法题型"""
    from app.routers.exam import _wrong_type_quotas
    wrong_counts = {"calc_int_basic": 3, "word_problem": 1}
    valid = ["calc_int_basic", "word_problem", "other_type"]
    quotas = _wrong_type_quotas(4, wrong_counts, valid)
    assert sum(quotas.values()) == 4
    assert set(quotas) <= set(valid)
    assert quotas.get("calc_int_basic", 0) >= quotas.get("word_problem", 0)
    # 非法题型被过滤
    quotas = _wrong_type_quotas(4, {"bad_type": 5}, valid)
    assert quotas == {}
    # n30 < 1 → 空
    assert _wrong_type_quotas(0, wrong_counts, valid) == {}


def test_generate_includes_wrong_types(client):
    """宽松断言：用户有未掌握错题时，生成卷里至少出现一道该错题题型"""
    from app.database import SessionLocal
    from app.models.exam import Question, WrongRecord
    uid = "错题题型分布生"
    # 先造一份卷 + 把某题标为错题（未掌握），题型 calc_int_basic
    exam_id = _generate_math_exam(client, count=3)
    qs = client.get(f"/api/exam/{exam_id}/questions").json()
    db = SessionLocal()
    try:
        for q in db.query(Question).filter(Question.exam_id == exam_id).all():
            q.type_code = "calc_int_basic"
            q.subject = "数学"
        db.commit()
        db.add(WrongRecord(user_id=uid, question_id=qs[0]["id"], is_mastered=False))
        db.commit()
    finally:
        db.close()
    # 生成 20 题卷：30% ≈ 6 题为错题题型，宽松断言至少出现 1 道
    r = client.post("/api/exam/generate", json={
        "subject": "数学", "grade": 6, "math_count": 20, "user_id": uid,
    })
    assert r.status_code == 200, r.text
    new_exam_id = int(r.headers["X-Exam-Id"])
    got = client.get(f"/api/exam/{new_exam_id}/questions").json()
    assert len(got) == 20
    types = {q.get("type_code") for q in got}
    assert "calc_int_basic" in types


def _generate_math_exam(client, count=5):
    r = client.post("/api/exam/generate", json={
        "subject": "数学", "grade": 6, "difficulty": "基础",
        "math_count": count, "user_id": USER,
    })
    assert r.status_code == 200, r.text
    exam_id = int(r.headers["X-Exam-Id"])
    assert exam_id > 0
    # Word 文档二进制流
    assert "wordprocessingml" in r.headers.get("content-type", "")
    return exam_id


def test_generate_math_exam(client):
    exam_id = _generate_math_exam(client)
    r = client.get(f"/api/exam/{exam_id}/questions")
    assert r.status_code == 200
    qs = r.json()
    assert len(qs) == 5
    assert all(q["answer"] for q in qs)


def test_submit_and_wrong_book(client):
    """交卷：一题答对一题答错 → 判分正确，错题自动入错题本"""
    exam_id = _generate_math_exam(client, count=2)
    qs = client.get(f"/api/exam/{exam_id}/questions").json()

    answers = [
        {"question_id": qs[0]["id"], "user_answer": qs[0]["answer"]},  # 答对
        {"question_id": qs[1]["id"], "user_answer": "故意答错的答案xyz"},  # 答错
    ]
    r = client.post("/api/exam/submit-answers", json={
        "user_id": USER, "exam_id": exam_id, "answers": answers,
        "duration_sec": 120,  # 满足防刷最低时长
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["correct"] == 1
    assert body["wrong"] == 1
    assert body["score"] == 50.0
    assert body["attempt_id"] > 0

    # 错题自动入本
    r = client.get("/api/exam/wrong/list", params={"user_id": USER})
    assert r.status_code == 200
    wrong = r.json()
    assert len(wrong) == 1
    assert wrong[0]["question_id"] == qs[1]["id"]

    # 做题记录可查（接口返回列表）
    r = client.get("/api/exam/attempts/list", params={"user_id": USER})
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_submit_too_fast_rejected(client):
    """防刷：答题时长过短被拒"""
    exam_id = _generate_math_exam(client, count=2)
    qs = client.get(f"/api/exam/{exam_id}/questions").json()
    r = client.post("/api/exam/submit-answers", json={
        "user_id": USER, "exam_id": exam_id,
        "answers": [{"question_id": qs[0]["id"], "user_answer": qs[0]["answer"]}],
        "duration_sec": 1,
    })
    assert r.status_code == 400


def test_mark_and_master_wrong(client):
    """手动标记错题 → 标记已掌握"""
    exam_id = _generate_math_exam(client, count=1)
    qs = client.get(f"/api/exam/{exam_id}/questions").json()
    uid = "错题手动标记生"

    r = client.post(f"/api/exam/{exam_id}/mark-wrong",
                    json={"user_id": uid, "question_ids": [qs[0]["id"]]})
    assert r.status_code == 200

    r = client.get("/api/exam/wrong/list", params={"user_id": uid})
    assert len(r.json()) == 1

    r = client.post(f"/api/exam/{exam_id}/master",
                    json={"user_id": uid, "question_ids": [qs[0]["id"]]})
    assert r.status_code == 200

    r = client.get("/api/exam/wrong/list", params={"user_id": uid})
    assert len(r.json()) == 0  # 默认不含已掌握
