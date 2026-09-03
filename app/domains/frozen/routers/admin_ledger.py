"""管理后台-个人账本数据管理（D9 冻结域，自 app/routers/admin_panel.py 迁出，端点与逻辑不变）

跨用户查看账单/账户/分类并支持删除（运营兜底）；挂载受 ENABLE_LEDGER 开关控制。
所有写操作落 admin_operation_logs 审计。
注：_require_admin/_audit 复用管理后台（admin 包），属既有跨域依赖，已记入契约债清单。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.ledger import Bill, Account, Category
from app.routers.admin import _require_admin, _audit

router = APIRouter()


# ═══════════════════════ 账本(ledger)管理 ═══════════════════════

def _bill_to_dict(b: Bill) -> dict:
    """将 Bill 模型对象转为前端展示字典（时间格式化、枚举转值）。"""
    return {
        "id": b.id, "user_id": b.user_id,
        "transaction_type": b.transaction_type.value if b.transaction_type else None,
        "amount": str(b.amount), "category_id": b.category_id,
        "note": b.note, "transaction_time": b.transaction_time.strftime("%Y-%m-%d %H:%M") if b.transaction_time else None,
    }


@router.get("/ledger/bills", summary="账本账单列表(跨用户)")
def list_bills(
    user_id: str = Query(None, description="按用户筛选"),
    skip: int = 0, limit: int = 50,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """跨用户分页查询账本账单列表，可按 user_id 筛选。"""
    q = db.query(Bill)
    if user_id:
        q = q.filter(Bill.user_id == user_id)
    total = q.count()
    rows = q.order_by(Bill.id.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [_bill_to_dict(b) for b in rows]}


@router.delete("/ledger/bills/{bill_id}", summary="删除账单")
def delete_bill(bill_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """删除指定账单（运营兜底），并记审计日志。"""
    b = db.query(Bill).filter(Bill.id == bill_id).first()
    if not b:
        raise HTTPException(404, "账单不存在")
    db.delete(b)
    db.commit()
    _audit(db, admin, "ledger_bill_delete", str(bill_id), f"user_id={b.user_id}")
    return {"ok": True}


@router.get("/ledger/accounts", summary="账本账户列表(跨用户)")
def list_accounts(user_id: str = None, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """跨用户查询账本账户列表，可按 user_id 筛选。"""
    q = db.query(Account)
    if user_id:
        q = q.filter(Account.user_id == user_id)
    rows = q.order_by(Account.id.desc()).all()
    return {"total": len(rows), "items": [
        {"id": a.id, "user_id": a.user_id, "account_name": a.account_name,
         "account_type": a.account_type.value if a.account_type else None,
         "balance": str(a.balance)} for a in rows]}


@router.delete("/ledger/accounts/{account_id}", summary="删除账户")
def delete_account(account_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """删除指定账本账户，并记审计日志。"""
    a = db.query(Account).filter(Account.id == account_id).first()
    if not a:
        raise HTTPException(404, "账户不存在")
    db.delete(a)
    db.commit()
    _audit(db, admin, "ledger_account_delete", str(account_id), f"user_id={a.user_id}")
    return {"ok": True}


@router.get("/ledger/categories", summary="账本分类列表(跨用户)")
def list_categories(user_id: str = None, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """跨用户查询账本分类列表（含三级分类），可按 user_id 筛选。"""
    q = db.query(Category)
    if user_id:
        q = q.filter(Category.user_id == user_id)
    rows = q.order_by(Category.id.desc()).all()
    return {"total": len(rows), "items": [
        {"id": c.id, "user_id": c.user_id,
         "category_type": c.category_type.value if c.category_type else None,
         "level1": c.level1, "level2": c.level2, "level3": c.level3} for c in rows]}


@router.delete("/ledger/categories/{category_id}", summary="删除分类")
def delete_category(category_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """删除指定账本分类，并记审计日志。"""
    c = db.query(Category).filter(Category.id == category_id).first()
    if not c:
        raise HTTPException(404, "分类不存在")
    db.delete(c)
    db.commit()
    _audit(db, admin, "ledger_category_delete", str(category_id), f"user_id={c.user_id}")
    return {"ok": True}
