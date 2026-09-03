"""055 - 掌握度数据底座（S3-M1 / 07-技术实施方案 §3.2.3）

新建两张表（与 `app/models/mastery.py` 单一真相源一致，幂等建）：
- `mastery_records`：学生×知识点 掌握度矩阵（增量 UPSERT，uq_mr_user_kp）；
- `mastery_snapshots`：每日/每周快照（趋势曲线与提升量指标，uq_ms）。

`create_all`（init_db）在本迁移前已建好表结构，本迁移对已存在表为 no-op，
仅对存量生产库补齐新表。无需 ALTER 补列（两张均为全新表）。
"""
import logging

from app.models.mastery import MasteryRecord, MasterySnapshot

logger = logging.getLogger("migrations")


def upgrade(db):
    # 两张新表均由模型表 checkfirst 建（与模型单一真相源一致，幂等）
    MasteryRecord.__table__.create(bind=db.get_bind(), checkfirst=True)
    MasterySnapshot.__table__.create(bind=db.get_bind(), checkfirst=True)
    logger.info("055 掌握度数据底座（mastery_records + mastery_snapshots）已就绪")
    db.commit()
