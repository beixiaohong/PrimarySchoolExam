"""请求上下文：通过 ContextVar 在日志与中间件间传递 request-id。

使用 ContextVar 而非手动透传，是为了让任意深度的同步/异步调用都能从
日志过滤器取到当前请求的 request-id，无需改动业务签名。
"""
import contextvars

# 默认空串：未进入请求作用域（如启动期、脚本）时日志不缺字段
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    """返回当前请求的 request-id（未设置时为空串）。"""
    return request_id_ctx.get()


def set_request_id(rid: str) -> contextvars.Token:
    """设置当前请求的 request-id，返回 token 供后续重置。"""
    return request_id_ctx.set(rid)
