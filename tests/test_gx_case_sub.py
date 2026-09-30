"""案例题「按小问刷」测试（后端不新增题目行，只在展示层展开 + 单问批改）

覆盖：
1. `/case/sub/list` 把案例大题的 sub_questions 展开成一问一练（key 唯一、分值/题干来自子问）；
2. 知识域筛选对展开后的小问同样生效；
3. `/case/sub/grade` 参数校验（题目不存在 / 不是案例题 / 小问越界 / 作答过短）；
4. 批改落库（GxCaseGrade.question_text 只含该小问）+ 折算分 earned；
5. 低于及格线入错题本，且错题本按**整道大题**归集（不是按小问建条目）；
6. 路由不被 `/case/{qid}` 吃掉（sub 是静态段，qid 是 int 转换器）。
"""
import json

import pytest

from app.database import SessionLocal
from app.models.gaoxiang import GxQuestion, GxWrong, GxCaseGrade, GxProgress

SUBS_A = [{"q": "问题一：指出存在的问题", "answer": "要点1；要点2", "points": 12},
          {"q": "问题二：给出改进措施", "answer": "措施1", "points": 8}]
SUBS_B = [{"q": "（1）计算 SV 与 CV", "answer": "SV=2, CV=-1", "points": 6},
          {"q": "（2）判断项目状态", "answer": "进度提前、成本超支", "points": 4},
          {"q": "（3）提出纠偏措施", "answer": "", "points": 5}]


def _mk_case(db, domain, title, subs, seq):
    row = GxQuestion(domain=domain, qtype="case", question="背景材料：某市智慧环保项目……",
                     options_json=None, answer="", analysis="", title=title,
                     chapter="第13章 资源管理", source_kind="案例专题",
                     seq=seq, source="import")
    row.sub_questions = json.dumps(subs, ensure_ascii=False)
    db.add(row)
    db.commit()
    return row.id


def _mk_choice(db):
    """非案例题（用于「该题不是案例题」的拒绝路径）"""
    row = GxQuestion(domain="资源管理", qtype="single", question="下列哪项是配置项？",
                     options_json=json.dumps(["A. 计划", "B. 需求"], ensure_ascii=False),
                     answer="A", analysis="", seq=99, source="import")
    db.add(row)
    db.commit()
    return row.id


@pytest.fixture
def cases(client):
    """两道自制案例大题（2 + 3 = 5 个小问），用 client._db 避免跨 session 竞争"""
    db = client._db
    ids = [_mk_case(db, "资源管理", "仿真模拟（一） 试题一", SUBS_A, 1),
           _mk_case(db, "成本管理", "仿真模拟（一） 试题二", SUBS_B, 2)]
    choice_id = _mk_choice(db)
    yield {"a": ids[0], "b": ids[1], "choice": choice_id}
    all_ids = ids + [choice_id]
    db.query(GxCaseGrade).filter(GxCaseGrade.question_id.in_(all_ids)).delete(
        synchronize_session=False)
    db.query(GxWrong).filter(GxWrong.question_id.in_(all_ids)).delete(
        synchronize_session=False)
    db.query(GxQuestion).filter(GxQuestion.id.in_(all_ids)).delete(
        synchronize_session=False)
    db.commit()


@pytest.fixture
def mock_ai(monkeypatch):
    """假 AI：默认给 85 分，用例可改 calls['score'] 再请求"""
    calls = {"score": 85, "system": "", "user": ""}

    def fake(*a, **kw):
        system = a[1] if len(a) > 1 else kw.get("system", "")
        user = a[2] if len(a) > 2 else kw.get("user", "")
        calls["system"], calls["user"] = system, user
        return {"text": json.dumps({"score": calls["score"], "feedback": "要点齐全，表述规范"},
                                   ensure_ascii=False),
                "prompt_tokens": 10, "completion_tokens": 20}

    monkeypatch.setattr("app.domains.platform.services.ai.chat_for", fake)
    return calls


def _mine(items, qid):
    return [it for it in items if it["question_id"] == qid]


def _fresh_db():
    """读断言必须用**新会话**：client._db 是长生命周期会话，REPEATABLE READ 下
    首次 SELECT 后快照冻结，读不到接口内部新建会话已提交的新行（会误判「没落库」）。"""
    return SessionLocal()


def test_sub_list_expands_every_sub_question(client, cases):
    r = client.get("/api/gx/case/sub/list?user_id=gxsub1")
    assert r.status_code == 200, r.text
    d = r.json()
    ma, mb = _mine(d["items"], cases["a"]), _mine(d["items"], cases["b"])
    assert (len(ma), len(mb)) == (2, 3)
    keys = [it["key"] for it in ma + mb]
    assert len(set(keys)) == len(keys)                       # key 必须唯一（前端靠它索引草稿）
    assert [it["sub_index"] for it in ma] == [0, 1]
    assert [it["sub_index"] for it in mb] == [0, 1, 2]
    a0 = ma[0]
    assert a0["key"] == "%d#0" % cases["a"]
    assert a0["points"] == 12 and a0["q"].startswith("问题一") and a0["has_answer"] is True
    b2 = mb[2]
    assert b2["points"] == 5 and b2["has_answer"] is False   # 资料没给参考答案的小问


def test_sub_list_domain_filter(client, cases):
    r = client.get("/api/gx/case/sub/list?user_id=gxsub1&domain=成本管理")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and all(it["domain"] == "成本管理" for it in items)
    assert not _mine(items, cases["a"])
    assert len(_mine(items, cases["b"])) == 3


def test_sub_list_unknown_domain_rejected(client, cases):
    r = client.get("/api/gx/case/sub/list?user_id=gxsub1&domain=不存在的域")
    assert r.status_code == 400


def test_sub_grade_rejects_bad_input(client, cases, mock_ai):
    # 题目不存在
    r = client.post("/api/gx/case/sub/grade", json={"user_id": "gxsub1",
                                                    "question_id": 99999999,
                                                    "sub_index": 0,
                                                    "user_answer": "这是一段足够长的作答内容"})
    assert r.status_code == 404
    # 不是案例题
    r = client.post("/api/gx/case/sub/grade", json={"user_id": "gxsub1",
                                                    "question_id": cases["choice"],
                                                    "sub_index": 0,
                                                    "user_answer": "这是一段足够长的作答内容"})
    assert r.status_code == 400
    # 小问越界
    r = client.post("/api/gx/case/sub/grade", json={"user_id": "gxsub1",
                                                    "question_id": cases["a"],
                                                    "sub_index": 9,
                                                    "user_answer": "这是一段足够长的作答内容"})
    assert r.status_code == 400
    # 作答过短（避免空跑一次 AI）
    r = client.post("/api/gx/case/sub/grade", json={"user_id": "gxsub1",
                                                    "question_id": cases["a"],
                                                    "sub_index": 0, "user_answer": "答"})
    assert r.status_code == 400
    assert mock_ai["user"] == ""          # 校验拦在 AI 之前，一次 AI 都没调


def test_sub_grade_pass_persists_and_scales(client, cases, mock_ai):
    r = client.post("/api/gx/case/sub/grade", json={"user_id": "gxsub2",
                                                    "question_id": cases["a"],
                                                    "sub_index": 0,
                                                    "user_answer": "一是没有资源管理计划；二是采购不到位。"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["score"] == 85 and d["sub_index"] == 0 and d["points"] == 12
    assert d["earned"] == 10.2                    # 85% × 12 分
    assert d["in_wrong_book"] is False
    # 只把「该小问」交给 AI：prompt 里必须带上背景（小问依赖情境）与本小问题干
    assert "背景材料" in mock_ai["user"]
    assert "问题一：指出存在的问题" in mock_ai["user"]
    # 另一个小问的题干不应出现在本次 prompt 里（否则就是整卷批改，失去按问刷的意义）
    assert "问题二：给出改进措施" not in mock_ai["user"]

    db = SessionLocal()          # 见 _fresh_db 说明：读最新已提交值
    try:
        row = db.query(GxCaseGrade).filter_by(user_id="gxsub2",
                                              question_id=cases["a"]).first()
        assert row is not None and row.kind == "case"
        assert "第 1 小问" in (row.question_text or "")
        assert row.score == 85
        assert db.query(GxWrong).filter_by(user_id="gxsub2",
                                           question_id=cases["a"]).first() is None
        db.query(GxCaseGrade).filter_by(user_id="gxsub2").delete()
        db.query(GxProgress).filter_by(user_id="gxsub2").delete()
        db.commit()
    finally:
        db.close()


def test_sub_grade_low_score_goes_to_wrong_book_by_case(client, cases, mock_ai):
    mock_ai["score"] = 42
    r = client.post("/api/gx/case/sub/grade", json={"user_id": "gxsub3",
                                                    "question_id": cases["b"],
                                                    "sub_index": 1,
                                                    "user_answer": "项目状态良好，无需纠偏。"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["in_wrong_book"] is True and d["points"] == 4
    db = SessionLocal()
    wrong = db.query(GxWrong).filter_by(user_id="gxsub3", question_id=cases["b"]).first()
    # 错题本按整道大题归集：小问没有独立题目行，点开仍是完整案例
    assert wrong is not None and wrong.kind == "case" and wrong.last_score == 42
    db.query(GxWrong).filter_by(user_id="gxsub3").delete()
    db.query(GxCaseGrade).filter_by(user_id="gxsub3").delete()
    db.query(GxProgress).filter_by(user_id="gxsub3").delete()
    db.commit()
    db.close()


def test_sub_route_not_shadowed_by_case_detail(client, cases):
    """`/case/sub/list` 不能被先注册的 `/case/{qid}` 吃掉（qid 是 int 转换器）"""
    r = client.get("/api/gx/case/sub/list?user_id=gxsub1")
    assert r.status_code == 200 and "count" in r.json()
    r = client.get("/api/gx/case/%d?user_id=gxsub1" % cases["a"])
    assert r.status_code == 200 and r.json()["id"] == cases["a"]
