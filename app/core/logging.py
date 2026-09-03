"""结构化日志设施（S1 可观测性）。

- RequestIdFilter：为每条日志记录注入 request_id（取自请求上下文 ContextVar）。
- JsonFormatter：将日志记录序列化为单行 JSON，便于日志聚合检索。
- install_structured_logging：复用现有滚动文件处理器
  （app.logging_setup.DailySizeRotatingHandler），仅追加 request-id 过滤器；
  结构化开关开启时把文件处理器格式替换为 JSON，控制台保持人类可读。

设计约束：不重写滚动处理器（沿用 app.logging_setup），不在此处建立 DB 连接。
"""
import json
import logging
import os
from logging import Filter, Formatter

from app.core.request_context import get_request_id

# 透传的结构化字段（由访问日志 extra 注入）；其余字段落在 message 文本中
_STRUCT_FIELDS = ("user_id", "path", "method", "status", "duration_ms", "error", "stack")


class RequestIdFilter(Filter):
    """为日志记录补充 request_id；缺失时从请求上下文取，保证每条日志可关联链路。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", ""):
            record.request_id = get_request_id()
        return True


class JsonFormatter(Formatter):
    """单行 JSON 日志格式：固定字段 + 透传 extra 中的结构化字段。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "") or get_request_id(),
            "message": record.getMessage(),
        }
        for field in _STRUCT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["stack"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def install_structured_logging(structured: bool | None = None) -> bool:
    """为已配置的处理器安装 request-id 过滤器；structured=True 时文件处理器改用 JSON 格式。

    返回是否应用了过滤器（用于自检）。复用 app.logging_setup 的滚动处理器，不新增处理器，
    避免在日志落盘路径上引入额外 I/O 或连接。
    """
    if structured is None:
        structured = os.environ.get("STRUCTURED_LOGS", "true").strip().lower() in ("1", "true", "yes", "on")
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.addFilter(RequestIdFilter())
        if structured and isinstance(handler, logging.FileHandler):
            if not isinstance(handler.formatter, JsonFormatter):
                handler.setFormatter(JsonFormatter())
    return True
