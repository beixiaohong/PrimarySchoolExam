"""S3-M5 验证：增量触发 + 离线重算脚本（07 §5.1.1 / C8）

覆盖：
- recompute_user_mastery + generate_snapshots：重算写 mastery_records，快照 UPSERT 且 delta 正确；
- trigger_incremental_recompute：fire-and-forget（同步 executor 验证实际落库，无外部调用）；
- tools/recompute_mastery.py --dry-run：CLI + 活跃用户查询可跑（只读，连测试库）。

build_answer_records 用 monkeypatch 注入，避免 ExamRecord→Question→ExamAttempt→AttemptAnswer 长 FK 链。
"""
from datetime import datetime

from app.database import SessionLocal
from app.domains.engine.services import mastery_store
from app.domains.engine.services.mastery import AnswerRecord
from app.models.knowledge import KnowledgePoint
from app.models.mastery import MasteryRecord, MasterySnapshot


def _seed_kp(db, kp_id):
    db.query(KnowledgePoint).filter_by(id=kp_id).delete()
    db.commit()
    db.add(KnowledgePoint(id=kp_id, subject="数学", grade=7, unit="", title=f"kp{kp_id}",
                          parent_id=0, status="active", textbook_ver=""))
    db.commit()


def test_s3_m5_recompute_and_snapshot(client, monkeypatch):
    db = SessionLocal()
    db.query(MasteryRecord).filter_by(user_id="s3m5_u").delete()
    db.query(MasterySnapshot).filter_by(user_id="s3m5_u").delete()
    _seed_kp(db, 74001)
    kp = 74001

    def fake_ok(db, user_id, limit=1000):
        return {kp: [AnswerRecord(answered_at=datetime(2026, 9, 1), is_correct=True,
                                  duration_ms=10000, difficulty=4, kp_id=kp)]}

    monkeypatch.setattr(mastery_store, "build_answer_records", fake_ok)
    n = mastery_store.recompute_user_mastery(db, "s3m5_u")
    assert n == 1
    mr = db.query(MasteryRecord).filter_by(user_id="s3m5_u", kp_id=kp).first()
    m1 = mr.mastery

    snap_n = mastery_store.generate_snapshots(db, user_ids=["s3m5_u"])
    assert snap_n == 1
    snap = db.query(MasterySnapshot).filter_by(user_id="s3m5_u", kp_id=kp).first()
    assert snap.mastery == m1
    assert snap.delta == m1                      # 无历史快照 → delta = mastery

    # 改为全错后重算并再生成快照
    def fake_bad(db, user_id, limit=1000):
        return {kp: [AnswerRecord(answered_at=datetime(2026, 9, 2), is_correct=False,
                                  duration_ms=10000, difficulty=4, kp_id=kp)]}

    monkeypatch.setattr(mastery_store, "build_answer_records", fake_bad)
    mastery_store.recompute_user_mastery(db, "s3m5_u")
    snap_n2 = mastery_store.generate_snapshots(db, user_ids=["s3m5_u"])
    assert snap_n2 == 1
    snap2 = db.query(MasterySnapshot).filter_by(user_id="s3m5_u", kp_id=kp).first()
    assert snap2.mastery < m1
    assert snap2.delta == snap2.mastery - m1      # delta = 本次 - 上次

    db.query(MasteryRecord).filter_by(user_id="s3m5_u").delete()
    db.query(MasterySnapshot).filter_by(user_id="s3m5_u").delete()
    db.query(KnowledgePoint).filter_by(id=kp).delete()
    db.commit()
    db.close()


def test_s3_m5_trigger_incremental(client, monkeypatch):
    """trigger_incremental_recompute 经线程池 fire-and-forget；同步 executor 验证实际落库。"""
    class _SyncExec:
        def submit(self, fn):
            fn()  # 同步执行，便于断言
            return None

    monkeypatch.setattr(mastery_store, "_recompute_executor", _SyncExec())

    db = SessionLocal()
    db.query(MasteryRecord).filter_by(user_id="s3m5_t").delete()
    _seed_kp(db, 74002)
    kp = 74002

    def fake_ok(db, user_id, limit=1000):
        return {kp: [AnswerRecord(answered_at=datetime(2026, 9, 1), is_correct=True,
                                  duration_ms=10000, difficulty=3, kp_id=kp)]}

    monkeypatch.setattr(mastery_store, "build_answer_records", fake_ok)
    mastery_store.trigger_incremental_recompute("s3m5_t")  # 同步执行
    mr = db.query(MasteryRecord).filter_by(user_id="s3m5_t", kp_id=kp).first()
    # 单条正确作答（difficulty=3）会被 prior_weight=2.0 拉向 prior=20，实测约 52；
    # 此处只验证「高于先验兜底 20 且已落库」即可证明增量触发生效，不卡具体档位。
    assert mr is not None and mr.mastery >= 50

    db.query(MasteryRecord).filter_by(user_id="s3m5_t").delete()
    db.query(KnowledgePoint).filter_by(id=kp).delete()
    db.commit()
    db.close()


def test_s3_m5_script_dry_run(client, monkeypatch):
    """离线脚本 --dry-run：CLI 解析 + 活跃用户查询可跑（只读，连测试库，不写）。"""
    import sys
    import tools.recompute_mastery as script

    monkeypatch.setattr(sys, "argv", ["recompute_mastery.py", "--dry-run"])
    script.main()  # 不应抛异常；仅统计 active_users
