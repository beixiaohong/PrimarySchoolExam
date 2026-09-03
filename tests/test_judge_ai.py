# -*- coding: utf-8 -*-
"""错题复核 AI 付费链 + 系统错题沉淀 + 申诉匹配修复 回归测试

覆盖：
1. judge 复核优先走付费链（chat_paid_first）并在判定「参考答案有误」时
   把系统错题沉淀到 judge_review_issues（供统一修复判题代码）；
2. chat_paid_first：deepseek 成功 → 按实际 token 扣钻石；钻石不足/无 key → 降级免费链；
3. 申诉 approve：作答存在格式差异（全半角/空格）也能定位做题记录（不报「找不到」）。
"""
import json

from app.database import SessionLocal
from app.models.diamond import DiamondAccount, DiamondLedger
from app.models.exam import ExamRecord, Question, ExamAttempt, AttemptAnswer
from app.models.appeal import AnswerAppeal
import app.domains.platform.services.ai as ai_svc


# ─────────────────────────────────────────────────────────────
# 1) judge 复核：AI 判定参考答案有误 → 系统错题沉淀
# ─────────────────────────────────────────────────────────────
def test_judge_records_system_issue(client, monkeypatch):
    from app.models.judge_review import JudgeReviewIssue

    # 撤销 conftest autouse no_ai_judge 对 judge_wrong_items 的整体打桩
    # （它把函数替换为返回 [] 的 lambda），本用例要验证真实复核链路。
    # 注意：必须先 undo 再 import，否则绑定到的仍是打桩后的 lambda。
    monkeypatch.undo()
    from app.domains.assessment.services.judge import judge_wrong_items

    calls = {}

    def fake_paid(user_id, system, user, max_tokens=800, history=None,
                  reason="judge", ref_id=0):
        calls["n"] = calls.get("n", 0) + 1
        if "参考答案可能算错" in user:  # Step2：参考答案有误，正确值 81
            return {"text": json.dumps(
                [{"idx": 7, "stored_wrong": True, "correct_answer": "81"}]),
                "prompt_tokens": 10, "completion_tokens": 5,
                "model": "deepseek-v4-flash", "provider": "deepseek"}
        # Step1：孩子答案与存储答案不符（判错），送 Step2
        return {"text": json.dumps(
            [{"idx": 7, "my_answer": "81", "child_correct": False,
              "reason": "与参考答案不符"}]),
            "prompt_tokens": 10, "completion_tokens": 5,
            "model": "deepseek-v4-flash", "provider": "deepseek"}

    monkeypatch.setattr(ai_svc, "chat_paid_first", fake_paid)
    monkeypatch.setattr(ai_svc, "ai_any_enabled", lambda: True)
    monkeypatch.setattr(ai_svc, "rate_limit", lambda *a, **k: True)

    items = [{
        "key": 7, "question_id": 77001,
        "question": "数据[79,63,85,85,81,85,60]的中位数是多少？",
        "answer": "83.0", "user_answer": "81", "subject": "数学",
    }]
    approved = judge_wrong_items("判题沉淀生", items)
    assert approved.get(7, {}).get("stored_wrong") is True

    db = SessionLocal()
    try:
        issue = db.query(JudgeReviewIssue).filter_by(
            question_id=77001, status="open").first()
        assert issue is not None, "参考答案有误的题应沉淀到 judge_review_issues"
        assert issue.correct_answer == "81"
        assert issue.stored_answer == "83.0"
        assert issue.user_answer == "81"
    finally:
        db.query(JudgeReviewIssue).filter_by(question_id=77001).delete()
        db.commit()
        db.close()


# ─────────────────────────────────────────────────────────────
# 2) chat_paid_first：deepseek 成功 → 扣钻石；钻石不足 → 降级免费链
# ─────────────────────────────────────────────────────────────
def test_chat_paid_first_uses_deepseek_and_deducts(client, monkeypatch):
    from app.domains.commerce.services.diamond import grant

    uid = "付费链生"
    db = SessionLocal()
    try:
        grant(db, uid, 10, "test")
        db.close()

        def fake_call_provider(name, cfg, system, user, max_tokens, history=None):
            return {"text": "ok", "prompt_tokens": 10000, "completion_tokens": 0,
                    "model": "deepseek-v4-flash"}

        monkeypatch.setattr(ai_svc, "_call_provider", fake_call_provider)
        # deepseek 有 key；免费链 key 为空（即使降级也只返回 None，不影响本用例断言）
        def fake_cfg(name):
            if name == "deepseek":
                return {"api_key": "sk-test", "model": "deepseek-v4-flash",
                        "base_url": "https://api.deepseek.com", "timeout": 25}
            return {"api_key": "", "model": "", "base_url": "", "timeout": 10}

        monkeypatch.setattr(ai_svc, "_config_provider", fake_cfg)
        monkeypatch.setattr(ai_svc, "rate_limit", lambda *a, **k: True)

        result = ai_svc.chat_paid_first(uid, "sys", "user", reason="judge")
        assert result is not None and result.get("provider") == "deepseek"

        db2 = SessionLocal()
        try:
            acc = db2.query(DiamondAccount).filter_by(user_id=uid).first()
            assert acc is not None
            # 10000 token = 1 钻石 → 余额 10 → 9
            assert acc.balance == 9.0, "deepseek 调用应按实际 token 扣 1 钻石"
            log = db2.query(DiamondLedger).filter_by(
                user_id=uid, reason="judge").first()
            assert log is not None and log.amount == -1.0
        finally:
            db2.close()
    finally:
        db3 = SessionLocal()
        db3.query(DiamondLedger).filter_by(user_id=uid).delete()
        db3.query(DiamondAccount).filter_by(user_id=uid).delete()
        db3.commit()
        db3.close()


def test_chat_paid_first_falls_back_when_no_balance(client, monkeypatch):
    uid = "无钻石生"
    db = SessionLocal()
    try:
        # 不充值：注册赠送 10 钻石也存在，先扣光
        from app.domains.commerce.services.diamond import deduct
        db.close()

        def fake_call_provider(name, cfg, system, user, max_tokens, history=None):
            return {"text": "ok", "prompt_tokens": 10000, "completion_tokens": 0,
                    "model": "deepseek-v4-flash"}

        monkeypatch.setattr(ai_svc, "_call_provider", fake_call_provider)

        def fake_cfg(name):
            if name == "deepseek":
                return {"api_key": "sk-test", "model": "deepseek-v4-flash",
                        "base_url": "https://api.deepseek.com", "timeout": 25}
            return {"api_key": "", "model": "", "base_url": "", "timeout": 10}

        monkeypatch.setattr(ai_svc, "_config_provider", fake_cfg)
        monkeypatch.setattr(ai_svc, "rate_limit", lambda *a, **k: True)

        # 新用户无账户：get_balance 会赠送 10 钻石 → 预检 >0 → 仍调 deepseek 并扣费。
        # 为模拟「余额不足」，先创建账户并把余额扣到 0。
        db2 = SessionLocal()
        try:
            from app.domains.commerce.services.diamond import get_balance
            get_balance(db2, uid)
            acc = db2.query(DiamondAccount).filter_by(user_id=uid).first()
            deduct(db2, uid, acc.balance, "clear")
        finally:
            db2.close()

        result = ai_svc.chat_paid_first(uid, "sys", "user", reason="judge")
        # 余额 0 → 不走付费链 → 免费链 key 空 → None（降级）
        assert result is None, "钻石余额不足时应跳过 deepseek 降级（此处免费链未配 key）"
    finally:
        db3 = SessionLocal()
        db3.query(DiamondLedger).filter_by(user_id=uid).delete()
        db3.query(DiamondAccount).filter_by(user_id=uid).delete()
        db3.commit()
        db3.close()


# ─────────────────────────────────────────────────────────────
# 3) 申诉 approve：作答格式差异也能定位做题记录
# ─────────────────────────────────────────────────────────────
def test_appeal_approve_fuzzy_match_finds_record(client):
    uid = "申诉格式生"
    db = SessionLocal()
    try:
        rec = ExamRecord(user_id=uid, title="申诉测试卷", subject="数学",
                         grade=6, difficulty="综合")
        db.add(rec)
        db.flush()
        q = Question(exam_id=rec.id, seq=1, subject="数学",
                     type_name="填空", question="1+1=?", answer="2")
        db.add(q)
        db.flush()
        att = ExamAttempt(user_id=uid, exam_id=rec.id, score=0, total=1,
                          correct=0, wrong=1)
        db.add(att)
        db.flush()
        # 交卷时存储的作答带尾部空格（格式差异），申诉时传 "2"（无空格）
        aa = AttemptAnswer(attempt_id=att.id, question_id=q.id,
                           user_answer="2 ", is_correct=False)
        db.add(aa)
        db.flush()
        ap = AnswerAppeal(user_id=uid, source="exam", question_id=q.id,
                          question="1+1=?", user_answer="2",
                          correct_answer="2", subject="数学", status="pending")
        db.add(ap)
        db.commit()
        db.refresh(ap)

        r = client.post("/api/appeal/decide", json={
            "user_id": uid, "appeal_id": ap.id, "action": "approve"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

        # 用全新会话验证（本会话 REPEATABLE READ 快照看不到 HTTP 会话已提交的改判）
        vdb = SessionLocal()
        try:
            a2 = vdb.get(AttemptAnswer, aa.id)
            assert a2.is_correct is True, "格式差异时应能定位并改判该作答"
            assert vdb.get(AnswerAppeal, ap.id).status == "approved"
        finally:
            vdb.close()
    finally:
        db.query(AnswerAppeal).filter_by(user_id=uid).delete()
        db.query(AttemptAnswer).filter_by(attempt_id=att.id).delete()
        db.query(ExamAttempt).filter_by(user_id=uid).delete()
        db.query(Question).filter_by(exam_id=rec.id).delete()
        db.query(ExamRecord).filter_by(user_id=uid).delete()
        db.commit()
        db.close()


# ─────────────────────────────────────────────────────────────
# 5) 申诉无做题记录：降级批准（家长确认有效，不再报「找不到题目」）
# ─────────────────────────────────────────────────────────────
def test_appeal_approve_without_attempt_record(client):
    """AI 出题/每日练习等路径的题无 attempt_answers 记录时，
    家长 approve 应降级批准（credited=False + note），不报 400 卡死。"""
    uid = "申诉无记录生"
    db = SessionLocal()
    try:
        ap = AnswerAppeal(user_id=uid, source="exam", question_id=999999,
                          question="无做题记录的题", user_answer="3",
                          correct_answer="3", subject="数学", status="pending")
        db.add(ap)
        db.commit()
        db.refresh(ap)

        r = client.post("/api/appeal/decide", json={
            "user_id": uid, "appeal_id": ap.id, "action": "approve"})
        assert r.status_code == 200, f"无做题记录时应降级批准而非 400: {r.text}"
        data = r.json()
        assert data["status"] == "approved"
        assert data["credited"] is False
        assert data["note"], "降级时应返回提示说明"

        vdb = SessionLocal()
        try:
            assert vdb.get(AnswerAppeal, ap.id).status == "approved"
        finally:
            vdb.close()
    finally:
        db.query(AnswerAppeal).filter_by(user_id=uid).delete()
        db.commit()
        db.close()


# ─────────────────────────────────────────────────────────────
# 4) 申诉带 attempt_id：按（做题记录 + 题号）精确定位，不改判其它次作答
# ─────────────────────────────────────────────────────────────
def test_appeal_approve_by_attempt_id_exact(client):
    uid = "申诉精确定位生"
    db = SessionLocal()
    try:
        rec = ExamRecord(user_id=uid, title="精确定位卷", subject="数学",
                         grade=6, difficulty="综合")
        db.add(rec)
        db.flush()
        q = Question(exam_id=rec.id, seq=1, subject="数学",
                     type_name="填空", question="1+1=?", answer="2")
        db.add(q)
        db.flush()
        # 同题两次不同的做题记录（att1 存 "3"、att2 存 "4"，都判错）
        att1 = ExamAttempt(user_id=uid, exam_id=rec.id, score=0, total=1,
                           correct=0, wrong=1)
        db.add(att1)
        db.flush()
        att2 = ExamAttempt(user_id=uid, exam_id=rec.id, score=0, total=1,
                           correct=0, wrong=1)
        db.add(att2)
        db.flush()
        aa1 = AttemptAnswer(attempt_id=att1.id, question_id=q.id,
                            user_answer="3", is_correct=False)
        db.add(aa1)
        db.flush()
        aa2 = AttemptAnswer(attempt_id=att2.id, question_id=q.id,
                            user_answer="4", is_correct=False)
        db.add(aa2)
        db.flush()
        ap = AnswerAppeal(user_id=uid, source="exam", question_id=q.id,
                          attempt_id=att1.id, question="1+1=?",
                          user_answer="3", correct_answer="2",
                          subject="数学", status="pending")
        db.add(ap)
        db.commit()
        db.refresh(ap)

        r = client.post("/api/appeal/decide", json={
            "user_id": uid, "appeal_id": ap.id, "action": "approve"})
        assert r.status_code == 200, r.text

        vdb = SessionLocal()
        try:
            assert vdb.get(AttemptAnswer, aa1.id).is_correct is True, \
                "应按 (attempt_id, question_id) 精确改判申诉对应那次作答"
            assert vdb.get(AttemptAnswer, aa2.id).is_correct is False, \
                "其它做题记录的作答不得被误改判"
        finally:
            vdb.close()
    finally:
        db.query(AnswerAppeal).filter_by(user_id=uid).delete()
        db.query(AttemptAnswer).filter(
            AttemptAnswer.attempt_id.in_([att1.id, att2.id])).delete()
        db.query(ExamAttempt).filter_by(user_id=uid).delete()
        db.query(Question).filter_by(exam_id=rec.id).delete()
        db.query(ExamRecord).filter_by(user_id=uid).delete()
        db.commit()
        db.close()
