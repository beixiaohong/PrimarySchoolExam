"""每日任务模型：强制任务 + 可选任务双轨"""
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, UniqueConstraint

from ..database import Base


class DailyTask(Base):
    """用户每日任务（强制 3 条 + 可选 3 条）"""
    __tablename__ = "daily_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "task_date", "task_code",
                         name="uq_user_date_taskcode"),
        {"comment": "每日任务：强制任务+可选任务双轨，每用户每天每任务类型一条"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    task_date = Column(Date, nullable=False, index=True, comment="任务日期")
    subject = Column(String(20), nullable=False, comment="学科：数学/语文/英语")
    task_code = Column(String(50), nullable=False, comment="任务类型编码")
    title = Column(String(100), nullable=False, comment="任务标题")
    target = Column(Integer, default=1, comment="目标数量")
    progress = Column(Integer, default=0, comment="当前进度")
    status = Column(String(20), default="pending", comment="pending/done")
    manual = Column("manual", Boolean, default=False, quote=True,
                    comment="True=需要手动确认完成（manual 为 MySQL 保留字，quote 强制加引号）")
    task_type = Column(String(20), default="mandatory", comment="mandatory/optional")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
