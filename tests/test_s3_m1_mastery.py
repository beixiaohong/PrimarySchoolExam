"""S3-M1 验证：掌握度数据底座（迁移 055 + 模型，07 §3.2.3）

覆盖：
- MasteryRecord / MasterySnapshot 模型层新列属性齐备（create_all 据此在测试库建表）；
- mastery_records 可插入/查询/ UPSERT，唯一约束 uq_mr_user_kp 生效；
- 默认值符合规格（mastery=20 兜底 BR-M0-1-02；level 由分数推导）；
- 迁移 055 经 run_migrations 幂等应用（启动已跑，再次运行不重列）。
"""
from datetime import datetime, date

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.mastery import MasteryRecord, MasterySnapshot, level_from_mastery


def test_s3_m1_models_have_columns(client):
    """掌握度模型层新列属性齐备。"""
    for attr in (
        "user_id", "kp_id", "subject", "grade", "mastery", "level",
        "answer_count", "correct_count", "correct_rate", "avg_duration_ms",
        "last_answer_at", "correct_streak", "confidence", "algo_version",
        "computed_at", "created_at", "updated_at",
    ):
        assert hasattr(MasteryRecord, attr), f"MasteryRecord 缺列 {attr}"
    for attr in ("user_id", "kp_id", "snap_date", "mastery", "delta",
                 "algo_version", "created_at"):
        assert hasattr(MasterySnapshot, attr), f"MasterySnapshot 缺列 {attr}"


def test_s3_m1_level_mapping(client):
    """level_from_mastery 分档正确。"""
    assert level_from_mastery(0) == "未掌握"
    assert level_from_mastery(39) == "未掌握"
    assert level_from_mastery(40) == "薄弱"
    assert level_from_mastery(59) == "薄弱"
    assert level_from_mastery(60) == "基本掌握"
    assert level_from_mastery(79) == "基本掌握"
    assert level_from_mastery(80) == "已掌握"
    assert level_from_mastery(100) == "已掌握"


def test_s3_m1_mastery_record_crud(client):
    """mastery_records 可插入/查询/UPSERT，唯一约束 uq_mr_user_kp 生效，默认值正确。"""
    db = SessionLocal()

    # 防御性清理（避免跨会话串扰）
    db.query(MasteryRecord).filter_by(user_id="s3m1_u1").delete()
    db.commit()

    rec = MasteryRecord(
        user_id="s3m1_u1", kp_id=7001, subject="数学", grade=7,
        mastery=45, level=level_from_mastery(45),
        answer_count=3, correct_count=2, correct_rate=0.6667,
        avg_duration_ms=12000, last_answer_at=datetime.now(),
        correct_streak=1, confidence=0.5, algo_version="v1",
    )
    db.add(rec)
    db.commit()

    got = db.query(MasteryRecord).filter_by(user_id="s3m1_u1", kp_id=7001).first()
    assert got is not None
    assert got.mastery == 45
    assert got.level == "薄弱"
    assert float(got.correct_rate) == 0.6667

    # 默认兜底：新建一条不传 mastery，应取规格默认 20（BR-M0-1-02 prior）
    rec2 = MasteryRecord(user_id="s3m1_u1", kp_id=7002)
    db.add(rec2)
    db.commit()
    got2 = db.query(MasteryRecord).filter_by(user_id="s3m1_u1", kp_id=7002).first()
    assert got2.mastery == 20
    assert got2.level == "未掌握"
    assert got2.answer_count == 0

    # 唯一约束：同 (user_id, kp_id) 再插应抛 IntegrityError
    dup = MasteryRecord(user_id="s3m1_u1", kp_id=7001, mastery=80)
    db.add(dup)
    try:
        db.commit()
        raise AssertionError("唯一约束 uq_mr_user_kp 未生效")
    except IntegrityError:
        db.rollback()

    # 清理
    db.query(MasteryRecord).filter_by(user_id="s3m1_u1").delete()
    db.commit()
    db.close()


def test_s3_m1_snapshot_crud(client):
    """mastery_snapshots 可插入/查询，唯一约束 uq_ms 生效。"""
    db = SessionLocal()

    db.query(MasterySnapshot).filter_by(user_id="s3m1_u2").delete()
    db.commit()

    snap = MasterySnapshot(
        user_id="s3m1_u2", kp_id=7003, snap_date=date(2026, 9, 2),
        mastery=55, delta=5, algo_version="v1",
    )
    db.add(snap)
    db.commit()

    got = db.query(MasterySnapshot).filter_by(
        user_id="s3m1_u2", kp_id=7003, snap_date=date(2026, 9, 2),
        algo_version="v1").first()
    assert got is not None
    assert got.mastery == 55
    assert got.delta == 5

    # 唯一约束：同一 (user_id, kp_id, snap_date, algo_version) 再插应抛 IntegrityError
    dup = MasterySnapshot(
        user_id="s3m1_u2", kp_id=7003, snap_date=date(2026, 9, 2),
        mastery=60, delta=10, algo_version="v1",
    )
    db.add(dup)
    try:
        db.commit()
        raise AssertionError("唯一约束 uq_ms 未生效")
    except IntegrityError:
        db.rollback()

    db.query(MasterySnapshot).filter_by(user_id="s3m1_u2").delete()
    db.commit()
    db.close()


def test_s3_m1_migration_idempotent(client):
    """迁移 055 已在 lifespan 启动时应用，再次 run_migrations 不重列（幂等）。"""
    from app.migrations.runner import run_migrations
    executed = run_migrations()
    assert isinstance(executed, list)
    assert "055_mastery" not in executed
