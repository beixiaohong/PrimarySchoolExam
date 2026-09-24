"""079 - 收藏夹 user_favorites 表（新功能 D 收藏夹，2026Q4）

新建 user_favorites 表：user_id / item_type / item_id / title / created_at，
唯一键 (user_id, item_type, item_id)。幂等建表（checkfirst），可重复执行。
模型单一真相源见 app/models/favorite.py。
"""
from app.models.favorite import UserFavorite


def upgrade(db):
    bind = db.get_bind()
    UserFavorite.__table__.create(bind=bind, checkfirst=True)
    db.commit()
