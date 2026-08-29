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

from ..services.answer_check import numeric_approx_equal

logger = logging.getLogger(__name__)

# ── Step 1: 独立解题（输入不含参考答案，迫使 AI 真正独立思考） ──
JUDGE_STEP1_SYSTEM = (
    "你是一位严谨的小学/初中（数学/语文/英语/科学）批改老师。\n"
    "以下题目被系统判为孩子答错，但系统判定可能有误。请独立、客观地复核。\n\n"
    "任务：\n"
    "1. **独立解答**：先看题目，自己得出正确答案（本题不提供参考答案，不要被题目措辞锚定）。"
    "数值题请完整计算并保留合理精度（如 202×0.8=161.6，不要截断为整数；百分数、单位换算同理）。\n"
    "2. **判断孩子作答是否正确**：以「知识点/核心结论是否一致」为准，不要做字面逐字比较。"
    "以下情形都应判为正确（child_correct=true）：\n"
    "   - 等价表达：分数/小数/百分数互化、单位换算正确、同义表述、语序不同；\n"
    "   - 中文数字与阿拉伯数字等价（\"三条\"=\"3条\"、\"六十\"=\"60\"）；\n"
    "   - 错别字/音近字/形近字但意思相同（如\"对轴相直\"=\"对边平行\"、\"礼拜天/星期天\"=\"星期日\"）；\n"
    "   - 繁简/全半角/标点/空格差异；\n"
    "   - 概念/定义/常识题：孩子用不同措辞表达了相同知识点"
    "（如\"每个角60度，三条对称轴\"等价于\"60°，3条\"；\"两组对边平行\"与\"一组对边平行\"的区别表述正确）；\n"
    "   - 孩子给出关键结论正确，仅多了合理的说明或过程、或个别非关键笔误。\n"
    "   仅当孩子确实答错（关键知识点错误、结论相反或数值明显算错）时才判 child_correct=false。\n"
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
    if not ai_svc.ai_any_enabled():
        logger.info("AI 判题复核跳过（未配置任何 Key，含 deepseek，user=%s）", user_id)
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

    # 准备：题字典 + 已批准结果（本地预判与 AI 复核共用）
    key_to_item = {it["key"]: it for it in todo}
    approved: dict = {}

    # 1.5) 本地语义预判：对确定性概念/常识题（纯文字参考答案）先容错判对，
    #      不依赖 AI（AI 降级/限频时也能判对）。保守：仅当本地可确认正确才采纳。
    for it in todo:
        if _local_semantic_correct(it.get("user_answer", ""), it.get("answer", "") or ""):
            approved[it["key"]] = {
                "correct": True,
                "stored_wrong": False,
                "correct_answer": (it.get("answer") or "").strip(),
                "reason": "本地语义预判：知识点正确",
            }

    # 2) Step 1: 独立解题 + 判断孩子作答（输入不含参考答案！）
    #    已本地判对的题跳过，节省 AI 调用。
    step1_lines = []
    for it in todo:
        if it["key"] in approved:
            continue
        q_text = it.get("question", "")
        opts = it.get("options")
        if opts:
            q_text = f"{q_text}\n选项：{' | '.join(opts)}"
        step1_lines.append(
            f"第{it['key']}题（{it.get('subject', '')}）："
            f"题目：{q_text}\n"
            f"孩子作答：{it.get('user_answer', '')}\n"
        )
    if step1_lines:
        # 付费优先：配置了 DeepSeek 且孩子有钻石 → 用 deepseek 复核并扣钻石；
        # 否则降级免费链（zhipu→relay，不扣钻石）。
        result1 = ai_svc.chat_paid_first(
            user_id,
            JUDGE_STEP1_SYSTEM,
            "以下是需要复核的题目（请独立解答后判断孩子作答）：\n" + "\n".join(step1_lines),
            max_tokens=1200,
            reason="judge",
        )
    else:
        result1 = None  # 全部已本地判对，无需调 AI

    if step1_lines and (not result1 or not result1.get("text", "").strip()):
        db = SessionLocal()
        try:
            _log_judge_usage(db, user_id, ok=False, error="Step1 AI 不可用，维持本地判定")
        finally:
            db.close()
        return approved  # 已本地判对的题仍生效（只升不降）

    verdicts1 = _parse_verdicts((result1 or {}).get("text", "")) if result1 else []
    if step1_lines and not verdicts1:
        db = SessionLocal()
        try:
            _log_judge_usage(db, user_id, ok=False, error="Step1 AI 输出无法解析，维持本地判定")
        finally:
            db.close()
        return approved  # 已本地判对的题仍生效（只升不降）

    # 3) 收集 Step1 结果
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
            result2 = ai_svc.chat_paid_first(
                user_id,
                JUDGE_STEP2_SYSTEM,
                "以下题目的参考答案可能算错，请校对：\n" + "\n".join(step2_lines),
                max_tokens=600,
                reason="judge",
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

    # 5) 落缓存 + 系统错题沉淀 + 用量日志
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
            _record_system_issue(db, user_id, key_to_item[key], verdict)
        _log_judge_usage(db, user_id, ok=True, result=result1,
                         detail=f"复核 {len(todo)} 题，判对 {len(approved)} 题"
                                f"（force={force}）")
        return approved
    finally:
        db.close()


def _record_system_issue(db, user_id: str, it: dict, verdict: dict):
    """系统判题错误题目沉淀：AI 复核判定「参考答案有误/本地判题逻辑把对的说错」。

    只记真正的系统问题，用于日后统一修复判题代码/题库：
    - stored_wrong=True：存储的参考答案本身算错；
    - correct=True 且非「本地语义预判」：本地判分逻辑把正确作答判错（AI 复核纠正）。
    幂等：同题 + 同作答 + 未处理（open）已存在则跳过。
    """
    stored_wrong = bool(verdict.get("stored_wrong"))
    reason = str(verdict.get("reason") or "")
    if not stored_wrong and not verdict.get("correct"):
        return
    if reason.startswith("本地语义预判"):
        return  # 已知容差场景（概念/常识题），非系统错误
    qid = it.get("question_id")
    if not qid:
        return
    from ..models.judge_review import JudgeReviewIssue
    user_answer = it.get("user_answer", "") or ""
    dup = db.query(JudgeReviewIssue).filter(
        JudgeReviewIssue.question_id == qid,
        JudgeReviewIssue.user_answer == user_answer,
        JudgeReviewIssue.status == "open",
    ).first()
    if dup:
        return
    try:
        db.add(JudgeReviewIssue(
            user_id=user_id,
            question_id=qid,
            question=(it.get("question") or "")[:2000],
            stored_answer=(it.get("answer") or ""),
            correct_answer=(verdict.get("correct_answer") or ""),
            user_answer=user_answer[:1000],
            subject=(it.get("subject") or "")[:20],
            reason=reason[:200],
            source="judge",
        ))
        db.commit()
        logger.info("系统判题错误题目已沉淀 question_id=%s user=%s reason=%s",
                    qid, user_id, reason[:50])
    except Exception as e:  # noqa: BLE001
        logger.warning("写系统错题沉淀失败: %s", e)
        db.rollback()


def _fuzzy_match(user_answer: str, correct_answer: str) -> bool:
    """语义级模糊匹配：用于 Step2 二次确认孩子作答是否等于正确值。

    放宽到「中文数字归一 + 核心关键词包含 + 冗余说明裁剪」：
    - 中文数字（三条/六十）与阿拉伯数字（3/60）等价；
    - 角度/温度单位「度」与「°」等价；
    - 不要求逐字相等，只要求较短一方是较长一方的子串（容忍冗余说明/过程）。
    """
    def _cn_num(s: str) -> str:
        table = {"零": "0", "〇": "0", "一": "1", "二": "2", "两": "2", "三": "3",
                 "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
                 "十": "10"}
        return "".join(table.get(ch, ch) for ch in s)

    def _norm(s: str) -> str:
        s = s.replace(" ", "").replace("\u3000", "")
        s = s.replace("度", "°").replace("，", ",").replace("。", ".")
        s = s.replace("、", ",")
        s = _cn_num(s)
        return s.lower()
    u, a = _norm(user_answer), _norm(correct_answer)
    if not u or not a:
        return False
    if u == a:
        return True
    short, long = (a, u) if len(a) <= len(u) else (u, a)
    if short in long and len(short) >= 2:
        return True
    return False


_CN_NUM_MAP = {"零": "0", "〇": "0", "一": "1", "二": "2", "两": "2", "三": "3",
               "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
               "十": "10"}
_SIM_TYPO = {  # 常见音近/形近错别字 → 标准词（小学数学概念题高频）
    "对轴相直": "对边平行", "对轴相直线": "对边平行线", "对轴": "对边", "相直": "平行",
    "礼拜天": "星期日", "星期天": "星期日", "周日": "星期日", "周天": "星期日",
}
_VOID_CHARS = ("有", "而", "的", "则", "与", "和", "及", "且", "也", "都", "就")


def _local_semantic_correct(user_answer: str, correct_answer: str) -> bool | None:
    """本地语义预判（不调 AI）：对确定性概念/常识题做容错判分。

    返回 True=可判对、False=可判错、None=无法本地判定（交由 AI）。
    规则保守：仅当参考答案为「非算式」的概念/常识表述，且孩子作答经归一
    （中文数字→阿拉伯、错别字、度/°、去标点虚字）后包含参考核心内容时判对，
    避免误判算式/数值题。含等号或运算符号的算式题一律交 AI。
    """
    if not user_answer or not correct_answer:
        return None
    import re as _re
    ua = user_answer.strip().lower()
    ca = correct_answer.strip().lower()
    # 含等号/运算符号的算式题（如 "25×125+4×125"、"59÷7=8余3"）交给 AI，本地不插手
    if _re.search(r"[=+\-*/×÷]", ca) and _re.search(r"\d", ca):
        return None

    def _norm(s: str) -> str:
        for k, v in _CN_NUM_MAP.items():
            s = s.replace(k, v)
        for bad, good in _SIM_TYPO.items():
            s = s.replace(bad, good)
        s = s.replace("度", "°")
        s = _re.sub(r"[\s，。、；：,.!?;:…（）()]", "", s)
        for vc in _VOID_CHARS:
            s = s.replace(vc, "")
        s = s.replace("线", "")  # 几何概念中冗余量词（平行线↔平行），不丢关键信息
        return s
    u, a = _norm(ua), _norm(ca)
    if not a or len(a) < 2:
        return None
    # 数值近似容差：孩子作答与存储答案在末位半个单位内 → 本地判对（不依赖 AI）。
    # 解决「孩子填 3.33333、参考答案存 3.33 被精确比对判错，且 AI 不可用时复查假复查」的问题。
    if numeric_approx_equal(user_answer, correct_answer):
        return True
    # 纯数值/角度类答案：已由数值容差精确或容差判过，不再做子串匹配，
    # 避免 "6" 误收 "6.4"、"3.33" 误收 "3.33333" 之类（数值近似已单独处理）。
    if _re.fullmatch(r"[\d.°]+", a):
        return None
    # 仅当孩子作答包含参考核心内容（参考为孩子子串）才判对；
    # 反向（孩子过短且为参考子串）不判，避免只答片段被误判为正确。
    if a in u:
        return True
    return None


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
