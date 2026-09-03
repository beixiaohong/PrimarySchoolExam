"""管理后台：多 AI 联合校对（D6）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.domains.engine.contracts import review_service

from . import router
from .common import _audit, _require_admin


class ReviewRunReq(BaseModel):
    """批量触发多 AI 校对请求：内容类型列表与数量上限。"""
    content_types: list = []   # 空=全部（middle_question/reading_passage）
    limit: int = 50


class ReviewResolveReq(BaseModel):
    """人工裁决校对请求：内容类型、内容 id 与裁决结果。"""
    content_type: str         # middle_question / reading_passage
    content_id: int
    verdict: str              # approved / rejected


@router.post("/reviews/run", summary="批量触发多 AI 校对（双供应商独立审阅）")
def reviews_run(req: ReviewRunReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    """批量触发多 AI 联合校对（双供应商独立审阅），并记审计日志。

    参数：req：content_types（空=全部）、limit。
    副作用：调用 review_service.run_reviews 执行校对、记审计日志。
    返回：{"ok": true, "reviewed","approved","conflict", ...}。
    """
    result = review_service.run_reviews(db, content_types=req.content_types or None,
                                         limit=req.limit, user_id=admin.username)
    _audit(db, admin, "reviews:run", "content_review",
           f"校对 {result['reviewed']} 条（approved={result['approved']}, conflict={result['conflict']}）")
    return {"ok": True, **result}


@router.get("/reviews", summary="审核队列（按状态过滤，默认 conflict）")
def reviews_queue(status: str = "conflict", page: int = 1, page_size: int = 20,
                  db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    """查询审核队列（按状态过滤，默认 conflict），委托 review_service 分页返回。"""
    data = review_service.list_reviews(db, status=status, page=page, page_size=page_size)
    return data


@router.post("/reviews/resolve", summary="人工裁决（采纳 approved / 驳回 rejected）")
def reviews_resolve(req: ReviewResolveReq, db: Session = Depends(get_db),
                    admin: Admin = Depends(_require_admin)):
    """人工裁决某条校对内容（采纳 approved / 驳回 rejected），并记审计日志。

    参数：req：content_type、content_id、verdict。
    业务约束：裁决失败（返回非 ok）时抛出 400。
    副作用：调用 review_service.resolve_review、记审计日志。
    返回：review_service 的结果字典。
    """
    result = review_service.resolve_review(db, req.content_type, req.content_id, req.verdict)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "裁决失败"))
    _audit(db, admin, "reviews:resolve", f"{req.content_type}#{req.content_id}", req.verdict)
    return result


__all__ = ["ReviewRunReq", "ReviewResolveReq", "reviews_run", "reviews_queue", "reviews_resolve"]
