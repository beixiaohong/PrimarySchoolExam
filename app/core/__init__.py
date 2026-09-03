"""跨切面基础设施：request-id / 结构化日志 / 统一异常信封 / RBAC 依赖。

本期新增（S1 可观测性 + 权限基座）。本包作为横切能力被 main.py 与各后台路由按需引用，
不被任何业务域 import 其内部实现。import-linter 的九域独立性契约不监控 app.core，
故本包引用 app.routers.admin.common 的共享鉴权辅助不构成域间耦合。
"""
