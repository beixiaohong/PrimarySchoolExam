"""路由层：HTTP 接口定义（参数校验 + 鉴权 + 调用服务层 + 组装响应）。

约定：
- 小模块单文件（如 `app/routers/weather.py`）；预计超过 300 行则拆同名子包：
  `__init__.py` 建 router、`common.py` 放公共依赖、其余按功能切薄路由文件
  （现有 7 个子包：admin / classical / exam / rewards / study / tasks / vocab）。
- 路由只做参数校验与鉴权，**业务逻辑一律下沉到 `app/services/`**。
- 新接口必须挂 `user_auth_deps`（严格账号绑定，禁止越权查改他人数据）；
  动作类接口（做题 / 提交 / 背诵判分）另加 `Depends(check_quiet_hours)` 夜间免打扰。
- 🚫 严禁在持有 DB 会话（`Depends(get_db)`）时发起外部阻塞调用（AI / HTTP / SMTP），
  详见 `docs/架构说明书.md` §6.1。
"""
