"""教材版本（用户端）：版本列表 + 用户每学科选择 + 默认版本解析

- GET  /api/textbook/versions?subject=&grade=  启用版本列表（按 sort_order,id 升序）
- GET  /api/textbook/prefs?user_id=            各学科当前生效版本（未配置回退默认）
- PUT  /api/textbook/prefs                     保存用户选择 {user_id, subject, textbook_id}

helper resolve_textbook_id：供词汇等模块按用户教材版本过滤取词（未配置取默认）。
S6 增强：按用户所在省份（IP 解析）优先匹配本地版本（TextbookVersion.region），
未配置省份时回退全国通用版本（region=''）。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.textbook import TextbookVersion, UserTextbookPref
from app.domains.platform.contracts import get_geo_by_request

router = APIRouter()

SUBJECTS = ("数学", "语文", "英语")


def _default_version(db: Session, subject: str, grade: int,
                     province_code: str = "") -> Optional[TextbookVersion]:
    """该学科年级的默认版本：
    1) province_code 非空时优先匹配 region=province_code 的版本；
    2) 否则回退 region='' 的全国通用版本；
    取 sort_order 最小，其次 id 最小；未启用不参与默认。
    """
    q = (db.query(TextbookVersion)
         .filter(TextbookVersion.subject == subject,
                 TextbookVersion.grade == grade,
                 TextbookVersion.enabled == True))  # noqa: E712
    if province_code:
        # 优先本省版本
        local = (q.filter(TextbookVersion.region == province_code)
                 .order_by(TextbookVersion.sort_order, TextbookVersion.id)
                 .first())
        if local:
            return local
    # 回退全国通用版本
    return (q.filter(TextbookVersion.region == "")
            .order_by(TextbookVersion.sort_order, TextbookVersion.id)
            .first())


def resolve_textbook_id(db: Session, user_id: str, subject: str, grade: int,
                        province_code: str = "") -> Optional[int]:
    """返回用户该学科应使用的版本 id：
    用户选择（且启用）→ 用户省份版本（region=province_code）→ 通用默认（region=''）。
    province_code 为空时跳过省份匹配（兼容未传 IP 的内部调用）。
    """
    if subject not in SUBJECTS:
        return None
    pref = db.query(UserTextbookPref).filter(
        UserTextbookPref.user_id == user_id,
        UserTextbookPref.subject == subject,
    ).first()
    if pref:
        t = db.query(TextbookVersion).filter(
            TextbookVersion.id == pref.textbook_id,
            TextbookVersion.enabled == True,  # noqa: E712
        ).first()
        if t:
            return t.id
    d = _default_version(db, subject, grade, province_code=province_code)
    return d.id if d else None


@router.get("/versions", summary="教材版本列表（启用，按排序）")
def list_versions(subject: str = Query(..., description="学科"),
                  grade: int = Query(6, description="年级"),
                  db: Session = Depends(get_db)):
    """返回启用中的教材版本（sort_order,id 升序），供选择下拉。"""
    if subject not in SUBJECTS:
        raise HTTPException(400, "subject 仅支持 数学/语文/英语")
    rows = (db.query(TextbookVersion)
            .filter(TextbookVersion.subject == subject,
                    TextbookVersion.grade == grade,
                    TextbookVersion.enabled == True)  # noqa: E712
            .order_by(TextbookVersion.sort_order, TextbookVersion.id)
            .all())
    return {"versions": [{
        "id": t.id, "name": t.name, "subject": t.subject, "grade": t.grade,
        "sort_order": t.sort_order, "region": t.region or "",
    } for t in rows]}


class PrefReq(BaseModel):
    user_id: str
    subject: str
    textbook_id: int = 0  # 0 = 清除选择（回退默认）


@router.get("/prefs", summary="各学科当前生效教材版本")
def get_prefs(request: Request,
              user_id: str = Query(..., description="用户名"),
              grade: int = Query(6, description="年级"),
              db: Session = Depends(get_db)):
    """返回每学科当前生效版本（用户选择 → 用户省份版本 → 通用默认）；
    province_code 来自 IP 解析（缓存）；未配置任何版本时 textbook_id=0。"""
    geo = get_geo_by_request(request)
    province_code = geo.province_code if geo else ""
    result = []
    for subject in SUBJECTS:
        tid = resolve_textbook_id(db, user_id, subject, grade,
                                  province_code=province_code)
        name = ""
        if tid:
            t = db.get(TextbookVersion, tid)
            name = t.name if t else ""
        result.append({"subject": subject, "grade": grade,
                       "textbook_id": tid or 0, "textbook_name": name,
                       "region": province_code or ""})
    return {"prefs": result, "province_code": province_code or "",
            "country_code": geo.country_code if geo else ""}


@router.put("/prefs", summary="保存用户教材版本选择")
def save_pref(req: PrefReq, db: Session = Depends(get_db)):
    if req.subject not in SUBJECTS:
        raise HTTPException(400, "subject 仅支持 数学/语文/英语")
    pref = db.query(UserTextbookPref).filter(
        UserTextbookPref.user_id == req.user_id,
        UserTextbookPref.subject == req.subject,
    ).first()
    if req.textbook_id <= 0:
        if pref:
            db.delete(pref)
            db.commit()
        return {"ok": True, "subject": req.subject, "textbook_id": 0}
    t = db.get(TextbookVersion, req.textbook_id)
    if not t or t.subject != req.subject or not t.enabled:
        raise HTTPException(400, "教材版本不存在或未启用")
    if not pref:
        pref = UserTextbookPref(user_id=req.user_id, subject=req.subject,
                                textbook_id=t.id)
        db.add(pref)
    else:
        pref.textbook_id = t.id
    db.commit()
    return {"ok": True, "subject": req.subject, "textbook_id": t.id}


__all__ = ["router", "resolve_textbook_id"]
