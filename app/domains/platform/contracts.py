"""D8 平台与运营域对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口（`.importlinter` 域独立契约强制）。

对外能力
- AI 网关（`services/ai.py`）：`chat` / `chat_with` / `chat_for` 会话补全、`ai_enabled` /
  `ai_any_enabled` 可用性判定、`rate_limit` 窗口限频。文档 02「本期重点：AI 网关治理」即以此
  契约为唯一出口，各业务域不得再自行拼装提供商链路。
- 通知通道：`send_email` / `mail_configured`（后台可在线覆盖发件配置）、`send_sms` /
  `sms_configured`（未接厂商时恒 False）。
- 系统配置：`sysconfig` 模块（`system_config` 表读写）。
- 免打扰：`check_quiet_hours`（quiet_hours 依赖，主应用装配时复用）。
- `ai` 为模块对象再导出，供 `ai_svc.chat_with(...)` 形态的存量调用点零改写接入；
  新代码请直呼上面列出的函数名。

再导出为延迟解析（PEP 562）：契约层不新增 import 期依赖 —— `services/ai.py` 内部在函数体里
反向引用商业域钻石计费，若契约层在 import 期就拉起该模块会形成环，延迟解析后时序与改造前一致。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    # AI 网关
    "ai": ("app.domains.platform.services.ai", None),
    "chat": ("app.domains.platform.services.ai", "chat"),
    "chat_for": ("app.domains.platform.services.ai", "chat_for"),
    "chat_with": ("app.domains.platform.services.ai", "chat_with"),
    "ai_enabled": ("app.domains.platform.services.ai", "ai_enabled"),
    "ai_any_enabled": ("app.domains.platform.services.ai", "ai_any_enabled"),
    "rate_limit": ("app.domains.platform.services.ai", "rate_limit"),
    # 通知通道
    "mailer": ("app.domains.platform.services.mailer", None),
    "send_email": ("app.domains.platform.services.mailer", "send_email"),
    "mail_configured": ("app.domains.platform.services.mailer", "mail_configured"),
    "send_sms": ("app.domains.platform.services.sms", "send_sms"),
    "sms_configured": ("app.domains.platform.services.sms", "sms_configured"),
    # 系统配置与免打扰
    "sysconfig": ("app.domains.platform.services.sysconfig", None),
    "check_quiet_hours": ("app.domains.platform.routers.quiet_hours", "check_quiet_hours"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)
