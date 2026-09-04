"""管理后台：教材版本配置（需求：每科目教材版本选择，每年级每科目单独配置）

- GET    /api/admin/textbooks          版本列表（按学科+年级筛选）
- POST   /api/admin/textbooks         新增版本
- PUT    /api/admin/textbooks/{id}    编辑版本（名称/排序/启用/省份/备注）
- DELETE /api/admin/textbooks/{id}    删除版本
- GET    /api/admin/textbooks/regions 省/直辖市代码字典（用于 region 下拉）
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.textbook import TextbookVersion

from . import router
from .common import _audit, _require_admin


class TextbookReq(BaseModel):
    subject: str          # 学科：数学/语文/英语
    grade: int            # 年级 1-9
    name: str             # 版本名，如 人教版
    sort_order: int = 0
    enabled: bool = True
    region: str = ""      # 省份代码（chinaAdminCode 前 2 位；空=全国通用）
    remark: str = ""


@router.get("/textbooks", summary="教材版本列表（按学科+年级+地区筛选）")
def list_textbooks(subject: str = "", grade: int = 0, region: str = "",
                   db: Session = Depends(get_db),
                   admin: Admin = Depends(_require_admin)):
    """教材版本列表。参数：subject（可选）、grade（可选，>0 过滤）、region（可选，省份代码）。"""
    q = db.query(TextbookVersion)
    if subject:
        q = q.filter(TextbookVersion.subject == subject)
    if grade > 0:
        q = q.filter(TextbookVersion.grade == grade)
    if region:
        q = q.filter(TextbookVersion.region == region)
    rows = q.order_by(TextbookVersion.subject, TextbookVersion.grade,
                      TextbookVersion.sort_order, TextbookVersion.id).all()
    return {"total": len(rows), "items": [{
        "id": t.id, "subject": t.subject, "grade": t.grade, "name": t.name,
        "sort_order": t.sort_order, "enabled": bool(t.enabled),
        "region": t.region or "",
        "remark": t.remark or "", "created_at": str(t.created_at)[:10] if t.created_at else "",
    } for t in rows]}


@router.post("/textbooks", summary="新增教材版本")
def create_textbook(req: TextbookReq, db: Session = Depends(get_db),
                    admin: Admin = Depends(_require_admin)):
    subject = (req.subject or "").strip()
    name = (req.name or "").strip()
    if subject not in ("数学", "语文", "英语"):
        raise HTTPException(400, "subject 仅支持 数学/语文/英语")
    if not name:
        raise HTTPException(400, "版本名不能为空")
    if not (1 <= req.grade <= 9):
        raise HTTPException(400, "年级需在 1-9 之间")
    region = (req.region or "").strip()[:8]
    dup = db.query(TextbookVersion).filter(
        TextbookVersion.subject == subject,
        TextbookVersion.grade == req.grade,
        TextbookVersion.name == name,
    ).first()
    if dup:
        raise HTTPException(400, f"该学科年级已存在版本「{name}」")
    t = TextbookVersion(subject=subject, grade=req.grade, name=name[:50],
                        sort_order=req.sort_order, enabled=req.enabled,
                        region=region,
                        remark=(req.remark or "")[:200])
    db.add(t)
    db.commit()
    _audit(db, admin, "textbook_create", f"tb:{t.id}",
           f"新增教材版本 {subject}/{req.grade}年级/{name} region={region or '全国'}")
    return {"id": t.id, "ok": True}


@router.put("/textbooks/{tid}", summary="编辑教材版本")
def update_textbook(tid: int, req: TextbookReq, db: Session = Depends(get_db),
                    admin: Admin = Depends(_require_admin)):
    t = db.get(TextbookVersion, tid)
    if not t:
        raise HTTPException(404, "版本不存在")
    subject = (req.subject or "").strip()
    name = (req.name or "").strip()
    if subject not in ("数学", "语文", "英语"):
        raise HTTPException(400, "subject 仅支持 数学/语文/英语")
    if not name:
        raise HTTPException(400, "版本名不能为空")
    dup = db.query(TextbookVersion).filter(
        TextbookVersion.subject == subject,
        TextbookVersion.grade == req.grade,
        TextbookVersion.name == name,
        TextbookVersion.id != tid,
    ).first()
    if dup:
        raise HTTPException(400, f"该学科年级已存在版本「{name}」")
    t.subject, t.grade, t.name = subject, req.grade, name[:50]
    t.sort_order, t.enabled = req.sort_order, req.enabled
    t.region = (req.region or "").strip()[:8]
    t.remark = (req.remark or "")[:200]
    db.commit()
    _audit(db, admin, "textbook_update", f"tb:{tid}",
           f"编辑教材版本 id={tid} region={t.region or '全国'}")
    return {"ok": True}


@router.delete("/textbooks/{tid}", summary="删除教材版本")
def delete_textbook(tid: int, db: Session = Depends(get_db),
                    admin: Admin = Depends(_require_admin)):
    t = db.get(TextbookVersion, tid)
    if not t:
        raise HTTPException(404, "版本不存在")
    from app.models.word import WordBook
    bound = db.query(WordBook).filter(WordBook.textbook_id == tid).count()
    if bound > 0:
        raise HTTPException(400, f"该版本下仍有 {bound} 本词书绑定，请先调整词书版本后再删除")
    db.delete(t)
    db.commit()
    _audit(db, admin, "textbook_delete", f"tb:{tid}", f"删除教材版本 id={tid} ({t.name})")
    return {"ok": True}


# 中国省/直辖市代码字典（chinaAdminCode 前 2 位 + GB/T 2260）
# 来源：https://www.mca.gov.cn/article/sj/xzqh/1980/ 民政部行政区划
_CHINA_REGIONS = [
    {"code": "11", "name": "北京市"},
    {"code": "12", "name": "天津市"},
    {"code": "13", "name": "河北省"},
    {"code": "14", "name": "山西省"},
    {"code": "15", "name": "内蒙古自治区"},
    {"code": "21", "name": "辽宁省"},
    {"code": "22", "name": "吉林省"},
    {"code": "23", "name": "黑龙江省"},
    {"code": "31", "name": "上海市"},
    {"code": "32", "name": "江苏省"},
    {"code": "33", "name": "浙江省"},
    {"code": "34", "name": "安徽省"},
    {"code": "35", "name": "福建省"},
    {"code": "36", "name": "江西省"},
    {"code": "37", "name": "山东省"},
    {"code": "41", "name": "河南省"},
    {"code": "42", "name": "湖北省"},
    {"code": "43", "name": "湖南省"},
    {"code": "44", "name": "广东省"},
    {"code": "45", "name": "广西壮族自治区"},
    {"code": "46", "name": "海南省"},
    {"code": "50", "name": "重庆市"},
    {"code": "51", "name": "四川省"},
    {"code": "52", "name": "贵州省"},
    {"code": "53", "name": "云南省"},
    {"code": "54", "name": "西藏自治区"},
    {"code": "61", "name": "陕西省"},
    {"code": "62", "name": "甘肃省"},
    {"code": "63", "name": "青海省"},
    {"code": "64", "name": "宁夏回族自治区"},
    {"code": "65", "name": "新疆维吾尔自治区"},
    {"code": "71", "name": "台湾省"},
    {"code": "81", "name": "中国香港"},
    {"code": "82", "name": "中国澳门"},
]


@router.get("/textbooks/regions", summary="中国省/直辖市代码字典")
def list_regions(admin: Admin = Depends(_require_admin)):
    """返回中国省/直辖市代码字典，供教材版本 region 下拉。
    教材版本 region 为空字符串表示「全国通用」，否则匹配该省。
    """
    return {"regions": _CHINA_REGIONS, "default_label": "全国通用"}
