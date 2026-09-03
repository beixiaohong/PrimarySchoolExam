"""D2 内容与教研域对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口（`.importlinter` 域独立契约强制）。

对外能力
- `resolve_textbook_id(db, uid, subject, grade)`：返回用户该学科应使用的教材版本 id
  （优先用户选择且启用，否则默认版本，无则 None）。文档 02 所列
  `TextbookService.get_user_version(uid)` 即由此函数承担，不另建同名包装。
- `_generate_quiz_from_text(text, count=1)`：从一篇古诗文生成填空题（学习引擎的古诗文
  练习直接复用，禁止各域自行切句出题）。

再导出为延迟解析（PEP 562）：内容域在函数体内反向引用测评域判分与平台域 AI 网关，
契约层若在 import 期拉起会与之成环，延迟解析后调用方时序与改造前一致。

文档 02 所列 `ContentService.get_questions(filter)`、`KnowledgeService.get_tree(subject, grade)`
为 M0「知识点体系标准化」的目标接口（掌握度模型前置条件），现由 `routers/knowledge.py`
的树接口与各题库查询直接实现，尚无统一服务层，本期不新建包装。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    "resolve_textbook_id": ("app.domains.content.routers.textbook", "resolve_textbook_id"),
    "_generate_quiz_from_text": ("app.domains.content.routers.classical", "_generate_quiz_from_text"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)
