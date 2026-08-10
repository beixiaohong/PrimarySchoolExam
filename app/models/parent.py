"""家长功能模型：密码 / 试卷最少题数 / 家长消息 / 任务设置（011 迁移建表）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from ..database import Base


class ParentPassword(Base):
    """家长密码（按孩子 user_id 一份），密保用于忘记密码时重置"""
    __tablename__ = "parent_passwords"
    __table_args__ = {"comment": "家长密码：按孩子 user_id 一份，密保问答用于忘记密码时重置"}

    user_id = Column(String(50), primary_key=True, comment="用户名（主键）")
    password_hash = Column(String(200), nullable=False, comment="密码哈希")
    hint_question = Column(String(100), nullable=False, comment="密保问题")
    hint_answer_hash = Column(String(200), nullable=False, comment="密保答案哈希")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class ExamMinCount(Base):
    """每科试卷最少题数（生成试卷时强制下限）+ 难度下限（防刷）"""
    __tablename__ = "exam_min_counts"
    __table_args__ = {"comment": "试卷防刷配置：每科最少题数+难度下限，由家长设置"}

    user_id = Column(String(50), primary_key=True, comment="用户名（主键）")
    math_min = Column(Integer, default=5, comment="数学卷最少题数")
    chi_min = Column(Integer, default=5, comment="语文卷最少题数")
    eng_min = Column(Integer, default=5, comment="英语卷最少题数")
    difficulty_min = Column(String(10), default="基础",
                            comment="试卷难度下限：基础/提高/拔高（综合卷不受限）")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class ParentMessage(Base):
    """家长发给孩子的留言"""
    __tablename__ = "parent_messages"
    __table_args__ = {"comment": "家长留言：家长发给孩子的消息，支持已读标记"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    content = Column(String(300), nullable=False, comment="留言内容")
    read_at = Column(DateTime, nullable=True, comment="孩子阅读时间（空=未读）")
    created_at = Column(DateTime, default=datetime.now, comment="发送时间")


class ParentTaskSettings(Base):
    """家长任务配置（每用户一行 JSON，008 迁移建表，补模型供 MySQL 基线建表）"""
    __tablename__ = "parent_task_settings"
    __table_args__ = {"comment": "家长任务配置：每用户一行 JSON，覆盖各任务的目标数量"}

    user_id = Column(String(50), primary_key=True, comment="用户名（与每日任务表一致，主键）")
    settings_json = Column(Text, nullable=False, default="{}",
                           comment='JSON：{"task_code": target}，只存与默认值不同的项')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
