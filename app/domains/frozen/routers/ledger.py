"""
个人账本系统 - FastAPI 实现（迁移版）
====================================

迁移自 temp/wulala/ledger/route_ledger.py：

- 鉴权：原 verify_user_points(N) → require_user（Bearer token），并使用 current_user.user_id
  （字符串）做所有写入/查询；路由开头校验 user_id == current_user.user_id。
- 序列化：pydantic v1 的 .dict() → v2 的 .model_dump()。
- 调度：周期交易由 tools/scheduler.py 每日 01:00 调用 tools/run_due_recurring.py
  （→ ledger_recurring.run_due_recurring_all，遍历全量用户）自动记账；另保留手动端点
  POST /recurring/run-due（仅当前用户）用于按需补记，两端共用 ledger_calc 的
  _adjust_balance / _advance_next_run，口径一致。
- 邮件：已移除 smtplib 推送，报表改为返回 JSON 的 GET /reports/summary。
  其余统计/看板端点全部保留。
"""
from sqlalchemy import func, extract
from decimal import Decimal
import logging
import json
import csv
import io
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from calendar import monthrange
from typing import Optional, List, Dict, Any

from app.database import get_db
from app.models.user import User
from app.models import ledger as model_ledger
from app.schemas import ledger as ledger_schemas
from app.domains.identity.contracts import require_user

logger = logging.getLogger(__name__)

router = APIRouter()

from app.domains.frozen.services.ledger_calc import (
    _adjust_balance,
    _advance_next_run,
    generate_financial_report,
)

# ================================ 多账本辅助 ================================

def _resolve_book_id(db: Session, user_id: str, book_id: Optional[int], create: bool = True) -> Optional[int]:
    """解析目标账本 id（随手记式多账本回落策略）。

    - 显式传入 book_id：校验归属后返回；
    - 未传：取该用户默认账本（is_default=1）；不存在时：
        create=True  → 即时创建「日常账本」并 flush 返回（写操作使用）；
        create=False → 返回 None（只读操作使用，避免无谓写入）。
    返回的 id 用于账单/账户/周期交易的 book_id 归属。
    """
    if book_id is not None:
        book = db.query(model_ledger.LedgerBook).filter(
            model_ledger.LedgerBook.id == book_id,
            model_ledger.LedgerBook.user_id == user_id,
        ).first()
        if not book:
            raise HTTPException(status_code=404, detail="账本不存在或不属于该用户")
        return book.id
    default_book = db.query(model_ledger.LedgerBook).filter(
        model_ledger.LedgerBook.user_id == user_id,
        model_ledger.LedgerBook.is_default == True,  # noqa: E712
    ).first()
    if default_book is not None:
        return default_book.id
    if not create:
        return None
    default_book = model_ledger.LedgerBook(
        user_id=user_id, name="日常账本", book_type="daily", is_default=True
    )
    db.add(default_book)
    db.flush()
    return default_book.id


# ================================ 预算辅助 ================================

def _current_month_window() -> tuple:
    """返回本月起止时间（naive datetime）：[month_start, month_end]。

    month_end 取到当月最后一天 23:59:59，便于用 <= / >= 直接框定本月区间。
    """
    m_start = date.today().replace(day=1)
    last_day = monthrange(m_start.year, m_start.month)[1]
    month_start = datetime.combine(m_start, datetime.min.time())
    month_end = datetime(m_start.year, m_start.month, last_day, 23, 59, 59)
    return month_start, month_end


def _compute_budget_status(db: Session, user_id: str, budgets: List) -> List[Dict[str, Any]]:
    """计算一组预算的当月执行率，并对跨过预警阈值的预算写 NotificationLog（同预算同月仅一条 pending）。

    返回每项预算的执行情况字典（含 scope_name / amount / spent / remaining / ratio /
    threshold / status）。spent 仅统计支出（EXPENSE），区间为本自然月，并按预算所属账本过滤；
    category/project 预算额外按 scope_id 过滤。status：ok(未到阈值) / warning(达阈值未超) /
    over(已超 100%)。超阈值时落 NotificationLog(status=pending)，前端轮询展示，不接短信/邮件
    （符合 D9 冻结域约束）。
    """
    month_start, month_end = _current_month_window()
    results: List[Dict[str, Any]] = []
    for b in budgets:
        spent_q = db.query(func.sum(model_ledger.Bill.amount)).filter(
            model_ledger.Bill.user_id == user_id,
            model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
            model_ledger.Bill.transaction_time >= month_start,
            model_ledger.Bill.transaction_time <= month_end,
        )
        if b.book_id is not None:
            spent_q = spent_q.filter(model_ledger.Bill.book_id == b.book_id)
        if b.scope_type == "category" and b.scope_id:
            spent_q = spent_q.filter(model_ledger.Bill.category_id == b.scope_id)
        elif b.scope_type == "project" and b.scope_id:
            spent_q = spent_q.filter(model_ledger.Bill.project_id == b.scope_id)
        spent = float(spent_q.scalar() or 0)

        amount = float(b.amount)
        threshold = float(b.notify_threshold or 0.8)
        ratio = (spent / amount) if amount > 0 else 0.0
        if ratio >= 1.0:
            status = "over"
        elif ratio >= threshold:
            status = "warning"
        else:
            status = "ok"

        if b.scope_type == "month":
            scope_name = "月度总预算"
        elif b.scope_type == "category" and b.scope_id:
            cat = db.query(model_ledger.Category).filter(
                model_ledger.Category.id == b.scope_id,
                model_ledger.Category.user_id == user_id,
            ).first()
            scope_name = " / ".join(filter(None, [cat.level1, cat.level2, cat.level3])) if cat else f"分类#{b.scope_id}"
        elif b.scope_type == "project" and b.scope_id:
            proj = db.query(model_ledger.Project).filter(
                model_ledger.Project.id == b.scope_id,
                model_ledger.Project.user_id == user_id,
            ).first()
            scope_name = proj.name if proj else f"项目#{b.scope_id}"
        else:
            scope_name = b.scope_type

        results.append({
            "budget_id": b.id,
            "scope_type": b.scope_type,
            "scope_id": b.scope_id,
            "scope_name": scope_name,
            "book_id": b.book_id,
            "amount": amount,
            "spent": spent,
            "remaining": round(amount - spent, 2),
            "ratio": round(ratio, 4),
            "threshold": threshold,
            "status": status,
        })

        # 超阈值提醒：同预算同月仅落一条 pending，避免重复推送
        if ratio >= threshold:
            exists = db.query(model_ledger.NotificationLog).filter(
                model_ledger.NotificationLog.budget_id == b.id,
                model_ledger.NotificationLog.period_start == month_start,
                model_ledger.NotificationLog.status == model_ledger.NotificationStatus.PENDING,
            ).first()
            if not exists:
                content = {
                    "scope_type": b.scope_type,
                    "scope_name": scope_name,
                    "amount": amount,
                    "spent": spent,
                    "ratio": round(ratio, 4),
                    "status": status,
                }
                db.add(model_ledger.NotificationLog(
                    user_id=user_id,
                    budget_id=b.id,
                    report_period=model_ledger.ReportPeriod.MONTHLY,
                    period_start=month_start,
                    period_end=month_end,
                    report_content=json.dumps(content, ensure_ascii=False),
                    status=model_ledger.NotificationStatus.PENDING,
                ))
    db.commit()
    return results


# ================================ 账户管理API ================================

@router.post("/users/{user_id}/accounts/", response_model=ledger_schemas.AccountResponse, summary="创建支付账户", tags=["账户管理"])
def create_account(user_id: str, account: ledger_schemas.AccountCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """为指定用户创建支付账户"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, account.book_id, create=True)
    db_account = model_ledger.Account(
        **account.model_dump(exclude={"book_id"}), user_id=current_user.user_id, book_id=bid
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@router.get("/users/{user_id}/accounts/", response_model=List[ledger_schemas.AccountResponse], summary="获取用户账户列表", tags=["账户管理"])
def get_accounts(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取指定用户的支付账户（默认按默认账本筛选）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    q = db.query(model_ledger.Account).filter(model_ledger.Account.user_id == current_user.user_id)
    if bid is not None:
        q = q.filter(model_ledger.Account.book_id == bid)
    return q.all()

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

    if transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="交易金额必须大于 0")

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
        if transaction.from_account_id == transaction.to_account_id:
            raise HTTPException(status_code=400, detail="转账的源账户与目标账户不能相同")
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

    bid = _resolve_book_id(db, current_user.user_id, transaction.book_id, create=True)
    transaction_data = transaction.model_dump(exclude={"book_id"})
    if transaction_data['transaction_time'] is None:
        transaction_data['transaction_time'] = datetime.now()

    db_transaction = model_ledger.Bill(**transaction_data, user_id=current_user.user_id, book_id=bid)

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
    book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """获取用户的交易记录列表（支持高级筛选）"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    query = db.query(model_ledger.Bill).filter(model_ledger.Bill.user_id == current_user.user_id)
    if bid is not None:
        query = query.filter(model_ledger.Bill.book_id == bid)

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

    # 第三步前置校验：若改为转账，目标账户必须存在、有效且不等于源账户
    if db_transaction.transaction_type == model_ledger.TransactionType.TRANSFER:
        if not db_transaction.to_account_id:
            raise HTTPException(status_code=400, detail="转账必须指定收入账户")
        if db_transaction.from_account_id == db_transaction.to_account_id:
            raise HTTPException(status_code=400, detail="转账的源账户与目标账户不能相同")
        to_account = db.query(model_ledger.Account).filter(
            model_ledger.Account.id == db_transaction.to_account_id,
            model_ledger.Account.user_id == current_user.user_id
        ).first()
        if not to_account:
            raise HTTPException(status_code=404, detail="收入账户不存在或不属于该用户")

    if db_transaction.amount is not None and db_transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="交易金额必须大于 0")

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
def get_summary(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取用户财务概览统计（总资产 / 本月收入 / 本月支出 / 本月结余）"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    acc_filter = [model_ledger.Account.user_id == current_user.user_id]
    bill_filter = [model_ledger.Bill.user_id == current_user.user_id]
    if bid is not None:
        acc_filter.append(model_ledger.Account.book_id == bid)
        bill_filter.append(model_ledger.Bill.book_id == bid)

    total_assets = db.query(func.sum(model_ledger.Account.balance)).filter(*acc_filter).scalar() or 0

    current_month = date.today().replace(day=1)

    monthly_income = db.query(func.sum(model_ledger.Bill.amount)).filter(
        *bill_filter,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= current_month
    ).scalar() or 0

    monthly_expense = db.query(func.sum(model_ledger.Bill.amount)).filter(
        *bill_filter,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= current_month
    ).scalar() or 0

    # 月度预算执行（仅读取，不写通知；通知由 statistics/budgets 端点落库）
    month_budget = None
    mb_q = db.query(model_ledger.LedgerBudget).filter(
        model_ledger.LedgerBudget.user_id == current_user.user_id,
        model_ledger.LedgerBudget.scope_type == "month",
    )
    if bid is not None:
        mb_q = mb_q.filter(model_ledger.LedgerBudget.book_id == bid)
    mb = mb_q.first()
    if mb:
        mb_amount = float(mb.amount)
        mb_threshold = float(mb.notify_threshold or 0.8)
        mb_ratio = (float(monthly_expense) / mb_amount) if mb_amount > 0 else 0.0
        month_budget = {
            "amount": mb_amount,
            "spent": float(monthly_expense),
            "remaining": round(mb_amount - float(monthly_expense), 2),
            "ratio": round(mb_ratio, 4),
            "threshold": mb_threshold,
            "status": "over" if mb_ratio >= 1 else ("warning" if mb_ratio >= mb_threshold else "ok"),
        }

    return {
        "total_assets": float(total_assets),
        "monthly_income": float(monthly_income),
        "monthly_expense": float(monthly_expense),
        "monthly_balance": float(monthly_income - monthly_expense),
        "month_budget": month_budget
    }

@router.get("/users/{user_id}/statistics/category", summary="按分类统计支出", tags=["统计分析"])
def get_category_statistics(
    user_id: str,
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """按分类统计用户支出情况"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
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
    if bid is not None:
        query = query.filter(model_ledger.Bill.book_id == bid)

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
    book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """按月统计指定年份的收支情况"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    monthly_income = db.query(
        extract('month', model_ledger.Bill.transaction_time).label('month'),
        func.sum(model_ledger.Bill.amount).label('amount')
    ).filter(
        model_ledger.Bill.user_id == current_user.user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        extract('year', model_ledger.Bill.transaction_time) == year
    )
    if bid is not None:
        monthly_income = monthly_income.filter(model_ledger.Bill.book_id == bid)
    monthly_income = monthly_income.group_by(extract('month', model_ledger.Bill.transaction_time)).all()

    monthly_expense = db.query(
        extract('month', model_ledger.Bill.transaction_time).label('month'),
        func.sum(model_ledger.Bill.amount).label('amount')
    ).filter(
        model_ledger.Bill.user_id == current_user.user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        extract('year', model_ledger.Bill.transaction_time) == year
    )
    if bid is not None:
        monthly_expense = monthly_expense.filter(model_ledger.Bill.book_id == bid)
    monthly_expense = monthly_expense.group_by(extract('month', model_ledger.Bill.transaction_time)).all()

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
def get_budget_stats(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取各项目的预算与实际支出对比"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    proj_q = db.query(model_ledger.Project).filter(model_ledger.Project.user_id == current_user.user_id)
    if bid is not None:
        proj_q = proj_q.filter(model_ledger.Project.book_id == bid)
    projects = proj_q.all()
    result = []
    for proj in projects:
        spent_q = db.query(func.sum(model_ledger.Bill.amount)).filter(
            model_ledger.Bill.project_id == proj.id,
            model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE
        )
        if bid is not None:
            spent_q = spent_q.filter(model_ledger.Bill.book_id == bid)
        total_spent = spent_q.scalar() or 0
        result.append({
            "project_id": proj.id,
            "project_name": proj.name,
            "budget": float(proj.budget) if proj.budget else 0,
            "spent": float(total_spent),
            "remaining": float(proj.budget) - float(total_spent) if proj.budget else 0
        })
    return result

# ================================ 预算管理API ================================

@router.post("/users/{user_id}/budgets/", response_model=ledger_schemas.BudgetResponse, summary="创建预算", tags=["预算管理"])
def create_budget(user_id: str, budget: ledger_schemas.BudgetCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """创建预算（月/分类/项目）。category/project 必须提供 scope_id；notify_threshold 默认 0.8。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    if budget.scope_type not in ("month", "category", "project"):
        raise HTTPException(status_code=400, detail="scope_type 仅支持 month|category|project")
    if budget.scope_type in ("category", "project") and not budget.scope_id:
        raise HTTPException(status_code=400, detail="category/project 预算必须指定 scope_id")
    if budget.amount <= 0:
        raise HTTPException(status_code=400, detail="预算金额必须大于 0")
    if budget.notify_threshold is not None and (budget.notify_threshold <= 0 or budget.notify_threshold > 1.5):
        raise HTTPException(status_code=400, detail="notify_threshold 应在 0~1.5 之间")
    bid = _resolve_book_id(db, current_user.user_id, budget.book_id, create=True)
    db_budget = model_ledger.LedgerBudget(
        **budget.model_dump(exclude={"book_id"}), user_id=current_user.user_id, book_id=bid
    )
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget

@router.get("/users/{user_id}/budgets/", response_model=List[ledger_schemas.BudgetResponse], summary="获取预算列表", tags=["预算管理"])
def get_budgets(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db), current_user: User = Depends(require_user)):
    """获取用户的预算列表（可按账本筛选）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    q = db.query(model_ledger.LedgerBudget).filter(model_ledger.LedgerBudget.user_id == current_user.user_id)
    if bid is not None:
        q = q.filter(model_ledger.LedgerBudget.book_id == bid)
    return q.order_by(model_ledger.LedgerBudget.scope_type, model_ledger.LedgerBudget.id).all()

@router.put("/users/{user_id}/budgets/{budget_id}", response_model=ledger_schemas.BudgetResponse, summary="更新预算", tags=["预算管理"])
def update_budget(user_id: str, budget_id: int, budget: ledger_schemas.BudgetUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新预算（仅提交的非空字段生效，需本人权限）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_budget = db.query(model_ledger.LedgerBudget).filter(
        model_ledger.LedgerBudget.id == budget_id,
        model_ledger.LedgerBudget.user_id == current_user.user_id
    ).first()
    if not db_budget:
        raise HTTPException(status_code=404, detail="预算不存在或不属于该用户")
    data = budget.model_dump(exclude_unset=True)
    if data.get("scope_type") is not None and data["scope_type"] not in ("month", "category", "project"):
        raise HTTPException(status_code=400, detail="scope_type 仅支持 month|category|project")
    # 合并后的最终取值：用于校验 category/project 必须有 scope_id
    final_scope_type = data.get("scope_type", db_budget.scope_type)
    final_scope_id = data.get("scope_id", db_budget.scope_id)
    if final_scope_type in ("category", "project") and not final_scope_id:
        raise HTTPException(status_code=400, detail="category/project 预算必须指定 scope_id")
    if data.get("amount") is not None and data["amount"] <= 0:
        raise HTTPException(status_code=400, detail="预算金额必须大于 0")
    if data.get("notify_threshold") is not None and (data["notify_threshold"] <= 0 or data["notify_threshold"] > 1.5):
        raise HTTPException(status_code=400, detail="notify_threshold 应在 0~1.5 之间")
    for key, value in data.items():
        setattr(db_budget, key, value)
    db.commit()
    db.refresh(db_budget)
    return db_budget

@router.delete("/users/{user_id}/budgets/{budget_id}", summary="删除预算", tags=["预算管理"])
def delete_budget(user_id: str, budget_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除预算（仅本人权限，需预算存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_budget = db.query(model_ledger.LedgerBudget).filter(
        model_ledger.LedgerBudget.id == budget_id,
        model_ledger.LedgerBudget.user_id == current_user.user_id
    ).first()
    if not db_budget:
        raise HTTPException(status_code=404, detail="预算不存在或不属于该用户")
    db.delete(db_budget)
    db.commit()
    return {"message": "预算已删除"}

@router.get("/users/{user_id}/statistics/budgets", summary="预算执行率与超支提醒", tags=["统计分析"])
def get_budget_execution(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db), current_user: User = Depends(require_user)):
    """返回各预算的当月执行率（已花/预算），并对跨过预警阈值的预算写 NotificationLog（去重）。

    status：ok(未到阈值) / warning(达阈值未超 100%) / over(已超 100%)；前端可借此渲染
    进度条与超支红标，并轮询 NotificationLog 展示提醒。
    """
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    q = db.query(model_ledger.LedgerBudget).filter(model_ledger.LedgerBudget.user_id == current_user.user_id)
    if bid is not None:
        q = q.filter(model_ledger.LedgerBudget.book_id == bid)
    budgets = q.all()
    month_start, month_end = _current_month_window()
    status = _compute_budget_status(db, current_user.user_id, budgets)
    return {
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "budgets": status
    }


@router.get("/users/{user_id}/notifications/", summary="获取通知（预算超支等提醒）", tags=["预算管理"])
def get_notifications(user_id: str, status: Optional[str] = Query(None, description="按状态筛选 pending|sent|failed"),
    db: Session = Depends(get_db), current_user: User = Depends(require_user)):
    """获取当前用户的通知记录（预算超支提醒等），前端轮询展示角标。

    仅返回本用户记录；可传 status 过滤（默认返回全部）。报告仅落库，不发短信/邮件。
    """
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    q = db.query(model_ledger.NotificationLog).filter(model_ledger.NotificationLog.user_id == current_user.user_id)
    if status:
        q = q.filter(model_ledger.NotificationLog.status == status)
    rows = q.order_by(model_ledger.NotificationLog.created_at.desc()).all()
    out = []
    for n in rows:
        content = None
        if n.report_content:
            try:
                content = json.loads(n.report_content)
            except Exception:
                content = n.report_content
        out.append({
            "id": n.id,
            "budget_id": n.budget_id,
            "period_start": n.period_start.isoformat() if n.period_start else None,
            "period_end": n.period_end.isoformat() if n.period_end else None,
            "content": content,
            "status": n.status.value if n.status else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })
    return out

# ================================ 借贷管理API ================================

@router.post("/users/{user_id}/debts/", response_model=ledger_schemas.DebtResponse, summary="记一笔借出/借入", tags=["借贷管理"])
def create_debt(user_id: str, debt: ledger_schemas.DebtCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """记录一笔借贷（lend=借出/债权，borrow=借入/债务）。person_id 可关联到人员。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    if debt.direction not in ("lend", "borrow"):
        raise HTTPException(status_code=400, detail="direction 仅支持 lend|borrow")
    if debt.total <= 0:
        raise HTTPException(status_code=400, detail="借贷金额必须大于 0")
    if debt.person_id:
        person = db.query(model_ledger.Person).filter(
            model_ledger.Person.id == debt.person_id,
            model_ledger.Person.user_id == current_user.user_id,
        ).first()
        if not person:
            raise HTTPException(status_code=404, detail="关联人员不存在或不属于该用户")
    bid = _resolve_book_id(db, current_user.user_id, debt.book_id, create=True)
    repaid = float(debt.repaid or 0)
    balance = float(debt.total) - repaid
    status = "cleared" if balance <= 0 else "active"
    db_debt = model_ledger.LedgerDebt(
        user_id=current_user.user_id, book_id=bid,
        person_id=debt.person_id, direction=debt.direction,
        total=debt.total, repaid=repaid, balance=balance,
        due_date=debt.due_date, status=status, note=debt.note,
    )
    db.add(db_debt)
    db.commit()
    db.refresh(db_debt)
    return db_debt

@router.get("/users/{user_id}/debts/", response_model=List[ledger_schemas.DebtResponse], summary="借贷清单", tags=["借贷管理"])
def get_debts(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    direction: Optional[str] = Query(None, description="lend|borrow"),
    status: Optional[str] = Query(None, description="active|cleared"),
    db: Session = Depends(get_db), current_user: User = Depends(require_user)):
    """获取借贷清单（可按账本/方向/状态筛选）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    q = db.query(model_ledger.LedgerDebt).filter(model_ledger.LedgerDebt.user_id == current_user.user_id)
    if bid is not None:
        q = q.filter(model_ledger.LedgerDebt.book_id == bid)
    if direction:
        q = q.filter(model_ledger.LedgerDebt.direction == direction)
    if status:
        q = q.filter(model_ledger.LedgerDebt.status == status)
    return q.order_by(model_ledger.LedgerDebt.created_at.desc()).all()

@router.put("/users/{user_id}/debts/{debt_id}", response_model=ledger_schemas.DebtResponse, summary="更新借贷", tags=["借贷管理"])
def update_debt(user_id: str, debt_id: int, debt: ledger_schemas.DebtUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新借贷（仅提交的非空字段生效，需本人权限）。total/repaid 变动自动重算 balance 与 status。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_debt = db.query(model_ledger.LedgerDebt).filter(
        model_ledger.LedgerDebt.id == debt_id,
        model_ledger.LedgerDebt.user_id == current_user.user_id,
    ).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="借贷不存在或不属于该用户")
    data = debt.model_dump(exclude_unset=True)
    if data.get("direction") is not None and data["direction"] not in ("lend", "borrow"):
        raise HTTPException(status_code=400, detail="direction 仅支持 lend|borrow")
    if data.get("person_id"):
        person = db.query(model_ledger.Person).filter(
            model_ledger.Person.id == data["person_id"],
            model_ledger.Person.user_id == current_user.user_id,
        ).first()
        if not person:
            raise HTTPException(status_code=404, detail="关联人员不存在或不属于该用户")
    for key, value in data.items():
        setattr(db_debt, key, value)
    # 重算未结清余额与状态（total/repaid 任一变动都需要）
    db_debt.balance = float(db_debt.total) - float(db_debt.repaid or 0)
    db_debt.status = "cleared" if db_debt.balance <= 0 else "active"
    db.commit()
    db.refresh(db_debt)
    return db_debt

@router.delete("/users/{user_id}/debts/{debt_id}", summary="删除借贷", tags=["借贷管理"])
def delete_debt(user_id: str, debt_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除借贷（仅本人权限，需借贷存在）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_debt = db.query(model_ledger.LedgerDebt).filter(
        model_ledger.LedgerDebt.id == debt_id,
        model_ledger.LedgerDebt.user_id == current_user.user_id,
    ).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="借贷不存在或不属于该用户")
    db.delete(db_debt)
    db.commit()
    return {"message": "借贷已删除"}

@router.post("/users/{user_id}/debts/{debt_id}/repay", response_model=ledger_schemas.DebtResponse, summary="还款/收款", tags=["借贷管理"])
def repay_debt(user_id: str, debt_id: int, repay: ledger_schemas.DebtRepayRequest, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """偿还/收回一笔借贷：生成一条 Bill（借出→收入收款，借入→支出还款）联动账户余额，并联动债务余额。

    遵循 D9 铁律：余额变更前对涉及的账户加 with_for_update()（经 _adjust_balance）。
    """
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_debt = db.query(model_ledger.LedgerDebt).filter(
        model_ledger.LedgerDebt.id == debt_id,
        model_ledger.LedgerDebt.user_id == current_user.user_id,
    ).first()
    if not db_debt:
        raise HTTPException(status_code=404, detail="借贷不存在或不属于该用户")
    if repay.amount <= 0:
        raise HTTPException(status_code=400, detail="还款金额必须大于 0")
    if db_debt.status == "cleared":
        raise HTTPException(status_code=400, detail="该借贷已结清")
    from_account = db.query(model_ledger.Account).filter(
        model_ledger.Account.id == repay.from_account_id,
        model_ledger.Account.user_id == current_user.user_id,
    ).first()
    if not from_account:
        raise HTTPException(status_code=404, detail="关联账户不存在或不属于该用户")

    # 借出→收款(income)，借入→还款(expense)
    ttype = model_ledger.TransactionType.INCOME if db_debt.direction == "lend" else model_ledger.TransactionType.EXPENSE
    now = repay.transaction_time or datetime.now()
    bill = model_ledger.Bill(
        user_id=current_user.user_id,
        book_id=db_debt.book_id,
        transaction_type=ttype,
        amount=repay.amount,
        from_account_id=repay.from_account_id,
        person_id=db_debt.person_id,
        note=repay.note or ("收回借款" if db_debt.direction == "lend" else "偿还借款"),
        transaction_time=now,
    )
    db.add(bill)
    db.flush()  # 取得 bill.id

    # 联动账户余额（带行锁）
    _adjust_balance(db, ttype, repay.amount, repay.from_account_id, None, 1)

    # 联动债务余额（已还累加，未结清余额递减，归零即结清）
    db_debt.repaid = float(db_debt.repaid or 0) + repay.amount
    db_debt.balance = float(db_debt.total) - db_debt.repaid
    if db_debt.balance <= 0:
        db_debt.balance = 0
        db_debt.status = "cleared"
    db.commit()
    db.refresh(db_debt)
    return db_debt

@router.get("/users/{user_id}/statistics/networth", summary="净资产（资产−负债）", tags=["统计分析"])
def get_networth(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db), current_user: User = Depends(require_user)):
    """计算净资产：资产 = 非信用卡账户余额合计 + 借出未收；负债 = 借入未还 + 信用卡应还(近似)。

    约定：信用卡账户余额视为「已消费待还欠款」（负债），不计入资产；净资产 = 资产 − 负债。
    可按账本筛选（仅统计该账本下的账户与借贷）。
    """
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    acc_filter = [model_ledger.Account.user_id == current_user.user_id]
    debt_filter = [model_ledger.LedgerDebt.user_id == current_user.user_id]
    if bid is not None:
        acc_filter.append(model_ledger.Account.book_id == bid)
        debt_filter.append(model_ledger.LedgerDebt.book_id == bid)

    # 全部账户余额原始合计（含信用卡）
    account_total = db.query(func.sum(model_ledger.Account.balance)).filter(*acc_filter).scalar() or 0
    # 信用卡应还（近似）：信用卡账户中余额 > 0 的部分视为欠款
    credit_payable = db.query(func.sum(model_ledger.Account.balance)).filter(
        *acc_filter,
        model_ledger.Account.account_type == model_ledger.AccountType.CREDIT_CARD,
        model_ledger.Account.balance > 0,
    ).scalar() or 0
    # 非信用卡账户余额合计
    non_credit_balance = float(account_total) - float(credit_payable)

    # 借出未收（资产，进行中）
    lent_outstanding = db.query(func.sum(model_ledger.LedgerDebt.balance)).filter(
        *debt_filter,
        model_ledger.LedgerDebt.direction == "lend",
        model_ledger.LedgerDebt.status == "active",
    ).scalar() or 0
    # 借入未还（负债，进行中）
    borrowed_outstanding = db.query(func.sum(model_ledger.LedgerDebt.balance)).filter(
        *debt_filter,
        model_ledger.LedgerDebt.direction == "borrow",
        model_ledger.LedgerDebt.status == "active",
    ).scalar() or 0

    assets = float(non_credit_balance) + float(lent_outstanding)
    liabilities = float(borrowed_outstanding) + float(credit_payable)
    net_worth = assets - liabilities
    return {
        "assets": round(assets, 2),
        "liabilities": round(liabilities, 2),
        "net_worth": round(net_worth, 2),
        "account_balance": round(float(non_credit_balance), 2),
        "lent_outstanding": round(float(lent_outstanding), 2),
        "borrowed_outstanding": round(float(borrowed_outstanding), 2),
        "credit_payable": round(float(credit_payable), 2),
    }

# ================================ 周期性交易 ================================

@router.post("/users/{user_id}/recurring/", response_model=ledger_schemas.RecurringTransactionResponse, summary="创建周期性交易", tags=["周期性交易"])
def create_recurring(user_id: str, rt: ledger_schemas.RecurringTransactionCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """创建周期性交易（如房租、订阅等）"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    next_run = rt.next_run or datetime.now()
    bid = _resolve_book_id(db, current_user.user_id, rt.book_id, create=True)
    rt_data = rt.model_dump(exclude={"book_id", "next_run"})
    db_rt = model_ledger.RecurringTransaction(
        **rt_data, user_id=current_user.user_id, book_id=bid, next_run=next_run, is_active=True
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
    然后按频率推进 next_run。通常由 tools/scheduler.py 每日 01:00 自动触发
    （run_due_recurring_all 遍历全量用户），此端点作为当前用户的按需补记入口。"""
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
            book_id=rt.book_id,
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
def export_csv(user_id: str, book_id: Optional[int] = Query(None, description="按账本筛选（缺省取默认账本）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """导出用户所有交易记录为 CSV 文件"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    bid = _resolve_book_id(db, current_user.user_id, book_id, create=False)
    q = db.query(model_ledger.Bill).filter(model_ledger.Bill.user_id == current_user.user_id)
    if bid is not None:
        q = q.filter(model_ledger.Bill.book_id == bid)
    transactions = q.order_by(model_ledger.Bill.transaction_time.desc()).all()

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
    bid = _resolve_book_id(db, current_user.user_id, None, create=True)
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
                book_id=bid,
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


# ================================ 账本管理API ================================

@router.post("/users/{user_id}/books/", response_model=ledger_schemas.BookResponse, summary="创建账本", tags=["账本管理"])
def create_book(user_id: str, book: ledger_schemas.BookCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """创建一本新的账本（如旅行账本、装修账本）。设为默认时自动取消其它默认账本。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    if book.is_default:
        db.query(model_ledger.LedgerBook).filter(
            model_ledger.LedgerBook.user_id == current_user.user_id,
            model_ledger.LedgerBook.is_default == True,  # noqa: E712
        ).update({model_ledger.LedgerBook.is_default: False})
    db_book = model_ledger.LedgerBook(**book.model_dump(), user_id=current_user.user_id)
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book


@router.get("/users/{user_id}/books/", response_model=List[ledger_schemas.BookResponse], summary="获取账本列表", tags=["账本管理"])
def get_books(user_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """获取用户的全部账本，并按账本聚合实时资产（账户余额合计）。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    # 确保至少有一个默认账本（首次使用时懒创建）
    _resolve_book_id(db, current_user.user_id, None, create=True)
    books = db.query(model_ledger.LedgerBook).filter(
        model_ledger.LedgerBook.user_id == current_user.user_id
    ).order_by(model_ledger.LedgerBook.is_default.desc(), model_ledger.LedgerBook.id.asc()).all()
    for b in books:
        bal = db.query(func.sum(model_ledger.Account.balance)).filter(
            model_ledger.Account.user_id == current_user.user_id,
            model_ledger.Account.book_id == b.id
        ).scalar() or 0
        b.balance = float(bal)
    db.commit()  # 持久化首次懒创建的默认账本，避免每次 GET 重建
    return books


@router.put("/users/{user_id}/books/{book_id}", response_model=ledger_schemas.BookResponse, summary="更新账本", tags=["账本管理"])
def update_book(user_id: str, book_id: int, book: ledger_schemas.BookUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """更新账本信息（改名/换色/设默认）。设为默认时自动取消其它默认账本。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_book = db.query(model_ledger.LedgerBook).filter(
        model_ledger.LedgerBook.id == book_id,
        model_ledger.LedgerBook.user_id == current_user.user_id
    ).first()
    if not db_book:
        raise HTTPException(status_code=404, detail="账本不存在或不属于该用户")
    if book.is_default:
        db.query(model_ledger.LedgerBook).filter(
            model_ledger.LedgerBook.user_id == current_user.user_id,
            model_ledger.LedgerBook.is_default == True,  # noqa: E712
            model_ledger.LedgerBook.id != book_id
        ).update({model_ledger.LedgerBook.is_default: False})
    update_data = book.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_book, key, value)
    db.commit()
    db.refresh(db_book)
    return db_book


@router.delete("/users/{user_id}/books/{book_id}", summary="删除账本", tags=["账本管理"])
def delete_book(user_id: str, book_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_user)):
    """删除账本。默认账本不可删；非空账本（含账户/账单/周期交易）须先清空或迁移。"""
    if user_id != current_user.user_id:
        raise HTTPException(403, "无权访问该账号数据")
    db_book = db.query(model_ledger.LedgerBook).filter(
        model_ledger.LedgerBook.id == book_id,
        model_ledger.LedgerBook.user_id == current_user.user_id
    ).first()
    if not db_book:
        raise HTTPException(status_code=404, detail="账本不存在或不属于该用户")
    if db_book.is_default:
        raise HTTPException(status_code=400, detail="默认账本不可删除")
    has_data = (
        db.query(model_ledger.Bill).filter(model_ledger.Bill.book_id == book_id).first()
        or db.query(model_ledger.Account).filter(model_ledger.Account.book_id == book_id).first()
        or db.query(model_ledger.RecurringTransaction).filter(model_ledger.RecurringTransaction.book_id == book_id).first()
    )
    if has_data:
        raise HTTPException(status_code=400, detail="账本仍含账户/账单/周期交易，请先清空或迁移后再删除")
    db.delete(db_book)
    db.commit()
    return {"message": "账本已删除"}
