"""运营指标落表助手（S1-B3 / 07-技术实施方案 §5.4.3）

metric_daily 表的模型在 app.models.metrics，由 create_all 建表；本模块提供幂等写助手
record_metric（按 stat_date+metric_name+dimension upsert），供后续指标采集任务落库。

约定（持连铁律）：
- 本助手只做数据库读写，不发起任何外部阻塞调用；事务由调用方控制（本函数不 commit，
  调用方在「短会话」内用完即关，避免占用连接池）。
- 指标采集任务（凌晨定时）应分批 upsert，单条短会话，崩溃只丢当前条。
"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.metrics import MetricDaily


def record_metric(db: Session, metric_name: str, value: float,
                  stat_date: date | None = None, dimension: str = "") -> MetricDaily:
    """幂等写入/更新一条每日指标（按 stat_date+metric_name+dimension）。

    参数：
        db：数据库会话（调用方负责短会话生命周期，本函数不 commit）。
        metric_name：指标名，如 "dau"/"answer_count"/"ai_calls"/"ai_cost"。
        value：指标值（float/int；金额类建议以「分」为单位，由调用方约定）。
        stat_date：统计日期，缺省取今天。
        dimension：维度标签（如 "grade_3"/"math"），缺省 "" 表示总览。
    返回：写入后的 MetricDaily 实例（尚未 commit，由调用方统一提交）。
    """
    if stat_date is None:
        stat_date = date.today()
    existing = db.query(MetricDaily).filter_by(
        stat_date=stat_date, metric_name=metric_name, dimension=dimension).first()
    if existing is not None:
        existing.value = value
        existing.updated_at = datetime.now()
        row = existing
    else:
        row = MetricDaily(stat_date=stat_date, metric_name=metric_name,
                          dimension=dimension, value=value)
        db.add(row)
    db.flush()
    return row
