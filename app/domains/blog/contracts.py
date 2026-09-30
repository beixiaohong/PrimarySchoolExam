"""内容 / Blog 域对外契约（同其余九域写法：PEP 562 延迟再导出）

本模块是该域唯一允许被其它域 / 后台装配层 import 的入口（`.importlinter` 域独立契约强制）。

对外能力：
- `articles` / `taxonomy` / `workspace`：三个服务模块对象，供后台 `app/routers/admin/blog.py`
  以 `articles_svc.xxx(...)` 形态复用（admin → contracts 属白名单边）；
- `latest_articles`：工作台「最新内容」轻量聚合（只返回标题/摘要/封面/时间，不含正文）；
- `record_app_usage` / `list_app_usage`：工作台模块使用记录读写。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    # 服务模块对象（后台管理复用）
    "articles": ("app.domains.blog.services.articles", None),
    "taxonomy": ("app.domains.blog.services.taxonomy", None),
    "workspace": ("app.domains.blog.services.workspace", None),
    # 工作台聚合用函数
    "latest_articles": ("app.domains.blog.services.articles", "latest_articles"),
    "record_app_usage": ("app.domains.blog.services.workspace", "record_app_usage"),
    "list_app_usage": ("app.domains.blog.services.workspace", "list_app_usage"),
}


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(_EXPORTS)
