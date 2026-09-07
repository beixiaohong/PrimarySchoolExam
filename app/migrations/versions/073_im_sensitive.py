"""073 - IM 敏感词过滤（D4 决策）

新建两张表（与 `app/models/im.py` 的 SensitiveWord / SensitiveHit 单一真相源一致，幂等建）：
- `db_im_sensitive_words`：敏感词库（后台可增删改停）；
- `db_im_sensitive_hits`：命中记录（后台审计与 Top 词统计）。

同时写入一批基础词（覆盖辱骂/广告引流/涉黄涉暴等通用类别），
已存在（按 word 唯一）则跳过，重复执行无副作用。

注意：本迁移只建表与灌基础词，**不开箱即硬性拦截**——动作由词库的 level 决定，
默认 reject；如需先观察误杀，可在后台把词批量改为 replace。
"""
import logging
from datetime import datetime

from sqlalchemy import text

from app.models.im import SensitiveWord, SensitiveHit

logger = logging.getLogger("migrations")

# 基础词库：运营/合规可在后台继续补充（避免留空导致功能形同虚设）
SEED_WORDS = [
    # 辱骂
    ("傻逼", "abuse"), ("智障", "abuse"), ("滚蛋", "abuse"), ("去死", "abuse"),
    ("废物", "abuse"), ("白痴", "abuse"),
    # 广告引流
    ("加微信", "ad"), ("加qq", "ad"), ("代练", "ad"), ("刷单", "ad"),
    ("兼职日结", "ad"), ("点击链接", "ad"),
    # 涉黄涉暴/不良诱导
    ("裸聊", "porn"), ("约炮", "porn"), ("自杀", "violence"), ("自残", "violence"),
    # 诈骗/交易
    ("转账给我", "fraud"), ("银行卡号", "fraud"), ("验证码发我", "fraud"),
]


def upgrade(db):
    SensitiveWord.__table__.create(bind=db.get_bind(), checkfirst=True)
    SensitiveHit.__table__.create(bind=db.get_bind(), checkfirst=True)

    bind = db.get_bind()
    inserted = 0
    for word, category in SEED_WORDS:
        exists = db.execute(
            text("SELECT id FROM db_im_sensitive_words WHERE word = :w"), {"w": word}
        ).first()
        if exists:
            continue
        db.execute(
            text(
                "INSERT INTO db_im_sensitive_words (word, level, category, is_active, created_at, updated_at) "
                "VALUES (:w, 'reject', :c, 1, :now, :now)"
            ),
            {"w": word, "c": category, "now": datetime.utcnow()},
        )
        inserted += 1

    db.commit()
    logger.info("073 IM 敏感词过滤已就绪（新增基础词 %d 条，表 db_im_sensitive_words/hits）", inserted)
