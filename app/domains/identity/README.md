# D1 身份与账号域

注册/登录/验证码/会话 Token、账号绑定、用户资料、管理员账号与 RBAC、监护人同意。

- 数据归属：users admins auth_codes parent_passwords
- 迁入代码：auth.py user.py admin/auth.py admin/users.py parent_guard.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
