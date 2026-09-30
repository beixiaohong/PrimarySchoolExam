"""工作台路由（/api/workspace）

只提供两件平台级能力，**不含任何业务逻辑**（blog.md §11：Workspace 负责聚合与展示，
业务模块负责业务数据）：
- 模块使用记录读写（我的应用 / 最近使用）；
- 最新内容的轻量聚合（内部转调 blog 域的 latest_articles）。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.contracts import require_user
from app.models.user import User
from app.schemas.blog import AppUsageResponse, LatestArticleItem
from app.domains.blog.services import workspace as ws_svc
from app.domains.blog.services import articles as articles_svc

logger = logging.getLogger(__name__)

router = APIRouter()


class AppUsageIn(BaseModel):
    """记录模块访问的入参。app_key 由前端 apps.js 的模块注册表定义。"""
    app_key: str


@router.post("/usage", response_model=AppUsageResponse, summary="记录模块访问", tags=["工作台"])
def record_usage(
    payload: AppUsageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """进入某模块时上报一次访问：累加次数并刷新最近访问时间。"""
    return ws_svc.record_app_usage(db, current_user.user_id, payload.app_key)


@router.get("/usage", response_model=list[AppUsageResponse], summary="模块使用记录", tags=["工作台"])
def list_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """当前用户的模块使用记录（按最近访问倒序，供首页排「我的应用 / 最近使用」）。"""
    return ws_svc.list_app_usage(db, current_user.user_id)


@router.get("/latest", response_model=list[LatestArticleItem], summary="最新内容", tags=["工作台"])
def latest_content(
    limit: int = Query(5, ge=1, le=20, description="返回条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """首页「最新内容」：转调内容模块的已发布文章聚合（不含正文）。"""
    return articles_svc.latest_articles(db, limit=limit)
