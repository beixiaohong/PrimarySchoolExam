"""账本相关 Pydantic 模型（pydantic v2）

对应 app.models.ledger 的 ORM 行。响应模型使用
`model_config = ConfigDict(from_attributes=True)` 以便从 ORM 对象序列化。
字段名与模型列名保持一致，使 `Model(**schema.model_dump(), user_id=...)`
可以直接构造 ORM 实例。
"""
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ledger import TransactionType, AccountType, CategoryType


# ================================ 账户 ================================
class AccountCreate(BaseModel):
    """创建支付账户请求模型。"""
    account_name: str
    account_type: AccountType
    account_subtype: Optional[str] = None
    account_number: Optional[str] = None
    balance: float = 0


class AccountUpdate(BaseModel):
    """更新支付账户请求模型（字段均可选）。"""
    account_name: Optional[str] = None
    account_type: Optional[AccountType] = None
    account_subtype: Optional[str] = None
    account_number: Optional[str] = None
    balance: Optional[float] = None


class AccountResponse(BaseModel):
    """支付账户响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    account_name: str
    account_type: AccountType
    account_subtype: Optional[str] = None
    account_number: Optional[str] = None
    balance: float = 0
    created_at: Optional[datetime] = None


# ================================ 分类 ================================
class CategoryCreate(BaseModel):
    """创建三级收支分类请求模型。"""
    category_type: CategoryType = CategoryType.EXPENSE
    level1: str
    level2: Optional[str] = None
    level3: Optional[str] = None


class CategoryUpdate(BaseModel):
    """更新收支分类请求模型（字段均可选）。"""
    category_type: Optional[CategoryType] = None
    level1: Optional[str] = None
    level2: Optional[str] = None
    level3: Optional[str] = None


class CategoryResponse(BaseModel):
    """收支分类响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    category_type: CategoryType
    level1: Optional[str] = None
    level2: Optional[str] = None
    level3: Optional[str] = None
    created_at: Optional[datetime] = None


# ================================ 地点 ================================
class LocationCreate(BaseModel):
    """创建支付地点请求模型。"""
    name: str
    address: Optional[str] = None


class LocationUpdate(BaseModel):
    """更新支付地点请求模型（字段均可选）。"""
    name: Optional[str] = None
    address: Optional[str] = None


class LocationResponse(BaseModel):
    """支付地点响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    name: Optional[str] = None
    address: Optional[str] = None
    created_at: Optional[datetime] = None


# ================================ 商户 ================================
class MerchantCreate(BaseModel):
    """创建支付商户请求模型。"""
    name: str
    description: Optional[str] = None


class MerchantUpdate(BaseModel):
    """更新支付商户请求模型（字段均可选）。"""
    name: Optional[str] = None
    description: Optional[str] = None


class MerchantResponse(BaseModel):
    """支付商户响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None


# ================================ 人员 ================================
class PersonCreate(BaseModel):
    """创建相关人员请求模型。"""
    name: str
    phone: Optional[str] = None
    relationship: Optional[str] = None


class PersonUpdate(BaseModel):
    """更新相关人员请求模型（字段均可选）。"""
    name: Optional[str] = None
    phone: Optional[str] = None
    relationship: Optional[str] = None


class PersonResponse(BaseModel):
    """相关人员响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    name: Optional[str] = None
    phone: Optional[str] = None
    relationship: Optional[str] = None
    created_at: Optional[datetime] = None


# ================================ 项目 ================================
class ProjectCreate(BaseModel):
    """创建关联项目请求模型。"""
    name: str
    description: Optional[str] = None
    budget: Optional[float] = None


class ProjectUpdate(BaseModel):
    """更新关联项目请求模型（字段均可选）。"""
    name: Optional[str] = None
    description: Optional[str] = None
    budget: Optional[float] = None


class ProjectResponse(BaseModel):
    """关联项目响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    budget: Optional[float] = None
    created_at: Optional[datetime] = None


# ================================ 交易（账单） ================================
class TransactionCreate(BaseModel):
    """创建交易（记账）请求模型：含交易类型、金额与相关维度ID。"""
    transaction_type: TransactionType
    amount: float
    category_id: Optional[int] = None
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    location_id: Optional[int] = None
    merchant_id: Optional[int] = None
    person_id: Optional[int] = None
    project_id: Optional[int] = None
    note: Optional[str] = None
    transaction_time: Optional[datetime] = None


class TransactionUpdate(BaseModel):
    """更新交易请求模型（字段均可选，仅传需修改项）。"""
    transaction_type: Optional[TransactionType] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    location_id: Optional[int] = None
    merchant_id: Optional[int] = None
    person_id: Optional[int] = None
    project_id: Optional[int] = None
    note: Optional[str] = None
    transaction_time: Optional[datetime] = None


class TransactionResponse(BaseModel):
    """交易响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    transaction_type: Optional[TransactionType] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    location_id: Optional[int] = None
    merchant_id: Optional[int] = None
    person_id: Optional[int] = None
    project_id: Optional[int] = None
    note: Optional[str] = None
    transaction_time: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ================================ 周期性交易 ================================
class RecurringTransactionCreate(BaseModel):
    """创建周期性交易请求模型：含频率与下次执行时间。"""
    name: str
    transaction_type: TransactionType = TransactionType.EXPENSE
    amount: float
    from_account_id: Optional[int] = None
    category_id: Optional[int] = None
    merchant_id: Optional[int] = None
    project_id: Optional[int] = None
    note: Optional[str] = None
    frequency: Optional[str] = None
    next_run: Optional[datetime] = None


class RecurringTransactionUpdate(BaseModel):
    """更新周期性交易请求模型（字段均可选）。"""
    name: Optional[str] = None
    transaction_type: Optional[TransactionType] = None
    amount: Optional[float] = None
    from_account_id: Optional[int] = None
    category_id: Optional[int] = None
    merchant_id: Optional[int] = None
    project_id: Optional[int] = None
    note: Optional[str] = None
    frequency: Optional[str] = None
    next_run: Optional[datetime] = None
    is_active: Optional[bool] = None


class RecurringTransactionResponse(BaseModel):
    """周期性交易响应模型（从 ORM 对象序列化）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    name: Optional[str] = None
    transaction_type: Optional[TransactionType] = None
    amount: Optional[float] = None
    from_account_id: Optional[int] = None
    category_id: Optional[int] = None
    merchant_id: Optional[int] = None
    project_id: Optional[int] = None
    note: Optional[str] = None
    frequency: Optional[str] = None
    next_run: Optional[datetime] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
