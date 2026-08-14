"""为缺失答案的采集题目调用 AI 补全答案。

原则：
- 仅补全 correct_answer 为空的题目；试卷自带的参考答案原样保留，不覆盖。
- 客观题（选择/填空/判断）直接给最终答案；主观/简答/应用题给关键步骤与要点。
- AI 生成的答案以「[AI生成] 」前缀存储，便于与来源答案区分。
- 复用 app.services.ai 的多提供商路由（智谱 GLM / relay / DeepSeek），自带全局节流。
"""
import json
import logging
import time

from .ai import chat, ai_enabled

logger = logging.getLogger("answer_generator")

_SYSTEM = (
    "你是小学题库助教。根据用户给出的题目，给出正确答案。\n"
    "规则：\n"
    "1) 选择题只输出正确选项字母（如 A 或 AB），不要解释；\n"
    "2) 填空题直接给出应填入的内容；\n"
    "3) 判断/计算/应用题给出最终结果或关键步骤与要点；\n"
    "4) 不要重复题目原文，不要输出『答案：』等多余前缀，只给答案本身。"
)


def _build_user(q) -> str:
    tag = {"choice": "[选择题]", "fill_blank": "[填空题]"}.get(q.qtype, "[问答题]")
    parts = [tag, "题目：", (q.question_text or "").strip()]
    if q.options:
        try:
            opts = json.loads(q.options) if isinstance(q.options, str) else q.options
            if opts:
                parts.append("选项：" + "  ".join(str(o) for o in opts))
        except Exception:
            pass
    return "\n".join(parts)


def generate_answer_for(q, max_tokens: int = 400) -> str | None:
    """对单题调用 AI 生成答案；返回答案文本或 None。"""
    user = _build_user(q)
    if not user.strip():
        return None
    try:
        res = chat(_SYSTEM, user, max_tokens=max_tokens)
    except Exception as e:  # 单个题目失败不影响整体
        logger.warning("AI 调用异常（题 %s/%s）: %s", q.subject, q.seq, e)
        return None
    if not res or not res.get("text", "").strip():
        return None
    return res["text"].strip()


def fill_missing_answers(limit: int | None = None, grade: str | None = None,
                          subject: str | None = None, dry_run: bool = False,
                          paper_ids: list | None = None):
    """为 correct_answer 为空的 PaperQuestion 补全答案。

    返回 (处理数, 成功数, 跳过数)。dry_run=True 时不写库，仅打印预览。
    limit：最多处理多少题（控成本/控时长）；None 表示全部。
    paper_ids：仅补全这些试卷下的题目（用于优先补全新采集卷）；None 表示全部试卷。
    """
    from ..database import collection_session
    from ..models.paper import PaperQuestion

    if not ai_enabled():
        logger.warning("AI 不可用，跳过答案补全")
        return (0, 0, 0)

    processed = skipped = ok = 0
    # 持续限流/超时保护：连续失败达到阈值即判定 AI 暂不可用，放弃本次补全，
    # 剩余题目留待后续运行（避免对 5671 道缺失题死循环刷接口、卡住数十小时）。
    MAX_CONSECUTIVE_FAILS = 10
    with collection_session() as s:
        q = s.query(PaperQuestion).filter(
            (PaperQuestion.correct_answer == None) | (PaperQuestion.correct_answer == "")
        )
        if grade:
            q = q.filter(PaperQuestion.grade == grade)
        if subject:
            q = q.filter(PaperQuestion.subject == subject)
        if paper_ids:
            q = q.filter(PaperQuestion.paper_id.in_(paper_ids))
        q = q.order_by(PaperQuestion.id)
        rows = q.all()
        total_missing = len(rows)
        if limit:
            rows = rows[:limit]
        consecutive_skip = 0
        for pq in rows:
            processed += 1
            ans = generate_answer_for(pq)
            if ans is None:
                skipped += 1
                consecutive_skip += 1
                if consecutive_skip >= MAX_CONSECUTIVE_FAILS:
                    logger.warning("连续 %d 题 AI 失败（多为限流/超时），判定为持续不可用，"
                                   "放弃本次补全；剩余 %d 题留待后续运行",
                                   consecutive_skip, total_missing - processed)
                    break
                # 温和退避：限流/超时时放慢节奏，不猛撞 API（用户要求「慢慢补充」）
                if consecutive_skip >= 5:
                    logger.warning("连续 %d 题 AI 失败（多为限流/超时），冷却 60s 后继续", consecutive_skip)
                    time.sleep(60)
                else:
                    time.sleep(2)
                continue
            consecutive_skip = 0
            if dry_run:
                logger.info("[dry] %s/%s q%d: %s", pq.subject, pq.grade, pq.seq, ans[:50])
                continue
            pq.correct_answer = "[AI生成] " + ans
            ok += 1
            # 分批提交，避免长任务中断时全部进度丢失
            if ok % 50 == 0:
                s.commit()
        if not dry_run:
            s.commit()
    logger.info("答案补全：本次处理 %d（待补共 %d），成功 %d，跳过 %d",
                processed, total_missing, ok, skipped)
    return (processed, ok, skipped)


def count_missing_answers(grade: str | None = None, subject: str | None = None) -> int:
    """统计仍有缺失答案的题目数（供采集后核对 / 刷题前确保全覆盖）。"""
    from ..database import collection_session
    from ..models.paper import PaperQuestion
    with collection_session() as s:
        q = s.query(PaperQuestion).filter(
            (PaperQuestion.correct_answer == None) | (PaperQuestion.correct_answer == "")
        )
        if grade:
            q = q.filter(PaperQuestion.grade == grade)
        if subject:
            q = q.filter(PaperQuestion.subject == subject)
        return q.count()
