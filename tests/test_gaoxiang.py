"""软考高项备考模块测试（/api/gx）

钉死七件事：
① 域清单端点：十大知识域完整返回；
② 判分纯函数：单选/多选归一化比对（'b,a'→'AB' 全等），多选必须全对；
③ 刷题闭环（集成）：答对→进度累计且不进错题本；答错→错题本 upsert；
   重做连对 3 次自动掌握；案例题走 quiz/submit 被 400 拒绝（必须走 AI 批改）；
④ quiz/generate 题库优先：题库有未做过题时不触发 AI（不扣费不出新题）；
⑤ AI 生成端点（mock chat_with）：知识点生成落库去重、案例批改评分落记录；
⑥ 进度端点：全部考纲知识域都返回（没学过的为 0），正确率口径一致；
⑦ 校验：非法知识域 400、不存在知识点/错题 404。

conftest 强制 MySQL 测试库；不做事务回滚 → 每用例专属 user_id，finally 清理自身数据。
"""
import json

import pytest

from app.database import SessionLocal
from app.models.gaoxiang import (GxKnowledge, GxQuestion, GxAttempt,
                                 GxWrong, GxCaseGrade, GxProgress)
from app.domains.assessment.services.gaoxiang import (
    GX_DOMAINS, MASTER_STREAK, QTYPE_SINGLE, QTYPE_MULTI, QTYPE_CASE,
    normalize_letters, grade_choice, parse_questions, parse_case,
    parse_knowledge, progress_overview, record_choice_attempt,
)

GX_UID = "gx_test_uid"


# ── 工具 ──

def _seed_question(db, domain="风险管理", qtype=QTYPE_SINGLE, answer="B",
                   question="高项单选测试题：以下哪项属于风险应对策略？",
                   options=None):
    q = GxQuestion(domain=domain, qtype=qtype, question=question,
                   options_json=json.dumps(options or ["A. 规避", "B. 转移",
                                                       "C. 减轻", "D. 接受"],
                                           ensure_ascii=False),
                   answer=answer, analysis="转移是把风险后果连同责任转给第三方。")
    db.add(q)
    db.commit()
    return q.id   # 会话由调用方 close，commit 后立刻取 id（close 后属性过期不可再读）


def _cleanup(uid):
    """清理该用例产生的所有 gx 数据（专属用户，避免跨用例污染）"""
    s = SessionLocal()
    try:
        s.query(GxAttempt).filter(GxAttempt.user_id == uid).delete()
        s.query(GxWrong).filter(GxWrong.user_id == uid).delete()
        s.query(GxCaseGrade).filter(GxCaseGrade.user_id == uid).delete()
        s.query(GxProgress).filter(GxProgress.user_id == uid).delete()
        s.query(GxQuestion).filter(GxQuestion.question.like("高项%")).delete()
        s.query(GxKnowledge).filter(GxKnowledge.title.like("高项%")).delete()
        s.commit()
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _isolated():
    _cleanup(GX_UID)
    yield
    _cleanup(GX_UID)


FAKE_QUIZ_AI = json.dumps({
    "questions": [
        {"question": "高项AI题：整体管理包括哪些过程？",
         "options": ["A. 制定章程", "B. 识别干系人", "C. 控制质量", "D. 结束项目或阶段"],
         "answer": "AD", "analysis": "识别干系人属于干系人管理，控制质量属于质量管理。"}
    ]}, ensure_ascii=False)

FAKE_KNOWLEDGE_AI = json.dumps({
    "points": [
        {"code": "11.1", "title": "高项知识点：风险登记册",
         "summary": "风险登记册的主要contents",
         "content": "风险登记册记录已识别风险、应对措施等。"}
    ]}, ensure_ascii=False)

FAKE_CASE_AI = json.dumps({
    "background": "高项案例背景：某公司承接政务系统集成项目，项目经理身兼数职……",
    "sub_questions": [
        {"q": "该项目在风险管理上存在哪些问题？", "answer": "未做风险识别；无风险登记册", "points": 10}
    ]}, ensure_ascii=False)

FAKE_GRADE_AI = json.dumps({"score": 60, "feedback": "命中要点1；遗漏风险登记册相关要点。"},
                           ensure_ascii=False)


@pytest.fixture()
def fake_ai(monkeypatch):
    """mock AI 网关（路由内延迟 import contracts → monkeypatch 模块属性即可）"""
    calls = []

    def _fake_chat(user_id, system, user, max_tokens=800, provider=None, history=None):
        calls.append(user)
        if "知识点卡片" in user:
            text = FAKE_KNOWLEDGE_AI
        elif "案例分析大题" in user:
            text = FAKE_CASE_AI
        elif "批改" in user or "阅卷" in system:
            text = FAKE_GRADE_AI
        else:
            text = FAKE_QUIZ_AI
        return {"text": text, "prompt_tokens": 100, "completion_tokens": 50}

    monkeypatch.setattr("app.domains.platform.contracts.chat_with", _fake_chat)
    return calls


# ── ① 域清单 ──

def test_domains_endpoint(client):
    r = client.get("/api/gx/domains")
    assert r.status_code == 200
    body = r.json()
    assert body["domains"] == GX_DOMAINS
    assert len(body["domains"]) == 10


# ── ② 判分纯函数 ──

@pytest.mark.parametrize("user_answer,correct,qtype,expected", [
    ("B", "B", QTYPE_SINGLE, True),
    ("b", "B", QTYPE_SINGLE, True),            # 小写归一
    ("A", "B", QTYPE_SINGLE, False),
    ("A,C", "CA", QTYPE_MULTI, True),          # 乱序+分隔符归一
    ("AB", "ABC", QTYPE_MULTI, False),         # 多选漏选=错
    ("ABD", "ABD", QTYPE_MULTI, True),
    ("", "B", QTYPE_SINGLE, False),            # 空答案必错
    ("说明理由", "B", QTYPE_SINGLE, False),     # 非选项作答必错
])
def test_grade_choice(user_answer, correct, qtype, expected):
    assert grade_choice(user_answer, correct, qtype) is expected


def test_normalize_letters():
    assert normalize_letters("b, a D") == "ABD"
    assert normalize_letters("") == ""


# ── ③ 刷题闭环（集成） ──

def test_quiz_submit_and_wrong_loop(client):
    s = SessionLocal()
    try:
        q1 = _seed_question(s, answer="B")
        q2 = _seed_question(s, answer="C", question="高项单选测试题2：风险审计的工具是？")
    finally:
        s.close()

    # 答对 q1
    r = client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID,
        "answers": [{"question_id": q1, "answer": "B", "duration_ms": 1500}]})
    assert r.status_code == 200
    out = r.json()["results"][0]
    assert out["is_correct"] is True and out["correct"] == "B"
    assert "转移" in out["analysis"]

    # 答错 q2 → 进错题本
    r = client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID, "answers": [{"question_id": q2, "answer": "A"}]})
    assert r.json()["results"][0]["is_correct"] is False

    s = SessionLocal()
    try:
        wrong = s.query(GxWrong).filter_by(user_id=GX_UID, question_id=q2).first()
        assert wrong is not None and wrong.wrong_count == 1
        assert wrong.is_mastered is False
        # 答对的不进错题本
        assert s.query(GxWrong).filter_by(user_id=GX_UID, question_id=q1).first() is None
    finally:
        s.close()

    # 错题列表含 q2
    r = client.get(f"/api/gx/wrong?user_id={GX_UID}")
    assert [i["question_id"] for i in r.json()["items"]] == [q2]

    # 重做连对 3 次自动掌握
    for i in range(MASTER_STREAK):
        r = client.post("/api/gx/quiz/submit", json={
            "user_id": GX_UID, "answers": [{"question_id": q2, "answer": "C"}]})
        assert r.json()["results"][0]["is_correct"] is True
    s = SessionLocal()
    try:
        wrong = s.query(GxWrong).filter_by(user_id=GX_UID, question_id=q2).first()
        assert wrong.is_mastered is True and wrong.mastered_at is not None
    finally:
        s.close()
    # 掌握后默认不再出现在错题列表
    r = client.get(f"/api/gx/wrong?user_id={GX_UID}")
    assert r.json()["items"] == []


def test_quiz_submit_rejects_case_question(client):
    s = SessionLocal()
    try:
        q = _seed_question(s, qtype=QTYPE_CASE, answer="",
                           question="高项案例测试：背景材料……")
    finally:
        s.close()
    r = client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID, "answers": [{"question_id": q, "answer": "随便写写"}]})
    assert r.status_code == 400


def test_quiz_submit_unknown_question(client):
    r = client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID, "answers": [{"question_id": 999999, "answer": "A"}]})
    assert r.status_code == 200
    assert r.json()["results"][0] == {"question_id": 999999, "found": False}


# ── ④ quiz/generate 题库优先（不触发 AI） ──

def test_quiz_generate_serves_bank_first(client, fake_ai):
    """题库有未做过题时直接出库题、不触发 AI（count=1 与库存恰好相等才可验证）"""
    s = SessionLocal()
    try:
        q = _seed_question(s, domain="进度管理", answer="B")
    finally:
        s.close()
    r = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "domain": "进度管理", "qtype": "single", "count": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["questions"][0]["id"] == q
    assert "answer" not in body["questions"][0]        # 答案不下发
    assert fake_ai == []                                # 题库足够 → 未调用 AI


def test_quiz_generate_fills_from_ai(client, fake_ai):
    """题库为空时 AI 补题落库；同用户再取同 count 时复用库存题，不再调 AI"""
    r = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "domain": "整体管理", "qtype": "multi", "count": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    first_id = body["questions"][0]["id"]
    assert len(fake_ai) == 1                            # 首次：AI 被调用

    r2 = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "domain": "整体管理", "qtype": "multi", "count": 1})
    assert r2.status_code == 200
    assert r2.json()["count"] == 1
    assert r2.json()["questions"][0]["id"] == first_id  # 复用上一轮 AI 生成的题
    assert len(fake_ai) == 1                            # 未再次调用 AI


# ── ⑤ AI 生成端点（mock） ──

def test_knowledge_generate_dedup(client, fake_ai):
    for _ in range(2):   # 同一知识域生成两次 → 第二次去重不新增
        r = client.post("/api/gx/knowledge/generate", json={
            "user_id": GX_UID, "domain": "风险管理"})
        assert r.status_code == 200
    assert r.json() == {"domain": "风险管理", "generated": 1, "added": 0}

    r = client.get("/api/gx/knowledge?user_id=%s&domain=风险管理" % GX_UID)
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["title"].startswith("高项")

    # 详情端点
    kid = items[0]["id"]
    r = client.get(f"/api/gx/knowledge/{kid}?user_id={GX_UID}")
    assert r.status_code == 200 and "风险登记册" in r.json()["title"]


def test_knowledge_generate_ai_failure_502(client, monkeypatch):
    monkeypatch.setattr("app.domains.platform.contracts.chat_with",
                        lambda *a, **k: {"text": "", "prompt_tokens": 0,
                                         "completion_tokens": 0})
    r = client.post("/api/gx/knowledge/generate", json={
        "user_id": GX_UID, "domain": "风险管理"})
    assert r.status_code == 502


def test_case_generate_and_grade(client, fake_ai):
    # 出题
    r = client.post("/api/gx/case/generate", json={
        "user_id": GX_UID, "domain": "风险管理"})
    assert r.status_code == 200
    body = r.json()
    assert "政务系统集成项目" in body["background"]
    # 子问题只下发题干与分值，不下发参考答案
    assert body["sub_questions"][0]["q"].startswith("该项目")
    assert "answer" not in body["sub_questions"][0]

    # 批改
    r = client.post("/api/gx/case/grade", json={
        "user_id": GX_UID, "question_id": body["question_id"],
        "user_answer": "问题：未做风险识别，也没有风险登记册。建议……"})
    assert r.status_code == 200
    out = r.json()
    assert out["score"] == 60 and "遗漏" in out["feedback"]

    # 批改记录落库 + 进度 case_count +1
    s = SessionLocal()
    try:
        assert s.query(GxCaseGrade).filter_by(user_id=GX_UID).count() == 1
        prog = s.query(GxProgress).filter_by(user_id=GX_UID, domain="风险管理").first()
        assert prog is not None and prog.case_count == 1
    finally:
        s.close()


# ── ⑥ 进度端点 ──

def test_progress_overview_structure_and_accumulation(client):
    # 初始：全部知识域都返回、全为 0
    r = client.get(f"/api/gx/progress?user_id={GX_UID}")
    assert r.status_code == 200
    body = r.json()
    assert [d["domain"] for d in body["domains"]] == GX_DOMAINS
    assert all(d["quiz_total"] == 0 for d in body["domains"])
    assert body["summary"]["accuracy"] is None

    # 做两题（1 对 1 错）→ 汇总正确率 50%
    s = SessionLocal()
    try:
        q1 = _seed_question(s, domain="成本管理", answer="B")
        q2 = _seed_question(s, domain="成本管理", answer="C",
                            question="高项单选测试题2：EV 是什么的缩写？")
    finally:
        s.close()
    client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID,
        "answers": [{"question_id": q1, "answer": "B"},
                    {"question_id": q2, "answer": "A"}]})
    r = client.get(f"/api/gx/progress?user_id={GX_UID}")
    cm = next(d for d in r.json()["domains"] if d["domain"] == "成本管理")
    assert cm["quiz_total"] == 2 and cm["quiz_correct"] == 1
    assert cm["accuracy"] == 50
    assert r.json()["summary"]["accuracy"] == 50


def test_progress_overview_pure_function(db_session=None):
    """纯函数形态：直接查库聚合（不经过 HTTP），口径与端点一致"""
    s = SessionLocal()
    try:
        overview = progress_overview(s, GX_UID)
        assert overview["summary"]["quiz_total"] == 0
    finally:
        s.close()


# ── ⑦ 校验 ──

def test_invalid_domain_400(client):
    r = client.get(f"/api/gx/knowledge?user_id={GX_UID}&domain=语文")
    assert r.status_code == 400
    r = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "domain": "奥数"})
    assert r.status_code == 400


def test_knowledge_404(client):
    r = client.get(f"/api/gx/knowledge/999999?user_id={GX_UID}")
    assert r.status_code == 404


def test_wrong_master_404(client):
    r = client.post("/api/gx/wrong/master", json={
        "user_id": GX_UID, "question_id": 999999})
    assert r.status_code == 404


# ── AI 解析函数边界 ──

def test_parse_questions_tolerates_fences_and_junk():
    wrapped = "好的，以下是题目：\n```json\n%s\n```\n祝备考顺利！" % FAKE_QUIZ_AI
    qs = parse_questions(wrapped)
    assert len(qs) == 1 and qs[0]["answer"] == "AD"

    assert parse_questions(" totally not json ") == []
    assert parse_questions('{"questions": [{"question": "缺答案"}]}') == []
    assert parse_questions("") == []


def test_parse_case_and_knowledge_edges():
    assert parse_case("不是 json") is None
    case = parse_case(FAKE_CASE_AI)
    assert case["sub_questions"][0]["points"] == 10

    assert parse_knowledge('{"points": [{"title": "只有标题"}]}') == []
    ks = parse_knowledge(FAKE_KNOWLEDGE_AI)
    assert ks[0]["title"].startswith("高项")


def test_record_choice_attempt_multi_partial_is_wrong(db_session=None):
    """多选漏选判错且进错题本（服务端判分口径）"""
    s = SessionLocal()
    uid = "gx_test_uid_multi"
    _cleanup(uid)
    try:
        qid = _seed_question(s, qtype=QTYPE_MULTI, answer="ABD",
                             question="高项多选测试：属于整体管理过程的有？")
        q = s.get(GxQuestion, qid)   # 会话未关，取对象给服务层判分
        out = record_choice_attempt(s, uid, q, "AB")   # 漏选 D
        assert out["is_correct"] is False
        wrong = s.query(GxWrong).filter_by(user_id=uid, question_id=qid).first()
        assert wrong is not None and wrong.wrong_count == 1
    finally:
        _cleanup(uid)
        s.close()
