"""同步学测试：学期过滤、三科单元结构、小测判分与成绩落库、每日任务联动"""
import datetime

from app.database import SessionLocal
from app.models.word import WordBook, Word
from app.models.classical import ClassicalText
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.sync import SyncQuizLog
from app.models.daily_task import DailyTask
from app.services.sync_service import _unsign


def _seed_english(db):
    b = db.query(WordBook).filter(WordBook.grade == 6, WordBook.name == "六年级上").first()
    if not b:
        b = WordBook(grade=6, name="六年级上", semester="全")
        db.add(b)
        db.flush()
    if not db.query(Word).filter(Word.book_id == b.id, Word.unit == "Unit 1").count():
        for i in range(10):
            db.add(Word(book_id=b.id, unit="Unit 1", word=f"word{i}",
                        phonetic=f"/w{i}/", pos="n", meaning=f"意思{i}"))
    return b


def _seed_chinese(db):
    for i in range(5):
        title = f"篇目{i}"
        if db.query(ClassicalText).filter(ClassicalText.title == title).first():
            continue
        db.add(ClassicalText(
            title=title, author="佚名", dynasty="唐", text_type="poem",
            grade=6, semester="全",
            content=f"床前明月光，疑是地上霜。\n举头望明月，低头思故乡{i}。",
        ))


def _seed_math(db):
    cat = db.query(ProblemCategory).first()
    if not cat:
        cat = ProblemCategory(name="计算题", subject="数学")
        db.add(cat)
        db.flush()
    chapters = ["六年级上·第1单元·分数乘法", "六年级上·第2单元·位置与方向"]
    for i, ch in enumerate(chapters):
        code = f"t607_{i}"
        if db.query(ProblemType).filter(ProblemType.code == code).first():
            continue
        db.add(ProblemType(category_id=cat.id, name=f"题型{i}", code=code,
                           grade_min=6, grade_max=6, textbook_chapter=ch))


def _quiz_full_loop(client, user_id, subject, grade, unit):
    """取卷 → 用正确答案交卷 → 返回判分结果（验证完整闭环）"""
    g = client.get("/api/sync/unit-quiz/generate",
                   params={"subject": subject, "grade": grade, "unit": unit})
    assert g.status_code == 200, g.text
    data = g.json()
    assert data["questions"], "小测应至少有一题"
    payload = _unsign(data["token"])
    answers = [{"qid": i, "user_answer": a} for i, a in enumerate(payload["a"])]
    r = client.post("/api/sync/unit-quiz", json={
        "user_id": user_id, "subject": subject, "grade": grade,
        "unit": unit, "token": data["token"], "answers": answers,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_sync_overview_english(client):
    db = SessionLocal()
    try:
        b = _seed_english(db)
        db.commit()
        r = client.get("/api/sync/overview", params={"user_id": "u1", "subject": "英语", "grade": 6})
        assert r.status_code == 200, r.text
        units = r.json()["units"]
        assert any(u["unit"].startswith("eng::") and "Unit 1" in u["unit"] for u in units)
        u = next(u for u in units if "Unit 1" in u["unit"])
        assert u["status"] == "未开始"
    finally:
        db.close()


def test_sync_chinese_units_by_semester(client):
    db = SessionLocal()
    try:
        _seed_chinese(db)
        db.commit()
        r = client.get("/api/sync/overview", params={"user_id": "u2", "subject": "语文", "grade": 6})
        assert r.status_code == 200
        units = r.json()["units"]
        assert units, "语文单元不应为空"
        unit = units[0]["unit"]
        # 要点：篇目列表
        rp = client.get("/api/sync/unit-points", params={"subject": "语文", "grade": 6, "unit": unit})
        assert len(rp.json()["points"]) >= 5
    finally:
        db.close()


def test_sync_math_units_from_chapters(client):
    db = SessionLocal()
    try:
        _seed_math(db)
        db.commit()
        r = client.get("/api/sync/overview", params={"user_id": "u3", "subject": "数学", "grade": 6})
        assert r.status_code == 200
        units = r.json()["units"]
        assert any("分数乘法" in u["unit"] for u in units)
    finally:
        db.close()


def test_sync_quiz_english_closed_loop_and_task_link(client):
    db = SessionLocal()
    try:
        b = _seed_english(db)
        today = datetime.date.today()
        db.add(DailyTask(user_id="u1", task_date=today, subject="英语",
                         task_code="eng_sync", title="英语同步练习", target=1,
                         progress=0, status="pending", manual=True, task_type="optional"))
        db.commit()
        unit = f"eng::{b.id}::Unit 1"
        res = _quiz_full_loop(client, "u1", "英语", 6, unit)
        assert res["score"] == 100.0
        assert res["passed"] is True
        # 刷新事务快照：HTTP 交卷在独立会话中落库（sync_quiz_log / 任务状态），
        # 本会话（MySQL REPEATABLE READ）需结束旧事务才能读到其它会话已提交的数据。
        db.rollback()
        # 成绩落库
        assert db.query(SyncQuizLog).filter_by(user_id="u1", unit=unit).count() == 1
        # D3 联动：eng_sync 任务自动完成
        task = db.query(DailyTask).filter_by(user_id="u1", task_code="eng_sync",
                                             task_date=today).first()
        assert task.status == "done"
        # 概览状态变为「已过关」
        ov = client.get("/api/sync/overview", params={"user_id": "u1", "subject": "英语", "grade": 6}).json()
        u = next(u for u in ov["units"] if unit in u["unit"])
        assert u["status"] == "已过关"
    finally:
        db.close()


def test_sync_quiz_chinese_and_math(client):
    db = SessionLocal()
    try:
        _seed_chinese(db)
        _seed_math(db)
        db.commit()
        # 语文
        c_units = client.get("/api/sync/overview", params={"user_id": "u4", "subject": "语文", "grade": 6}).json()["units"]
        c_res = _quiz_full_loop(client, "u4", "语文", 6, c_units[0]["unit"])
        assert c_res["correct"] == c_res["total"]
        # 数学
        m_units = client.get("/api/sync/overview", params={"user_id": "u5", "subject": "数学", "grade": 6}).json()["units"]
        m_unit = next(u["unit"] for u in m_units if "分数乘法" in u["unit"])
        m_res = _quiz_full_loop(client, "u5", "数学", 6, m_unit)
        assert m_res["total"] > 0
    finally:
        db.close()


def test_sync_quiz_invalid_token(client):
    db = SessionLocal()
    try:
        b = _seed_english(db)
        db.commit()
        unit = f"eng::{b.id}::Unit 1"
        r = client.post("/api/sync/unit-quiz", json={
            "user_id": "u1", "subject": "英语", "grade": 6, "unit": unit,
            "token": "garbage.token", "answers": [],
        })
        assert r.status_code == 400
    finally:
        db.close()
