"""D7 交易与商业化域对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口：其它域只能
`from app.domains.commerce.contracts import ...`，不得直连 `services/diamond.py`
或 `routers/diamond.py`（由仓库根 `.importlinter` 的域独立契约强制）。

对外能力
- `DiamondService.consume(db, uid, prompt_tokens, completion_tokens, biz)`：按 token 用量计费扣款，
  收口此前 8 处 `check_and_deduct` 直连（ai_quiz / grading×2 / reading_service / platform ai、
  assistant、qa、search）。计划文档的示意签名不含 `db`，实现保留 `db` 为首参以维持调用方
  既有事务边界与「等 AI 期间不持有连接」的短会话语义，不改任何行为。
- `DiamondService.balance / cost / charge / grant`：账户读写，收口 `get_balance`、`calc_cost`、
  `deduct`、`grant` 的直呼点。
- 其余为钻石账户函数的显式再导出（延迟解析），供 `app/routers/admin/assets.py`、
  `tools/`、`tests/` 等域外调用方零行为变更接入。

文档 02 所列 `OrderService.create()`、`PaymentService.pay()`、`EntitlementService.has(uid, code)`
属 M1「正规交易链路」（取代现有二维码人工充值），本期不实现；落地后在此登记并同样收口。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    # 模块对象：供 `diamond_svc.get_balance(...)` 形态的存量调用点直接换用契约入口
    "diamond": ("app.domains.commerce.services.diamond", None),
    # 计费与账户（实现见 services/diamond.py）
    "TOKENS_PER_DIAMOND": ("app.domains.commerce.services.diamond", "TOKENS_PER_DIAMOND"),
    "REGISTRATION_GIFT": ("app.domains.commerce.services.diamond", "REGISTRATION_GIFT"),
    "calc_cost": ("app.domains.commerce.services.diamond", "calc_cost"),
    "check_and_deduct": ("app.domains.commerce.services.diamond", "check_and_deduct"),
    "deduct": ("app.domains.commerce.services.diamond", "deduct"),
    "get_balance": ("app.domains.commerce.services.diamond", "get_balance"),
    "grant": ("app.domains.commerce.services.diamond", "grant"),
    "grant_all_existing": ("app.domains.commerce.services.diamond", "grant_all_existing"),
}

__all__ = ("DiamondService",) + tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)


class DiamondService:
    """钻石计费与账户的唯一对外入口（无状态静态方法）。"""

    @staticmethod
    def consume(db, uid: str, prompt_tokens: int, completion_tokens: int,
                biz: str = "", ref_id: int = 0) -> dict:
        """按 AI token 用量扣钻石，返回 {"ok","cost","balance","error"}。

        biz 为业务归因（落 `diamond_ledger.reason`，如「作文批改」「趣味出题」），
        ref_id 为业务单据 id（可空）。余额不足时不扣款、ok=False 并带中文提示。
        """
        from app.domains.commerce.services.diamond import check_and_deduct
        return check_and_deduct(db, uid, prompt_tokens, completion_tokens,
                                reason=biz, ref_id=ref_id)

    @staticmethod
    def balance(db, uid: str) -> float:
        """查询余额（账户不存在时自动开户并赠送注册钻石）"""
        from app.domains.commerce.services.diamond import get_balance
        return get_balance(db, uid)

    @staticmethod
    def cost(prompt_tokens: int, completion_tokens: int) -> float:
        """按 1 万 token = 1 钻石换算消耗（保留 2 位小数）"""
        from app.domains.commerce.services.diamond import calc_cost
        return calc_cost(prompt_tokens, completion_tokens)

    @staticmethod
    def charge(db, uid: str, amount: float, biz: str = "", ref_id: int = 0) -> bool:
        """按固定金额扣钻石，余额不足返回 False"""
        from app.domains.commerce.services.diamond import deduct
        return deduct(db, uid, amount, reason=biz, ref_id=ref_id)

    @staticmethod
    def grant(db, uid: str, amount: float, biz: str = "admin_grant") -> float:
        """充值钻石，返回新余额（管理后台人工充值入口）"""
        from app.domains.commerce.services.diamond import grant
        return grant(db, uid, amount, reason=biz)
