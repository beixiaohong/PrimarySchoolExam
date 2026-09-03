"""题目-知识点映射模型（S2-M1 / 07-技术实施方案 §3.2.1 / 迁移 053）

一题可标注多个知识点（主/副），统一覆盖 `questions` / `paper_questions` /
`middle_questions` 三种题源。标注来源 `manual` / `ai_pred` / `batch_import`，
AI 预标注带 `confidence`（置信度）。

设计取舍（见 07 §3.2.1 设计说明）：用独立映射表而非在 `questions` 上加列——
① 一题多知识点；② 三种题源统一标注模型；③ 加列要动 3 张表，映射表只需一张。
`weight` 与 `is_primary` 冗余但有用：`is_primary` 供查询过滤，`weight` 供掌握度
算法计算，避免算法里写魔法值。
"""
from datetime import datetime

from sqlalchemy import (Column, Integer, String, DateTime, Numeric, SmallInteger,
                        UniqueConstraint, Index)

from ..database import Base


class QuestionKpMap(Base):
    """题目-知识点映射：一题多知识点（主/副，覆盖三种题源）"""
    __tablename__ = "question_kp_map"
    __table_args__ = (
        UniqueConstraint("source_table", "question_id", "kp_id", name="uq_qkm"),
        Index("idx_qkm_kp", "kp_id"),
        Index("idx_qkm_src", "source_table", "question_id"),
        {"comment": "题目-知识点映射（一题多知识点；覆盖三种题源）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    source_table = Column(String(32), nullable=False, default="questions",
                          comment="题源表：questions/paper_questions/middle_questions")
    question_id = Column(Integer, nullable=False, comment="题目ID")
    kp_id = Column(Integer, nullable=False, comment="知识点ID")
    is_primary = Column(SmallInteger, nullable=False, default=1,
                        comment="是否主知识点：1=主(权重1.0) 0=副(权重0.5)")
    weight = Column(Numeric(4, 2), nullable=False, default=1.00, comment="权重")
    source = Column(String(16), nullable=False, default="manual",
                    comment="标注来源：manual/ai_pred/batch_import")
    confidence = Column(Numeric(4, 3), nullable=False, default=1.000,
                        comment="AI 预标注置信度")
    annotated_by = Column(String(64), nullable=False, default="", comment="标注人")
    reviewed_by = Column(String(64), nullable=False, default="", comment="复核人")
    status = Column(String(16), nullable=False, default="active",
                    comment="状态：active/deprecated")
    created_at = Column(DateTime, nullable=False, default=datetime.now,
                        comment="创建时间")
    updated_at = Column(DateTime, nullable=True, comment="更新时间")

    def __repr__(self):
        return f"<QuestionKpMap {self.source_table}:{self.question_id} -> kp:{self.kp_id}>"
