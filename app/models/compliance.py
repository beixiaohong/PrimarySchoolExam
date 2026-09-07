"""合规底座数据模型（CMP / 儿童个人信息保护）

- GuardianConsent：监护人同意记录（CMP-02），注册/首次使用时强制阅读并同意。
- DataExportRequest：数据导出申请（CMP-06），用户可申请导出个人数据（JSON）。
- DataDeletionRequest：数据删除申请（CMP-06），用户可申请删除个人数据。

设计要点：
- consent_at + rule_version 唯一约束，同一规则版本只记录一次同意；
- revoked_at 非空表示已撤回同意；
- 导出/删除请求由后台审批后执行，状态流转：pending → processing → done / rejected。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from ..database import Base


class GuardianConsent(Base):
    """监护人同意记录（CMP-02）"""
    __tablename__ = "guardian_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "rule_version", name="uq_gc_user_version"),
        {"comment": "监护人同意记录（儿童个人信息处理规则）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户ID")
    guardian_name = Column(String(100), nullable=True, comment="监护人姓名")
    consent_at = Column(DateTime, nullable=False, default=datetime.now, comment="同意时间")
    rule_version = Column(String(20), nullable=False, comment="规则版本号，如 v1.0")
    ip_address = Column(String(45), nullable=True, comment="同意时 IP")
    user_agent = Column(Text, nullable=True, comment="同意时 UA")
    revoked_at = Column(DateTime, nullable=True, comment="撤回同意时间（NULL=有效）")


class DataExportRequest(Base):
    """数据导出申请（CMP-06）"""
    __tablename__ = "data_export_requests"
    __table_args__ = {"comment": "数据导出申请（用户申请导出个人数据 JSON）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户ID")
    status = Column(String(20), nullable=False, default="pending",
                    comment="状态：pending/processing/done/rejected")
    result_url = Column(String(500), nullable=True, comment="导出文件 URL（完成后填写）")
    requested_at = Column(DateTime, nullable=False, default=datetime.now, comment="申请时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    note = Column(Text, nullable=True, comment="备注（拒绝原因等）")


class DataDeletionRequest(Base):
    """数据删除申请（CMP-06）"""
    __tablename__ = "data_deletion_requests"
    __table_args__ = {"comment": "数据删除申请（用户申请删除个人数据）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户ID")
    status = Column(String(20), nullable=False, default="pending",
                    comment="状态：pending/processing/done/rejected")
    reason = Column(Text, nullable=True, comment="删除原因")
    requested_at = Column(DateTime, nullable=False, default=datetime.now, comment="申请时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    note = Column(Text, nullable=True, comment="备注（拒绝原因等）")
