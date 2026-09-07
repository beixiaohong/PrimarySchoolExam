"""072 - 合规底座（CMP / 儿童个人信息保护）

新建三张表（与 `app/models/compliance.py` 单一真相源一致，幂等建）：
- `guardian_consents`：监护人同意记录（CMP-02）；
- `data_export_requests`：数据导出申请（CMP-06）；
- `data_deletion_requests`：数据删除申请（CMP-06）。

`create_all`（init_db）在本迁移前已建好表结构，本迁移对已存在表为 no-op，
仅对存量生产库补齐新表。无需 ALTER 补列（三张均为全新表）。
"""
import logging

from app.models.compliance import GuardianConsent, DataExportRequest, DataDeletionRequest

logger = logging.getLogger("migrations")


def upgrade(db):
    GuardianConsent.__table__.create(bind=db.get_bind(), checkfirst=True)
    DataExportRequest.__table__.create(bind=db.get_bind(), checkfirst=True)
    DataDeletionRequest.__table__.create(bind=db.get_bind(), checkfirst=True)
    logger.info("072 合规底座（guardian_consents + data_export/deletion_requests）已就绪")
    db.commit()
