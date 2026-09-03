"""S2-M2 验证：知识点标注服务（kp_annotation）

覆盖 07 §3.2.1 / §4.4 / §10.C：知识点树、标注队列、提交标注、批量导入、
标注统计、AI 预标注（持连铁律：读→关→AI→写，且不覆盖人工标注）。
经 content.contracts 暴露给路由（本测试一并验证契约路径）。

注意：SessionLocal 关闭了 autoflush（app/database.py），写后若要在同一会话内
读回，须显式 db.flush()/commit()（与生产路由「先写后 commit 再读」语义一致）。
"""
from app.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.models.exam import ExamRecord, Question
from app.models.kp_map import QuestionKpMap
from app.domains.content import contracts as content_contracts
from app.domains.content.services import kp_annotation

_MARK = "__S2T__"


def _seed_kp(db):
    kp1 = KnowledgePoint(subject=_MARK, grade=7, unit="U1", title="有理数加法(S2)",
                         parent_id=0, code="M1")
    db.add(kp1)
    db.flush()
    kp2 = KnowledgePoint(subject=_MARK, grade=7, unit="U1", title="有理数减法(S2)",
                         parent_id=kp1.id, code="M2")
    db.add(kp2)
    db.flush()
    return kp1, kp2


def _seed_question(db):
    ex = ExamRecord(user_id=_MARK, subject=_MARK, title=_MARK, grade=7)
    db.add(ex)
    db.flush()
    q = Question(exam_id=ex.id, seq=1, subject=_MARK, question="计算 1+2 的值", answer="3")
    db.add(q)
    db.flush()
    return q


def _cleanup(db):
    # FK 安全删除顺序：QuestionKpMap → Question → KnowledgePoint → ExamRecord
    # （Question.exam_id → exam_records.id；QuestionKpMap.question_id → questions.id）
    ex_ids = [r[0] for r in db.query(ExamRecord.id).filter(
        ExamRecord.title == _MARK).all()]
    q_ids = [r[0] for r in db.query(Question.id).filter(
        Question.exam_id.in_(ex_ids)).all()] if ex_ids else []
    if q_ids:
        db.query(QuestionKpMap).filter(
            QuestionKpMap.source_table == "questions",
            QuestionKpMap.question_id.in_(q_ids)).delete(synchronize_session=False)
    if q_ids:
        db.query(Question).filter(Question.exam_id.in_(ex_ids)).delete(
            synchronize_session=False)
    # 先删子节点（parent_id!=0）再删根，避免层级 FK 约束
    db.query(KnowledgePoint).filter(
        KnowledgePoint.subject == _MARK, KnowledgePoint.parent_id != 0).delete(
        synchronize_session=False)
    db.query(KnowledgePoint).filter(KnowledgePoint.subject == _MARK).delete(
        synchronize_session=False)
    db.query(ExamRecord).filter(ExamRecord.title == _MARK).delete(synchronize_session=False)
    db.commit()


def test_m2_kp_tree_nesting():
    db = SessionLocal()
    try:
        kp1, kp2 = _seed_kp(db)
        db.commit()
        tree = content_contracts.get_kp_tree(db, subject=_MARK)
        assert len(tree) == 1
        assert tree[0]["id"] == kp1.id
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["id"] == kp2.id
    finally:
        _cleanup(db)
        db.close()


def test_m2_annotation_queue_and_submit():
    db = SessionLocal()
    try:
        q = _seed_question(db)
        db.commit()
        # 防御性清理：确保本测试题处于未标注态（隔离共享测试库里其它用例可能残留的 kp_map）
        db.query(QuestionKpMap).filter_by(question_id=q.id).delete(
            synchronize_session=False)
        db.commit()
        # 队列应含该未标注题（测试库含大量存量题；get_annotation_queue 将 page_size
        # 封顶到 MAX_PAGE_SIZE=100，故按页遍历直到找到该 q 或耗尽）
        assert content_contracts.get_annotation_queue(
            db, source_table="questions", page=1).get("total", 0) >= 1
        found = False
        page = 1
        while True:
            queue = content_contracts.get_annotation_queue(
                db, source_table="questions", page=page, page_size=100)
            if any(i["question_id"] == q.id for i in queue["items"]):
                found = True
                break
            if len(queue["items"]) < 100:  # 已是末页
                break
            page += 1
        assert found, f"未标注题 q.id={q.id} 未出现在标注队列中（total={queue['total']}）"
        # 提交标注（首项主知识点）；路由层会 commit，这里 flush 后同会话读回
        kp1, kp2 = _seed_kp(db)
        db.commit()
        n = content_contracts.submit_annotation(
            db, "questions", q.id, [kp1.id, kp2.id], annotated_by="tester")
        db.flush()
        assert n == 2
        maps = db.query(QuestionKpMap).filter_by(question_id=q.id).order_by(
            QuestionKpMap.id).all()
        assert maps[0].is_primary == 1 and float(maps[0].weight) == 1.00
        assert maps[1].is_primary == 0 and float(maps[1].weight) == 0.50
        # 重提交应替换旧标注（不重复）
        n2 = content_contracts.submit_annotation(db, "questions", q.id, [kp2.id])
        db.flush()
        assert n2 == 1
        assert db.query(QuestionKpMap).filter_by(question_id=q.id).count() == 1
    finally:
        _cleanup(db)
        db.close()


def test_m2_annotation_stats_coverage():
    db = SessionLocal()
    try:
        q = _seed_question(db)
        kp1, kp2 = _seed_kp(db)
        db.commit()
        # 防御性清理：隔离共享测试库里其它用例可能残留的 kp_map（用增量断言而非绝对值）
        db.query(QuestionKpMap).filter_by(question_id=q.id).delete(
            synchronize_session=False)
        db.commit()
        stats_before = content_contracts.get_annotation_stats(db, source_table="questions")
        assert stats_before["total"] >= 1
        assert stats_before["coverage"] >= 0.0
        content_contracts.submit_annotation(db, "questions", q.id, [kp1.id])
        db.flush()
        stats_after = content_contracts.get_annotation_stats(db, source_table="questions")
        # 增量断言：本题标注后，已标注量 +1、覆盖率上升、总量不变
        assert stats_after["annotated"] == stats_before["annotated"] + 1
        assert stats_after["coverage"] > stats_before["coverage"]
        assert stats_after["total"] == stats_before["total"]
    finally:
        _cleanup(db)
        db.close()


def test_m2_batch_import_idempotent():
    db = SessionLocal()
    try:
        q = _seed_question(db)
        kp1, kp2 = _seed_kp(db)
        db.commit()
        # 防御性清理：隔离共享测试库里其它用例可能残留的 kp_map
        db.query(QuestionKpMap).filter_by(question_id=q.id).delete(
            synchronize_session=False)
        db.commit()
        rows = [
            {"source_table": "questions", "question_id": q.id, "kp_id": kp1.id,
             "is_primary": 1, "weight": 1.00, "source": "batch_import"},
            {"source_table": "questions", "question_id": q.id, "kp_id": kp2.id,
             "is_primary": 0, "weight": 0.50},
            {"source_table": "questions", "question_id": q.id, "kp_id": kp1.id},  # 重复→跳过
        ]
        res = content_contracts.batch_import_kp(db, rows, annotated_by="importer")
        assert res["added"] == 2
        assert res["skipped"] == 1
        assert res["errors"] == []
    finally:
        _cleanup(db)
        db.close()


def test_m2_ai_annotate_respects_session_and_no_overwrite(client, monkeypatch):
    db = SessionLocal()
    try:
        kp1, kp2 = _seed_kp(db)
        q = _seed_question(db)
        db.commit()
        # 防御性清理：隔离共享测试库里其它用例可能残留的 kp_map
        db.query(QuestionKpMap).filter_by(question_id=q.id).delete(
            synchronize_session=False)
        db.commit()

        def fake_predict(text, catalog):
            # 不持有 DB 会话；返回本题库 kp
            return [{"kp_id": kp1.id, "confidence": 0.9},
                    {"kp_id": kp2.id, "confidence": 0.7}]

        monkeypatch.setattr(kp_annotation, "predict_kp_for_question", fake_predict)
        monkeypatch.setattr(kp_annotation, "ai_any_enabled", lambda: True)

        # 人工先标注（提交持久化，模拟路由层先 commit 再跑 AI 批），AI 不应覆盖
        content_contracts.submit_annotation(db, "questions", q.id, [kp2.id],
                                            annotated_by="human")
        db.commit()
        res = content_contracts.ai_annotate_questions([q.id], annotated_by="ai")
        assert res["processed"] == 1
        assert res["predicted"] == 0  # 已有人工标注→跳过
        # 路由层回查结果须用新会话（跨会话提交的标注在 REPEATABLE READ 下需新事务才可见）
        with SessionLocal() as rdb:
            maps = rdb.query(QuestionKpMap).filter_by(question_id=q.id).all()
        assert len(maps) == 1 and maps[0].source == "manual"

        # 删除人工标注后，AI 可写入（ai_annotate_questions 内部自管会话并提交）
        db.query(QuestionKpMap).filter_by(question_id=q.id).delete()
        db.commit()
        res2 = content_contracts.ai_annotate_questions([q.id], annotated_by="ai")
        assert res2["predicted"] == 2
        with SessionLocal() as rdb:
            ai_maps = rdb.query(QuestionKpMap).filter_by(question_id=q.id).all()
        assert len(ai_maps) == 2
        assert any(m.source == "ai_pred" and m.is_primary == 1 and m.kp_id == kp1.id
                   for m in ai_maps)
    finally:
        _cleanup(db)
        db.close()
