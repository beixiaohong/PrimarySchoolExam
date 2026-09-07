"""IM 敏感词过滤服务（D4 决策：内容安全）。

设计要点
--------
1. **词库缓存**：模块级缓存 60s，避免每条消息查库；后台改词后最多 60s 生效。
2. **双通道共用**：REST `POST /api/im/messages` 与 WebSocket `message` 帧都必须调用
   `check_text()`，只拦 REST 会被 WS 绕过。
3. **动作可配**：词库 `level` = `reject`（拒绝发送，不入库）/ `replace`（打码后放行）。
4. **命中留痕**：`record_hit()` 用**独立短会话**立即提交，即使主流程因 reject 回滚，
   审计记录依然保留（合规需要）。

性能：词库量 < 1000 时线性 `in` 匹配足够（单条消息微秒级）；若后续词库膨胀，
可替换为 DFA/Aho-Corasick，`check_text` 签名不变。
"""
import logging
import time

from app.database import SessionLocal
from app.models.im import SensitiveWord, SensitiveHit

logger = logging.getLogger(__name__)

CACHE_TTL = 60  # 秒
_CACHE = {"ts": 0.0, "words": []}  # words: [(word_lower, level)]


def _load_words(db):
    """加载启用中的词库到缓存（忽略空词）。"""
    rows = db.query(SensitiveWord.word, SensitiveWord.level).filter(
        SensitiveWord.is_active == True,  # noqa: E712
    ).all()
    words = [(w.strip().lower(), lv) for w, lv in rows if w and w.strip()]
    _CACHE["words"] = words
    _CACHE["ts"] = time.time()
    return words


def invalidate_cache():
    """后台改动词库后调用，立即失效（否则最多延迟 CACHE_TTL 秒）。"""
    _CACHE["ts"] = 0.0
    _CACHE["words"] = []


def _current_words(db):
    if time.time() - _CACHE["ts"] > CACHE_TTL or not _CACHE["words"]:
        return _load_words(db)
    return _CACHE["words"]


def check_text(db, content, scene: str = "message"):
    """检测文本，返回 (ok, action, hit_word, out_text)。

    - 无命中：`(True, None, None, 原文)`
    - `reject`：`(False, "reject", 词, None)` —— 调用方应拒绝写入
    - `replace`：`(True, "replace", 词, 打码文本)` —— 调用方用打码文本入库
    """
    if not content:
        return True, None, None, content

    low = str(content).lower()
    for word, level in _current_words(db):
        if word and word in low:
            if level == "replace":
                # 打码：按原词长度替换（保持原文长度便于用户理解被拦了几处）
                out = _mask(content, word)
                return True, "replace", word, out
            return False, "reject", word, None
    return True, None, None, content


def _mask(content: str, word: str) -> str:
    """把 content 中所有出现的 word（忽略大小写）替换为等长 *。"""
    low = str(content).lower()
    w = word.lower()
    out = []
    i = 0
    while True:
        idx = low.find(w, i)
        if idx < 0:
            out.append(content[i:])
            break
        out.append(content[i:idx])
        out.append("*" * len(w))
        i = idx + len(w)
    return "".join(out)


def record_hit(user_id: str, chat_id: str, scene: str, word: str,
               raw_content: str, action: str):
    """写入命中记录（独立短会话立即提交，不依赖调用方事务是否回滚）。"""
    try:
        with SessionLocal() as s:
            s.add(SensitiveHit(
                user_id=str(user_id) if user_id else "",
                chat_id=str(chat_id) if chat_id else None,
                scene=scene or "message",
                word=word,
                raw_content=(raw_content or "")[:1000],
                action=action,
            ))
            s.commit()
    except Exception:
        # 审计写失败不得影响主流程，仅记日志
        logger.exception("[sensitive] 命中记录写入失败 user=%s scene=%s", user_id, scene)
