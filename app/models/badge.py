"""成就徽章模型（对应迁移 017 建表）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from ..database import Base


class BadgeEarned(Base):
    """用户已获得的徽章（首次达成时间）"""
    __tablename__ = "badge_earned"
    __table_args__ = (
        UniqueConstraint("user_id", "badge_code", name="uq_user_badge"),
        {"comment": "成就徽章：每用户每徽章一条，记录首次达成时间"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户标识")
    badge_code = Column(String(40), nullable=False, comment="徽章编码")
    earned_at = Column(DateTime, default=datetime.now, comment="首次达成时间")
