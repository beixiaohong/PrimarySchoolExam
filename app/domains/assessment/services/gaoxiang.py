"""软考高项备考服务层（assessment 域）

职责分界：
- 本文件：静态考纲数据、AI 输出解析（纯函数，可单测）、判分/错题回写/进度聚合（DB 逻辑）。
- routers/gaoxiang.py：HTTP 编排。**AI 调用发生在 DB 会话之外**（铁律：不得持连接等
  外部阻塞调用），调用成功后才开短会话落库/扣费。

设计要点：
- 题目落库复用：AI 生成的题存入 gx_questions，刷题时优先从「该用户未做过」的
  题库出题，不够才补生成 —— 同样的内容不重复扣费。
- 错题闭环与小学侧同构：答错进错题本，重做连对 3 次自动掌握。
- 判分在服务端做（与 ai_quiz 的前端判分不同）：答案存库，防止前端被绕过刷进度。
"""
import json
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.gaoxiang import GxKnowledge, GxQuestion, GxAttempt, GxWrong, GxProgress

logger = logging.getLogger("gaoxiang")

# ── 静态考纲：第 4 版教材 24 章（章名即知识域名）──
# 演进说明：早期只列「十大知识域」（第 8~17 章），但导入的真实备考资料覆盖第 1~24 章
# （信息化发展、信息系统治理、绩效域、法律法规…），只认十大域会让这些章节的题目
# 无处归置或被迫错标 → 扩展为完整考纲。第 8~17 章名称保持与旧版一致，便于既有数据对齐。
GX_CHAPTERS = (
    (1, "信息化发展"),
    (2, "信息技术发展"),
    (3, "信息系统治理"),
    (4, "信息系统管理"),
    (5, "信息系统工程"),
    (6, "项目管理概论"),
    (7, "项目立项管理"),
    (8, "整体管理"),          # 第8章 项目整合管理
    (9, "范围管理"),
    (10, "进度管理"),
    (11, "成本管理"),
    (12, "质量管理"),
    (13, "资源管理"),
    (14, "沟通管理"),
    (15, "风险管理"),
    (16, "采购管理"),
    (17, "干系人管理"),
    (18, "绩效域"),            # 第18章 项目绩效域
    (19, "配置与变更管理"),
    (20, "高级项目管理"),
    (21, "项目管理科学基础"),
    (22, "组织通用治理"),
    (23, "组织通用管理"),
    (24, "法律法规与标准规范"),
)
GX_DOMAINS = [name for _, name in GX_CHAPTERS]
CHAPTER_OF = {name: no for no, name in GX_CHAPTERS}
DOMAIN_OF_CHAPTER = {no: name for no, name in GX_CHAPTERS}

# 域别名表（用于把资料里的自由文本归到域；**长的键在前**，避免「项目管理概论」被「项目」类短键抢走）
DOMAIN_ALIASES = (
    ("信息化发展", ("信息化发展", "信息化")),
    ("信息技术发展", ("信息技术发展", "信息技术")),
    ("信息系统治理", ("信息系统治理", "IT治理")),
    ("信息系统管理", ("信息系统管理", "IT管理")),
    ("信息系统工程", ("信息系统工程",)),
    ("项目管理概论", ("项目管理概论", "项目管理基础")),
    ("项目立项管理", ("项目立项管理", "立项管理")),
    ("整体管理", ("整体管理", "整合管理")),
    ("范围管理", ("范围管理",)),
    ("进度管理", ("进度管理", "时间管理")),
    ("成本管理", ("成本管理",)),
    ("质量管理", ("质量管理",)),
    ("资源管理", ("资源管理", "人力资源管理")),
    ("沟通管理", ("沟通管理",)),
    ("风险管理", ("风险管理",)),
    ("采购管理", ("采购管理",)),
    ("干系人管理", ("干系人管理", "干系人")),
    ("绩效域", ("绩效域",)),
    ("配置与变更管理", ("配置与变更管理", "配置管理", "变更管理")),
    ("高级项目管理", ("高级项目管理", "高级管理")),
    ("项目管理科学基础", ("项目管理科学基础", "科学基础")),
    ("组织通用治理", ("组织通用治理", "组织治理")),
    ("组织通用管理", ("组织通用管理", "组织管理")),
    ("法律法规与标准规范", ("法律法规与标准规范", "法律法规", "标准规范")),
)

# 题型
QTYPE_SINGLE = "single"
QTYPE_MULTI = "multi"
QTYPE_CASE = "case"
QTYPE_ESSAY = "essay"          # 论文题（主观大论述，四维评分）
QTYPES = (QTYPE_SINGLE, QTYPE_MULTI, QTYPE_CASE, QTYPE_ESSAY)

# 主观题（走 AI 批改 + 低于阈值进错题本），与客观题（服务端判分）区分
SUBJECTIVE_QTYPES = (QTYPE_CASE, QTYPE_ESSAY)

QTYPE_LABELS = {QTYPE_SINGLE: "单选题", QTYPE_MULTI: "多选题",
                QTYPE_CASE: "案例分析题", QTYPE_ESSAY: "论文题"}


def qtype_label(qtype: str) -> str:
    """题型中文名（错误提示/前端展示共用）"""
    return QTYPE_LABELS.get(qtype, qtype or "题目")

# 主观题「未达标」阈值：低于该分视为错题入库，供后续重练
SUBJECTIVE_PASS_SCORE = 60

# 重做连对 N 次自动掌握（与小学错题闭环一致）
MASTER_STREAK = 3

# 错题本题型分栏（`gx_wrongs.kind`）：前端按此把选择/案例/论文错题分开列
WK_CHOICE = "choice"
WK_CASE = "case"
WK_ESSAY = "essay"
KIND_OF_QTYPE = {QTYPE_SINGLE: WK_CHOICE, QTYPE_MULTI: WK_CHOICE,
                 QTYPE_CASE: WK_CASE, QTYPE_ESSAY: WK_ESSAY}
WRONG_KINDS = (WK_CHOICE, WK_CASE, WK_ESSAY)

# 各题型 AI 单次生成的题数（太大易超时/超 token）
GEN_BATCH = {QTYPE_SINGLE: 5, QTYPE_MULTI: 4, QTYPE_CASE: 1}

QUIZ_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）的资深辅导老师，熟悉第4版教材与历年真题风格。
根据知识域与题型出题，要求：
1. 题目贴近真题风格：单选考概念辨析/ITO 归属/计算题，多选考过程/输入输出的组合；
2. 每题必须给出正确答案与一段简洁解析（说明为什么选它、易混淆点在哪）；
3. 严格按给定知识域出题，不要跨域；
4. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"questions": [{{"question": "题干", "options": ["A. ...", "B. ...", "C. ...", "D. ..."] 或 null(多选给4-5个), "answer": "正确选项字母（多选如 ABD）", "analysis": "解析"}}]}}"""

CASE_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）案例分析题的资深辅导老师。
按给定知识域出一道案例分析大题，要求：
1. 给出一段真实项目背景（200-400字，包含该知识域的典型问题情境）；
2. 出 2-3 个子问题，覆盖「找问题/说原因/给对策」中的至少两类；
3. 每个子问题给出参考答案要点（用于后续 AI 批改的评分依据）；
4. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"background": "背景材料", "sub_questions": [{{"q": "子问题", "answer": "参考答案要点", "points": 10}}]}}"""

KNOWLEDGE_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）的资深辅导老师，熟悉第4版教材。
按给定知识域生成一批核心知识点卡片，要求：
1. 覆盖该知识域的主要考点：定义、主要过程、输入输出工具技术（ITO）、常考易混点；
2. 每个知识点 content 用简洁的结构化文字（可用换行与序号），200-400字；
3. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"points": [{{"code": "如 4.1", "title": "知识点标题", "summary": "一句话摘要", "content": "正文"}}]}}"""


# ── 考纲归一（纯函数，供资料导入与端点校验共用） ──

_CHAPTER_NUM_RE = re.compile(r"第\s*(\d{1,2}(?:\s*[、,，~\-至]\s*\d{1,2})*)\s*章")
# 小节号写法（`第6.4.1节--项目管理12原则`）：每日一练文件名大量使用，
# 不认它就有约 7% 的题目知识域为空（实测 2026 年 1~2 月那批每日一练全是这种）。
# 章号 = 小节号的第一段：6.4.1 → 第6章。
_SECTION_NUM_RE = re.compile(r"第\s*(\d{1,2})\s*[.．]\s*\d{1,2}(?:\s*[.．]\s*\d{1,2})*\s*节")


def _expand_chapter_numbers(expr: str) -> list:
    """展开章节号表达式：'10'→[10]；'6、7'→[6,7]；'8~10'→[8,9,10]；'3-5'→[3,4,5]"""
    out = []
    for part in re.split(r"[、,，]", expr):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d{1,2})\s*[~\-至]\s*(\d{1,2})$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b:
                out.extend(range(a, b + 1))
            continue
        if part.isdigit():
            out.append(int(part))
    return out


def normalize_domains(text: str) -> list:
    """把自由文本归一到知识域列表（顺序去重）

    优先按「第N章 / 第A、B~C章」抽取（最可靠，资料文件名基本都带）；
    没有章号时退回别名包含匹配（长键优先，避免短键抢词）。
    无法判定时返回空列表 —— 调用方决定兜底策略，不在纯函数里猜。
    """
    if not text:
        return []
    found = []
    for m in _CHAPTER_NUM_RE.finditer(text):
        for no in _expand_chapter_numbers(m.group(1)):
            name = DOMAIN_OF_CHAPTER.get(no)
            if name and name not in found:
                found.append(name)
    if found:
        return found
    # 小节号 → 章号（`第6.4.1节` → 第6章 项目管理概论）
    for m in _SECTION_NUM_RE.finditer(text):
        name = DOMAIN_OF_CHAPTER.get(int(m.group(1)))
        if name and name not in found:
            found.append(name)
    if found:
        return found
    # 无章号 → 别名匹配（按别名长度降序，避免「绩效域」被更短的同义键截断）
    hits = []
    for domain, aliases in DOMAIN_ALIASES:
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in text:
                hits.append((len(alias), domain))
                break
    hits.sort(key=lambda x: -x[0])
    for _, domain in hits:
        if domain not in found:
            found.append(domain)
    return found


def normalize_domain(text: str, default: str = "") -> str:
    """归一为单个域（取第一个命中；无法判定时返回 default）"""
    got = normalize_domains(text)
    return got[0] if got else default


def chapter_label(no: int) -> str:
    """章号 → 规范章节名（12 → '第12章 项目质量管理'）；未知章号返回空串"""
    name = DOMAIN_OF_CHAPTER.get(no)
    return "第%d章 %s" % (no, name) if name else ""


def normalize_chapter(text: str) -> str:
    """从任意文本抽出**规范**章节名（'第12章 项目质量管理'）；抽不到返回 ""

    资料里的「章节标签」五花八门：`第12章 项目质量管理（下）`、`第6.4.1节`、
    甚至整条横幅 `试题解析 软考高项教程第四版P373：控制质量过程的主要作用`。
    前端要做「按章节筛选」，必须统一成考纲的 24 章口径，所以这里做两级回退：
    先按章号表达式取（最可靠），再按域名反查章号。
    """
    if not text:
        return ""
    for m in _CHAPTER_NUM_RE.finditer(text):
        for no in _expand_chapter_numbers(m.group(1)):
            label = chapter_label(no)
            if label:
                return label
    for m in _SECTION_NUM_RE.finditer(text):
        label = chapter_label(int(m.group(1)))
        if label:
            return label
    # 没有章号 → 拿域名反查章号（如 `项目管理12原则` 里的「项目管理概论」）
    for domain in normalize_domains(text):
        no = CHAPTER_OF.get(domain)
        if no:
            return chapter_label(no)
    return ""


def is_valid_domain(domain: str) -> bool:
    return domain in CHAPTER_OF


# ── AI 输出解析（纯函数） ──

def _extract_json(text: str):
    """从 AI 输出中提取首个 JSON 对象（容忍 markdown 代码围栏与前后杂文）"""
    if not text:
        return None
    text = text.strip()
    # 优先剥 ```json ... ``` 围栏
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except Exception:
        pass
    # 兜底：取第一个 { 到最后一个 } 之间
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def parse_questions(text: str):
    """解析出题 AI 输出 → [{question, options, answer, analysis}]（结构非法的字段丢弃）"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        return []
    out = []
    for q in data.get("questions") or []:
        if not isinstance(q, dict):
            continue
        question = (q.get("question") or "").strip()
        answer = (q.get("answer") or "").strip()
        if not question or not answer:
            continue
        options = q.get("options")
        if options is not None and not (isinstance(options, list) and options):
            options = None
        out.append({"question": question, "options": options,
                    "answer": answer, "analysis": (q.get("analysis") or "").strip()})
    return out


def parse_case(text: str):
    """解析案例出题 AI 输出 → {background, sub_questions:[{q, answer, points}]} 或 None"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    background = (data.get("background") or "").strip()
    subs = []
    for s in data.get("sub_questions") or []:
        if not isinstance(s, dict):
            continue
        q = (s.get("q") or "").strip()
        if not q:
            continue
        try:
            points = int(s.get("points") or 10)
        except (TypeError, ValueError):
            points = 10
        subs.append({"q": q, "answer": (s.get("answer") or "").strip(), "points": points})
    if not background or not subs:
        return None
    return {"background": background, "sub_questions": subs}


def parse_knowledge(text: str):
    """解析知识点 AI 输出 → [{code, title, summary, content}]"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        return []
    out = []
    for p in data.get("points") or []:
        if not isinstance(p, dict):
            continue
        title = (p.get("title") or "").strip()
        content = (p.get("content") or "").strip()
        if not title or not content:
            continue
        out.append({"code": (p.get("code") or "").strip(), "title": title,
                    "summary": (p.get("summary") or "").strip()[:500], "content": content})
    return out


# ── 判分（纯函数） ──

def normalize_letters(s: str) -> str:
    """把答案归一为大写字母升序串（'b,a' / 'B A' → 'AB'），供单/多选比对"""
    return "".join(sorted({c for c in (s or "").upper() if "A" <= c <= "Z"}))


def grade_choice(user_answer: str, correct: str, qtype: str) -> bool:
    """单选/多选判分：字母归一后全等（多选必须全对，与考试规则一致）"""
    if qtype not in (QTYPE_SINGLE, QTYPE_MULTI):
        return False
    return bool(normalize_letters(user_answer)) and \
        normalize_letters(user_answer) == normalize_letters(correct)


# ── DB 逻辑（调用方持有会话，方法内不开新会话） ──

def _bump_progress(db: Session, user_id: str, domain: str, **inc) -> None:
    """进度增量更新（user_id+domain 一行，缺则建）"""
    row = db.query(GxProgress).filter_by(user_id=user_id, domain=domain).first()
    if row is None:
        row = GxProgress(user_id=user_id, domain=domain, knowledge_read=0,
                         quiz_total=0, quiz_correct=0, case_count=0)
        db.add(row)
    for k, v in inc.items():
        setattr(row, k, (getattr(row, k) or 0) + v)
    row.last_at = datetime.now()


def record_choice_attempt(db: Session, user_id: str, question: GxQuestion,
                          user_answer: str, duration_ms: int = 0) -> dict:
    """选择题作答：落记录 + 进度 + 错题闭环，返回 {judged, is_correct, correct, analysis}

    错误：错题本 upsert（wrong_count+1、correct_streak 清零）；
    正确：若在错题本中则 correct_streak+1，达 MASTER_STREAK 自动掌握。

    `judged=False` 的情况：导入的打印版资料本来就**没有参考答案**（约 5%）。
    这类题不能判「错」—— 判错会把正确答案的题塞进错题本、污染错题分析。
    所以只记作答、不计对错、不动错题本，由前端提示「本题资料未提供参考答案」。
    """
    correct = (question.answer or "").strip()
    judged = bool(correct)
    is_correct = grade_choice(user_answer, correct, question.qtype) if judged else None
    db.add(GxAttempt(user_id=user_id, question_id=question.id,
                     user_answer=user_answer, is_correct=is_correct,
                     duration_ms=max(0, int(duration_ms or 0))))
    _bump_progress(db, user_id, question.domain,
                   quiz_total=1, quiz_correct=1 if is_correct else 0)

    if judged:
        wrong = db.query(GxWrong).filter_by(user_id=user_id,
                                            question_id=question.id).first()
        if is_correct:
            if wrong is not None and not wrong.is_mastered:
                wrong.correct_streak = (wrong.correct_streak or 0) + 1
                if wrong.correct_streak >= MASTER_STREAK:
                    wrong.is_mastered = True
                    wrong.mastered_at = datetime.now()
        else:
            if wrong is None:
                wrong = GxWrong(user_id=user_id, question_id=question.id,
                                user_answer=user_answer, wrong_count=1, correct_streak=0,
                                kind=KIND_OF_QTYPE.get(question.qtype, WK_CHOICE))
                db.add(wrong)
            else:
                wrong.wrong_count = (wrong.wrong_count or 0) + 1
                wrong.correct_streak = 0
                wrong.is_mastered = False
                wrong.mastered_at = None
                wrong.user_answer = user_answer
                wrong.kind = KIND_OF_QTYPE.get(question.qtype, WK_CHOICE)
            wrong.last_wrong_at = datetime.now()
    db.commit()
    return {"judged": judged, "is_correct": is_correct, "correct": correct,
            "analysis": question.analysis or "",
            "has_answer": judged}


def record_subjective_grade(db: Session, user_id: str, question: GxQuestion,
                            kind: str, score: int) -> dict:
    """案例/论文批改后的错题闭环：低于及格线（60）入错题本，达线则累计连对

    主观题没有「对/错」，只有分数，所以错题本用 best_score / last_score 记录轨迹；
    重做连对 N 次（MASTER_STREAK）就自动掌握，与选择题同一套闭环。
    """
    passed = (score or 0) >= SUBJECTIVE_PASS_SCORE
    wrong = db.query(GxWrong).filter_by(user_id=user_id,
                                        question_id=question.id).first()
    added = False
    if passed:
        if wrong is not None and not wrong.is_mastered:
            wrong.correct_streak = (wrong.correct_streak or 0) + 1
            wrong.best_score = max(wrong.best_score or 0, score or 0)
            wrong.last_score = score or 0
            if wrong.correct_streak >= MASTER_STREAK:
                wrong.is_mastered = True
                wrong.mastered_at = datetime.now()
    else:
        if wrong is None:
            wrong = GxWrong(user_id=user_id, question_id=question.id,
                            user_answer="", wrong_count=1, correct_streak=0,
                            kind=kind, last_score=score or 0, best_score=score or 0)
            db.add(wrong)
            added = True
        else:
            wrong.wrong_count = (wrong.wrong_count or 0) + 1
            wrong.correct_streak = 0
            wrong.is_mastered = False
            wrong.mastered_at = None
            wrong.kind = kind
            wrong.last_score = score or 0
            wrong.best_score = max(wrong.best_score or 0, score or 0)
        wrong.last_wrong_at = datetime.now()
    db.commit()
    return {"passed": passed, "added": added, "pass_score": SUBJECTIVE_PASS_SCORE}


def quiz_pick(db: Session, user_id: str, domain: str = "", qtype: str = QTYPE_SINGLE,
              source_kind: str = "", chapter: str = "", scope: str = "",
              count: int = 5) -> list:
    """按条件挑选未做过的题目 id（纯查库，不调 AI）

    scope：
      - ""（默认）：题库里该域/题型下未做过的题，按 id 升序（先导入的先刷）
      - "wrong"：错题重练 —— 从错题本取未掌握的题，**不再过滤「未做过」**
        （否则错题永远刷不到），并按答错次数降序（错得多的先练）。
    """
    n = max(1, min(int(count or 5), 50))
    if scope == "wrong":
        wrongs = (db.query(GxWrong)
                  .filter(GxWrong.user_id == user_id, GxWrong.is_mastered.is_(False))
                  .order_by(GxWrong.wrong_count.desc(), GxWrong.last_wrong_at.desc())
                  .limit(n * 3).all())
        ids = [w.question_id for w in wrongs]
        if not ids:
            return []
        q = db.query(GxQuestion).filter(GxQuestion.id.in_(ids))
        if domain:
            q = q.filter(GxQuestion.domain == domain)
        if qtype:
            q = q.filter(GxQuestion.qtype == qtype)
        got = {r.id: r for r in q.all()}
        # 保持错题本的顺序（错得多 → 先练）
        return [got[i] for i in ids if i in got][:n]

    # 已做过的题在 SQL 层排除（NOT EXISTS 子查询）。
    # 早期实现是「取 n*8 行再在 Python 里剔除已做」，用户做满前 40 道后窗口内全是旧题
    # → 明明库里有上千道真题却判定「资料不够」回退到 AI 出题（白扣费）。子查询无此问题，
    # 也不必把已做 id 全量捞进内存。
    q = db.query(GxQuestion).filter(
        ~db.query(GxAttempt.id).filter(GxAttempt.user_id == user_id,
                                       GxAttempt.question_id == GxQuestion.id).exists())
    if domain:
        q = q.filter(GxQuestion.domain == domain)
    if qtype:
        q = q.filter(GxQuestion.qtype == qtype)
    if source_kind:
        q = q.filter(GxQuestion.source_kind == source_kind)
    if chapter:
        q = q.filter(GxQuestion.chapter == chapter)
    return q.order_by(GxQuestion.id).limit(n).all()


# ── 错因分析（AI 输出的构造与解析，纯函数） ──

WRONG_ANALYSIS_PROMPT = """你是软考高级「信息系统项目管理师」（高项）的辅导老师。
考生答错了一道题，请给出错因分析。要求：
1. 一句话点明错在哪（概念混淆 / 记错要点 / 审题不清 / 知识空白）；
2. 讲清正确选项为什么对、考生所选项为什么错（结合考纲知识点）；
3. 给出 1-2 条可执行的记忆锚点或口诀；
4. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"reason_type": "概念混淆|记忆偏差|审题不清|知识空白|其它", "analysis": "错因分析与订正（可换行）", "tips": "记忆锚点"}}"""


def build_wrong_analysis_prompt(question: GxQuestion, user_answer: str) -> str:
    """构造错因分析的提问（把题干/选项/正解/错选都喂进去）"""
    lines = [f"题干：{question.question or ''}"]
    try:
        options = json.loads(question.options_json) if question.options_json else None
    except ValueError:
        options = None
    if options:
        lines.append("选项：")
        lines.extend(f"  {o}" for o in options)
    if (question.answer or "").strip():
        lines.append(f"正确答案：{question.answer}")
    lines.append(f"考生所选：{user_answer or '（空）'}")
    if (question.analysis or "").strip():
        lines.append(f"参考解析：{question.analysis}")
    if (question.sub_questions or "").strip():
        lines.append(f"子问题与参考答案：{question.sub_questions}")
    lines.append("请输出 JSON 错因分析。")
    return "\n".join(lines)


def parse_wrong_analysis(text: str) -> dict:
    """解析错因分析 AI 输出 → {reason_type, analysis, tips}（缺失字段留空）"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        return {}
    return {
        "reason_type": (data.get("reason_type") or "").strip()[:20],
        "analysis": (data.get("analysis") or "").strip(),
        "tips": (data.get("tips") or "").strip(),
    }


# ── 论文四维评分（纯函数） ──

# 高项论文阅卷的四个维度（官方评分口径的简化版）：切题 / 结构 / 实践 / 文字
ESSAY_DIMS = (
    ("relevance", "切题与完整性", 35),
    ("structure", "结构与管理过程", 25),
    ("practice", "项目实践与真实性", 25),
    ("writing", "文字表达与字数", 15),
)


def parse_essay_grade(text: str):
    """解析论文评分 AI 输出 → {score, feedback, rubric:[{dim,label,score,comment}]}

    兼容两种输出：四维明细（rubric）或缺省（只有 score/feedback）。
    总分以四维加权为准（AI 直接给的总分常在四维不自洽）；四维缺失则用 AI 总分。
    """
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    raw = data.get("rubric") or data.get("dims") or []
    rubric, total, weight = [], 0, 0
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            dim = (item.get("dim") or item.get("name") or "").strip()
            try:
                sc = int(item.get("score"))
            except (TypeError, ValueError):
                continue
            sc = max(0, min(100, sc))
            label = dict((k, v) for k, v, _ in ESSAY_DIMS).get(dim, dim)
            weight_full = next((w for k, _, w in ESSAY_DIMS if k == dim), 0)
            rubric.append({"dim": dim, "label": label, "score": sc,
                           "full": weight_full,
                           "comment": (item.get("comment") or "").strip()})
            if weight_full:
                total += sc * weight_full
                weight += weight_full
    feedback = (data.get("feedback") or "").strip()
    score = round(total / weight) if weight else None
    if score is None:
        try:
            score = max(0, min(100, int(data.get("score"))))
        except (TypeError, ValueError):
            score = None
    if score is None and not feedback:
        return None
    return {"score": score, "feedback": feedback, "rubric": rubric}


def build_essay_grade_prompt(question: GxQuestion, user_answer: str) -> str:
    """构造论文评分的提问（题目名 + 背景 + 论述要求 + 考生正文）"""
    reqs = ""
    try:
        parsed = json.loads(question.sub_questions) if question.sub_questions else None
        if parsed:
            reqs = "\n".join(f"  {r.get('q')}" for r in parsed if isinstance(r, dict))
    except ValueError:
        reqs = ""
    return ("论文题目：" + (question.title or "") + "\n\n"
            + (f"题目背景：{question.question}\n\n" if (question.question or "").strip() else "")
            + (f"论述要求：\n{reqs}\n\n" if reqs else "")
            + f"考生论文正文（约 {len(user_answer)} 字）：\n{user_answer}\n\n"
            + "请按四维评分并输出 JSON。")


def mark_mastered(db: Session, user_id: str, question_id: int) -> bool:
    """手动标记错题已掌握（不存在或已掌握返回 False）"""
    wrong = db.query(GxWrong).filter_by(user_id=user_id, question_id=question_id).first()
    if wrong is None or wrong.is_mastered:
        return False
    wrong.is_mastered = True
    wrong.mastered_at = datetime.now()
    db.commit()
    return True


def progress_overview(db: Session, user_id: str) -> dict:
    """分知识域进度总览：考纲全部知识域都列出（没学过的为 0），附汇总"""
    rows = {r.domain: r for r in
            db.query(GxProgress).filter_by(user_id=user_id).all()}
    domains = []
    total_q = total_c = total_case = total_read = 0
    for d in GX_DOMAINS:
        r = rows.get(d)
        qt, qc = (r.quiz_total or 0, r.quiz_correct or 0) if r else (0, 0)
        domains.append({
            "domain": d,
            "knowledge_read": (r.knowledge_read or 0) if r else 0,
            "quiz_total": qt, "quiz_correct": qc,
            "accuracy": round(qc / qt * 100) if qt else None,
            "case_count": (r.case_count or 0) if r else 0,
        })
        total_q += qt
        total_c += qc
        total_case += (r.case_count or 0) if r else 0
        total_read += (r.knowledge_read or 0) if r else 0
    return {"domains": domains,
            "summary": {"quiz_total": total_q, "quiz_correct": total_c,
                        "accuracy": round(total_c / total_q * 100) if total_q else None,
                        "case_count": total_case, "knowledge_read": total_read}}
