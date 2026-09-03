"""为缺失答案的采集题目调用 AI 补全答案。

原则：
- 仅补全 correct_answer 为空的题目；试卷自带的参考答案原样保留，不覆盖。
- 客观题（选择/填空/判断）直接给最终答案；主观/简答/应用题给关键步骤与要点。
- AI 生成的答案以「[AI生成] 」前缀存储，便于与来源答案区分。
- 复用 app.domains.platform.services.ai 的多提供商路由（智谱 GLM / relay / DeepSeek），自带全局节流。
"""
import json
import logging
import time

from app.domains.platform.contracts import chat, ai_enabled, ai_any_enabled

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


def _deepseek_configured() -> bool:
    """DeepSeek Key 是否已配置（采集批量补答案的主用提供商）"""
    try:
        from app.domains.platform.contracts import ai as _ai
        return bool(_ai._config_provider("deepseek").get("api_key"))
    except Exception:
        return False


def generate_answer_for(q, max_tokens: int = 400) -> str | None:
    """对单题调用 AI 生成答案；返回答案文本或 None。

    提供商选择：
    - 配置了 DEEPSEEK_API_KEY → 仅走 DeepSeek（当前免费链 zhipu/relay 余额耗尽/限流，
      必然失败且每题浪费 ~55s，故不再回退；失败留待后续运行补全）。
    - 未配置 DeepSeek → 退化走原免费链 chat()（保持旧行为，键恢复时自动生效）。
    """
    user = _build_user(q)
    if not user.strip():
        return None
    if _deepseek_configured():
        try:
            from app.domains.platform.contracts import ai as _ai
            ds_cfg = _ai._config_provider("deepseek")
            res = _ai._call_provider("deepseek", ds_cfg, _SYSTEM, user, max_tokens)
        except Exception as e:
            logger.warning("DeepSeek 调用异常（题 %s/%s）: %s",
                           getattr(q, "subject", None), getattr(q, "seq", None), e)
            return None
        if res and res.get("text", "").strip():
            return res["text"].strip()
        return None
    # 回退免费链（zhipu→relay），仅当 DeepSeek 未配置时
    try:
        res = chat(_SYSTEM, user, max_tokens=max_tokens)
    except Exception as e:  # 单个题目失败不影响整体
        logger.warning("AI 调用异常（题 %s/%s）: %s",
                       getattr(q, "subject", None), getattr(q, "seq", None), e)
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

    连接池铁律：AI 调用期间绝不持有 DB 会话。本函数分三段——
      1) 短会话取出待补题目（仅取字段）为纯数据；
      2) 【无会话】状态下逐题调 AI（含全局节流/并发退避）；
      3) 短会话按批 UPDATE 写回。
    避免「持 DB 连接等外部阻塞调用」导致连接池耗尽（曾致全站卡死）。
    """
    import types as _types
    from app.database import collection_session
    from app.models.paper import PaperQuestion

    if not ai_any_enabled():
        logger.warning("AI 不可用，跳过答案补全")
        return (0, 0, 0)

    # ── 阶段 1：短会话取出待补题目（仅字段，不绑定 ORM 对象） ──
    with collection_session() as s:
        q = s.query(
            PaperQuestion.id, PaperQuestion.subject, PaperQuestion.grade,
            PaperQuestion.seq, PaperQuestion.qtype,
            PaperQuestion.question_text, PaperQuestion.options,
        ).filter(
            (PaperQuestion.correct_answer == None) | (PaperQuestion.correct_answer == "")
        )
        if grade:
            q = q.filter(PaperQuestion.grade == grade)
        if subject:
            q = q.filter(PaperQuestion.subject == subject)
        if paper_ids:
            q = q.filter(PaperQuestion.paper_id.in_(paper_ids))
        rows = q.order_by(PaperQuestion.id).all()
    total_missing = len(rows)
    if limit:
        rows = rows[:limit]

    # ── 阶段 2：无会话逐题调 AI ──
    processed = skipped = ok = 0
    # 持续限流/超时保护：连续失败达到阈值即判定 AI 暂不可用，放弃本次补全，
    # 剩余题目留待后续运行（避免对大量缺失题死循环刷接口、卡住数十小时）。
    MAX_CONSECUTIVE_FAILS = 10
    consecutive_skip = 0
    for r in rows:
        rid, subject_, grade_, seq_, qtype_, qtext_, opts_ = r
        # 轻量对象供 generate_answer_for / _build_user 使用（不绑定任何会话）
        qobj = _types.SimpleNamespace(
            subject=subject_, grade=grade_, seq=seq_, qtype=qtype_,
            question_text=qtext_, options=opts_)
        processed += 1
        ans = generate_answer_for(qobj)
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
            logger.info("[dry] %s/%s q%d: %s", subject_, grade_, seq_, ans[:50])
            continue
        # 增量写回：每题一个「短会话」（开→写→提交→关），AI 调用期间绝不持连，
        # 既遵守连接池铁律，又保证长任务中途崩溃只丢当前题、已补答案全部落库。
        try:
            with collection_session() as s2:
                pq = s2.query(PaperQuestion).get(rid)
                if pq is not None:
                    pq.correct_answer = "[AI生成] " + ans
                    s2.commit()
            ok += 1
        except Exception as e:
            logger.warning("写回答案失败（id=%s）: %s", rid, e)

    logger.info("答案补全：本次处理 %d（待补共 %d），成功 %d，跳过 %d",
                processed, total_missing, ok, skipped)
    return (processed, ok, skipped)


def count_missing_answers(grade: str | None = None, subject: str | None = None) -> int:
    """统计仍有缺失答案的题目数（供采集后核对 / 刷题前确保全覆盖）。"""
    from app.database import collection_session
    from app.models.paper import PaperQuestion
    with collection_session() as s:
        q = s.query(PaperQuestion).filter(
            (PaperQuestion.correct_answer == None) | (PaperQuestion.correct_answer == "")
        )
        if grade:
            q = q.filter(PaperQuestion.grade == grade)
        if subject:
            q = q.filter(PaperQuestion.subject == subject)
        return q.count()
