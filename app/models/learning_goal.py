"""学习目标管理台数据模型（有终点、有总量的学习目标，区别于无限期习惯打卡）

三张表：
- learning_goals        ：目标定义（名称/单位/总量/截止日/配色/障碍/对策）
- learning_checkins     ：每日打卡记录（真实日期/完成量/投入分钟/是否补记；一天可多条）
- learning_weekly_reviews：每周复盘（周一起始日 + 保持/问题/尝试/下周预案 四栏）

所有表均按 user_id 隔离；写操作即时落库（页面读写都走线上数据）。
"""
from datetime import datetime, date

from sqlalchemy import (
    Column, Date, DateTime, Integer, String, Text, Float, Boolean,
)

from ..database import Base


class LearningGoal(Base):
    """学习目标（有终点、有总量）。

    示例：背完 2000 个单词 / 读完一本 440 页的书 / 学完 Python 入门课。
    current（已完成量）不冗余存储，统一由 learning_checkins 聚合得出，避免补记/删除后不一致。
    """

    __tablename__ = "learning_goals"
    __table_args__ = {"comment": "学习目标管理台：有终点/有总量的学习目标"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名（账号绑定）")

    name = Column(String(100), nullable=False, comment="目标名称")
    unit = Column(String(20), default="个", comment="单位（个/页/课/题…）")
    total = Column(Float, nullable=False, default=0, comment="总量")
    deadline = Column(Date, nullable=True, comment="截止日（YYYY-MM-DD）；空=无截止日")
    color = Column(String(20), default="purple", comment="配色主题（purple/blue/green/amber/red/teal）")

    # 两个选填字段：最容易拦住我的障碍 / "如果它出现，我就……"的对策
    obstacle = Column(Text, default="", comment="最容易拦住我的障碍（选填）")
    counter = Column(Text, default="", comment="如果障碍出现就……的对策（选填）")

    status = Column(String(20), default="active", comment="active/archived/done")
    achieved_at = Column(DateTime, nullable=True, comment="达成时间（current>=total 时记录）")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class LearningCheckin(Base):
    """每日打卡记录（一天可多条；支持补记最近 6 天）。"""

    __tablename__ = "learning_checkins"
    __table_args__ = {"comment": "学习目标每日打卡记录"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    goal_id = Column(Integer, nullable=False, index=True, comment="关联目标 id")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名（账号绑定）")

    # 真实日期：补记按真实日期参与连续天数与近 7 天均速推算
    date = Column(Date, nullable=False, index=True, comment="打卡归属日期（YYYY-MM-DD）")
    amount = Column(Float, nullable=False, default=0, comment="本次完成量")
    minutes = Column(Integer, nullable=True, comment="投入分钟数（选填；空=未记录）")
    is_backfill = Column(Boolean, default=False, comment="是否补记（最近 6 天）")

    created_at = Column(DateTime, default=datetime.now, comment="记录创建时间")


class LearningWeeklyReview(Base):
    """每周复盘（周一开始，周一~周日汇总）。"""

    __tablename__ = "learning_weekly_reviews"
    __table_args__ = {"comment": "学习目标每周复盘（四栏：保持/问题/尝试/下周预案）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    # 周起始日（周一，YYYY-MM-DD）；同一用户每周唯一
    week_start = Column(Date, nullable=False, index=True, comment="本周一日期")

    keep = Column(Text, default="", comment="保持（上周做得好的）")
    problem = Column(Text, default="", comment="问题（上周卡住的）")
    try_plan = Column(Text, default="", comment="尝试（本周想试的）")
    next_plan = Column(Text, default="", comment="下周预案")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
