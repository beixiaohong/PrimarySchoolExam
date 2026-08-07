"""金币宠物模型（对应迁移 016 建表）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class CoinLedger(Base):
    """金币流水：余额 = SUM(amount)，发币为正、消费为负"""
    __tablename__ = "coin_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    reason = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class PetProfile(Base):
    """宠物档案（每用户一只）"""
    __tablename__ = "pet_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, unique=True, index=True)
    pet_key = Column(String(20), nullable=False, default="qicai")
    level = Column(Integer, nullable=False, default=1)
    exp = Column(Integer, nullable=False, default=0)
    pats_today = Column(Integer, nullable=False, default=0)
    pat_date = Column(String(10), nullable=True)
    feeds_today = Column(Integer, nullable=False, default=0)
    feed_date = Column(String(10), nullable=True)
    fed_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now)
