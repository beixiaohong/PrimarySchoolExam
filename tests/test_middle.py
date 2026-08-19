"""初中九科：出卷分发 / 学期解锁 / 课堂同步 / 升年级引导（M1-M3 回归）

注意：029+ 迁移在测试库执行，六科题库需本文件自行插种子。
"""
import io
import json
import zipfile
from datetime import date

PARENT_PWD = "8888"


def _ensure_parent_pwd(client, uid):
    r = client.get("/api/parent/status", params={"user_id": uid})
    if not r.json()["has_password"]:
        r = client.post("/api/parent/setup", json={
            "user_id": uid, "password": PARENT_PWD,
            "hint_question": "测试密保？", "hint_answer": "测试答案",
        })
        assert r.status_code == 200


def _set_settings(client, uid, settings):
    _ensure_parent_pwd(client, uid)
    r = client.post("/api/tasks/settings", json={
        "user_id": uid, "settings": settings,
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text


def _docx_text(content: bytes) -> str:
    """解析 docx 正文 XML 文本（校验标题学段）"""
    return zipfile.ZipFile(io.BytesIO(content)).read("word/document.xml").decode("utf-8")


# ═══════════════════════════════════════════════════════════
# 九科出卷
# ═══════════════════════════════════════════════════════════

def _seed_middle_questions(subject, grade=7, n=5):
    from app.database import SessionLocal
    from app.models.middle import MiddleQuestion
    db = SessionLocal()
    try:
        for i in range(n):
            db.add(MiddleQuestion(
                subject=subject, grade=grade, type="choice",
                question=f"{subject}测试题{i}：下列选项正确的是？",
                options_json=json.dumps(
                    ["A. 甲", "B. 乙", "C. 丙", "D. 丁"]),
                answer="A. 甲", analysis=f"{subject}解析{i}",
            ))
        db.commit()
    finally:
        db.close()


def test_middle_subject_exam(client):
    """六科出卷：选择题结构完整、答案在选项内、docx 标题带学段"""
    _seed_middle_questions("物理")
    r = client.post("/api/exam/generate", json={
        "subject": "物理", "grade": 8, "english_count": 3,
    })
    assert r.status_code == 200, r.text
    exam_id = int(r.headers["X-Exam-Id"])
    qs = client.get(f"/api/exam/{exam_id}/questions").json()
    assert len(qs) == 3
    for q in qs:
        assert q["answer"], "每题必须有答案"
        options = json.loads(q["options_json"] or "[]")
        assert q["answer"] in options, "答案必须在选项内（可离线判分）"
    assert "初中" in _docx_text(r.content)


def test_middle_subject_grade_guard(client):
    """年级守卫：6 年级请求初中科目返回 400"""
    r = client.post("/api/exam/generate", json={
        "subject": "物理", "grade": 6, "english_count": 3,
    })
    assert r.status_code == 400


def test_math_grade8_only_mid_types(client):
    """初中数学打通：8 年级数学卷题型全部为 mid_*，标题标注初中"""
    r = client.post("/api/exam/generate", json={
        "subject": "数学", "grade": 8, "math_count": 5, "difficulty": "综合",
    })
    assert r.status_code == 200, r.text
    exam_id = int(r.headers["X-Exam-Id"])
    qs = client.get(f"/api/exam/{exam_id}/questions").json()
    assert len(qs) == 5
    assert all(q["type_code"].startswith("mid_") for q in qs), \
        "8 年级可用题型仅中学题型 mid_*"
    assert "初中" in _docx_text(r.content)


# ═══════════════════════════════════════════════════════════
# 学期解锁（vocab 词书 + classical 篇目）
# ═══════════════════════════════════════════════════════════

def test_vocab_semester_filter_and_include_next(client, monkeypatch):
    """vocab：3 月只开下学期册、10 月只开上学期册；include_next 预支下学期"""
    import app.services.semester as sem
    from app.database import SessionLocal
    from app.models.word import Word, WordBook
    from app.routers.vocab import _get_grade_books

    uid = "学期过滤生"
    db = SessionLocal()
    try:
        b_up = WordBook(name="学期测试册上", grade=6, semester="上", publisher="测试")
        b_dn = WordBook(name="学期测试册下", grade=6, semester="下", publisher="测试")
        db.add_all([b_up, b_dn])
        db.flush()
        db.add(Word(book_id=b_up.id, word="semupword", meaning="上学期的词",
                    unit="Unit1", difficulty=1))
        db.add(Word(book_id=b_dn.id, word="semdnword", meaning="下学期的词",
                    unit="Unit1", difficulty=1))
        db.commit()
        up_id, dn_id = b_up.id, b_dn.id
    finally:
        db.close()

    # 3 月（下学期）：只开「学期测试册下」
    monkeypatch.setattr(sem, "current_semester", lambda today=None: "下")
    monkeypatch.setattr(sem, "next_semester", lambda today=None: "上")
    db = SessionLocal()
    try:
        ids_mar = _get_grade_books(db, 6, uid)
        assert dn_id in ids_mar and up_id not in ids_mar
    finally:
        db.close()

    # 10 月（上学期）：只开「学期测试册上」
    monkeypatch.setattr(sem, "current_semester", lambda today=None: "上")
    monkeypatch.setattr(sem, "next_semester", lambda today=None: "下")
    db = SessionLocal()
    try:
        ids_oct = _get_grade_books(db, 6, uid)
        assert up_id in ids_oct and dn_id not in ids_oct

        # 打开 include_next → 下学期册预支解锁
        _set_settings(client, uid, {"include_next": True})
        db.rollback()  # 刷新事务快照，使刚提交的 include_next 设置对当前会话可见
        ids_pre = _get_grade_books(db, 6, uid)
        assert up_id in ids_pre and dn_id in ids_pre
    finally:
        db.close()

    # GET settings 返回 study_flags
    r = client.get("/api/tasks/settings", params={"user_id": uid})
    assert r.json()["study_flags"]["include_next"] is True


def test_vocab_career_stats_span_semester_and_grade(client, monkeypatch):
    """vocab 累计统计应为整个学生生涯：
    - 跨学期：上学期学过的词，在放学前的下学期仍计入 learned（修复 28→120 类丢失）
    - 跨年级：本年级及以下词库都计入 total（与古诗文 grade<= 口径一致）
    - 新学选材仍只取自当前阶段（当前年级+当前学期），不跨低年级、不重教已学
    """
    import app.services.semester as sem
    from app.database import SessionLocal
    from app.models.word import Word, WordBook
    from app.models.vocab import VocabProgress
    from app.routers.vocab import _career_book_ids

    uid = "生涯累计生"
    db = SessionLocal()
    try:
        b_up = WordBook(name="生涯上", grade=6, semester="上", publisher="测试")
        b_dn = WordBook(name="生涯下", grade=6, semester="下", publisher="测试")
        b_low = WordBook(name="生涯五", grade=5, semester="上", publisher="测试")
        db.add_all([b_up, b_dn, b_low])
        db.flush()
        up_ids, dn_ids, low_ids = [], [], []
        for i in range(3):
            w = Word(book_id=b_up.id, word=f"careerup{i}", meaning=f"上{i}", unit="U1", difficulty=1)
            db.add(w); db.flush(); up_ids.append(w.id)
        for i in range(2):
            w = Word(book_id=b_dn.id, word=f"careerdn{i}", meaning=f"下{i}", unit="U1", difficulty=1)
            db.add(w); db.flush(); dn_ids.append(w.id)
        for i in range(4):
            w = Word(book_id=b_low.id, word=f"careerlow{i}", meaning=f"低{i}", unit="U1", difficulty=1)
            db.add(w); db.flush(); low_ids.append(w.id)
        db.commit()
    finally:
        db.close()

    # 模拟「下学期」（8 月）：当前阶段只开下册
    monkeypatch.setattr(sem, "current_semester", lambda today=None: "下")
    monkeypatch.setattr(sem, "next_semester", lambda today=None: "上")

    # 学会上学期的 3 个词（模拟上学期已学）
    db = SessionLocal()
    try:
        for wid in up_ids:
            db.add(VocabProgress(user_id=uid, word_id=wid, status="learning",
                                 review_stage=0, first_learn_date=date.today(),
                                 last_review_date=date.today(),
                                 next_review_date=date.today()))
        db.commit()
    finally:
        db.close()

    # 统计：learned 必须含上学期 3 词（跨学期不丢失）；total 等于累计池词数（跨年级）
    r = client.get("/api/vocab/stats", params={"user_id": uid, "grade": 6})
    assert r.status_code == 200, r.text
    s = r.json()
    db = SessionLocal()
    try:
        career_ids = _career_book_ids(db, 6, uid)
        expected_total = db.query(Word).filter(Word.book_id.in_(career_ids)).count()
        expected_learned = db.query(VocabProgress).filter(
            VocabProgress.user_id == uid,
            VocabProgress.word_id.in_(db.query(Word.id).filter(Word.book_id.in_(career_ids)))
        ).count()
    finally:
        db.close()
    assert s["total_words"] == expected_total, "累计总量应等于整个学生生涯词库大小（含低年级）"
    assert s["learned_count"] == expected_learned == 3, \
        f"上学期学的词在放学前的下学期应仍计入，实际 learned={s['learned_count']}"

    # 今日新学：只取自当前阶段下册，且不得包含已学的上学期词或低年级词
    r = client.get("/api/vocab/today", params={"user_id": uid, "grade": 6})
    assert r.status_code == 200, r.text
    new_ids = [w["word_id"] for w in r.json()["new_words"]]
    assert set(new_ids).isdisjoint(set(up_ids)), "不得把已学的上学期词当新词重教"
    assert set(new_ids).isdisjoint(set(low_ids)), "新学不得取自低年级词库"


def test_classical_semester_filter(client, monkeypatch):
    """classical /today：下学期篇目在上学期不出现；include_next 可预支"""
    import app.services.semester as sem
    from app.database import SessionLocal
    from app.models.classical import ClassicalText

    uid = "学期古诗生"
    title = "AA学期测试诗"
    db = SessionLocal()
    try:
        if not db.query(ClassicalText).filter_by(title=title).first():
            db.add(ClassicalText(
                title=title, author="测试", dynasty="唐", text_type="poem",
                grade=1, semester="下", content="测试句一\n测试句二",
                lines_json=json.dumps(["测试句一", "测试句二"]),
            ))
            db.commit()
    finally:
        db.close()

    _set_settings(client, uid, {"quotas": {"daily_new_texts": 50}})

    # 上学期：该「下」学期篇目不出现
    monkeypatch.setattr(sem, "current_semester", lambda today=None: "上")
    monkeypatch.setattr(sem, "next_semester", lambda today=None: "下")
    r = client.get("/api/classical/today", params={"user_id": uid, "grade": 6})
    assert r.status_code == 200, r.text
    titles = [t["title"] for t in r.json()["new_texts"]]
    assert title not in titles

    # 开启 include_next：下学期篇目预支出现
    _set_settings(client, uid, {"include_next": True})
    r = client.get("/api/classical/today", params={"user_id": uid, "grade": 6})
    titles = [t["title"] for t in r.json()["new_texts"]]
    assert title in titles


# ═══════════════════════════════════════════════════════════
# 教学进度 API + sync_mode 单元同步
# ═══════════════════════════════════════════════════════════

def test_progress_api_roundtrip_and_guard(client):
    """progress API：家长密码守卫 + options + PUT/GET roundtrip"""
    uid = "进度同步生"
    _ensure_parent_pwd(client, uid)

    # 未带家长密码 → 403
    r = client.put("/api/study/progress", json={
        "user_id": uid, "subject": "英语", "book_id": 0, "chapter": "",
    })
    assert r.status_code == 403

    # options：初中词书 → 单元（init_data 已建人教版七年级册）
    r = client.get("/api/study/progress/options", params={"user_id": uid, "grade": 7})
    assert r.status_code == 200, r.text
    books = r.json()["books"]
    assert books, "应有七年级词书"
    book = next(b for b in books if b["units"])
    assert book["units"][0].startswith("Unit"), "单元按数字解析排序"
    bid, unit = book["book_id"], book["units"][0]

    # PUT roundtrip
    r = client.put("/api/study/progress", json={
        "user_id": uid, "subject": "英语", "book_id": bid, "chapter": unit,
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text
    r = client.get("/api/study/progress", params={"user_id": uid})
    item = next(i for i in r.json()["items"] if i["subject"] == "英语")
    assert item["book_id"] == bid and item["chapter"] == unit
    assert item["book_name"] == book["book_name"]


def test_sync_mode_unit_filter(client, monkeypatch):
    """sync_mode：开启后 /today 新词只取教学进度的当前 unit"""
    import app.services.semester as sem
    from app.database import SessionLocal
    from app.models.word import Word, WordBook

    uid = "课堂同步生"
    monkeypatch.setattr(sem, "current_semester", lambda today=None: "下")
    monkeypatch.setattr(sem, "next_semester", lambda today=None: "上")

    db = SessionLocal()
    try:
        book = WordBook(name="同步测试册", grade=6, semester="下", publisher="测试")
        db.add(book)
        db.flush()
        for i in range(3):
            db.add(Word(book_id=book.id, word=f"syncu1w{i}", meaning=f"一单元词{i}",
                        unit="Unit1", difficulty=1))
        for i in range(5):
            db.add(Word(book_id=book.id, word=f"syncu2w{i}", meaning=f"二单元词{i}",
                        unit="Unit2", difficulty=1))
        db.commit()
        bid = book.id
    finally:
        db.close()

    _set_settings(client, uid, {"quotas": {"daily_new_words": 3}, "sync_mode": True})
    _ensure_parent_pwd(client, uid)
    r = client.put("/api/study/progress", json={
        "user_id": uid, "subject": "英语", "book_id": bid, "chapter": "Unit2",
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text

    r = client.get("/api/vocab/today", params={"user_id": uid, "grade": 6})
    assert r.status_code == 200, r.text
    new_words = r.json()["new_words"]
    assert len(new_words) == 3
    assert all(w["unit"] == "Unit2" for w in new_words), "sync_mode 应只出当前 unit 的词"


# ═══════════════════════════════════════════════════════════
# 小升初衔接 xsc_bridge + 升年级 promoted
# ═══════════════════════════════════════════════════════════

def test_xsc_bridge_mixes_grade7(client, monkeypatch):
    """xsc_bridge：六年级新学批次 7:3 混入七年级词"""
    import app.services.semester as sem
    from app.database import SessionLocal
    from app.models.word import Word, WordBook

    uid = "衔接预学生"
    monkeypatch.setattr(sem, "current_semester", lambda today=None: "下")
    monkeypatch.setattr(sem, "next_semester", lambda today=None: "上")

    _set_settings(client, uid, {"quotas": {"daily_new_words": 10}, "xsc_bridge": True})

    r = client.get("/api/vocab/today", params={"user_id": uid, "grade": 6})
    assert r.status_code == 200, r.text
    new_words = r.json()["new_words"]
    assert len(new_words) == 10
    word_ids = [w["word_id"] for w in new_words]

    db = SessionLocal()
    try:
        grades = {w.id: db.get(WordBook, w.book_id).grade
                  for w in db.query(Word).filter(Word.id.in_(word_ids)).all()}
    finally:
        db.close()
    g7 = [wid for wid in word_ids if grades.get(wid) == 7]
    assert g7, "xsc_bridge 开启后应混入七年级词"
    assert len(g7) == 3, "10 词按 7:3 混入 3 个七年级词"


def test_promoted_flag_on_upgrade(client, monkeypatch):
    """9月1日自动升级后登录返回 promoted/new_grade"""
    import app.routers.user as user_mod

    uid = "升年级引导生"
    r = client.post("/api/user/login", json={"user_id": uid, "grade": 6})
    assert r.status_code == 200, r.text
    assert r.json()["promoted"] is False, "新注册用户不算升级"

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 1)

    monkeypatch.setattr(user_mod, "date", _FakeDate)
    r = client.post("/api/user/login", json={"user_id": uid})
    body = r.json()
    assert body["promoted"] is True
    assert body["prev_grade"] == 6 and body["new_grade"] == 7
    assert body["grade"] == 7
