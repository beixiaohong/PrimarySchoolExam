"""
个人账本系统 - FastAPI 实现（迁移版）
====================================

迁移自 temp/wulala/ledger/route_ledger.py：

- 鉴权：原 verify_user_points(N) → require_user（Bearer token），并使用 current_user.user_id
  （字符串）做所有写入/查询；路由开头校验 user_id == current_user.user_id。
- 序列化：pydantic v1 的 .dict() → v2 的 .model_dump()。
- 调度/邮件：移除 apscheduler / smtplib 后台调度器与邮件推送；
  周期交易改由手动端点 POST /recurring/run-due 触发；报表改为返回 JSON 的
  GET /reports/summary。其余统计/看板端点全部保留。
"""
from sqlalchemy import func, extract
import logging
import json
import csv
import io
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any

from app.database import get_db
from app.models.user import User
from app.models import ledger as model_ledger
from app.schemas import ledger as ledger_schemas
from app.domains.identity.contracts import require_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================ 余额更新辅助 ================================

def _adjust_balance(db: Session, transaction_type, amount, from_account_id,
                    to_account_id=None, multiplier: int = 1):
    """按交易类型调整账户余额。

    multiplier=1 应用交易影响；multiplier=-1 撤销交易影响。
    逻辑与账本原实现保持一致：
    - 支出：from_account.balance -= amount
    - 收入：from_account.balance += amount
    - 转账：from_account.balance -= amount, to_account.balance += amount
    """
    from_account = db.query(model_ledger.Account).filter(
        model_ledger.Account.id == from_account_id
    ).first()
    if from_account is None:
        return
    t = transaction_type
    if t == model_ledger.TransactionType.EXPENSE:
        from_account.balance -= amount * multiplier
    elif t == model_ledger.TransactionType.INCOME:
        from_account.balance += amount * multiplier
    elif t == model_ledger.TransactionType.TRANSFER:
        from_account.balance -= amount * multiplier
        if to_account_id:
            to_account = db.query(model_ledger.Account).filter(
                model_ledger.Account.id == to_account_id
            ).first()
            if to_account:
                to_account.balance += amount * multiplier


def _advance_next_run(next_run: datetime, frequency: str, now: datetime) -> datetime:
    """根据频率把 next_run 推进到未来时间（处理漏跑的情况）。"""
    while next_run <= now:
        if frequency == "weekly":
            next_run += timedelta(weeks=1)
        elif frequency == "monthly":
            next_run += timedelta(days=30)
        elif frequency == "yearly":
            next_run += timedelta(days=365)
        else:
            next_run += timedelta(days=1)
    return next_run


def generate_financial_report(db: Session, user_id: str,
                              period_start: datetime, period_end: datetime,
                              period_type: str) -> Dict[str, Any]:
    """生成财务周期报告数据（返回 dict，不发邮件）。

    统计区间 [period_start, period_end]，并与上一周期对比（环比）。
    """
    current_income = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).scalar() or 0

    current_expense = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).scalar() or 0

    net_income = current_income - current_expense

    current_balance = db.query(func.sum(model_ledger.Account.balance)).filter(
        model_ledger.Account.user_id == user_id
    ).scalar() or 0

    top_expense_categories = db.query(
        model_ledger.Category.level1,
        model_ledger.Category.level2,
        model_ledger.Category.level3,
        func.sum(model_ledger.Bill.amount).label('amount'),
        func.count(model_ledger.Bill.id).label('count')
    ).join(
        model_ledger.Bill, model_ledger.Bill.category_id == model_ledger.Category.id
    ).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).group_by(
        model_ledger.Category.level1, model_ledger.Category.level2, model_ledger.Category.level3
    ).order_by(
        func.sum(model_ledger.Bill.amount).desc()
    ).limit(5).all()

    top_income_categories = db.query(
        model_ledger.Category.level1,
        model_ledger.Category.level2,
        model_ledger.Category.level3,
        func.sum(model_ledger.Bill.amount).label('amount'),
        func.count(model_ledger.Bill.id).label('count')
    ).join(
        model_ledger.Bill, model_ledger.Bill.category_id == model_ledger.Category.id
    ).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).group_by(
        model_ledger.Category.level1, model_ledger.Category.level2, model_ledger.Category.level3
    ).order_by(
        func.sum(model_ledger.Bill.amount).desc()
    ).limit(5).all()

    if period_type == "weekly":
        prev_start = period_start - timedelta(weeks=1)
        prev_end = period_end - timedelta(weeks=1)
    elif period_type == "monthly":
        prev_start = period_start - timedelta(days=30)
        prev_end = period_end - timedelta(days=30)
    else:  # yearly
        prev_start = period_start - timedelta(days=365)
        prev_end = period_end - timedelta(days=365)

    prev_income = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= prev_start,
        model_ledger.Bill.transaction_time <= prev_end
    ).scalar() or 0

    prev_expense = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= prev_start,
        model_ledger.Bill.transaction_time <= prev_end
    ).scalar() or 0

    income_change = ((current_income - prev_income) / prev_income * 100) if prev_income > 0 else 0
    expense_change = ((current_expense - prev_expense) / prev_expense * 100) if prev_expense > 0 else 0

    return {
        "period_type": period_type,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "current_data": {
            "total_income": float(current_income),
            "total_expense": float(current_expense),
            "net_income": float(net_income),
            "account_balance": float(current_balance)
        },
        "top_expense_categories": [
            {
                "category": f"{cat.level1} > {cat.level2} > {cat.level3}",
                "amount": float(cat.amount),
                "count": cat.count,
                "percentage": round(float(cat.amount) / float(current_expense) * 100, 2) if current_expense > 0 else 0
            }
            for cat in top_expense_categories
        ],
        "top_income_categories": [
            {
                "category": f"{cat.level1} > {cat.level2} > {cat.level3}",
                "amount": float(cat.amount),
                "count": cat.count,
                "percentage": round(float(cat.amount) / float(current_income) * 100, 2) if current_income > 0 else 0
            }
            for cat in top_income_categories
        ],
        "comparison": {
            "prev_income": float(prev_income),
            "prev_expense": float(prev_expense),
            "income_change": round(income_change, 2),
            "expense_change": round(expense_change, 2),
            "income_change_amount": float(current_income - prev_income),
            "expense_change_amount": float(current_expense - prev_expense)
        }
    }


# ================================ 账户管理API ================================

@router.post("/users/{user_id}/accounts/", response_model=ledger_schemas.AccountResponse, summary="创建支付账户", tags=["账户管理"])
def create_account(user_id: str, account: ledger_schemas.AccountCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """为指定用户创建支付账户"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_account = model_ledger.Account(**account.model_dump(), user_id=current_user.user_id)
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@router.get("/users/{user_id}/accounts/", response_model=List[ledger_schemas.AccountResponse], summary="获取用户账户列表", tags=["账户管理"])
def get_accounts(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取指定用户的所有支付账户"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    accounts = db.query(model_ledger.Account).filter(model_ledger.Account.user_id == current_user.user_id).all()
    return accounts

@router.put("/users/{user_id}/accounts/{account_id}", response_model=ledger_schemas.AccountResponse, summary="更新账户", tags=["账户管理"])
def update_account(user_id: str, account_id: int, account: ledger_schemas.AccountUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新指定用户的支付账户信息（仅提交的非空字段生效，需本人权限）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_account = db.query(model_ledger.Account).filter(model_ledger.Account.id == account_id, model_ledger.Account.user_id == current_user.user_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="账户不存在")
    update_data = account.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_account, key, value)
    db.commit()
    db.refresh(db_account)
    return db_account

@router.delete("/users/{user_id}/accounts/{account_id}", summary="删除账户", tags=["账户管理"])
def delete_account(user_id: str, account_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除指定用户的支付账户（仅本人权限，需账户存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_account = db.query(model_ledger.Account).filter(model_ledger.Account.id == account_id, model_ledger.Account.user_id == current_user.user_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="账户不存在")
    db.delete(db_account)
    db.commit()
    return {"message": "账户已删除"}

# ================================ 分类管理API ================================

@router.post("/users/{user_id}/categories/", response_model=ledger_schemas.CategoryResponse, summary="创建收支分类", tags=["分类管理"])
def create_category(user_id: str, category: ledger_schemas.CategoryCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """创建三级收支分类"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_category = model_ledger.Category(**category.model_dump(), user_id=current_user.user_id)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

@router.get("/users/{user_id}/categories/", response_model=List[ledger_schemas.CategoryResponse], summary="获取用户分类列表", tags=["分类管理"])
def get_categories(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    categories = db.query(model_ledger.Category).filter(model_ledger.Category.user_id == current_user.user_id).all()
    return categories

@router.put("/users/{user_id}/categories/{category_id}", response_model=ledger_schemas.CategoryResponse, summary="更新分类", tags=["分类管理"])
def update_category(user_id: str, category_id: int, category: ledger_schemas.CategoryUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新指定用户的收支分类（仅提交的非空字段生效，需本人权限）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_category = db.query(model_ledger.Category).filter(model_ledger.Category.id == category_id, model_ledger.Category.user_id == current_user.user_id).first()
    if not db_category:
        raise HTTPException(status_code=404, detail="分类不存在")
    update_data = category.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_category, key, value)
    db.commit()
    db.refresh(db_category)
    return db_category

@router.delete("/users/{user_id}/categories/{category_id}", summary="删除分类", tags=["分类管理"])
def delete_category(user_id: str, category_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除指定用户的收支分类（仅本人权限，需分类存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_category = db.query(model_ledger.Category).filter(model_ledger.Category.id == category_id, model_ledger.Category.user_id == current_user.user_id).first()
    if not db_category:
        raise HTTPException(status_code=404, detail="分类不存在")
    db.delete(db_category)
    db.commit()
    return {"message": "分类已删除"}

# ================================ 地点管理API ================================

@router.post("/users/{user_id}/locations/", response_model=ledger_schemas.LocationResponse, summary="创建支付地点", tags=["地点管理"])
def create_location(user_id: str, location: ledger_schemas.LocationCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_location = model_ledger.Location(**location.model_dump(), user_id=current_user.user_id)
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    return db_location

@router.get("/users/{user_id}/locations/", response_model=List[ledger_schemas.LocationResponse], summary="获取用户地点列表", tags=["地点管理"])
def get_locations(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    locations = db.query(model_ledger.Location).filter(model_ledger.Location.user_id == current_user.user_id).all()
    return locations

@router.put("/users/{user_id}/locations/{location_id}", response_model=ledger_schemas.LocationResponse, summary="更新地点", tags=["地点管理"])
def update_location(user_id: str, location_id: int, location: ledger_schemas.LocationUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新指定用户的支付地点（仅提交的非空字段生效，需本人权限）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_location = db.query(model_ledger.Location).filter(model_ledger.Location.id == location_id, model_ledger.Location.user_id == current_user.user_id).first()
    if not db_location:
        raise HTTPException(status_code=404, detail="地点不存在")
    update_data = location.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_location, key, value)
    db.commit()
    db.refresh(db_location)
    return db_location

@router.delete("/users/{user_id}/locations/{location_id}", summary="删除地点", tags=["地点管理"])
def delete_location(user_id: str, location_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除指定用户的支付地点（仅本人权限，需地点存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_location = db.query(model_ledger.Location).filter(model_ledger.Location.id == location_id, model_ledger.Location.user_id == current_user.user_id).first()
    if not db_location:
        raise HTTPException(status_code=404, detail="地点不存在")
    db.delete(db_location)
    db.commit()
    return {"message": "地点已删除"}

# ================================ 商户管理API ================================

@router.post("/users/{user_id}/merchants/", response_model=ledger_schemas.MerchantResponse, summary="创建支付商户", tags=["商户管理"])
def create_merchant(user_id: str, merchant: ledger_schemas.MerchantCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_merchant = model_ledger.Merchant(**merchant.model_dump(), user_id=current_user.user_id)
    db.add(db_merchant)
    db.commit()
    db.refresh(db_merchant)
    return db_merchant

@router.get("/users/{user_id}/merchants/", response_model=List[ledger_schemas.MerchantResponse], summary="获取用户商户列表", tags=["商户管理"])
def get_merchants(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    merchants = db.query(model_ledger.Merchant).filter(model_ledger.Merchant.user_id == current_user.user_id).all()
    return merchants

@router.put("/users/{user_id}/merchants/{merchant_id}", response_model=ledger_schemas.MerchantResponse, summary="更新商户", tags=["商户管理"])
def update_merchant(user_id: str, merchant_id: int, merchant: ledger_schemas.MerchantUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新指定用户的支付商户（仅提交的非空字段生效，需本人权限）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_merchant = db.query(model_ledger.Merchant).filter(model_ledger.Merchant.id == merchant_id, model_ledger.Merchant.user_id == current_user.user_id).first()
    if not db_merchant:
        raise HTTPException(status_code=404, detail="商户不存在")
    update_data = merchant.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_merchant, key, value)
    db.commit()
    db.refresh(db_merchant)
    return db_merchant

@router.delete("/users/{user_id}/merchants/{merchant_id}", summary="删除商户", tags=["商户管理"])
def delete_merchant(user_id: str, merchant_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除指定用户的支付商户（仅本人权限，需商户存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_merchant = db.query(model_ledger.Merchant).filter(model_ledger.Merchant.id == merchant_id, model_ledger.Merchant.user_id == current_user.user_id).first()
    if not db_merchant:
        raise HTTPException(status_code=404, detail="商户不存在")
    db.delete(db_merchant)
    db.commit()
    return {"message": "商户已删除"}

# ================================ 人员管理API ================================

@router.post("/users/{user_id}/persons/", response_model=ledger_schemas.PersonResponse, summary="创建相关人员", tags=["人员管理"])
def create_person(user_id: str, person: ledger_schemas.PersonCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_person = model_ledger.Person(**person.model_dump(), user_id=current_user.user_id)
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person

@router.get("/users/{user_id}/persons/", response_model=List[ledger_schemas.PersonResponse], summary="获取用户人员列表", tags=["人员管理"])
def get_persons(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    persons = db.query(model_ledger.Person).filter(model_ledger.Person.user_id == current_user.user_id).all()
    return persons

@router.put("/users/{user_id}/persons/{person_id}", response_model=ledger_schemas.PersonResponse, summary="更新人员", tags=["人员管理"])
def update_person(user_id: str, person_id: int, person: ledger_schemas.PersonUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新指定用户的相关人员（仅提交的非空字段生效，需本人权限）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_person = db.query(model_ledger.Person).filter(model_ledger.Person.id == person_id, model_ledger.Person.user_id == current_user.user_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="人员不存在")
    update_data = person.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_person, key, value)
    db.commit()
    db.refresh(db_person)
    return db_person

@router.delete("/users/{user_id}/persons/{person_id}", summary="删除人员", tags=["人员管理"])
def delete_person(user_id: str, person_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除指定用户的相关人员（仅本人权限，需人员存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_person = db.query(model_ledger.Person).filter(model_ledger.Person.id == person_id, model_ledger.Person.user_id == current_user.user_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="人员不存在")
    db.delete(db_person)
    db.commit()
    return {"message": "人员已删除"}

# ================================ 项目管理API ================================

@router.post("/users/{user_id}/projects/", response_model=ledger_schemas.ProjectResponse, summary="创建关联项目", tags=["项目管理"])
def create_project(user_id: str, project: ledger_schemas.ProjectCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_project = model_ledger.Project(**project.model_dump(), user_id=current_user.user_id)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.get("/users/{user_id}/projects/", response_model=List[ledger_schemas.ProjectResponse], summary="获取用户项目列表", tags=["项目管理"])
def get_projects(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    projects = db.query(model_ledger.Project).filter(model_ledger.Project.user_id == current_user.user_id).all()
    return projects

@router.put("/users/{user_id}/projects/{project_id}", response_model=ledger_schemas.ProjectResponse, summary="更新项目", tags=["项目管理"])
def update_project(user_id: str, project_id: int, project: ledger_schemas.ProjectUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新指定用户的关联项目（仅提交的非空字段生效，需本人权限）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_project = db.query(model_ledger.Project).filter(model_ledger.Project.id == project_id, model_ledger.Project.user_id == current_user.user_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="项目不存在")
    update_data = project.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_project, key, value)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.delete("/users/{user_id}/projects/{project_id}", summary="删除项目", tags=["项目管理"])
def delete_project(user_id: str, project_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除指定用户的关联项目（仅本人权限，需项目存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_project = db.query(model_ledger.Project).filter(model_ledger.Project.id == project_id, model_ledger.Project.user_id == current_user.user_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="项目不存在")
    db.delete(db_project)
    db.commit()
    return {"message": "项目已删除"}

# ================================ 核心记账API ================================

@router.post("/users/{user_id}/transactions/", response_model=ledger_schemas.TransactionResponse, summary="创建交易记录", tags=["记账管理"])
def create_transaction(user_id: str, transaction: ledger_schemas.TransactionCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """创建交易记录（记账功能），自动更新相关账户余额。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")

    from_account = db.query(model_ledger.Account).filter(
        model_ledger.Account.id == transaction.from_account_id,
        model_ledger.Account.user_id == current_user.user_id
    ).first()
    if not from_account:
        raise HTTPException(status_code=404, detail="支出账户不存在或不属于该用户")

    to_account = None
    if transaction.transaction_type == model_ledger.TransactionType.TRANSFER:
        if not transaction.to_account_id:
            raise HTTPException(status_code=400, detail="转账必须指定收入账户")
        to_account = db.query(model_ledger.Account).filter(
            model_ledger.Account.id == transaction.to_account_id,
            model_ledger.Account.user_id == current_user.user_id
        ).first()
        if not to_account:
            raise HTTPException(status_code=404, detail="收入账户不存在或不属于该用户")

    category = db.query(model_ledger.Category).filter(
        model_ledger.Category.id == transaction.category_id,
        model_ledger.Category.user_id == current_user.user_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在或不属于该用户")

    transaction_data = transaction.model_dump()
    if transaction_data['transaction_time'] is None:
        transaction_data['transaction_time'] = datetime.now()

    db_transaction = model_ledger.Bill(**transaction_data, user_id=current_user.user_id)

    # 更新账户余额
    _adjust_balance(db, transaction.transaction_type, transaction.amount,
                    transaction.from_account_id, transaction.to_account_id, 1)

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction

@router.get("/users/{user_id}/transactions/", response_model=List[ledger_schemas.TransactionResponse], summary="获取交易记录列表", tags=["记账管理"])
def get_transactions(
    user_id: str,
    skip: int = Query(0, ge=0, description="跳过记录数，用于分页"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数，最大1000条"),
    transaction_type: Optional[model_ledger.TransactionType] = Query(None, description="按交易类型筛选"),
    category_id: Optional[int] = Query(None, description="按分类ID筛选"),
    account_id: Optional[int] = Query(None, description="按账户ID筛选（付款或收款账户）"),
    location_id: Optional[int] = Query(None, description="按地点ID筛选"),
    merchant_id: Optional[int] = Query(None, description="按商户ID筛选"),
    person_id: Optional[int] = Query(None, description="按人员ID筛选"),
    project_id: Optional[int] = Query(None, description="按项目ID筛选"),
    start_date: Optional[date] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[date] = Query(None, description="截止日期 YYYY-MM-DD"),
    min_amount: Optional[float] = Query(None, ge=0, description="最小金额"),
    max_amount: Optional[float] = Query(None, ge=0, description="最大金额"),
    keyword: Optional[str] = Query(None, description="关键词搜索（备注模糊匹配）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """获取用户的交易记录列表（支持高级筛选）"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    query = db.query(model_ledger.Bill).filter(model_ledger.Bill.user_id == current_user.user_id)

    if transaction_type:
        query = query.filter(model_ledger.Bill.transaction_type == transaction_type)
    if category_id:
        query = query.filter(model_ledger.Bill.category_id == category_id)
    if account_id:
        query = query.filter(
            (model_ledger.Bill.from_account_id == account_id) | (model_ledger.Bill.to_account_id == account_id)
        )
    if location_id:
        query = query.filter(model_ledger.Bill.location_id == location_id)
    if merchant_id:
        query = query.filter(model_ledger.Bill.merchant_id == merchant_id)
    if person_id:
        query = query.filter(model_ledger.Bill.person_id == person_id)
    if project_id:
        query = query.filter(model_ledger.Bill.project_id == project_id)
    if start_date:
        query = query.filter(model_ledger.Bill.transaction_time >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(model_ledger.Bill.transaction_time < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
    if min_amount is not None:
        query = query.filter(model_ledger.Bill.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(model_ledger.Bill.amount <= max_amount)
    if keyword:
        query = query.filter(model_ledger.Bill.note.ilike(f"%{keyword}%"))

    transactions = query.order_by(model_ledger.Bill.transaction_time.desc()).offset(skip).limit(limit).all()
    return transactions

@router.get("/users/{user_id}/transactions/{transaction_id}", response_model=ledger_schemas.TransactionResponse, summary="获取单条交易记录", tags=["记账管理"])
def get_transaction(user_id: str, transaction_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取指定的交易记录详情"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    transaction = db.query(model_ledger.Bill).filter(
        model_ledger.Bill.id == transaction_id,
        model_ledger.Bill.user_id == current_user.user_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return transaction

@router.put("/users/{user_id}/transactions/{transaction_id}", response_model=ledger_schemas.TransactionResponse, summary="修改交易记录", tags=["记账管理"])
def update_transaction(
    user_id: str,
    transaction_id: int,
    transaction_update: ledger_schemas.TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """修改交易记录，自动维持账户余额一致性。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_transaction = db.query(model_ledger.Bill).filter(
        model_ledger.Bill.id == transaction_id,
        model_ledger.Bill.user_id == current_user.user_id
    ).first()
    if not db_transaction:
        raise HTTPException(status_code=404, detail="交易记录不存在")

    # 第一步：恢复原账户余额
    _adjust_balance(db, db_transaction.transaction_type, db_transaction.amount,
                    db_transaction.from_account_id, db_transaction.to_account_id, -1)

    # 第二步：更新交易记录
    update_data = transaction_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_transaction, field, value)

    # 第三步：重新计算账户余额
    _adjust_balance(db, db_transaction.transaction_type, db_transaction.amount,
                    db_transaction.from_account_id, db_transaction.to_account_id, 1)

    db.commit()
    db.refresh(db_transaction)
    return db_transaction

@router.delete("/users/{user_id}/transactions/{transaction_id}", summary="删除交易记录", tags=["记账管理"])
def delete_transaction(user_id: str, transaction_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除交易记录，恢复其对账户余额的影响。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_transaction = db.query(model_ledger.Bill).filter(
        model_ledger.Bill.id == transaction_id,
        model_ledger.Bill.user_id == current_user.user_id
    ).first()
    if not db_transaction:
        raise HTTPException(status_code=404, detail="交易记录不存在")

    # 恢复账户余额
    _adjust_balance(db, db_transaction.transaction_type, db_transaction.amount,
                    db_transaction.from_account_id, db_transaction.to_account_id, -1)

    db.delete(db_transaction)
    db.commit()
    return {"message": "交易记录删除成功"}


# ================================ 统计分析API ================================

@router.get("/users/{user_id}/statistics/summary", summary="获取财务概览", tags=["统计分析"])
def get_summary(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取用户财务概览统计（总资产 / 本月收入 / 本月支出 / 本月结余）"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    total_assets = db.query(func.sum(model_ledger.Account.balance)).filter(model_ledger.Account.user_id == current_user.user_id).scalar() or 0

    current_month = date.today().replace(day=1)

    monthly_income = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == current_user.user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= current_month
    ).scalar() or 0

    monthly_expense = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == current_user.user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= current_month
    ).scalar() or 0

    return {
        "total_assets": float(total_assets),
        "monthly_income": float(monthly_income),
        "monthly_expense": float(monthly_expense),
        "monthly_balance": float(monthly_income - monthly_expense)
    }

@router.get("/users/{user_id}/statistics/category", summary="按分类统计支出", tags=["统计分析"])
def get_category_statistics(
    user_id: str,
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """按分类统计用户支出情况"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    query = db.query(
        model_ledger.Category.level1,
        model_ledger.Category.level2,
        model_ledger.Category.level3,
        func.sum(model_ledger.Bill.amount).label('total_amount'),
        func.count(model_ledger.Bill.id).label('transaction_count')
    ).join(
        model_ledger.Bill, model_ledger.Bill.category_id == model_ledger.Category.id
    ).filter(
        model_ledger.Bill.user_id == current_user.user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE
    )

    if start_date:
        query = query.filter(model_ledger.Bill.transaction_time >= start_date)
    if end_date:
        query = query.filter(model_ledger.Bill.transaction_time <= end_date)

    results = query.group_by(
        model_ledger.Category.level1, model_ledger.Category.level2, model_ledger.Category.level3
    ).order_by(
        func.sum(model_ledger.Bill.amount).desc()
    ).all()

    category_stats = []
    for result in results:
        category_stats.append({
            "category": f"{result.level1} > {result.level2} > {result.level3}",
            "level1": result.level1,
            "level2": result.level2,
            "level3": result.level3,
            "total_amount": float(result.total_amount),
            "transaction_count": result.transaction_count
        })

    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date
        },
        "categories": category_stats
    }

@router.get("/users/{user_id}/statistics/monthly", summary="按月统计收支", tags=["统计分析"])
def get_monthly_statistics(
    user_id: str,
    year: int = Query(..., description="年份"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """按月统计指定年份的收支情况"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    monthly_income = db.query(
        extract('month', model_ledger.Bill.transaction_time).label('month'),
        func.sum(model_ledger.Bill.amount).label('amount')
    ).filter(
        model_ledger.Bill.user_id == current_user.user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        extract('year', model_ledger.Bill.transaction_time) == year
    ).group_by(extract('month', model_ledger.Bill.transaction_time)).all()

    monthly_expense = db.query(
        extract('month', model_ledger.Bill.transaction_time).label('month'),
        func.sum(model_ledger.Bill.amount).label('amount')
    ).filter(
        model_ledger.Bill.user_id == current_user.user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        extract('year', model_ledger.Bill.transaction_time) == year
    ).group_by(extract('month', model_ledger.Bill.transaction_time)).all()

    income_dict = {int(row.month): float(row.amount) for row in monthly_income}
    expense_dict = {int(row.month): float(row.amount) for row in monthly_expense}

    monthly_data = []
    for month in range(1, 13):
        income = income_dict.get(month, 0)
        expense = expense_dict.get(month, 0)
        monthly_data.append({
            "month": month,
            "income": income,
            "expense": expense,
            "balance": income - expense
        })

    return {
        "year": year,
        "monthly_data": monthly_data
    }

@router.get("/users/{user_id}/statistics/budget", summary="获取项目预算统计", tags=["统计分析"])
def get_budget_stats(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取各项目的预算与实际支出对比"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    projects = db.query(model_ledger.Project).filter(model_ledger.Project.user_id == current_user.user_id).all()
    result = []
    for proj in projects:
        total_spent = db.query(func.sum(model_ledger.Bill.amount)).filter(
            model_ledger.Bill.project_id == proj.id,
            model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE
        ).scalar() or 0
        result.append({
            "project_id": proj.id,
            "project_name": proj.name,
            "budget": float(proj.budget) if proj.budget else 0,
            "spent": float(total_spent),
            "remaining": float(proj.budget) - float(total_spent) if proj.budget else 0
        })
    return result

# ================================ 周期性交易 ================================

@router.post("/users/{user_id}/recurring/", response_model=ledger_schemas.RecurringTransactionResponse, summary="创建周期性交易", tags=["周期性交易"])
def create_recurring(user_id: str, rt: ledger_schemas.RecurringTransactionCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """创建周期性交易（如房租、订阅等）"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    next_run = rt.next_run or datetime.now()
    db_rt = model_ledger.RecurringTransaction(
        **rt.model_dump(), user_id=current_user.user_id, next_run=next_run, is_active=True
    )
    db.add(db_rt)
    db.commit()
    db.refresh(db_rt)
    return db_rt

@router.get("/users/{user_id}/recurring/", response_model=List[ledger_schemas.RecurringTransactionResponse], summary="获取周期性交易列表", tags=["周期性交易"])
def get_recurring_list(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取用户所有周期性交易"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    return db.query(model_ledger.RecurringTransaction).filter(
        model_ledger.RecurringTransaction.user_id == current_user.user_id
    ).order_by(model_ledger.RecurringTransaction.next_run.asc()).all()

@router.put("/users/{user_id}/recurring/{rt_id}", response_model=ledger_schemas.RecurringTransactionResponse, summary="更新周期性交易", tags=["周期性交易"])
def update_recurring(user_id: str, rt_id: int, rt: ledger_schemas.RecurringTransactionUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新周期性交易"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_rt = db.query(model_ledger.RecurringTransaction).filter(
        model_ledger.RecurringTransaction.id == rt_id,
        model_ledger.RecurringTransaction.user_id == current_user.user_id
    ).first()
    if not db_rt:
        raise HTTPException(status_code=404, detail="周期性交易不存在")
    update_data = rt.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_rt, key, value)
    db.commit()
    db.refresh(db_rt)
    return db_rt

@router.delete("/users/{user_id}/recurring/{rt_id}", summary="删除周期性交易", tags=["周期性交易"])
def delete_recurring(user_id: str, rt_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除周期性交易"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_rt = db.query(model_ledger.RecurringTransaction).filter(
        model_ledger.RecurringTransaction.id == rt_id,
        model_ledger.RecurringTransaction.user_id == current_user.user_id
    ).first()
    if not db_rt:
        raise HTTPException(status_code=404, detail="周期性交易不存在")
    db.delete(db_rt)
    db.commit()
    return {"message": "已删除"}

@router.post("/users/{user_id}/recurring/{rt_id}/toggle", summary="启用/停用周期性交易", tags=["周期性交易"])
def toggle_recurring(user_id: str, rt_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """切换周期性交易的启用/停用状态"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_rt = db.query(model_ledger.RecurringTransaction).filter(
        model_ledger.RecurringTransaction.id == rt_id,
        model_ledger.RecurringTransaction.user_id == current_user.user_id
    ).first()
    if not db_rt:
        raise HTTPException(status_code=404, detail="周期性交易不存在")
    db_rt.is_active = not db_rt.is_active
    db.commit()
    db.refresh(db_rt)
    return {"is_active": db_rt.is_active}

# ================================ 周期交易手动触发 ================================

@router.post("/recurring/run-due", summary="处理到期周期交易（手动触发）", tags=["周期性交易"])
def run_due_recurring(db: Session = Depends(get_db),
                      current_user: User = Depends(require_user)):
    """找出当前用户所有到期（next_run <= now 且启用）的周期交易，为其生成账单并更新余额，
    然后按频率推进 next_run。无后台调度器，由调用方手动触发。"""
    now = datetime.now()
    due = db.query(model_ledger.RecurringTransaction).filter(
        model_ledger.RecurringTransaction.user_id == current_user.user_id,
        model_ledger.RecurringTransaction.is_active == True,
        model_ledger.RecurringTransaction.next_run <= now,
    ).all()

    processed = []
    for rt in due:
        from_account = db.query(model_ledger.Account).filter(
            model_ledger.Account.id == rt.from_account_id,
            model_ledger.Account.user_id == current_user.user_id
        ).first()
        if not from_account:
            continue

        bill = model_ledger.Bill(
            user_id=current_user.user_id,
            transaction_type=rt.transaction_type,
            amount=rt.amount,
            from_account_id=rt.from_account_id,
            category_id=rt.category_id,
            merchant_id=rt.merchant_id,
            project_id=rt.project_id,
            note=rt.note,
            transaction_time=now,
        )
        db.add(bill)
        db.flush()  # 取得 bill.id

        # 复用同一套余额更新逻辑
        _adjust_balance(db, rt.transaction_type, rt.amount, rt.from_account_id, None, 1)

        rt.next_run = _advance_next_run(rt.next_run, rt.frequency, now)
        rt.updated_at = now
        processed.append(bill.id)

    db.commit()
    return {"processed": len(processed), "bill_ids": processed}

# ================================ 报告（返回JSON，不发邮件） ================================

@router.get("/reports/summary", summary="生成财务周期报告(返回JSON)", tags=["报告"])
def report_summary(period: str = Query("monthly", description="周期: weekly|monthly|yearly"),
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_user)):
    """按周期（周/月/年）生成财务报告数据，返回 JSON。

    周期口径：
    - weekly：上周（上周一至上周日）
    - monthly：上月（上月1号至上月末）
    - yearly：去年（1/1 ~ 12/31）
    """
    if period not in ("weekly", "monthly", "yearly"):
        raise HTTPException(400, "period 仅支持 weekly|monthly|yearly")

    today = date.today()
    if period == "weekly":
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_sunday = last_monday + timedelta(days=6)
        period_start = datetime.combine(last_monday, datetime.min.time())
        period_end = datetime.combine(last_sunday, datetime.max.time())
    elif period == "monthly":
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        period_start = datetime.combine(first_day_last_month, datetime.min.time())
        period_end = datetime.combine(last_day_last_month, datetime.max.time())
    else:  # yearly
        last_year = today.year - 1
        period_start = datetime(last_year, 1, 1)
        period_end = datetime(last_year, 12, 31, 23, 59, 59)

    return generate_financial_report(db, current_user.user_id, period_start, period_end, period)

# ================================ 导入导出 ================================

@router.get("/users/{user_id}/export/csv", summary="导出交易记录为CSV", tags=["导入导出"])
def export_csv(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """导出用户所有交易记录为 CSV 文件"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    transactions = db.query(model_ledger.Bill).filter(
        model_ledger.Bill.user_id == current_user.user_id
    ).order_by(model_ledger.Bill.transaction_time.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "类型", "金额", "分类", "账户", "地点", "商户", "人员", "项目", "备注"])
    for tx in transactions:
        cat_name = ""
        if tx.category:
            cat_name = " / ".join(filter(None, [tx.category.level1, tx.category.level2, tx.category.level3]))
        writer.writerow([
            str(tx.transaction_time),
            tx.transaction_type.value if tx.transaction_type else "",
            float(tx.amount),
            cat_name,
            tx.from_account.account_name if tx.from_account else "",
            tx.location.name if tx.location else "",
            tx.merchant.name if tx.merchant else "",
            tx.person.name if tx.person else "",
            tx.project.name if tx.project else "",
            tx.note or ""
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ledger_export.csv"}
    )

@router.post("/users/{user_id}/import/csv", summary="从CSV导入交易记录", tags=["导入导出"])
async def import_csv(user_id: str, file: UploadFile, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """从 CSV 文件导入交易记录（需包含表头行）"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    count = 0
    for row in reader:
        try:
            amount = float(row.get("金额", 0))
            if amount <= 0:
                continue
            tx_type = row.get("类型", "expense").strip().lower()
            if tx_type in ["收入", "income"]:
                tx_type = model_ledger.TransactionType.INCOME
            elif tx_type in ["转账", "transfer"]:
                tx_type = model_ledger.TransactionType.TRANSFER
            else:
                tx_type = model_ledger.TransactionType.EXPENSE

            tx_time = None
            time_str = row.get("时间", "").strip()
            if time_str:
                try:
                    tx_time = datetime.strptime(time_str[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    tx_time = datetime.now()

            db_tx = model_ledger.Bill(
                user_id=current_user.user_id,
                transaction_type=tx_type,
                amount=amount,
                note=row.get("备注", ""),
                transaction_time=tx_time or datetime.now()
            )
            db.add(db_tx)
            count += 1
        except Exception:
            continue
    db.commit()
    return {"imported": count}
