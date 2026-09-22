"""小说站社区：读者评论表 db_novel_comments

新增一张表支撑「小说站社区」的书评/短评（#8 增强项）。
幂等建表：checkfirst=True，重复迁移不会报错。
"""
from alembic import op
import sqlalchemy as sa

from app.database import Base
from app.models.novel import NovelComment

# 迁移标识（Alembic 用，保持唯一）
revision = "078_novel_comment"
down_revision = "077_novel_bookmark"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    NovelComment.__table__.create(bind=bind, checkfirst=True)
    # 兼容性兜底：极早期部署可能缺 (novel_id, created_at) 复合索引
    insp = sa.inspect(bind)
    existing = set(insp.get_indexes("db_novel_comments"))
    if "idx_nc_novel_created" not in existing:
        op.create_index("idx_nc_novel_created", "db_novel_comments",
                        ["novel_id", "created_at"], if_not_exists=True)


def downgrade():
    bind = op.get_bind()
    NovelComment.__table__.drop(bind=bind, checkfirst=True)
