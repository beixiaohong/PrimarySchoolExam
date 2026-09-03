"""网课（用户端）：系统网课列表（默认展示）+ 家长单独配置

- GET    /api/courses            用户可见网课（系统 + 家长配置合并，按排序）
- GET    /api/courses/parent     家长自己配置的网课（管理列表）
- POST   /api/courses/parent     家长添加网课 {user_id, title, video_url, subject, grade, description}
- DELETE /api/courses/parent/{id} 家长删除自己的网课

可见性：
- 系统网课：enabled 且（subject 为空或匹配）+（grade=0 或匹配用户年级）
- 家长网课：parent_uid == 当前账号（user_id）
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.online_course import OnlineCourse

router = APIRouter()


def _course_out(c: OnlineCourse) -> dict:
    return {
        "id": c.id, "title": c.title, "subject": c.subject or "不限",
        "grade": c.grade, "description": c.description or "",
        "cover_url": c.cover_url or "", "video_url": c.video_url or "",
        "duration_min": c.duration_min, "source": c.source,
        "sort_order": c.sort_order,
    }


@router.get("", summary="用户可见网课列表（系统 + 家长配置）")
def list_courses(user_id: str = Query(..., description="用户名"),
                 grade: int = Query(6, description="年级"),
                 subject: str = Query("", description="学科筛选，空=全部"),
                 db: Session = Depends(get_db)):
    """系统网课（按学科/年级过滤）+ 家长为该用户配置的网课，按 sort_order 合并。"""
    q = db.query(OnlineCourse).filter(OnlineCourse.enabled == True)  # noqa: E712
    q = q.filter(or_(
        (OnlineCourse.source == "system") & (OnlineCourse.grade.in_((0, grade))),
        (OnlineCourse.source == "parent") & (OnlineCourse.parent_uid == user_id),
    ))
    if subject:
        q = q.filter(or_(OnlineCourse.subject == "", OnlineCourse.subject == subject))
    rows = q.order_by(OnlineCourse.sort_order, OnlineCourse.id).all()
    return {"courses": [_course_out(c) for c in rows]}


@router.get("/parent", summary="家长自己配置的网课列表")
def list_parent_courses(user_id: str = Query(..., description="用户名"),
                        db: Session = Depends(get_db)):
    rows = (db.query(OnlineCourse)
            .filter(OnlineCourse.source == "parent",
                    OnlineCourse.parent_uid == user_id)
            .order_by(OnlineCourse.sort_order, OnlineCourse.id).all())
    return {"courses": [_course_out(c) for c in rows]}


class ParentCourseReq(BaseModel):
    user_id: str
    title: str
    video_url: str
    subject: str = ""
    grade: int = 0
    description: str = ""


@router.post("/parent", summary="家长添加网课")
def create_parent_course(req: ParentCourseReq, db: Session = Depends(get_db)):
    title = (req.title or "").strip()
    video_url = (req.video_url or "").strip()
    if not title or not video_url:
        raise HTTPException(400, "标题与视频链接必填")
    c = OnlineCourse(title=title[:100], subject=(req.subject or "")[:20],
                     grade=req.grade, description=(req.description or "")[:2000],
                     video_url=video_url[:500], source="parent",
                     parent_uid=req.user_id, enabled=True)
    db.add(c)
    db.commit()
    return {"id": c.id, "ok": True}


@router.delete("/parent/{cid}", summary="家长删除自己配置的网课")
def delete_parent_course(cid: int, user_id: str = Query(..., description="用户名"),
                         db: Session = Depends(get_db)):
    c = db.query(OnlineCourse).filter(
        OnlineCourse.id == cid, OnlineCourse.source == "parent",
        OnlineCourse.parent_uid == user_id).first()
    if not c:
        raise HTTPException(404, "网课不存在（只能删除自己配置的）")
    db.delete(c)
    db.commit()
    return {"ok": True}


__all__ = ["router"]
