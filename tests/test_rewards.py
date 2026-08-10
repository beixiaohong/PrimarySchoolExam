"""奖励闭环 + 防刷加固：心愿截止日期、卡券进度修正、错题判分不下发答案"""
from datetime import date, timedelta

USER = "奖励测试生"


def _make_wish(client, uid, deadline="", wish_type="task_count"):
    return client.post("/api/rewards/wish", json={
        "user_id": uid, "title": "测试心愿", "target": 5,
        "wish_type": wish_type, "daily_target": 3, "deadline": deadline,
    })


def test_wish_deadline_validation(client):
    uid = USER + "截止"
    # 非法格式 / 早于今天 都拒绝
    assert _make_wish(client, uid, deadline="2020-01-01").status_code == 400
    assert _make_wish(client, uid, deadline="not-a-date").status_code == 400
    # 合法截止日期
    dl = str(date.today() + timedelta(days=30))
    r = _make_wish(client, uid, deadline=dl)
    assert r.status_code == 200, r.text
    assert r.json()["deadline"] == dl
    # 不限期也允许
    uid2 = USER + "不限期"
    r = _make_wish(client, uid2)
    assert r.status_code == 200
    assert r.json()["deadline"] == ""


def test_wish_expire_after_deadline(client):
    uid = USER + "过期"
    dl = str(date.today() + timedelta(days=1))
    r = _make_wish(client, uid, deadline=dl)
    assert r.status_code == 200
    wid = r.json()["id"]

    # 把截止日期改到昨天 → overview 读取时应自动置为 expired
    from app.database import SessionLocal
    from app.models.reward import WishItem
    db = SessionLocal()
    try:
        w = db.query(WishItem).filter(WishItem.id == wid).first()
        w.deadline = date.today() - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/rewards/overview", params={"user_id": uid})
    assert r.status_code == 200
    # expired 的心愿不在进行中列表（wish 为 None）
    assert r.json()["wish"] is None


def test_coupon_progress_not_reset_for_new_user(client):
    """新上线用户：首条任务记录之前的日期不计中断，进度不被误清零"""
    from app.database import SessionLocal
    from app.models.daily_task import DailyTask
    from app.models.reward import RewardCoupon
    from app.routers.rewards import sync_coupon_progress

    uid = USER + "卡券"
    today = date.today()
    db = SessionLocal()
    try:
        # 最近 3 天（含今天）强制任务全勤；此前无任何记录（模拟新部署）
        for i in range(3):
            d = today - timedelta(days=i)
            for subj, code in (("数学", "math_exam"), ("语文", "chi_exam"), ("英语", "eng_exam")):
                db.add(DailyTask(user_id=uid, task_date=d, subject=subj, task_code=code,
                                 title=f"测试{subj}", target=1, progress=1, status="done",
                                 task_type="mandatory"))
        # 已累计 2 天（昨天累计过）
        db.add(RewardCoupon(user_id=uid, title="全勤券", kind="cartoon", status="active",
                            required_days=7, progress_days=2,
                            progress_date=str(today - timedelta(days=1)),
                            granted_count=0, redeemed_count=0))
        db.commit()

        sync_coupon_progress(db, uid)
        c = db.query(RewardCoupon).filter(RewardCoupon.user_id == uid).first()
        # 今天全勤 → 2+1=3；旧逻辑会因"首条记录前连续无记录=中断"清零成 1
        assert c.progress_days == 3
    finally:
        db.close()


def test_practice_quiz_no_answer_and_check_answer(client):
    """错题修正不下发正确答案；逐题判分走 check-answer"""
    uid = USER + "判分"
    # 生成试卷并交卷制造 1 道错题
    r = client.post("/api/exam/generate", json={
        "subject": "数学", "grade": 6, "difficulty": "基础",
        "math_count": 2, "user_id": uid,
    })
    assert r.status_code == 200
    exam_id = int(r.headers["X-Exam-Id"])
    qs = client.get(f"/api/exam/{exam_id}/questions").json()
    client.post("/api/exam/submit-answers", json={
        "user_id": uid, "exam_id": exam_id,
        "answers": [
            {"question_id": qs[0]["id"], "user_answer": qs[0]["answer"]},
            {"question_id": qs[1]["id"], "user_answer": "故意答错xyz"},
        ],
        "duration_sec": 120,
    })

    r = client.post("/api/exam/wrong/practice-quiz",
                    json={"user_id": uid, "subject": "数学", "count": 5})
    assert r.status_code == 200, r.text
    groups = r.json()["groups"]
    assert groups, "应有错题修正分组"
    for g in groups:
        for q in g["questions"]:
            assert "answer" not in q or q.get("answer") in (None, ""), "不得下发正确答案"

    # check-answer：用原题答案验证判分
    qid = qs[1]["id"]
    r = client.post("/api/study/check-answer", json={
        "user_id": uid, "kind": "exam", "qid": qid,
        "user_answer": qs[1]["answer"],
    })
    assert r.status_code == 200 and r.json()["correct"] is True
    r = client.post("/api/study/check-answer", json={
        "user_id": uid, "kind": "exam", "qid": qid,
        "user_answer": "错误答案abc",
    })
    assert r.status_code == 200 and r.json()["correct"] is False


def test_manual_mastered_not_counted_in_task_progress(client):
    """防刷：手动标记已掌握不计入错题订正任务进度（须答对才算）"""
    from app.database import SessionLocal
    from app.routers.tasks import _today_mastered

    uid = USER + "手动掌握"
    r = client.post("/api/exam/generate", json={
        "subject": "数学", "grade": 6, "difficulty": "基础",
        "math_count": 1, "user_id": uid,
    })
    exam_id = int(r.headers["X-Exam-Id"])
    qs = client.get(f"/api/exam/{exam_id}/questions").json()
    client.post(f"/api/exam/{exam_id}/mark-wrong",
                json={"user_id": uid, "question_ids": [qs[0]["id"]]})
    client.post(f"/api/exam/{exam_id}/master",
                json={"user_id": uid, "question_ids": [qs[0]["id"]]})

    db = SessionLocal()
    try:
        # 手动标记（correct_streak=0）不计入任务进度
        assert _today_mastered(db, uid, "数学") == 0
    finally:
        db.close()
