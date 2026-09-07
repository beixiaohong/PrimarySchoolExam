"""慢查询日志（OBS-05）

通过 SQLAlchemy event 监听 Connection 的 before_cursor_execute / after_cursor_execute，
对超过阈值（默认 500ms，可通过 SLOW_QUERY_THRESHOLD_MS 环境变量配置）的 SQL 记录 warning 日志。

设计取舍：
- 仅记录执行时长，不记录参数值（避免敏感数据泄漏到日志）；
- 使用 app.core.request_context 的 request_id 关联链路；
- 阈值以下查询完全无开销（仅一次 time.perf_counter 差值比较）。
"""
import logging
import os
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.core.request_context import get_request_id

logger = logging.getLogger("app.slow_query")

# 阈值（毫秒），环境变量可覆盖
_THRESHOLD_MS = int(os.environ.get("SLOW_QUERY_THRESHOLD_MS", "500"))

# 是否已安装（幂等）
_installed = False


def install_slow_query_listener(engine: Engine, threshold_ms: int = _THRESHOLD_MS) -> bool:
    """为指定 engine 安装慢查询监听。幂等（多次调用只装一次）。

    返回是否成功安装。
    """
    global _installed
    if _installed:
        return True

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info["_query_start"] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        start = conn.info.pop("_query_start", None)
        if start is None:
            return
        duration_ms = int((time.perf_counter() - start) * 1000)
        if duration_ms >= threshold_ms:
            rid = get_request_id()
            # 截断 SQL 到 200 字符，避免超长语句撑爆日志
            sql_preview = statement[:200].replace("\n", " ")
            logger.warning(
                "slow_query",
                extra={
                    "request_id": rid,
                    "duration_ms": duration_ms,
                    "sql": sql_preview,
                    "threshold_ms": threshold_ms,
                },
            )

    _installed = True
    return True
