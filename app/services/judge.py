"""AI 判题复核服务：本地判错的题送 AI 批量复核（只升不降）

提供两种能力：
1. 等价作答复核：孩子作答与参考答案写法不同但实质正确（等价表达式、单位换算、
   分数/小数/百分数互换、全角半角/标点差异等）→ 判对，改判正确。
2. 错误参考答案检测：AI 忽略题面参考答案、独立计算正确答案；若发现「参考答案本身
   算错了」（如 202 打八折应为 161.6，库里却存 161）且孩子作答恰为正确值 → 除改判
   正确外，还返回 stored_wrong=True 与 correct_answer，由调用方（交卷/手动复核）把该
   题目的存储答案修正为正确值，避免以后同题反复误判。仅在高置信（孩子确实答对且参考
   答案确实算错）时才修正，杜绝 AI 臆造答案污染题库。

约定：
- 仅对本地判定为错误的作答复核；AI 判对 → 采纳（改判正确）。
- AI 不可用 / 超时 / 返回无法解析 / 未判对 → 全部维持本地判定（降级，不影响主流程）。
- 全局缓存：同题 + 同作答被判对过 → 直接复用（ai_qa 表 q_type='judge'），不再请求 AI。
- 每次调用记录 ai_usage_log（feature='judge'）。

测试钩子：环境变量 ZX_JUDGE_MOCK=all 时，所有送复核项直接判对（验证「AI 判对 → 改判正确」
链路）；ZX_JUDGE_MOCK=none 时全部维持本地判定（验证降级链路）。生产环境不要设置。
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# 批改判定：温度写死在 0.7，靠 prompt 强调严格，只认「确实答对」才标 true
JUDGE_SYSTEM = (
    "你是严谨的小学（数学/语文/英语）试卷批改老师，正在复核一道被判为错误的题。"
    "请按以下步骤处理每一题：\n"
    "1. 先忽略题面给出的「参考答案」，独立计算/推理出这道题的正确答案"
    "（数值题请直接计算并保留合理小数，例如 202 打八折 = 202×0.8 = 161.6，"
    "不要截断为整数；百分数、单位换算同理）。\n"
    "2. 判断孩子的作答在数学/语义上是否等价于你算出的正确答案"
    "（等价表达式、单位换算正确、同义词/语序不同、分数/小数/百分数等价写法、"
    "全角半角/标点/空格差异都算对）。\n"
    "3. 判断题面「参考答案」是否与你算出的正确答案明显不同"
    "（仅书写格式不同不算错；只有确实算错，如 161.6 被写成 161，才算 stored_wrong=true）。\n"
    "只输出一个 JSON 数组，不要输出任何其他文字，格式：\n"
    '[{"idx": 0, "child_correct": true, "stored_wrong": false, '
    '"correct_answer": "161.6", "reason": "不超过20字的理由"}, ...]'
)

JUDGE_RATE_LIMIT = 30  # 次/小时/用户


def judge_wrong_items(user_id: str, items: list) -> dict:
    """批量 AI 复核本地判错的作答。

    items: [{"key": 任意可哈希标识, "question_id": 可选, "question": 题干,
             "answer": 参考答案, "user_answer": 孩子作答, "subject": 学科,
             "options": 可选}]

    返回 {key: {"correct": bool, "stored_wrong": bool,
                "correct_answer": str, "reason": str}}。
    - correct=True 表示孩子作答经 AI 复核为正确（调用方据此改判正确）。
    - stored_wrong=True 且 correct_answer 非空表示参考答案本身算错，且 correct=true，
      调用方可将题目存储答案修正为该 correct_answer（高置信才会出现）。
    任何失败返回 {}（维持本地判定）。
    内部用短会话：等待 AI 期间不持有数据库连接（防连接池耗尽，交卷高频路径）。
    """
    if not items:
        return {}

    # 测试钩子：ZX_JUDGE_MOCK=all → 全部判对（验证「AI 判对即改判」链路）；
    # ZX_JUDGE_MOCK=none → 全部维持本地判定（验证降级链路）。生产环境不要设置。
    mock = os.environ.get("ZX_JUDGE_MOCK", "").strip().lower()
    if mock == "all":
        return {it["key"]: {"correct": True, "stored_wrong": False,
                            "correct_answer": "", "reason": "mock:all"} for it in items}
    if mock == "none":
        return {}

    from ..services import ai as ai_svc
    if not ai_svc.ai_enabled():
        logger.info("AI 判题复核跳过（未配置 Key，user=%s）", user_id)
        return {}
    if not ai_svc.rate_limit(f"judge:{user_id}", JUDGE_RATE_LIMIT, 3600):
        logger.warning("AI 判题复核限频（user=%s），维持本地判定", user_id)
        return {}

    # 1) 全局缓存命中：同题+同作答已被判对 → 直接采纳（不请求 AI）；短会话读后即释放
    from ..database import SessionLocal
    from ..models.ai_usage import AiQa
    todo = []
    db = SessionLocal()
    try:
        for it in items:
            qid = it.get("question_id")
            if qid:
                cached = db.query(AiQa).filter(
                    AiQa.q_type == "judge",
                    AiQa.ref_id == qid,
                    AiQa.question == it.get("user_answer", ""),
                    AiQa.answer == "correct",
                    AiQa.degraded == 0,
                ).first()
                if cached:
                    # 缓存命中只表示「判对」，不重放 stored_wrong 修正（题目已在首次修正）
                    continue
            todo.append(it)
    finally:
        db.close()
    if not todo:
        return {}

    # 2) 一次批量调用，AI 输出 JSON 数组（idx → child_correct / stored_wrong）；会话外执行
    lines = []
    for it in todo:
        q_text = it.get("question", "")
        opts = it.get("options")
        if opts:
            q_text = f"{q_text}\n选项：{' | '.join(opts)}"
        lines.append(
            f"第{it['key']}题（{it.get('subject', '')}）："
            f"题目：{q_text}\n参考答案：{it.get('answer', '')}\n"
            f"孩子作答：{it.get('user_answer', '')}\n"
        )
    result = ai_svc.chat_for(
        user_id,
        JUDGE_SYSTEM,
        "以下是需要复核的题目：\n" + "\n".join(lines),
        max_tokens=900,
    )

    # 3) 解析并落缓存 / 用量日志：短会话
    db = SessionLocal()
    try:
        if not result or not result.get("text", "").strip():
            _log_judge_usage(db, user_id, ok=False, error="AI 不可用或无输出，维持本地判定")
            return {}

        verdicts = _parse_verdicts(result["text"])
        if not verdicts:
            _log_judge_usage(db, user_id, ok=False, error="AI 输出无法解析，维持本地判定")
            return {}

        approved: dict = {}
        key_to_item = {it["key"]: it for it in todo}
        for v in verdicts:
            key = v.get("idx")
            if key not in key_to_item:
                continue
            child_correct = bool(v.get("child_correct") or v.get("correct") or False)
            if not child_correct:
                continue
            stored_wrong = bool(v.get("stored_wrong") or False)
            correct_answer = str(v.get("correct_answer") or "").strip()
            approved[key] = {
                "correct": True,
                "stored_wrong": stored_wrong,
                "correct_answer": correct_answer,
                "reason": str(v.get("reason") or "")[:60],
            }

            # 判对结果写缓存（同题+同作答复用）；写失败不影响主流程
            qid = key_to_item[key].get("question_id")
            if qid:
                try:
                    db.add(AiQa(user_id=user_id,
                                question=key_to_item[key].get("user_answer", ""),
                                answer="correct",
                                provider=result.get("provider", ""),
                                model=result.get("model", ""),
                                q_type="judge", ref_id=qid, degraded=0))
                    db.commit()
                except Exception as e:  # noqa: BLE001
                    logger.warning("写 AI 判题缓存失败: %s", e)
                    db.rollback()
        _log_judge_usage(db, user_id, ok=True, result=result,
                         detail=f"复核 {len(todo)} 题，判对 {len(approved)} 题")
        return approved
    finally:
        db.close()


def _parse_verdicts(text: str) -> list:
    """从 AI 输出解析 [{idx, child_correct, stored_wrong, correct_answer, reason}]；
    容忍代码围栏/前后杂文"""
    try:
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return []
        data = json.loads(m.group(0))
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except (ValueError, TypeError):
        return []
    return []


def _log_judge_usage(db, user_id: str, ok: bool, result: dict | None = None,
                     error: str = "", detail: str = ""):
    from ..models.ai_usage import AIUsageLog
    try:
        db.add(AIUsageLog(
            user_id=user_id,
            provider=(result or {}).get("provider") or "template",
            feature="judge",
            model=(result or {}).get("model") or "",
            prompt_tokens=(result or {}).get("prompt_tokens") or 0,
            completion_tokens=(result or {}).get("completion_tokens") or 0,
            ok=ok,
            error=(error or detail)[:500],
        ))
        db.commit()
    except Exception as e:  # 用量记录失败不影响主流程
        logger.warning("写 AI 判题用量日志失败: %s", e)
        db.rollback()
