"""金币宠物模型（对应迁移 016 建表）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class CoinLedger(Base):
    """金币流水：余额 = SUM(amount)，发币为正、消费为负"""
    __tablename__ = "coin_ledger"
    __table_args__ = {"comment": "金币流水：余额=SUM(amount)，发币为正消费为负"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户标识")
    amount = Column(Integer, nullable=False, comment="变动数量（正=发放，负=消费）")
    reason = Column(String(100), nullable=False, comment="变动原因")
    created_at = Column(DateTime, default=datetime.now, comment="发生时间")


class PetProfile(Base):
    """宠物档案（每用户一只）"""
    __tablename__ = "pet_profiles"
    __table_args__ = {"comment": "宠物档案：每用户一只，金币喂养升级，每日抚摸/喂食次数限制"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, unique=True, index=True, comment="用户标识")
    pet_key = Column(String(20), nullable=False, default="qicai", comment="宠物形象标识")
    level = Column(Integer, nullable=False, default=1, comment="宠物等级")
    exp = Column(Integer, nullable=False, default=0, comment="当前经验值")
    pats_today = Column(Integer, nullable=False, default=0, comment="今日已抚摸次数")
    pat_date = Column(String(10), nullable=True, comment="抚摸计数所属日期")
    feeds_today = Column(Integer, nullable=False, default=0, comment="今日已喂食次数")
    feed_date = Column(String(10), nullable=True, comment="喂食计数所属日期")
    fed_count = Column(Integer, nullable=False, default=0, comment="累计喂食次数")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
