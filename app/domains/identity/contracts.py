"""D1 身份与权限域对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口（`.importlinter` 域独立契约强制）。

对外能力
- `require_user`：普通用户登录鉴权依赖（Bearer token 会话制），业务路由以
  `dependencies=[Depends(require_user)]` 强制登录；`require_self` 在此基础上强制
  请求内 `user_id` == 登录账号（家长代管孩子场景的严格绑定）。文档 02 所列
  `AuthService.verify_token()` 即由这两个 FastAPI 依赖承担，不另建同名包装。
- `ensure_parent_pwd`：家长密码守卫（请求头校验，失败 403），供家校区/激励域敏感接口复用。
- `streak_days`：连续学习天数（合并词汇与古诗文日志取最大连续值），供家校区周报与申诉展示。

再导出为延迟解析（PEP 562）：契约层不新增 import 期依赖，调用方解析时机与改造前一致。

文档 02 所列 `UserService.get_profile()`、`PermissionService.check()`、
`ConsentService.has_valid_consent(uid)` 分别对应 M0 的 RBAC 细化与监护人同意（合规 P0），
现无独立服务实现（用户资料由 `/api/user/*` 路由直接读写、管理员权限为粗粒度），本期不新建。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    "require_user": ("app.domains.identity.routers.auth", "require_user"),
    "require_self": ("app.domains.identity.routers.auth", "require_self"),
    "ensure_parent_pwd": ("app.domains.identity.services.parent_guard", "ensure_parent_pwd"),
    "streak_days": ("app.domains.identity.routers.user", "_streak"),
    # 存量私有符号（契约债：与 streak_days 同实现，供未改名的调用点过渡）
    "_streak": ("app.domains.identity.routers.user", "_streak"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)
