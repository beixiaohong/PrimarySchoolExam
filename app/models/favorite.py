"""用户收藏夹模型（新功能 D 收藏夹，2026Q4）

设计：仅存 user_id + item_type(paper/question) + item_id + 可选 title 快照，
避免跨域 JOIN（试卷/题目详情由各域经 contracts 提供）。唯一键
(user_id, item_type, item_id) 保证同一用户对同一对象不重复收藏。

title 为去规范化快照（收藏时由客户端传入），便于列表直接展示；item 被删除后
允许变孤儿（列表展示时标记为「已失效」即可，MVP 不强制清理）。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from ..database import Base


class UserFavorite(Base):
    """用户收藏（试卷 / 题目）"""
    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "item_type", "item_id",
                         name="uq_fav_user_item"),
        {"comment": "用户收藏夹：paper/question 去重收藏，title 为去规范化快照便于列表展示"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名（与 daily_tasks 等一致）")
    item_type = Column(String(20), nullable=False, comment="类型：paper=试卷 / question=题目")
    item_id = Column(String(64), nullable=False, comment="被收藏对象 id（试卷 id / 题目 id）")
    title = Column(String(200), nullable=True, comment="去规范化标题快照（收藏时由客户端传入）")
    created_at = Column(DateTime, default=datetime.now, comment="收藏时间")
