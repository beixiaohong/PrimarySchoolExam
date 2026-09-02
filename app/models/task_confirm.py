"""完成确认模型：孩子提交学习任务完成 → 家长确认/拒绝（含理由）

流程：
- 孩子完成背诵等学习任务后，前端调用 /create 生成一条 status=pending 的确认请求；
- 首页「完成确认」区块展示全部记录（待确认/已通过/已拒绝），家长模式开启时可操作；
- 家长调用 /resolve 进行 confirm（通过）或 reject（拒绝，必须填写理由）。

状态机（与补签卡 MakeupUsageLog、家长自定义任务共用同一套命名）：
- pending   ：待家长确认
- confirmed ：家长已通过
- rejected ：家长已拒绝（reject_reason 非空）
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class TaskConfirm(Base):
    """孩子提交的任务完成确认请求"""
    __tablename__ = "task_confirms"
    __table_args__ = {"comment": "孩子提交的任务完成确认：家长确认/拒绝（含理由）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    task_type = Column(String(30), nullable=False, default="recite",
                       comment="任务类型：recite_word 背单词 / recite_text 背古诗文 / daily 每日任务")
    title = Column(String(100), nullable=False, default="学习任务完成", comment="展示标题")
    summary = Column(String(255), nullable=False, default="", comment="展示摘要，如「新词 10 个 · 复习 3 个」")
    status = Column(String(20), nullable=False, default="pending",
                    comment="pending 待确认 / confirmed 已通过 / rejected 已拒绝")
    reject_reason = Column(String(255), nullable=True, comment="家长拒绝理由（reject 时必填）")
    created_at = Column(DateTime, default=datetime.now, comment="提交时间")
    resolved_at = Column(DateTime, nullable=True, comment="家长处理时间")
