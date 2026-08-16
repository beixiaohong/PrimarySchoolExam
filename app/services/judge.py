"""AI 判题复核服务：本地判错的题送 AI 批量复核（只升不降）

两步独立判题（v2）：
  Step 1 - 独立解题（不给参考答案）：
    AI 拿到题目后必须先独立解答，输出自己的答案，再判断孩子作答是否正确。
    这避免了 AI 看到参考答案后被锚定、只做简单字符串对比的问题。
  Step 2 - 检查参考答案（仅 Step1 判错时触发）：
    此时引入存储的参考答案，让 AI 判断参考答案本身是否算错。
    若参考答案确实有误且孩子作答为正确值 → 返回 stored_wrong=True + correct_answer。

约定：
- 仅对本地判定为错误的作答复核；AI 判对 → 采纳（改判正确）。
- AI 不可用 / 超时 / 返回无法解析 / 未判对 → 全部维持本地判定（降级，不影响主流程）。
- 全局缓存：同题 + 同作答被判对过 → 直接复用（ai_qa 表 q_type='judge'），不再请求 AI。
  force=True 时跳过缓存（手动复审按钮用，确保每次都触发真正 AI 调用）。
- 每次调用记录 ai_usage_log（feature='judge'）。

测试钩子：环境变量 ZX_JUDGE_MOCK=all 时，所有送复核项直接判对（验证「AI 判对 → 改判正确」
链路）；ZX_JUDGE_MOCK=none 时全部维持本地判定（验证降级链路）。生产环境不要设置。
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# ── Step 1: 独立解题（输入不含参考答案，迫使 AI 真正独立思考） ──
JUDGE_STEP1_SYSTEM = (
    "你是一位严谨的小学/初中（数学/语文/英语）批改老师。\n"
    "以下题目被系统判为孩子答错，但系统判定可能有误。请你完成以下任务：\n"
    "1. **独立解答**：不看任何参考答案，自己完整解答题目，给出你认为的正确答案。"
    "（数值题请直接计算并保留合理小数，例如 202 打八折 = 202×0.8 = 161.6，"
    "不要截断为整数；百分数、单位换算同理。）\n"
    "2. **判断孩子作答**：比较你算出的答案和孩子的作答，判断孩子的作答是否正确。"
    "以下情况均视为正确：等价表达式、单位换算正确、同义词/语序不同、"
    "分数/小数/百分数等价写法、全角半角/标点/空格差异、繁体字与简体字等价。\n"
    "3. **给出理由**：用不超过 20 字简要说明判断依据。\n\n"
    "只输出一个 JSON 数组，不要输出任何其他文字：\n"
    '[{"idx": 0, "my_answer": "你算出的正确答案", '
    '"child_correct": true, "reason": "不超过20字的理由"}, ...]'
)

# ── Step 2: 检查参考答案是否算错（仅在 Step1 判错时触发） ──
JUDGE_STEP2_SYSTEM = (
    "你是一位严谨的试卷校对员。以下题目的存储参考答案可能本身就算错了。"
    "请根据题目和已确认的正确答案，判断存储的参考答案是否有误。\n"
    "仅当参考答案与你算出的正确答案在数值/实质上明显不同时才算 stored_wrong=true"
    "（仅书写格式不同不算错）。\n"
    "只输出一个 JSON 数组：\n"
    '[{"idx": 0, "stored_wrong": true, "correct_answer": "正确答案"}, ...]'
)

JUDGE_RATE_LIMIT = 30  # 次/小时/用户


def judge_wrong_items(user_id: str, items: list, *, force: bool = False) -> dict:
    """批量 AI 复核本地判错的作答（两步独立判题）。

    items: [{"key": 任意可哈希标识, "question_id": 可选, "question": 题干,
             "answer": 参考答案, "user_answer": 孩子作答, "subject": 学科,
             "options": 可选}]
    force: True 时跳过缓存，每次都真正调用 AI（手动复审按钮用）。

    返回 {key: {"correct": bool, "stored_wrong": bool,
                "correct_answer": str, "reason": str}}。
    - correct=True 表示孩子作答经 AI 独立复核为正确。
    - stored_wrong=True 且 correct_answer 非空表示参考答案本身算错。
    任何失败返回 {}（维持本地判定）。
    """
    if not items:
        return {}

    # 测试钩子
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

    # 1) 缓存检查（force=True 时跳过，手动复审每次都真正调 AI）
    from ..database import SessionLocal
    from ..models.ai_usage import AiQa
    todo = list(items) if force else []
    if not force:
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
                        continue
                todo.append(it)
        finally:
            db.close()
    if not todo:
        return {}

    # 2) Step 1: 独立解题 + 判断孩子作答（输入不含参考答案！）
    step1_lines = []
    for it in todo:
        q_text = it.get("question", "")
        opts = it.get("options")
        if opts:
            q_text = f"{q_text}\n选项：{' | '.join(opts)}"
        step1_lines.append(
            f"第{it['key']}题（{it.get('subject', '')}）："
            f"题目：{q_text}\n"
            f"孩子作答：{it.get('user_answer', '')}\n"
        )
    result1 = ai_svc.chat_for(
        user_id,
        JUDGE_STEP1_SYSTEM,
        "以下是需要复核的题目（请独立解答后判断孩子作答）：\n" + "\n".join(step1_lines),
        max_tokens=1200,
    )

    if not result1 or not result1.get("text", "").strip():
        db = SessionLocal()
        try:
            _log_judge_usage(db, user_id, ok=False, error="Step1 AI 不可用，维持本地判定")
        finally:
            db.close()
        return {}

    verdicts1 = _parse_verdicts(result1["text"])
    if not verdicts1:
        db = SessionLocal()
        try:
            _log_judge_usage(db, user_id, ok=False, error="Step1 AI 输出无法解析，维持本地判定")
        finally:
            db.close()
        return {}

    # 3) 收集 Step1 结果
    key_to_item = {it["key"]: it for it in todo}
    approved: dict = {}
    wrong_in_step1: list = []  # Step1 判错的题，送 Step2 检查参考答案
    my_answers: dict = {}       # key -> AI 独立算出的答案

    for v in verdicts1:
        key = v.get("idx")
        if key not in key_to_item:
            continue
        child_correct = bool(v.get("child_correct") or v.get("correct") or False)
        my_ans = str(v.get("my_answer") or "").strip()
        reason = str(v.get("reason") or "")[:60]

        if child_correct:
            approved[key] = {
                "correct": True,
                "stored_wrong": False,
                "correct_answer": my_ans,
                "reason": reason or "AI 独立判题：作答正确",
            }
        else:
            wrong_in_step1.append(key)
            my_answers[key] = my_ans

    # 4) Step 2: 仅对 Step1 判错的题检查参考答案是否算错
    if wrong_in_step1:
        step2_lines = []
        for key in wrong_in_step1:
            it = key_to_item[key]
            ref_answer = (it.get("answer") or "").strip()
            if not ref_answer:
                continue
            q_text = it.get("question", "")
            opts = it.get("options")
            if opts:
                q_text = f"{q_text}\n选项：{' | '.join(opts)}"
            step2_lines.append(
                f"第{key}题（{it.get('subject', '')}）："
                f"题目：{q_text}\n"
                f"AI 独立算出的答案：{my_answers.get(key, '')}\n"
                f"存储的参考答案：{ref_answer}\n"
            )
        if step2_lines:
            result2 = ai_svc.chat_for(
                user_id,
                JUDGE_STEP2_SYSTEM,
                "以下题目的参考答案可能算错，请校对：\n" + "\n".join(step2_lines),
                max_tokens=600,
            )
            if result2 and result2.get("text", "").strip():
                verdicts2 = _parse_verdicts(result2["text"])
                for v in verdicts2:
                    key = v.get("idx")
                    if key not in key_to_item:
                        continue
                    stored_wrong = bool(v.get("stored_wrong") or False)
                    correct_answer = str(v.get("correct_answer") or "").strip()
                    if stored_wrong and correct_answer:
                        # 参考答案确实算错，且孩子的作答可能就是正确值
                        # 用 Step2 的 correct_answer 重新判孩子
                        it = key_to_item[key]
                        ua = (it.get("user_answer") or "").strip()
                        if ua and _fuzzy_match(ua, correct_answer):
                            approved[key] = {
                                "correct": True,
                                "stored_wrong": True,
                                "correct_answer": correct_answer,
                                "reason": f"参考答案有误({it.get('answer','')})，孩子作答正确",
                            }

    # 5) 落缓存 + 用量日志
    db = SessionLocal()
    try:
        for key, verdict in approved.items():
            qid = key_to_item[key].get("question_id")
            if qid:
                try:
                    db.add(AiQa(user_id=user_id,
                                question=key_to_item[key].get("user_answer", ""),
                                answer="correct",
                                provider=result1.get("provider", ""),
                                model=result1.get("model", ""),
                                q_type="judge", ref_id=qid, degraded=0))
                    db.commit()
                except Exception as e:  # noqa: BLE001
                    logger.warning("写 AI 判题缓存失败: %s", e)
                    db.rollback()
        _log_judge_usage(db, user_id, ok=True, result=result1,
                         detail=f"复核 {len(todo)} 题，判对 {len(approved)} 题"
                                f"（force={force}）")
        return approved
    finally:
        db.close()


def _fuzzy_match(user_answer: str, correct_answer: str) -> bool:
    """简单模糊匹配：去空格/全角半角后比较，用于 Step2 二次确认孩子作答。"""
    def _norm(s: str) -> str:
        return s.replace(" ", "").replace("\u3000", "").replace("，", ",").replace("。", ".").lower()
    return _norm(user_answer) == _norm(correct_answer)


def _parse_verdicts(text: str) -> list:
    """从 AI 输出解析 JSON 数组；容忍代码围栏/前后杂文"""
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
