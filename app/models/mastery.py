"""掌握度模型（S3-M1 / 07-技术实施方案 §3.2.3 / 迁移 055）

「学生 × 知识点」掌握度矩阵的数据底座：
- `mastery_records`：每个 (user_id, kp_id) 一条掌握度记录，支持增量 UPSERT；
- `mastery_snapshots`：每日/每周快照，用于趋势曲线与「掌握度提升量」北极星指标。

设计要点：
- `mastery` 默认 20（BR-M0-1-02：未作答知识点按 prior=20 兜底，不污染计算）；
- `level` 由 `mastery` 推导（未掌握/薄弱/基本掌握/已掌握），纯函数 `level_from_mastery`；
- `duration_ms = 0` 视为「无用时数据」，用时因子取中性值 1.0（07 §3.2.2）；
- 持连铁律：本模型仅为存储结构，计算逻辑在 `app/domains/engine/services/mastery.py`
  （纯 DB 计算，无外部阻塞调用）。
"""
from datetime import datetime

from sqlalchemy import (BigInteger, Column, Date, DateTime, Index, Integer,
                        Numeric, SmallInteger, String, UniqueConstraint)

from ..database import Base


def level_from_mastery(mastery: int) -> str:
    """纯函数：掌握度分数(0-100) → 等级档位。

    与 `mastery_records.level` 列语义一致，算法层用以落库、接口层用以展示。
    """
    if mastery < 40:
        return "未掌握"
    if mastery < 60:
        return "薄弱"
    if mastery < 80:
        return "基本掌握"
    return "已掌握"


class MasteryRecord(Base):
    """掌握度记录：每个 (user_id, kp_id) 一条，支持增量 UPSERT（07 §3.2.3）"""
    __tablename__ = "mastery_records"
    __table_args__ = (
        UniqueConstraint("user_id", "kp_id", name="uq_mr_user_kp"),
        Index("idx_mr_user_subj", "user_id", "subject"),
        Index("idx_mr_mastery", "user_id", "mastery"),
        Index("idx_mr_computed", "computed_at"),
        {"comment": "掌握度记录：学生×知识点 矩阵（增量 UPSERT）"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户ID")
    kp_id = Column(Integer, nullable=False, comment="知识点ID")
    subject = Column(String(32), nullable=False, default="", comment="学科（冗余，便于按学科聚合）")
    grade = Column(Integer, nullable=False, default=0, comment="年级")
    mastery = Column(SmallInteger, nullable=False, default=20, comment="掌握度 0-100")
    level = Column(String(16), nullable=False, default="未掌握",
                   comment="等级：未掌握/薄弱/基本掌握/已掌握")
    answer_count = Column(Integer, nullable=False, default=0, comment="参与计算的作答次数")
    correct_count = Column(Integer, nullable=False, default=0, comment="正确次数")
    correct_rate = Column(Numeric(5, 4), nullable=False, default=0, comment="加权正确率")
    avg_duration_ms = Column(Integer, nullable=False, default=0, comment="平均用时(ms)，0=无用时数据")
    last_answer_at = Column(DateTime, nullable=True, comment="最近一次作答时间")
    correct_streak = Column(Integer, nullable=False, default=0, comment="连续正确次数")
    confidence = Column(Numeric(4, 3), nullable=False, default=0, comment="样本置信度 0-1")
    algo_version = Column(String(16), nullable=False, default="v1", comment="算法版本")
    computed_at = Column(DateTime, nullable=False, default=datetime.now, comment="计算时间")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=True, comment="更新时间")

    def __repr__(self):
        return f"<MasteryRecord {self.user_id} kp:{self.kp_id} mastery:{self.mastery}>"


class MasterySnapshot(Base):
    """掌握度快照：每日/每周对 (user_id, kp_id) 的掌握度定点留存（07 §3.2.3）"""
    __tablename__ = "mastery_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "kp_id", "snap_date", "algo_version", name="uq_ms"),
        Index("idx_ms_date", "snap_date"),
        {"comment": "掌握度快照：趋势曲线与提升量指标"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户ID")
    kp_id = Column(Integer, nullable=False, comment="知识点ID")
    snap_date = Column(Date, nullable=False, comment="快照日期")
    mastery = Column(SmallInteger, nullable=False, default=20, comment="当日掌握度 0-100")
    delta = Column(SmallInteger, nullable=False, default=0, comment="相对上一次快照的变化量")
    algo_version = Column(String(16), nullable=False, default="v1", comment="算法版本")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<MasterySnapshot {self.user_id} kp:{self.kp_id} {self.snap_date} m:{self.mastery}>"
