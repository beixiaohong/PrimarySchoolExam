"""D6 家长与家校区对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口（`.importlinter` 域独立契约强制）。

对外能力
- 家长密码算法：`hash_password` / `verify_password` / `validate_password`
  （PBKDF2-SHA256，200,000 轮 + 16 字节随机盐，长度校验 4-32 位）。身份域登录、管理后台
  账号维护、初始数据灌入均复用同一实现，禁止各域自行实现口令散列（文档 02 D1「禁止」条目）。
  带下划线的 `_hash_pwd` / `_verify_pwd` / `_validate_pwd` 为同实现的过渡别名，
  存量调用点逐步改名后移除。
- `MIDDLE_SUBJECTS`：由 `middle_questions` 题库支撑的初中学科常量
  （物理/化学/生物/道德与法治/历史/地理），供测评域趣味出题分流。

再导出为延迟解析（PEP 562）：家校区在函数体内反向引用身份域与平台域，
契约层若在 import 期拉起 `routers/parent.py` 会与之成环，延迟解析后时序与改造前一致。
"""
from app.domains._lazy import resolve

_P = "app.domains.family.routers.parent"

_EXPORTS = {
    "hash_password": (_P, "_hash_pwd"),
    "verify_password": (_P, "_verify_pwd"),
    "validate_password": (_P, "_validate_pwd"),
    # 过渡别名（与上面同实现）
    "_hash_pwd": (_P, "_hash_pwd"),
    "_verify_pwd": (_P, "_verify_pwd"),
    "_validate_pwd": (_P, "_validate_pwd"),
    "MIDDLE_SUBJECTS": ("app.domains.family.services.sync_service", "MIDDLE_SUBJECTS"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)
