"""管理后台：系统网课管理（需求2：网课模块——后台配置系统网课）

- GET    /api/admin/courses        系统网课列表（按学科/关键字）
- POST   /api/admin/courses        新增系统网课
- PUT    /api/admin/courses/{id}   编辑
- DELETE /api/admin/courses/{id}   删除（仅系统网课；家长配置的由家长自己管理）
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.online_course import OnlineCourse

from . import router
from .common import _audit, _require_admin


class CourseReq(BaseModel):
    title: str
    subject: str = ""          # 空=不限学科
    grade: int = 0             # 0=不限年级
    description: str = ""
    cover_url: str = ""
    video_url: str = ""
    duration_min: int = 0
    enabled: bool = True
    sort_order: int = 0


@router.get("/courses", summary="系统网课列表")
def list_courses(subject: str = "", keyword: str = "",
                 db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    q = db.query(OnlineCourse).filter(OnlineCourse.source == "system")
    if subject:
        q = q.filter(OnlineCourse.subject == subject)
    kw = keyword.strip()
    if kw:
        q = q.filter(OnlineCourse.title.like(f"%{kw}%"))
    rows = q.order_by(OnlineCourse.sort_order, OnlineCourse.id).all()
    return {"items": [{
        "id": c.id, "title": c.title, "subject": c.subject or "不限",
        "grade": c.grade, "description": c.description or "",
        "cover_url": c.cover_url or "", "video_url": c.video_url or "",
        "duration_min": c.duration_min, "enabled": bool(c.enabled),
        "sort_order": c.sort_order,
    } for c in rows]}


@router.post("/courses", summary="新增系统网课")
def create_course(req: CourseReq, db: Session = Depends(get_db),
                  admin: Admin = Depends(_require_admin)):
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "课程标题不能为空")
    if not (req.video_url or "").strip():
        raise HTTPException(400, "视频 URL 必填")
    c = OnlineCourse(title=title[:100], subject=(req.subject or "")[:20],
                     grade=req.grade, description=(req.description or "")[:2000],
                     cover_url=(req.cover_url or "").strip()[:500],
                     video_url=(req.video_url or "").strip()[:500],
                     duration_min=max(0, req.duration_min),
                     enabled=req.enabled, sort_order=req.sort_order,
                     source="system")
    db.add(c)
    db.commit()
    _audit(db, admin.user_id, "course_create", f"新增网课 {title}")
    return {"id": c.id, "ok": True}


@router.put("/courses/{cid}", summary="编辑系统网课")
def update_course(cid: int, req: CourseReq, db: Session = Depends(get_db),
                  admin: Admin = Depends(_require_admin)):
    c = db.query(OnlineCourse).filter(
        OnlineCourse.id == cid, OnlineCourse.source == "system").first()
    if not c:
        raise HTTPException(404, "网课不存在")
    c.title = (req.title or "").strip()[:100]
    c.subject, c.grade = (req.subject or "")[:20], req.grade
    c.description = (req.description or "")[:2000]
    c.cover_url = (req.cover_url or "").strip()[:500]
    c.video_url = (req.video_url or "").strip()[:500]
    c.duration_min = max(0, req.duration_min)
    c.enabled, c.sort_order = req.enabled, req.sort_order
    db.commit()
    _audit(db, admin.user_id, "course_update", f"编辑网课 id={cid}")
    return {"ok": True}


@router.delete("/courses/{cid}", summary="删除系统网课")
def delete_course(cid: int, db: Session = Depends(get_db),
                  admin: Admin = Depends(_require_admin)):
    c = db.query(OnlineCourse).filter(
        OnlineCourse.id == cid, OnlineCourse.source == "system").first()
    if not c:
        raise HTTPException(404, "网课不存在")
    db.delete(c)
    db.commit()
    _audit(db, admin.user_id, "course_delete", f"删除网课 id={cid} ({c.title})")
    return {"ok": True}
