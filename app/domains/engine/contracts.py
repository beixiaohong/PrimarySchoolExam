"""D4 学习引擎域对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口（`.importlinter` 域独立契约强制）。

对外能力
- `get_passages(db, subject, grade, limit=5)`：按学科+年级抽取阅读篇目。
- `submit_reading_quiz(user_id, passage_id, answers)`：阅读交卷判分（客观题即时判、主观题走 AI）；
  内部使用短会话 —— 等 AI 判分期间不持有数据库连接（防连接池耗尽），故签名不含 `db`。
- `MASTER_STREAK`：单题累计答对 3 次（或修正模式整组全对）即判定为已掌握的阈值常量，
  家校区申诉复核复用同一口径。

再导出为延迟解析（PEP 562）：学习引擎在模块级与函数体中反向引用内容域、测评域、平台域、
商业域与激励域，契约层若在 import 期拉起实现模块会成环，延迟解析后调用方时序与改造前一致。

文档 02 所列 `MasteryService.get_mastery(uid, kp_id)`、`MasteryService.update(uid, kp_id, result)`、
`PathService.daily_path(uid)`、`DiagnosticService.run(uid, scope)` 是 M0 最高优先级的**新建**能力
（掌握度模型 / 个性化路径 / 诊断测评），依赖 `mastery_records`、`diagnostic_sessions`、
`learning_paths` 三张新表，按计划不在 S1-R 搬迁期实现（S1 期间不并行新功能）；
落地后在此登记为本域对外契约。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    "get_passages": ("app.domains.engine.services.reading_service", "get_passages"),
    "submit_reading_quiz": ("app.domains.engine.services.reading_service", "submit_reading_quiz"),
    "MASTER_STREAK": ("app.domains.engine.routers.study", "MASTER_STREAK"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)
