"""管理后台：VIP 设置"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.user import User, VipUser

from . import router
from .common import _audit, _require_admin


class VipReq(BaseModel):
    user_id: str
    action: str  # add / remove
    note: str = ""


@router.post("/vip", summary="VIP 设置（增删 + 备注）")
def manage_vip(req: VipReq, db: Session = Depends(get_db),
               admin: Admin = Depends(_require_admin)):
    uid = req.user_id.strip()
    user = db.query(User).filter(User.user_id == uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    row = db.query(VipUser).filter(VipUser.user_id == uid).first()

    if req.action == "add":
        if row:
            row.note = req.note.strip()
        else:
            db.add(VipUser(user_id=uid, note=req.note.strip()))
        detail = f"开通 VIP（备注：{req.note.strip() or '无'}）"
    elif req.action == "remove":
        if row:
            db.delete(row)
        detail = "取消 VIP"
    else:
        raise HTTPException(400, "无效操作（add/remove）")

    db.commit()
    _audit(db, admin, "vip:" + req.action, uid, detail)
    return {"ok": True, "detail": detail}


__all__ = ["VipReq", "manage_vip"]
