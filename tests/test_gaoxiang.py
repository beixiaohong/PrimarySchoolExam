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
    GX_DOMAINS, MASTER_STREAK, QTYPE_SINGLE, QTYPE_MULTI, QTYPE_CASE, QTYPE_ESSAY,
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
    # 完整考纲 = 第1~24章（早期只列十大知识域，导入资料覆盖全 24 章后扩展）
    assert len(body["domains"]) == 24
    assert len(set(body["domains"])) == 24          # 无重名
    for must in ("信息化发展", "进度管理", "绩效域", "法律法规与标准规范"):
        assert must in body["domains"]


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


# ══════════════════════════════════════════════════════════════════════════════
# 备考资料导入扩展（082）：筛选出题 / 案例·论文入口 / 错因分析 / 资料审计
# 覆盖需求：「分类存储四类资料」+「做完自动分析错题并入库、后续重练」
# ══════════════════════════════════════════════════════════════════════════════

def _seed_imported(db, qtype=QTYPE_SINGLE, answer="B", domain="质量管理",
                   chapter="第12章 质量管理", source_kind="每日一练",
                   title="", sub=None, question="高项导入题：控制质量的输出是什么？"):
    """模拟一条「资料导入」的题（带资料维度字段）"""
    q = GxQuestion(domain=domain, qtype=qtype, question=question, title=title,
                   chapter=chapter, source_kind=source_kind, source_file="t.pdf",
                   deck="", seq=1,
                   options_json=json.dumps(["A. 变更请求", "B. 核实的可交付成果",
                                            "C. 工作绩效信息", "D. 质量报告"],
                                           ensure_ascii=False) if qtype != QTYPE_CASE else None,
                   answer=answer, analysis="质量控制的输出含核实的可交付成果。",
                   sub_questions=json.dumps(sub, ensure_ascii=False) if sub else None)
    db.add(q)
    db.commit()
    return q.id


# ── ① 无参考答案的题不得被判错（打印版资料本来就无答案） ──

def test_quiz_submit_unanswered_question_is_not_judged(client):
    s = SessionLocal()
    try:
        qid = _seed_imported(s, answer="", question="高项导入题：本题资料未给答案？")
    finally:
        s.close()
    r = client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID, "answers": [{"question_id": qid, "answer": "A"}]})
    assert r.status_code == 200
    out = r.json()["results"][0]
    assert out["judged"] is False and out["is_correct"] is None
    assert r.json()["wrong_count"] == 0
    s = SessionLocal()
    try:
        # 不判错 → 不污染错题本（否则正确答案的题会被反复塞进错题本）
        assert s.query(GxWrong).filter_by(user_id=GX_UID, question_id=qid).first() is None
        assert s.query(GxAttempt).filter_by(user_id=GX_UID, question_id=qid).count() == 1
    finally:
        s.close()


# ── ② 资料维度出题与筛选 ──

def test_quiz_generate_filters_by_source_and_chapter(client, fake_ai):
    s = SessionLocal()
    try:
        hit = _seed_imported(s, question="高项导入题：命中筛选的题？")
        _seed_imported(s, source_kind="仿真模拟", chapter="第10章 进度管理",
                       question="高项导入题：不该被选中的题？")
    finally:
        s.close()
    r = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "qtype": "single", "count": 5, "source": "import",
        "source_kind": "每日一练", "chapter": "第12章 质量管理"})
    assert r.status_code == 200
    ids = [q["id"] for q in r.json()["questions"]]
    assert ids == [hit]
    assert fake_ai == []                       # source=import → 不调 AI、不扣费
    assert r.json()["questions"][0]["chapter"] == "第12章 质量管理"


def test_quiz_generate_scope_wrong_repractices_done_questions(client):
    """错题重练：必须能出「已做过」的题（常规出题会把它排除掉）"""
    s = SessionLocal()
    try:
        qid = _seed_imported(s, answer="B", question="高项导入题：错题重练习题？")
    finally:
        s.close()
    # 先做一遍（答错）→ 进错题本
    client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID, "answers": [{"question_id": qid, "answer": "A"}]})
    # 常规出题不会再出这道
    r = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "qtype": "single", "count": 5, "source": "import"})
    assert qid not in [q["id"] for q in r.json()["questions"]]
    # 错题重练能出
    r = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "qtype": "single", "count": 5, "scope": "wrong"})
    assert r.json()["scope"] == "wrong"
    assert qid in [q["id"] for q in r.json()["questions"]]


def test_quiz_generate_rejects_bad_scope(client):
    r = client.post("/api/gx/quiz/generate", json={
        "user_id": GX_UID, "qtype": "single", "scope": "whatever"})
    assert r.status_code == 400


def test_quiz_pick_excludes_done_at_sql_level(client):
    """防回归：已做题必须在 SQL 层排除，不能用「取 n*8 行再删」

    旧实现取窗口 = n*8 行后才剔除已做题：用户做过 25 道、请求 3 道时（窗口 24 行全做过）
    会误判「资料不够」→ 回退 AI 出题（白扣费），而库里其实还有上百道没做过的真题。
    """
    uid = "gx_test_uid_sqlwin"
    kind = "SQL窗口回归"          # 专属资料子类：把本用例的题与库里其他残留题隔开
    n = 30
    s = SessionLocal()
    try:
        ids = []
        for i in range(n):
            q = GxQuestion(domain="质量管理", qtype=QTYPE_SINGLE,
                           question=f"高项导入题：SQL 窗口回归 {i}？", answer="B",
                           chapter="第12章 质量管理", source_kind=kind)
            s.add(q)
            s.flush()
            ids.append(q.id)
        s.commit()
        # 前 25 道已做（> 旧窗口 n*8=24），剩 5 道没做过
        for qid in ids[:25]:
            s.add(GxAttempt(user_id=uid, question_id=qid, user_answer="A",
                            is_correct=False, duration_ms=0))
        s.commit()
    finally:
        s.close()
    try:
        r = client.post("/api/gx/quiz/generate", json={
            "user_id": uid, "qtype": "single", "count": 3, "source": "import",
            "source_kind": kind})
        assert r.status_code == 200
        got = [q["id"] for q in r.json()["questions"]]
        assert len(got) == 3, "窗口内已做不应导致判定「没题了」"
        assert all(g in ids[25:] for g in got)      # 只会抽到没做过的
    finally:
        s = SessionLocal()
        try:
            s.query(GxAttempt).filter(GxAttempt.user_id == uid).delete()
            s.query(GxQuestion).filter(GxQuestion.id.in_(ids)).delete(
                synchronize_session=False)
            s.commit()
        finally:
            s.close()


# ── ③ 筛选项与资料审计端点 ──

def test_catalog_endpoint(client):
    s = SessionLocal()
    try:
        _seed_imported(s, question="高项导入题：catalog 用题？")
    finally:
        s.close()
    r = client.get("/api/gx/catalog")
    assert r.status_code == 200
    body = r.json()
    kinds = {k["value"]: k["count"] for k in body["source_kinds"]}
    chapters = {c["value"]: c["count"] for c in body["chapters"]}
    assert kinds.get("每日一练", 0) >= 1
    assert chapters.get("第12章 质量管理", 0) >= 1
    assert body["qtypes"].get("single", 0) >= 1


def test_materials_endpoint(client):
    from app.models.gaoxiang import GxMaterial
    s = SessionLocal()
    try:
        s.query(GxMaterial).filter(GxMaterial.rel_path == "t/测试资料.pdf").delete()
        s.add(GxMaterial(rel_path="t/测试资料.pdf", category="选择题练习",
                         sub_kind="每日一练", title="测试资料", ext="pdf",
                         size_bytes=1, items=5, reason="命中规则"))
        s.commit()
    finally:
        s.close()
    r = client.get("/api/gx/materials?category=选择题练习")
    assert r.status_code == 200
    body = r.json()
    assert any(m["rel_path"] == "t/测试资料.pdf" for m in body["items"])
    assert any(x["sub_kind"] == "每日一练" for x in body["summary"])
    s = SessionLocal()
    try:
        s.query(GxMaterial).filter(GxMaterial.rel_path == "t/测试资料.pdf").delete()
        s.commit()
    finally:
        s.close()


# ── ④ 案例题入口 ──

SUB = [{"q": "请指出存在的问题", "answer": "未制定计划", "points": 10}]


def test_case_list_and_detail(client):
    s = SessionLocal()
    try:
        qid = _seed_imported(s, qtype=QTYPE_CASE, answer="", title="试题一",
                             source_kind="案例专题", chapter="第8章 整体管理",
                             domain="整体管理", sub=SUB,
                             question="高项导入案例：某公司承接政务项目……")
    finally:
        s.close()
    r = client.get(f"/api/gx/case/list?user_id={GX_UID}&source_kind=案例专题")
    assert r.status_code == 200
    rows = r.json()["items"]
    assert [x["id"] for x in rows] == [qid]
    assert rows[0]["sub_count"] == 1 and rows[0]["title"] == "试题一"

    r = client.get(f"/api/gx/case/{qid}?user_id={GX_UID}")
    body = r.json()
    assert body["sub_questions"][0]["points"] == 10
    assert "政务项目" in body["background"]
    # 题型不匹配必须 400（论文详情接口不认案例题）
    assert client.get(f"/api/gx/essay/{qid}?user_id={GX_UID}").status_code == 400


def test_case_grade_below_pass_enrolls_wrong_book(client, fake_ai, monkeypatch):
    """案例批改低于及格线（60）自动进错题本，供后续「错题重练」"""
    s = SessionLocal()
    try:
        qid = _seed_imported(s, qtype=QTYPE_CASE, answer="", title="试题一",
                             sub=SUB, question="高项导入案例：背景材料……")
    finally:
        s.close()
    monkeypatch.setattr("app.domains.assessment.routers.gaoxiang._call_ai",
                        lambda *a, **k: {"text": json.dumps(
                            {"score": 40, "feedback": "要点几乎全漏"},
                            ensure_ascii=False), "prompt_tokens": 10, "completion_tokens": 5})
    r = client.post("/api/gx/case/grade", json={
        "user_id": GX_UID, "question_id": qid, "user_answer": "随便答几句"})
    assert r.status_code == 200
    assert r.json()["score"] == 40 and r.json()["in_wrong_book"] is True
    s = SessionLocal()
    try:
        w = s.query(GxWrong).filter_by(user_id=GX_UID, question_id=qid).first()
        assert w is not None and w.kind == "case" and w.last_score == 40
    finally:
        s.close()
    # 错题本按题型分栏能捞到案例题
    r = client.get(f"/api/gx/wrong?user_id={GX_UID}&kind=case")
    assert [i["question_id"] for i in r.json()["items"]] == [qid]
    assert r.json()["by_kind"]["case"] == 1


# ── ⑤ 论文题入口与四维评分 ──

def test_essay_list_detail_and_grade(client, monkeypatch):
    s = SessionLocal()
    try:
        qid = _seed_imported(s, qtype=QTYPE_ESSAY, answer="", title="论信息系统项目的范围管理",
                             domain="范围管理", chapter="第9章 范围管理",
                             source_kind="论文练习", question="实施项目范围管理的目的……",
                             sub=[{"q": "1、概要叙述你参与的项目", "answer": "", "points": 0},
                                  {"q": "2、论述你对范围管理的认识", "answer": "", "points": 0}])
    finally:
        s.close()
    r = client.get(f"/api/gx/essay/list?user_id={GX_UID}")
    assert [x["id"] for x in r.json()["items"]] == [qid]
    assert r.json()["items"][0]["title"].startswith("论信息系统项目")

    # 正文太短 → 400（论文必须有分量）
    assert client.post("/api/gx/essay/grade", json={
        "user_id": GX_UID, "question_id": qid, "user_answer": "太短"}).status_code == 400

    fake = json.dumps({"rubric": [
        {"dim": "relevance", "score": 80, "comment": "切题"},
        {"dim": "structure", "score": 60, "comment": "过程描述略粗"},
        {"dim": "practice", "score": 70, "comment": "有数据"},
        {"dim": "writing", "score": 90, "comment": "流畅"}],
        "feedback": "总体不错，过程描述再细化"}, ensure_ascii=False)
    monkeypatch.setattr("app.domains.assessment.routers.gaoxiang._call_ai",
                        lambda *a, **k: {"text": fake, "prompt_tokens": 10,
                                         "completion_tokens": 5})
    r = client.post("/api/gx/essay/grade", json={
        "user_id": GX_UID, "question_id": qid, "user_answer": "正文" * 200})
    assert r.status_code == 200
    body = r.json()
    # 加权总分 = (80*35 + 60*25 + 70*25 + 90*15) / 100 = 74
    assert body["score"] == 74
    assert len(body["rubric"]) == 4
    assert body["in_wrong_book"] is False            # 达线不入错题本
    s = SessionLocal()
    try:
        g = s.query(GxCaseGrade).filter_by(user_id=GX_UID).first()
        assert g.kind == "essay" and g.rubric_json and json.loads(g.rubric_json)[0]["label"] == "切题与完整性"
    finally:
        s.close()


# ── ⑥ 错因分析（懒生成 + 缓存） ──

def test_wrong_analyze_generates_and_caches(client, monkeypatch):
    s = SessionLocal()
    try:
        qid = _seed_imported(s, answer="B", question="高项导入题：错因分析用题？")
    finally:
        s.close()
    client.post("/api/gx/quiz/submit", json={
        "user_id": GX_UID, "answers": [{"question_id": qid, "answer": "A"}]})

    fake = json.dumps({"reason_type": "概念混淆", "analysis": "你把XX和YY搞混了。",
                       "tips": "口诀：先章程后计划"}, ensure_ascii=False)
    seen = []

    def _ai(user_id, system, user, max_tokens=900, **kw):
        seen.append(user)
        return {"text": fake, "prompt_tokens": 10, "completion_tokens": 5}

    monkeypatch.setattr("app.domains.assessment.routers.gaoxiang._call_ai", _ai)
    r = client.post("/api/gx/wrong/analyze", json={"user_id": GX_UID,
                                                  "question_id": qid})
    assert r.status_code == 200
    body = r.json()
    assert body["analyzed"] == 1
    assert body["items"][0]["reason_type"] == "概念混淆"
    assert "概念混淆" in seen[0] or "题干" in seen[0]      # prompt 带上了题目与错选

    # 已分析的题不再重复扣费（默认只看 wrong_reason 为空的）
    r2 = client.post("/api/gx/wrong/analyze", json={"user_id": GX_UID, "limit": 5})
    assert r2.json()["analyzed"] == 0
    # 错题列表带上缓存的错因
    rows = client.get(f"/api/gx/wrong?user_id={GX_UID}").json()["items"]
    target = [x for x in rows if x["question_id"] == qid][0]
    assert "你把XX和YY搞混了" in target["wrong_reason"]
    assert target["kind"] == "choice"


# ── ⑦ 纯函数：论文加权与错因 prompt ──

def test_parse_essay_grade_weights_rubric():
    from app.domains.assessment.services.gaoxiang import parse_essay_grade
    fake = json.dumps({"rubric": [{"dim": "relevance", "score": 100, "comment": ""},
                                  {"dim": "structure", "score": 100, "comment": ""},
                                  {"dim": "practice", "score": 100, "comment": ""},
                                  {"dim": "writing", "score": 100, "comment": ""}],
                       "feedback": "满分"}, ensure_ascii=False)
    got = parse_essay_grade(fake)
    assert got["score"] == 100 and len(got["rubric"]) == 4
    # 只有总分没有四维 → 用总分兜底
    assert parse_essay_grade('{"score": 55, "feedback": "x"}')["score"] == 55
    assert parse_essay_grade("不是 JSON") is None


def test_build_wrong_analysis_prompt_includes_choices():
    from app.domains.assessment.services.gaoxiang import build_wrong_analysis_prompt
    q = GxQuestion(domain="质量管理", qtype=QTYPE_SINGLE, question="题干E",
                   options_json=json.dumps(["A. 甲", "B. 乙"], ensure_ascii=False),
                   answer="B", analysis="解析E")
    text = build_wrong_analysis_prompt(q, "A")
    for must in ("题干E", "A. 甲", "正确答案：B", "考生所选：A", "解析E"):
        assert must in text


def test_record_subjective_grade_pass_accumulates_streak():
    """主观题达线 → 累计连对、更新最高分；未达线 → 入错题本并记 last_score"""
    from app.domains.assessment.services.gaoxiang import record_subjective_grade
    s = SessionLocal()
    uid = "gx_test_uid_subj"
    _cleanup(uid)
    try:
        qid = _seed_imported(s, qtype=QTYPE_CASE, answer="", sub=SUB,
                             question="高项导入案例：主观题连对测试……")
        q = s.get(GxQuestion, qid)
        out = record_subjective_grade(s, uid, q, "case", 40)
        assert out["passed"] is False and out["added"] is True
        w = s.query(GxWrong).filter_by(user_id=uid, question_id=qid).first()
        assert w.kind == "case" and w.last_score == 40 and w.best_score == 40
        # 重做达线 → 连对 1 次，最高分更新，但仍未掌握
        record_subjective_grade(s, uid, q, "case", 85)
        s.refresh(w)
        assert w.correct_streak == 1 and w.best_score == 85 and w.is_mastered is False
    finally:
        _cleanup(uid)
        s.close()
