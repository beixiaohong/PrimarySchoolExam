"""账本模块 SQLAlchemy 模型

定义个人账本系统的数据库表结构：交易账单(Bill)、支付账户(Account)、
地点(Location)、商户(Merchant)、人员(Person)、项目(Project)、三级分类(Category)、
通知记录(NotificationLog)、报告设置(UserReportSettings)、周期性交易(RecurringTransaction)，
以及交易类型/账户类型等枚举。所有账户级数据均按 user_id 隔离。
"""
from sqlalchemy import Column, Boolean, Integer, String, Text, Enum, Float, ForeignKey, DateTime, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum
from decimal import Decimal

# ================================ 枚举定义 ================================
class TransactionType(str, enum.Enum):
    """交易类型枚举"""
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"

class AccountType(str, enum.Enum):
    """账户类型枚举 - 一级分类"""
    SAVINGS_CARD = "savings_card"
    CREDIT_CARD = "credit_card"
    VIRTUAL_ACCOUNT = "virtual_account"

class ReportPeriod(str, enum.Enum):
    """报告周期枚举"""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"

class CategoryType(str, enum.Enum):
    """分类类型枚举"""
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"

class NotificationStatus(str, enum.Enum):
    """通知状态枚举"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"

# ================================ 数据库模型定义 ================================

class Bill(Base):
    """交易账单表 - 记录每一笔收支/转账明细，并关联账户、分类、地点等维度。"""
    __tablename__ = "db_ledger_bills"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    transaction_type = Column(Enum(TransactionType), comment="交易类型：收入/支出/转账")
    amount = Column(Numeric(15, 2), comment="交易金额，精确到分")
    category_id = Column(Integer, ForeignKey("db_ledger_categories.id"), comment="收支分类ID") 
    from_account_id = Column(Integer, ForeignKey("db_ledger_accounts.id"), comment="支出账户ID（支出/转账的源账户）")
    to_account_id = Column(Integer, ForeignKey("db_ledger_accounts.id"), nullable=True, comment="收入账户ID（仅转账时使用）")
    location_id = Column(Integer, ForeignKey("db_ledger_locations.id"), nullable=True, comment="支付地点ID")
    merchant_id = Column(Integer, ForeignKey("db_ledger_merchants.id"), nullable=True, comment="支付商户ID")
    person_id = Column(Integer, ForeignKey("db_ledger_persons.id"), nullable=True, comment="相关人员ID")
    project_id = Column(Integer, ForeignKey("db_ledger_projects.id"), nullable=True, comment="关联项目ID")
    note = Column(Text, nullable=True, comment="备注信息")
    transaction_time = Column(DateTime, default=datetime.now, comment="交易发生时间")
    created_at = Column(DateTime, default=datetime.now, comment="记录创建时间")


    # 关联关系
    user = relationship("User")
    category = relationship("Category")
    from_account = relationship("Account", foreign_keys=[from_account_id])
    to_account = relationship("Account", foreign_keys=[to_account_id])
    location = relationship("Location")
    merchant = relationship("Merchant")
    person = relationship("Person")
    project = relationship("Project")


class Account(Base):
    """支付账户表 - 用户的一类资金账户（储蓄卡/信用卡/虚拟账户），保存实时余额。"""
    __tablename__ = "db_ledger_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, comment="所属用户ID")
    account_name = Column(String(100), comment="账户名称，如'工资卡'、'零钱包'等")
    account_type = Column(Enum(AccountType), comment="账户类型：储蓄卡/信用卡/虚拟账户")
    account_subtype = Column(String(50), comment="账户子类型，如'招商银行'、'支付宝'等")
    account_number = Column(String(50), comment="账户号码，如银行卡号、支付宝账号等")
    balance = Column(Numeric(15, 2), default=0, comment="账户余额，精确到分")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    user = relationship("User")


class Location(Base):
    """支付地点表 - 用户常用的消费地点（如家附近超市、公司楼下）。"""
    __tablename__ = "db_ledger_locations"

    id = Column(Integer, primary_key=True, index=True, comment="地点唯一标识")
    user_id = Column(String(36), ForeignKey("users.user_id"), comment="所属用户ID")
    name = Column(String(100), comment="地点名称，如'家附近超市'、'公司楼下'")
    address = Column(String(200), comment="详细地址")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class Merchant(Base):
    """支付商户表 - 用户常用的收款/消费商户（如沃尔玛、星巴克）。"""
    __tablename__ = "db_ledger_merchants"

    id = Column(Integer, primary_key=True, index=True, comment="商户唯一标识")
    user_id = Column(String(36), ForeignKey("users.user_id"), comment="所属用户ID")
    name = Column(String(100), comment="商户名称，如'沃尔玛'、'星巴克'")
    description = Column(String(200), comment="商户描述，如经营范围、特色等")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class Person(Base):
    """相关人员表 - 交易中涉及的自然人（如朋友、同事、家人）。"""
    __tablename__ = "db_ledger_persons"

    id = Column(Integer, primary_key=True, index=True, comment="人员唯一标识")
    user_id = Column(String(36), ForeignKey("users.user_id"), comment="所属用户ID")
    name = Column(String(50), comment="人员姓名")
    phone = Column(String(20), comment="联系电话")
    relationship = Column(String(50), comment="与用户关系，如'朋友'、'同事'、'家人'")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class Project(Base):
    """关联项目表 - 可绑定预算的专项（如装修、旅游、学习），用于预算统计。"""
    __tablename__ = "db_ledger_projects"

    id = Column(Integer, primary_key=True, index=True, comment="项目唯一标识")
    user_id = Column(String(36), ForeignKey("users.user_id"), comment="所属用户ID")
    name = Column(String(100), comment="项目名称，如'装修'、'旅游'、'学习'")
    description = Column(String(200), comment="项目描述")
    budget = Column(Numeric(15, 2), nullable=True, comment="项目预算金额")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class Category(Base):
    """收支分类表 - 三级分类体系"""
    __tablename__ = "db_ledger_categories"
    
    id = Column(Integer, primary_key=True, index=True, comment="分类唯一标识") 
    user_id = Column(String(36), ForeignKey("users.user_id"), comment="所属用户ID")
    category_type = Column(Enum(CategoryType), default=CategoryType.EXPENSE, comment="分类类型：收入/支出")
    level1 = Column(String(50), comment="一级分类，如'食品'、'交通'、'娱乐'")
    level2 = Column(String(50), nullable=True, comment="二级分类，如'饮食'、'打车'、'电影'")
    level3 = Column(String(50), nullable=True, comment="三级分类，如'三餐'、'滴滴'、'院线'")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class NotificationLog(Base):
    """通知记录表 - 记录推送消息历史"""
    __tablename__ = "db_ledger_notification_logs"
    
    id = Column(Integer, primary_key=True, index=True, comment="通知记录唯一标识")
    user_id = Column(String(36), ForeignKey("users.user_id"), comment="用户ID")
    report_period = Column(Enum(ReportPeriod), comment="报告周期：周报/月报/年报")
    period_start = Column(DateTime, comment="统计周期开始时间")
    period_end = Column(DateTime, comment="统计周期结束时间")
    report_content = Column(Text, comment="报告内容JSON格式")
    status = Column(Enum(NotificationStatus), default=NotificationStatus.PENDING, comment="发送状态")
    sent_at = Column(DateTime, nullable=True, comment="发送时间")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    user = relationship("User")


class UserReportSettings(Base):
    """用户报告设置表 - 个性化推送配置"""
    __tablename__ = "db_ledger_user_report_settings"
    
    id = Column(Integer, primary_key=True, index=True, comment="设置唯一标识")
    user_id = Column(String(36), ForeignKey("users.user_id"), unique=True, comment="用户ID")
    weekly_day = Column(Integer, default=1, comment="周报推送日期(1-7,1为周一)")
    monthly_day = Column(Integer, default=1, comment="月报推送日期(1-28)")
    yearly_month = Column(Integer, default=1, comment="年报推送月份(1-12)")
    yearly_day = Column(Integer, default=1, comment="年报推送日期(1-28)")
    include_charts = Column(Boolean, default=True, comment="是否包含图表")
    include_comparison = Column(Boolean, default=True, comment="是否包含同比环比")
    include_recommendations = Column(Boolean, default=True, comment="是否包含理财建议")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    user = relationship("User")


class RecurringTransaction(Base):
    """周期性交易表 - 自动记录固定支出（房租、订阅等）"""
    __tablename__ = "db_ledger_recurring_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    name = Column(String(100), comment="周期性交易名称，如'房租'、'Netflix订阅'")
    transaction_type = Column(Enum(TransactionType), default=TransactionType.EXPENSE, comment="交易类型")
    amount = Column(Numeric(15, 2), comment="交易金额")
    from_account_id = Column(Integer, ForeignKey("db_ledger_accounts.id"), comment="付款账户")
    category_id = Column(Integer, ForeignKey("db_ledger_categories.id"), nullable=True, comment="分类")
    merchant_id = Column(Integer, ForeignKey("db_ledger_merchants.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("db_ledger_projects.id"), nullable=True)
    note = Column(Text, nullable=True, comment="备注")
    frequency = Column(String(20), comment="频率: daily/weekly/monthly/yearly")
    next_run = Column(DateTime, comment="下次执行时间")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User")
    from_account = relationship("Account", foreign_keys=[from_account_id])
    category = relationship("Category")
