"""试卷生成与在线做题：生成 Word → 题目入库 → 交卷判分 → 错题落库"""

USER = "试卷测试生"


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
