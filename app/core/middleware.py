"""HTTP 中间件与统一异常处理器（S1 可观测性）。

- request_context_middleware：生成/透传 X-Request-ID，记录访问日志，
  把未捕获异常统一为 500 信封（避免栈信息泄漏到响应）。
- register_exception_handlers：把 HTTPException / 校验错误 / 未捕获异常统一为
  {"code", "message", "request_id"} 信封，便于前端与日志关联。

设计取舍：成功响应保持原有结构（避免一次性改动全站响应契约导致前端/测试大面积返工）；
仅错误路径统一信封。成功响应信封化作为后续独立模块协调推进。
"""
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id, set_request_id

logger = logging.getLogger("app.access")


def _envelope(code: int, message: str) -> dict:
    return {"code": code, "message": message, "request_id": get_request_id()}


def _as_message(detail) -> str:
    """HTTPException.detail 可能是字符串或结构化 dict，统一成可读字符串。"""
    if isinstance(detail, str):
        return detail
    try:
        return json.dumps(detail, ensure_ascii=False)
    except Exception:
        return str(detail)


async def request_context_middleware(request: Request, call_next):
    """请求上下文中间件：透传/生成 request-id，记录访问日志，吞掉未捕获异常为 500 信封。"""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    set_request_id(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 - 统一兜底，避免栈泄漏到响应
        logger.exception("unhandled_exception", extra={"request_id": rid})
        response = JSONResponse(_envelope(500, "服务器内部错误"), status_code=500)
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "http_request",
            extra={
                "request_id": rid,
                "path": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
    response.headers["X-Request-ID"] = rid
    return response


def register_exception_handlers(app: FastAPI) -> None:
    """注册统一异常处理器，错误响应统一为 {code, message, request_id} 信封。"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.status_code, _as_message(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "message": "参数校验失败",
                "data": exc.errors(),
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception", extra={"request_id": get_request_id()})
        return JSONResponse(status_code=500, content=_envelope(500, "服务器内部错误"))
