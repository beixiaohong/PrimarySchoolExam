"""D1 身份与账号域（identity）

职责：注册/登录/验证码/会话 Token、账号绑定、用户资料、管理员账号与 RBAC、监护人同意。

边界纪律（S1-R）：
- 数据归属：users admins auth_codes parent_passwords
- 迁入代码：auth.py user.py admin/auth.py admin/users.py parent_guard.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
