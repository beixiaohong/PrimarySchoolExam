"""家长自定义每日任务：集成进每日任务（强制/可选），由家长确认完成

与旧版「孩子创建、家长确认」的 custom_tasks 不同：
- 此处为家长在任务设置中定义，直接出现在每日任务列表的「强制」或「可选」区；
- 任务为手动确认（manual=True），完成需家长在家长面板点「确认完成」；
- 可添加多个，按天循环出现，家长删除后次日不再生成。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from ..database import Base


class ParentCustomTask(Base):
    """家长定义的自定义每日任务（持久定义，每日注入 daily_tasks）"""
    __tablename__ = "parent_custom_tasks"
    __table_args__ = {"comment": "家长自定义每日任务：集成进每日任务强制/可选区，由家长确认完成"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    title = Column(String(100), nullable=False, comment="任务标题")
    subject = Column(String(20), default="其他", comment="学科：数学/语文/英语/其他")
    task_type = Column(String(20), default="optional", comment="mandatory(强制)/optional(可选)")
    target = Column(Integer, default=1, comment="每天完成数量（手动确认一般=1）")
    sort_order = Column(Integer, default=0, comment="排序权重，小的在前")
    active = Column(Boolean, default=True, comment="是否生效（删除=置 false）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
