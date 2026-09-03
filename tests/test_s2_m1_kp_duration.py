"""S2-M1 验证：知识点树字段 + 题目-知识点映射 + 答题用时采集

覆盖 07 §3.2.1 / §3.2.2 的数据底座（迁移 053 / 054 + 模型扩展）：
- KnowledgePoint 新增 parent_id/code/sort_order/status/textbook_ver/updated_at
- AttemptAnswer 新增 started_at/duration_ms/seq/difficulty/created_at
- QuestionKpMap 映射表可建、可 CRUD、唯一约束生效
"""
from app.models.knowledge import KnowledgePoint
from app.models.exam import AttemptAnswer
from app.models.kp_map import QuestionKpMap


def test_s2_m1_models_have_new_columns(client):
    """模型层新列属性齐备（create_all 据此在测试库建表）。"""
    for attr in ("parent_id", "code", "sort_order", "status", "textbook_ver", "updated_at"):
        assert hasattr(KnowledgePoint, attr), f"KnowledgePoint 缺列 {attr}"
    for attr in ("started_at", "duration_ms", "seq", "difficulty", "created_at"):
        assert hasattr(AttemptAnswer, attr), f"AttemptAnswer 缺列 {attr}"


def test_s2_m1_question_kp_map_crud(client):
    """question_kp_map 可插入/查询/删除，唯一约束生效。"""
    from app.database import SessionLocal
    db = SessionLocal()
    kp = KnowledgePoint(
        subject="数学", grade=7, unit="七上·第1章", title="有理数加法(S2测试)",
        parent_id=0, code="M7U1-S2TEST", sort_order=1, status="active",
        textbook_ver="人教版", updated_at=None,
    )
    db.add(kp)
    db.flush()

    m = QuestionKpMap(
        source_table="questions", question_id=990001, kp_id=kp.id,
        is_primary=1, weight=1.00, source="manual", confidence=1.000,
        annotated_by="tester", reviewed_by="", status="active",
    )
    db.add(m)
    db.commit()

    got = db.query(QuestionKpMap).filter_by(question_id=990001).first()
    assert got is not None
    assert got.kp_id == kp.id
    assert float(got.weight) == 1.00
    assert got.is_primary == 1

    # 唯一约束：同 (source_table, question_id, kp_id) 再插应抛 IntegrityError
    from sqlalchemy.exc import IntegrityError
    dup = QuestionKpMap(
        source_table="questions", question_id=990001, kp_id=kp.id,
        is_primary=0, weight=0.50, source="ai_pred", confidence=0.820,
        annotated_by="ai", reviewed_by="", status="active",
    )
    db.add(dup)
    try:
        db.commit()
        raise AssertionError("唯一约束 uq_qkm 未生效")
    except IntegrityError:
        db.rollback()

    # 清理
    db.query(QuestionKpMap).filter_by(question_id=990001).delete()
    db.delete(kp)
    db.commit()
    db.close()


def test_s2_m1_migrations_idempotent(client):
    """迁移 053/054 已应用，再次 run_migrations 不报错（幂等）。"""
    from app.migrations.runner import run_migrations
    executed = run_migrations()
    assert isinstance(executed, list)
    # 053/054 此前已在 lifespan 启动时应用，再次运行不应被再次列入执行
    assert "053_kp_map" not in executed
    assert "054_attempt_duration" not in executed
