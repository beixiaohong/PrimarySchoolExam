"""自定义任务模型：孩子创建，家长确认（DEPRECATED 已废弃，保留待复活）

废弃说明（2026-09-02 核对）：
- 本模型对应孩子端 /api/tasks/custom 系列接口，前端 web/src 与 admin/src 均无引用，
  库内 custom_tasks 表 0 行（无历史数据），属历史遗留死代码。
- 现行方案请用 ParentCustomTask（表 parent_custom_tasks）：家长在任务设置中定义，
  注入每日任务的强制/可选区，由家长手动确认完成，见 app/models/parent_custom_task.py。
- 保留本模型与表，便于日后若需复活孩子端任务可直接复用，勿在其上新增逻辑。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class CustomTask(Base):
    """孩子自定义每日任务"""
    __tablename__ = "custom_tasks"
    __table_args__ = {"comment": "自定义任务：孩子创建，家长确认后生效"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    title = Column(String(100), nullable=False, comment="任务标题")
    subject = Column(String(20), default="其他", comment="学科分类")
    # status 取值：pending=待家长确认，confirmed=已确认生效，rejected=已拒绝
    status = Column(String(20), default="pending", comment="pending/confirmed/rejected")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    confirmed_at = Column(DateTime, nullable=True, comment="家长确认时间")
