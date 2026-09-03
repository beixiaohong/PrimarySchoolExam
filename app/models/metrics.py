"""运营指标模型（S1-B3 / 07-技术实施方案 §5.4.3）

metric_daily 存放每日运营指标快照，供后续指标采集任务落库（DAU/答题量/AI 调用与成本/
接口 P95/错误率/订单量金额/核销笔数），看板在 B/D 迭代接入。

约定（DB-03/DB-05）：
- 由 create_all 建表，同时补 `migrations/versions/070_*` 之外的显式迁移（本表为新增表，
  迁移交由 create_all 即可；生产如需显式迁移可另起 0NN_）。
- value 用 DECIMAL(18,4) 兼容整数与小数指标；金额类单位由调用方约定（建议「分」）。
- stat_date+metric_name+dimension 唯一，便于幂等 upsert（见 app.core.metrics.record_metric）。
"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, UniqueConstraint

from ..database import Base


class MetricDaily(Base):
    """每日运营指标快照（按 统计日期 + 指标名 + 维度 唯一）。"""
    __tablename__ = "metric_daily"
    __table_args__ = (
        UniqueConstraint(
            "stat_date", "metric_name", "dimension",
            name="uq_metric_daily",
        ),
        {"comment": "每日运营指标快照（DAU/答题量/AI成本/接口P95/订单量金额等）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    stat_date = Column(Date, nullable=False, index=True, comment="统计日期")
    metric_name = Column(String(64), nullable=False, index=True,
                         comment="指标名：dau/answer_count/ai_calls/ai_cost/p95/error_rate/order_count/order_amount_fen/redeem_count")
    dimension = Column(String(64), nullable=False, default="",
                       comment="维度标签（如 grade_3/math/总览''），默认总览")
    value = Column(Numeric(18, 4), nullable=False, default=0,
                   comment="指标值（金额类建议以「分」为单位）")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
