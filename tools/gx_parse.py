"""软考高项备考资料：分类与解析（纯函数，不碰数据库）

为什么单独成文件
----------------
资料排版千变万化（PPT 转 PDF、打印版、带解析版混排），解析是最容易出错的一环，
必须能被单测直接调用、能在不连数据库的情况下反复跑。导入脚本
`tools/import_gx_materials.py` 只做编排（分类 → 解析 → 打包/入库），不掺解析细节。

四类目标（用户口径）
------------------
- 知识点        ：知识点清单 / 思维导图 / 必背 / 填空记忆 / 公式 / 口诀 / 课件 / 教材
- 选择题练习    ：每日一练 / 章节练习 / 仿真模拟选择题 / 冲刺选择题汇总
- 案例分析练习  ：文字案例专题 / 计算专题 / 回家作业 / 仿真模拟案例题 / 冲刺案例
- 论文练习      ：论文练习题 / 论文冲刺资料

排版要点（实测）
--------------
1. PDF 都是**文本型**（可直接抽取），封面页只有 55 字左右（乐凯培训学院 Logo）需丢弃；
2. 页眉页脚每页重复，按「出现页数占比」自动剔除；
3. 选择题分两段：先「题目」后「解析」，解析段才带 `【参考答案】/【试题解析】`；
   两段题号各自从 1 开始 → 用「期望题号」状态机分块，避免把解析正文里的
   `1、项目的必要性；` 误认成新题；
4. 案例题的块标记是 `⚫案例练习一----整合管理----问题解析`（`----` 分段，
   末段为「解析/问题解析」），同一块跨页会重复出现同一行标记 → 视为续写；
5. 论文题一页一份：`题目----论信息系统项目的XXX` + 背景 + `请以…分别从以下三个方面进行论述：`
   + 编号要求。

约束
----
**不使用 dataclass / `from __future__ import annotations`** —— 本模块会被按路径加载
（未注册 sys.modules）时字符串注解解析会抛 AttributeError，详见 tools/preflight.py。
"""
import difflib
import hashlib
import re
import sys

# ── 分类常量 ──

CAT_KNOWLEDGE = "知识点"
CAT_CHOICE = "选择题练习"
CAT_CASE = "案例分析练习"
CAT_ESSAY = "论文练习"
CAT_OTHER = "其他"

CATEGORIES = (CAT_KNOWLEDGE, CAT_CHOICE, CAT_CASE, CAT_ESSAY, CAT_OTHER)

# 需要解析入库的类别（其他类只登记归档，不解析）
PARSED_CATEGORIES = (CAT_KNOWLEDGE, CAT_CHOICE, CAT_CASE, CAT_ESSAY)

# 知识点子类
KN_LIST = "list"          # 知识点清单
KN_MINDMAP = "mindmap"    # 思维导图（单页一小节，ITO 卡片）
KN_RECITE = "recite"      # 填空辅助记忆清单
KN_MUST = "must"          # 必背知识点
KN_FORMULA = "formula"    # 公式汇总
KN_MNEMONIC = "mnemonic"  # 辅助记忆口诀
KN_ITTO = "itto"          # 子过程定义/作用/ITTO 汇总
KN_SLIDE = "slide"        # 直播课件讲义
KN_TEXTBOOK = "textbook"  # 教材/考纲/讲义电子版
KN_REF = "ref"            # 参考/汇总文档（案例常见问题、论文论点清单等，非题目）

# 题目来源子类（gx_questions.source_kind）
SK_DAILY = "每日一练"
SK_CHAPTER = "章节练习"
SK_MOCK = "仿真模拟"
SK_DIGEST = "冲刺汇总"
SK_CLASS = "课堂练习"
SK_CALC = "计算专题"     # 计算型选择题（题干 + 选项 + 解题过程）

# 文件名里命中这些词的案例/论文资料 → 实为背诵型汇总，不是题目
_REF_HINT = ("汇总", "常见问题", "原因", "要点", "口诀", "公式", "清单", "模板")

# ── 分类规则（按顺序匹配，先具体后宽泛）──
# (路径片段, 类别, 子类, 备注)；片段以 "/" 结尾表示目录前缀
_RULES = (
    # 论文
    ("/04. 课前练习（计算+案例+论文）/论文专题课练习", CAT_ESSAY, "论文练习", ""),
    ("/08.考前冲刺相关资料/论文题相关", CAT_ESSAY, "论文冲刺", ""),
    # 案例（计算题本身是案例分析的一部分；「计算专题课练习」实为**计算型选择题**
    # ——题干带 A/B/C/D 选项、解析给解题过程，故归选择题而非案例）
    ("/04. 课前练习（计算+案例+论文）/文字案例专题课练习", CAT_CASE, "案例专题", ""),
    ("/04. 课前练习（计算+案例+论文）/计算专题课练习", CAT_CHOICE, SK_CALC, ""),
    ("/04. 课前练习（计算+案例+论文）", CAT_CASE, "回家作业", ""),
    ("/08.考前冲刺相关资料/案例题相关", CAT_CASE, "案例冲刺", ""),
    # 选择题
    ("/03. 题目电子版（每日一练+章节练习+仿真模拟）/每日一练", CAT_CHOICE, SK_DAILY, ""),
    ("/03. 题目电子版（每日一练+章节练习+仿真模拟）/章节练习", CAT_CHOICE, SK_CHAPTER, ""),
    ("/08.考前冲刺相关资料/选择题相关", CAT_CHOICE, SK_DIGEST, ""),
    # 知识点（02 目录按文件名再细分，见 _knowledge_kind）
    ("/02. 课程主要知识点清单+思维导图+填空辅助记忆清单", CAT_KNOWLEDGE, "", ""),
    ("/01. 直播课程课件", CAT_KNOWLEDGE, KN_SLIDE, ""),
    ("/06. 第四版教材", CAT_KNOWLEDGE, KN_TEXTBOOK, ""),
    # 08 目录兜底：非上述三类的（必背/公式/口诀/ITTO/知识点清单汇总）都是知识点
    ("/08.考前冲刺相关资料", CAT_KNOWLEDGE, "", ""),
    # 其他（仅归档）
    ("/05. 项目管理实战模板", CAT_OTHER, "实战模板", "文档模板，不参与刷题"),
    ("/09.音频", CAT_OTHER, "音频", "课程录音，不做文本解析"),
)


def _norm_rel(rel_path) -> str:
    """统一为 POSIX 风格、以 / 开头、便于前缀匹配"""
    s = str(rel_path).replace("\\", "/")
    if not s.startswith("/"):
        s = "/" + s
    return s


def _knowledge_kind(rel_path: str, filename: str) -> str:
    """知识点子类细分（02 目录里清单/导图/填空混杂，按**目录内**路径与文件名判定）

    坑：02 顶层目录名本身叫「…+思维导图+填空辅助记忆清单」，直接对整条路径 find
    会把该目录下 200 个文件全判成思维导图 → 必须先剥掉规则片段再看剩余路径。
    """
    if "/思维导图/" in rel_path or "思维导图" in filename:
        return KN_MINDMAP
    if "填空" in filename:
        return KN_RECITE
    if "必背" in filename:
        return KN_MUST
    if "公式" in filename:
        return KN_FORMULA
    if "口诀" in filename:
        return KN_MNEMONIC
    if "子过程" in filename or "ITTO" in filename.upper():
        return KN_ITTO
    return KN_LIST


def classify(rel_path) -> dict:
    """把资料相对路径归入四类之一

    返回 {"category", "sub", "note", "reason"}；无法归类落到「其他」而不是抛异常
    —— 分类是审计信息，宁可漏判也不要让整批导入中断。
    """
    rel = _norm_rel(rel_path)
    filename = rel.rsplit("/", 1)[-1]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # 仿真模拟目录内按文件名区分选择题/案例题（打印版是选择题）
    if "/03. 题目电子版（每日一练+章节练习+仿真模拟）/仿真模拟" in rel:
        if "案例" in filename:
            return {"category": CAT_CASE, "sub": SK_MOCK, "note": "", "reason": "仿真模拟案例题"}
        if "选择" in filename:
            return {"category": CAT_CHOICE, "sub": SK_MOCK, "note": "",
                    "reason": "仿真模拟选择题"}
        return {"category": CAT_CHOICE, "sub": SK_MOCK, "note": "",
                "reason": "仿真模拟打印版（选择题为主）"}

    for frag, cat, sub, note in _RULES:
        if frag in rel:
            if cat == CAT_KNOWLEDGE and not sub:
                sub = _knowledge_kind(rel, filename)
            # 案例/论文目录里混着「背诵型汇总」（案例常见问题汇总、论文论点清单汇总），
            # 它们不是题目 → 改判为知识点，否则会被当成题目解析出 0 条而白跑
            if cat in (CAT_CASE, CAT_ESSAY) and any(h in filename for h in _REF_HINT):
                cat, sub = CAT_KNOWLEDGE, KN_REF
                note = (note + "；" if note else "") + "题目目录内的背诵型汇总文档，改判为知识点"
            extra = ""
            if ext and ext not in ("pdf",) and cat in PARSED_CATEGORIES:
                extra = f"{ext} 非 PDF，仅归档不解析"
            return {"category": cat, "sub": sub, "note": note,
                    "reason": f"命中规则 {frag}" + (f"；{extra}" if extra else "")}
    return {"category": CAT_OTHER, "sub": "", "note": "未匹配任何规则",
            "reason": "未匹配规则"}


# ── 文本抽取 ──

_BULLET_ONLY = re.compile(r"^[\s➢⚫●◆◇▪▫·•※→\-\u2014\u2013]*$")
_PAGE_NUM = re.compile(r"^\s*(?:第\s*)?\d{1,3}\s*(?:页|/\s*\d{1,3})?\s*$")
_COVER_HINT = ("乐凯", "培训学院", "luckeeinc", "www.")
# 承载结构信息的行：即使每页重复也不能当页眉删掉
# （每日一练的 `…----题目` / `…----解析` 会在多页重复出现，删了就丢了分节与域）
_INFORMATIVE = re.compile(r"(题目|解析|答案|第\s*\d{1,2}\s*章|【[^】]{1,40}】)")


def _is_cover(page_text: str) -> bool:
    """封面页：字极少且含机构标识（乐凯培训学院 Logo 页）

    判据是「去掉机构标识行后几乎无内容」，而不是「总字数少」——
    否则会把只有一行小标题的思维导图页/知识点首页误杀。
    """
    t = (page_text or "").strip()
    if not t:
        return True
    rest = [ln for ln in t.splitlines()
            if ln.strip() and not any(h in ln for h in _COVER_HINT)]
    return not rest or (len("".join(rest)) < 40 and any(h in t for h in _COVER_HINT))


def read_pdf(path) -> list:
    """读取 PDF 每页文本（丢封面，去页眉页脚，剔纯页码/纯项目符行）

    页眉页脚判据（**谨慎**）：只认「位于页面首尾几行、且在 >=80% 页面重复、长度 <= 40、
    不含结构信息」的行。

    为什么不用「>=50% 页面重复」：每日一练的排版是「题目段 + 解析段」，同一道题的文字
    会原样出现两次（约占页面 40~50%），用低阈值会把**题目当成页眉删掉** ——
    实测直接导致 81 份每日一练解析出 0 题。
    """
    import fitz
    doc = fitz.open(str(path))
    try:
        raw = []
        for page in doc:
            txt = page.get_text("text") or ""
            if _is_cover(txt):
                continue
            raw.append(txt)
    finally:
        doc.close()
    if not raw:
        return []

    # 只统计页面首尾若干行（页眉页脚的位置特征）
    edge = {}
    anywhere = {}
    for txt in raw:
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        for s in set(lines[:3] + lines[-2:]):
            edge[s] = edge.get(s, 0) + 1
        for s in set(lines):
            anywhere[s] = anywhere.get(s, 0) + 1
    threshold = max(2, int(len(raw) * 0.8 + 0.999))
    repeated = {ln for ln, c in edge.items()
                if c >= threshold and len(ln) <= 40
                and not _INFORMATIVE.search(ln) and not _DECK.match(ln)}
    # 页面中部重复出现的牌组页脚（如「仿真模拟（三）」）：要求至少有 5 次且占比 >=80%
    # —— 门槛设高是刻意的：每日一练的题目文字会在「题目段 + 解析段」各出现一次，
    #    低门槛会把题目本身当页眉删掉（实测曾让 81 份每日一练解析出 0 题）。
    # 牌组名（_DECK）不删：案例解析要靠它区分「模拟一 试题一」与「模拟二 试题一」。
    repeated |= {ln for ln, c in anywhere.items()
                 if c >= 5 and c >= threshold and len(ln) <= 40
                 and not _INFORMATIVE.search(ln) and not _DECK.match(ln)}

    out = []
    for txt in raw:
        lines = []
        for ln in txt.splitlines():
            s = ln.strip()
            if not s or s in repeated or _PAGE_NUM.match(s) or _BULLET_ONLY.match(s):
                continue
            lines.append(s)
        if lines:
            out.append(lines)
    return out


def flatten(pages: list) -> list:
    """页列表 → 行列表（解析器的统一输入）"""
    return [ln for page in pages for ln in page]


# ── 通用小工具 ──

_FULLWIDTH = str.maketrans({
    "（": "(", "）": ")", "，": ",", "：": ":", "；": ";",
    "．": ".", "、": ",", "？": "?", "！": "!", "“": '"', "”": '"',
})


def norm_for_hash(text: str) -> str:
    """归一化文本用于去重指纹：去空白/标点全半角差异/题号、用括号噪声"""
    s = (text or "").translate(_FULLWIDTH)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[()\[\]{}<>]", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", s)
    return s


def fingerprint(*parts) -> str:
    """内容指纹（16 位）：同题在不同资料里重复出现时用于去重"""
    joined = "|".join(norm_for_hash(p) for p in parts if p)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def file_sha1(path, block: int = 1 << 20) -> str:
    """文件内容摘要（前 16 位），用于资料归档表判重"""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(block)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]


# ── 选择题解析 ──

_ANSWER = re.compile(r"^【参考答案】\s*[：:]?\s*([A-Ea-e][A-Ea-e\s,，、]*)?")
_ANSWER_ALT = re.compile(r"^答案\s*[：:]\s*([A-Ea-e][A-Ea-e\s,，、]*)?")
# 题号/选项的分隔符。实测同一批资料里 `、` `．`（全角句点）`，` `：` `)` 都在用，
# **漏一个就会让整份资料解析为 0**：仿真模拟「选择题--带解析」用 `A．技术创新；`，
# 选项识别不到 → 75 个题块全部因「无选项」被丢弃，只留下 6 道。
_MARK_SEP = "、,，.．:：;；)）"
_Q_START = re.compile(r"^(\d{1,3})\s*[" + _MARK_SEP + r"]\s*(\S.*)$")
_OPT = re.compile(r"^([A-Ea-e])\s*[" + _MARK_SEP + r"]\s*(.*)$")
_OPT_SPACE = re.compile(r"^([A-E])\s+(\S.*)$")
_OPT_SPLIT = re.compile(r"(?=[A-E][" + _MARK_SEP + r"]\s*\S)")
_ANALYSIS = re.compile(r"^【(?:试题)?解析】\s*[：:]?\s*(.*)$")
# 无括号的解析引导语（计算专题「解题思路：」「解析：」；每日一练少量用「答案解析：」）。
# 不认这几行的话，引导语会被并进最后一个选项，后面的要点又各自另起一题 → 答案全丢。
_ANALYSIS_ALT = re.compile(r"^(?:解题思路|解题过程|思路|答案解析|试题解析|详解)\s*[：:]\s*(.*)$")
# 解析正文里的项目符号（`◆已知升级方案的EMV为90；`）与主题型题目标记共用 ◆，
# 用句末标点区分「散文要点」与「短标题」——标题里几乎不会出现句号/分号/问号。
_PROSE_HINT = re.compile(r"[。；？]")
# 仿真模拟「带解析」排版：`⚫第2题` 起题、`◼` 分隔、`答案：A` 给答案、`⚫题意解析` 收尾
_Q_MARK = re.compile(r"^[\u26ab\u25cf\u25a0\u25c6●◆]\s*第\s*(\d{1,3})\s*题\s*$")
_MARK_ANY = re.compile(r"^[\u26ab\u25cf\u25a0\u25c6●◆]")
_BANNER = re.compile(r"^[\-\u2014\u2013\s]*【([^】]{1,60})】[\-\u2014\u2013\s]*$")
_DASH_MARK = re.compile(r"[\-\u2014\u2013]{2,}")
# 分节后缀：`…--项目管理概论（上）----题目` / `----解析`（每日一练的每页标题就长这样）
_SECTION_SUFFIX = re.compile(r"[\-\u2014\u2013]{2,}\s*(题目|解析|答案|答案及解析|答案解析|试题解析)\s*$")


def _strip_dash(text: str) -> str:
    """去掉首尾装饰性横线（----第39课----案例分析---- → 第39课--案例分析）"""
    return _DASH_MARK.sub("--", (text or "").strip()).strip("-—– \t")


def _section_of(text: str):
    """判断该文本是否声明了分节 → '题目' / '解析' / None"""
    t = re.sub(r"[\s\-\u2014\u2013]+$", "", (text or "").strip())
    for tail, name in (("答案及解析", "解析"), ("答案解析", "解析"), ("试题解析", "解析"),
                       ("解析", "解析"), ("答案", "解析"), ("题目", "题目")):
        if t.endswith(tail):
            return name
    return None


def _label_of(text: str) -> str:
    """去掉分节后缀，留下标签文本（域/节名）"""
    t = (text or "").strip()
    for tail in ("答案及解析", "答案解析", "试题解析", "解析", "答案", "题目"):
        if t.endswith(tail):
            t = t[:-len(tail)]
            break
    return _strip_dash(t)


def _looks_like_section_banner(line: str):
    """横幅/分节行识别 → {"section": '题目'|'解析'|None, "label": str} 或 None

    三类实测排版：
    1. `-----------------【第1 章 信息化发展】-----------------`；
    2. `------------第1 次章节练习--第1，6~8 章--题目------------`；
    3. `2025.12.17 每日一练----项目管理概论（上）----题目`（**每页重复**，且自带分节与域）。
    """
    s = (line or "").strip()
    if not s or len(s) > 90:
        return None
    stripped = s.strip("-—– \t")
    if not stripped:
        return None
    has_rule = bool(_DASH_MARK.search(s))
    m = re.search(r"【([^】]{1,60})】(.*)$", stripped, re.S)
    if m and has_rule:
        inner = m.group(1).strip()
        tail = m.group(2).strip()
        combined = (inner + " " + tail).strip()
        return {"section": _section_of(combined) or _section_of(inner),
                "label": _label_of(inner + " " + tail)}
    if not has_rule:
        return None
    return {"section": _section_of(stripped), "label": _label_of(stripped)}


def parse_choice_lines(lines: list, meta: dict) -> dict:
    """解析选择题文本 → {"items": [...]}

    策略：状态机按「期望题号」分块；带 `【参考答案】` 的块视为完整题，
    只在「解析段」出现而题目段缺失的题号不做补偿（解析段已含题干与选项）。
    无答案的题（打印版）单独标记 answer 为空，由上层决定是否入库。
    """
    items = []
    answered = []        # 有参考答案的
    only_q = []          # 只有题目（打印版/题目段独有）
    cur = None
    expect = 1
    auto = 0             # 无题号排版（主题即一题）的自增序号
    section = "题目"
    label = ""           # 当前大节标题（如「技术管理」）
    last_domain = ""
    bad_blocks = 0

    def flush():
        nonlocal cur, bad_blocks
        if cur is None:
            return
        if not cur["question"].strip() or not cur["options"]:
            if cur["num"]:
                bad_blocks += 1
            cur = None
            return
        rec = {
            "num": cur["num"],
            "domain": cur["domain"] or last_domain or meta.get("domain") or "",
            "question": re.sub(r"\s+", " ", cur["question"]).strip(),
            "options": cur["options"],
            "answer": cur["answer"].strip().upper(),
            "analysis": cur["analysis"].strip(),
            "source_kind": meta.get("sub") or "",
            "source_file": meta.get("source_file") or "",
            "deck": meta.get("deck") or "",
            # 章节统一成考纲口径（`第12章 项目质量管理`）。**不能直接写标签原文**：
            # 横幅里的 label 常是「试题解析 软考高项教程第四版P373：…」这种整段文字，
            # 写进 chapter 会让前端章节筛选变成一堆噪声。优先级：横幅章号 → 域反查 →
            # 来源文件名的章号，保证与 domain 自洽且总能落到一个规范章节。
            "chapter": chapter_of(cur["chapter"])
                       or chapter_of(cur["domain"] or "")
                       or meta.get("chapter") or "",
        }
        # 部分排版（计算专题「带解析」）不写【参考答案】，答案藏在解析正文里
        # （`所以选择C。`）。这类题不回收就等于白丢，故做一次兜底抽取并打标，
        # 便于人工复核。
        if not rec["answer"] and rec["analysis"]:
            hit = _ANS_IN_TEXT.search(rec["analysis"])
            if hit:
                rec["answer"] = hit.group(1).upper()
                rec["answer_from_analysis"] = True
        if rec["answer"]:
            answered.append(rec)
        else:
            only_q.append(rec)
        cur = None

    def new_block(num, rest):
        nonlocal cur
        flush()
        cur = {"num": num, "question": rest, "options": [], "answer": "",
               "analysis": "", "domain": "", "chapter": label}

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # 仿真模拟/计算专题的标记行：
        #   `⚫第2题`  → 带题号起题；
        #   `⚫决策树和预期货币价值分析（风险管理）` → 主题即一题（无题号，自增）；
        #   `⚫题意解析` → 收尾装饰，跳过。
        m = _Q_MARK.match(line)
        if m:
            num = int(m.group(1))
            new_block(num, "")
            cur["domain"] = last_domain
            expect = num + 1
            continue
        # 标记行字符被两种排版共用：`⚫主题名` 是「主题即一题」，而 `◆已知…；` 是解析
        # 正文里的项目符号（计算专题「解题思路」）。只能靠上下文区分：真起新题的话，
        # 后面几行一定会出现选项；解析要点则不会。
        if _MARK_ANY.match(line):
            mark_text = line.lstrip("⚫●◆■▪▫·• ").strip()
            if mark_text and mark_text not in ("题意解析",):
                if cur is not None and cur["options"] \
                        and not _options_following(lines, raw, 0, 12) \
                        and _prose_like(mark_text):
                    # 是解析里的要点 → 收进解析，不要另起一题（否则答案整段丢失）
                    cur["analysis"] = (cur["analysis"] + " " + mark_text).strip() \
                        if cur["analysis"] else mark_text
                    continue
                auto += 1
                new_block(auto, "")
                cur["domain"] = last_domain
                cur["chapter"] = mark_text[:200]
                label = mark_text
                doms = _domains_of(mark_text)
                if doms:
                    last_domain = doms[0]
                    cur["domain"] = doms[0]
            continue
        # 牌组页脚（如「仿真模拟（三）」）直接跳过，否则会被续接到选项上
        if _DECK.match(line):
            continue

        banner = _looks_like_section_banner(line)
        if banner:
            flush()
            if banner["section"]:
                section = banner["section"]
                expect = 1
            if banner["label"]:
                label = banner["label"]
                doms = _domains_of(banner["label"])
                if doms:
                    last_domain = doms[0]
            continue

        # 参考答案 / 解析（可能在题目段缺失，故不依赖 section）
        m = _ANSWER.match(line) or _ANSWER_ALT.match(line)
        if m and cur is not None:
            cur["answer"] = (m.group(1) or "").strip()
            if not cur["domain"]:
                cur["domain"] = last_domain
            continue
        m = _ANALYSIS.match(line) or _ANALYSIS_ALT.match(line)
        if m and cur is not None:
            cur["analysis"] = m.group(1).strip()
            if not cur["domain"]:
                cur["domain"] = last_domain
            continue

        # 题号行：仅接受「期望题号」或「题号更大且后续有选项」的行，
        # 避免把解析正文里的序号（1、项目的必要性；）误判为新题
        m = _Q_START.match(line)
        if m:
            num = int(m.group(1))
            if num == expect or (num > expect and _options_following(lines, raw, num)):
                new_block(num, m.group(2).strip())
                expect = num + 1
                continue

        # 选项行：答案已出现后不再收选项 —— 解析正文里常有 "A．xxx" 这类引用，
        # 会被误当选项串进题干
        if cur is not None and not cur["answer"]:
            got = _split_option_line(line, cur["options"])
            if got:
                for letter, text in got:
                    cur["options"].append(f"{letter}. {text}")
                continue

        # 普通文本的行归属：答案之后一律进解析；否则补进末选项，再否则补进题干
        if cur is not None:
            if cur["answer"]:
                cur["analysis"] = (cur["analysis"] + " " + line).strip() \
                    if cur["analysis"] else line
            elif cur["analysis"]:
                cur["analysis"] += " " + line
            elif cur["options"]:
                cur["options"][-1] += " " + line
            else:
                cur["question"] += " " + line

    flush()

    # 合并：完整题优先；题目段独有的题（同域同号）不重复收录
    keys = {(x["domain"], x["num"]) for x in answered}
    # 必须复制：merged 与 answered 是同一个列表的话，"answered" 统计会把
    # 后并入的无答案题也数进去（曾把「75 题全无答案」误报成「75 题有答案」）
    merged = list(answered)
    missing_ans = 0
    for x in only_q:
        if (x["domain"], x["num"]) in keys:
            continue
        missing_ans += 1
        merged.append(x)

    for x in merged:
        x.pop("num", None)
        if not x["domain"]:
            x["domain"] = meta.get("domain") or ""
        x["fingerprint"] = fingerprint(x["question"], "".join(x["options"]))
    return {"items": merged, "answered": len(answered),
            "answer_missing": missing_ans, "bad_blocks": bad_blocks,
            "last_section": section}


def _split_option_line(line: str, existing: list) -> list:
    """一行拆出多个选项 → [(字母, 文本)]

    实测有两种排版：
    1. 每行一个选项：`A、项目的工期短`；
    2. 一行挤多个选项：`B、150；      C、140；      D、100；`（计算专题）。
    另外兼容 `A xxx`（字母 + 空格）写法，但**要求字母正好接在已有选项之后**
    （A→B→C→D 顺序），否则「A 公司是一家…」这类正文会被误判成选项。
    """
    m = _OPT.match(line)
    if m:
        parts = [p for p in _OPT_SPLIT.split(line) if p.strip()]
        out = []
        for p in parts:
            mm = _OPT.match(p.strip())
            if mm:
                out.append((mm.group(1).upper(), mm.group(2).strip()))
        if out:
            return out
        return [(m.group(1).upper(), m.group(2).strip())]
    m = _OPT_SPACE.match(line)
    if m and len(m.group(2)) > 1:
        letter = m.group(1).upper()
        expect_letter = chr(ord(existing[-1][0]) + 1) if existing else "A"
        if letter == expect_letter:
            return [(letter, m.group(2).strip())]
    return []


_ANS_IN_TEXT = re.compile(r"(?:故选|选择|选|答案为|答案是|答案)\s*[:：]?\s*([A-Ea-e])(?![A-Za-z0-9])")


def _options_following(lines, raw, num, lookahead: int = 8) -> bool:
    """题号不在期望位置时，看随后是否紧跟 >=2 行选项来确认它确实是题号"""
    try:
        i = lines.index(raw)
    except ValueError:
        return False
    seen = 0
    for ln in lines[i + 1:i + 1 + lookahead]:
        s = ln.strip()
        if _OPT.match(s):
            seen += 1
            if seen >= 2:
                return True
        elif _Q_START.match(s) and not _OPT.match(s):
            break
    return False


_DOMAIN_LOAD_ERR = []      # 首次导入失败的原因（只记一条，避免刷屏）


def _prose_like(text: str) -> bool:
    """该行像「解析正文」而不是「题目标题」（判据：含句末标点）"""
    return bool(_PROSE_HINT.search(text or ""))


def _domains_of(text: str) -> list:
    """调用后端考纲归一（延迟导入：tools 脚本未必总能 import app）

    失败必须**发声**：曾因为 sys.path 里没有项目根，7383 条题目的知识域全部静默写成空，
    直到抽查才发现。所以首次失败打一条 stderr 告警，并暴露 `taxonomy_check()` 给
    调用方做前置自检。
    """
    try:
        from app.domains.assessment.services.gaoxiang import normalize_domains
        return normalize_domains(text)
    except Exception as e:
        if not _DOMAIN_LOAD_ERR:
            _DOMAIN_LOAD_ERR.append("%s: %s" % (type(e).__name__, e))
            sys.stderr.write(
                "[gx_parse] 警告：考纲归一不可用，知识域将全部为空！原因：%s\n"
                "           请在项目根目录用项目 venv 运行（脚本需能 import app）。\n"
                % _DOMAIN_LOAD_ERR[0])
        return []


def taxonomy_check() -> str:
    """前置自检：返回 "" 表示考纲归一可用，否则返回失败原因

    打包/导入类脚本应在开始前调用一次并直接中止 —— 与其产出上万条空域数据，
    不如早失败。
    """
    doms = _domains_of("第12章 项目质量管理")
    if doms:
        return ""
    if _DOMAIN_LOAD_ERR:
        return _DOMAIN_LOAD_ERR[0]
    return "normalize_domains 返回空（考纲表可能被改坏）"


def chapter_of(text: str) -> str:
    """从任意文本抽出**规范**考纲章节名（如 `第12章 项目质量管理`）；抽不到返回 ""

    为什么不用原始标签：选择题的横幅会把「试题解析 软考高项教程第四版P373：…」整段
    当成 label，直接写进 chapter 会让前端章节筛选变成一堆噪声。这里统一走考纲表归一。
    """
    try:
        from app.domains.assessment.services.gaoxiang import normalize_chapter
        return normalize_chapter(text or "")
    except Exception as e:
        if not _DOMAIN_LOAD_ERR:
            _DOMAIN_LOAD_ERR.append("%s: %s" % (type(e).__name__, e))
        return _chapter_of_local(text)


_CHAP_NUM = re.compile(r"第\s*(\d{1,2})\s*章")


def _chapter_of_local(text: str) -> str:
    """考纲表不可用时的降级实现：只抽章号，不带章节名"""
    m = _CHAP_NUM.search(text or "")
    return "第%s章" % m.group(1) if m else ""


# 套卷名（仿真模拟（一、二）/ 章节练习（三）…）：同题号在不同套卷下必须区分开
_DECK_PAT = re.compile(
    r"((?:仿真模拟|每日一练|章节练习|冲刺|计算题?专题|案例分析综合|论文练习)"
    r"[^/（）()]{0,10}[（(][一二三四五六七八九十\d、,，]{1,6}[）)])")


def deck_of(text: str) -> str:
    """从文件名/标签里抽套卷名（如 `仿真模拟（四）`）；抽不到返回 "" """
    m = _DECK_PAT.search(text or "")
    return m.group(1) if m else ""


# ── 案例分析解析 ──

_CASE_MARK = re.compile(r"^[\u26ab\u25cf\u25a0\u25c6●◆]\s*(\S.*)$")
# 说明标记实测有两种括号：全角 `【说明】` 与半角 `[说明]`
_CASE_DESC = re.compile(r"^[【\[]\s*说明\s*[】\]]\s*(.*)$")
# 子问题编号实测有两种：阿拉伯（`【问题1】`）与中文（`【问题一】`），必须都认
_CASE_PROB = re.compile(r"^【问题\s*([0-9一二三四五六七八九十]{1,3})\s*】\s*(.*)$")
# 牌组名（仿真模拟一/案例分析综合二…）：同题号在不同牌组下必须区分开
_DECK = re.compile(r"^(?:仿真模拟|案例分析综合|案例综合|案例分析|章节练习|每日一练)"
                   r"\s*[（(]?\s*[一二三四五六七八九十\d]{0,3}\s*[)）]?\s*$")
_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def cn_num(text: str) -> int:
    """中文数字/阿拉伯数字 → int（'一'→1、'十'→10、'十一'→11、'二十三'→23、'7'→7）"""
    s = (text or "").strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    if "十" in s:
        tens, _, ones = s.partition("十")
        t = _CN_DIGITS.get(tens, 1) if tens else 1
        o = _CN_DIGITS.get(ones, 0) if ones else 0
        return t * 10 + o
    return 0


def _assign_decks(lines: list) -> dict:
    """给每个 ⚫ 块标记判定所属牌组（返回 {行号: 牌组名}）

    实测排版把牌组名（`仿真模拟（一）`）放在**块标记之后**的页脚位置，所以不能
    「扫到就用」—— 否则同一文件里「模拟一 试题一」与「模拟二 试题一」会撞成一块。
    规则：取「本标记之后、下一个标记之前」出现的牌组名；找不到就沿用上一个标记的。
    """
    marks = [i for i, ln in enumerate(lines) if _CASE_MARK.match(ln.strip())]
    decks = [i for i, ln in enumerate(lines) if _DECK.match(ln.strip())]
    assign = {}
    prev = ""
    for j, mi in enumerate(marks):
        nxt = marks[j + 1] if j + 1 < len(marks) else len(lines)
        found = ""
        for di in decks:
            if mi < di < nxt:
                found = lines[di].strip()
                break
        assign[mi] = found or prev
        prev = assign[mi]
    return assign


def parse_case_lines(lines: list, meta: dict, store: dict = None) -> dict:
    """解析案例分析文本 → {"items": [...]}

    块标记实测形态：
      · `⚫案例练习一----整合管理----问题解析`（`----` 分段，末段「解析/问题解析」= 答案块）；
      · `⚫试题一` / `⚫试题一----解析`（同一题号跨页重复出现，必须合并成一块）；
      · `⚫回家作业1`（纯图形作业，题干在图上，文本抽取无意义 → 无子问题时自动跳过）。

    合并规则：键取 (牌组, 题号标题, 域文本) —— **不区分题目块/答案块**，让 `【问题N】`
    的第二次出现自然切换到「填答案」模式。这样两种排版都能吃下：
      (a) 题目段在前、`----问题解析` 段在后（案例专题、仿真模拟案例）；
      (b) 题目与答案在同一块内交替（部分打印版）。

    背景取法：`【说明】` 之后、首个 `【问题N】` 之前的正文；缺 `【说明】` 时用块内
    首个 `【问题N】` 之前的全部正文（实测仿真模拟案例就没有 `【说明】`）。

    `store` 用于**跨文件**解析：部分练习把「题目」与「答案」拆成两个 PDF
    （`…回家作业5题.pdf` 与 `…回家作业5题（答案）.pdf`），两次调用共用同一块存储，
    答案文件以 `meta["is_answer_file"]=True` 传入即可正确灌入答案。
    """
    if store is None:
        store = {"blocks": {}, "order": []}
    blocks = store["blocks"]
    order = store["order"]
    cur_key = None
    deck_assign = _assign_decks(lines)
    pending = []        # 块标记**之前**的正文（实测「进度+成本计算综合」把背景放在标记前）
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue

        m = _CASE_MARK.match(line)
        if m:
            body = m.group(1).strip()
            parts = [p.strip() for p in body.split("--") if p.strip()]
            # 答案块标记：`…----问题解析` / `…----解析`（末段是解析就直接丢掉）
            is_ans_mark = False
            while parts and parts[-1] in ("解析", "问题解析", "答案解析", "试题解析"):
                parts.pop()
                is_ans_mark = True
            if not parts:
                continue
            title = parts[0]
            dom_text = " ".join(parts[1:]) if len(parts) > 1 else ""
            dom_text = re.sub(r"[（(][^）)]*[）)]", " ", dom_text).strip()
            deck = deck_assign.get(idx, "")
            # 键里剥掉括号补注（`…（2017年11月真题）` 与 `…----解析` 必须归到同一块），
            # 展示用标题保留原文
            key_title = re.sub(r"[（(][^）)]*[）)]", "", title).strip() or title
            k = (deck, key_title, dom_text)
            if k not in blocks:
                blocks[k] = {"title": title, "domain_text": dom_text, "deck": deck,
                             "background": " ".join(pending).strip(), "subs": [],
                             "marks": [], "mode": None,
                             # 源文件记在块上：跨文件配对（题目+答案）时，
                             # 条目应归属「题目」那个文件而不是最后解析的答案文件
                             "source_file": meta.get("source_file") or "",
                             "source_kind": meta.get("sub") or ""}
                order.append(k)
                pending = []
            blocks[k]["marks"].append(body)
            blk = blocks[k]
            if is_ans_mark:
                # `----解析` 段：它后面若先出现答案正文（无 `【问题N】` 引导），应按
                # 「最后一道问题」的答案收（实测仿真模拟案例就是这样：解析段的解题过
                # 程在没有题号的情况下紧跟标记，而对应的 `【问题四】` 在更后面才重述）。
                blk["_ans_section"] = True
                mx = blk.get("_max") or 0
                blk["mode"] = ("a%d" % mx) if mx else "bg"
            cur_key = k
            continue

        if _DECK.match(line):
            continue

        if cur_key is None:
            # 首个块标记之前的内容先攒着，等块建好后作为背景
            pending.append(line)
            continue
        blk = blocks[cur_key]

        m = _CASE_DESC.match(line)
        if m:
            blk["mode"] = "bg"
            txt = m.group(1).strip()
            if txt:
                blk["background"] = (blk["background"] + " " + txt).strip()
            continue

        m = _CASE_PROB.match(line)
        if m:
            num = cn_num(m.group(1))
            if not num:
                continue
            txt = m.group(2).strip()
            slot = _sub_slot(blk, num)
            max_before = blk.get("_max") or 0
            blk["_max"] = max(max_before, num)
            # 是否已进入「答案段」：三种进入方式
            #   1) 显式 `----解析` 标记（上面已置位）或跨文件解析的答案文件；
            #   2) **问题号回退** —— 答案段会把问题从「问题一」重新抄一遍，
            #      题号回退是它和「题干跨行续写」最可靠的区分信号；
            #   3) 原样重述同一问题（题号相同、文本完全一致）。
            # 不加这层判断的代价实测很直观：答案全文被当成题干续行灌进 q，
            # 仿真模拟案例 5 条题的题干里全是答案。
            ans_section = bool(blk.get("_ans_section") or meta.get("is_answer_file"))
            if not ans_section and slot["q"]:
                if num <= max_before:
                    ans_section = True
                elif txt and norm_for_hash(txt) == norm_for_hash(slot["q"]):
                    ans_section = True
            if ans_section:
                blk["_ans_section"] = True
                blk["mode"] = f"a{num}"
                blk["_answered"][num] = True
                # 解析段通常把问题原文再抄一遍当标题（`【问题一】（12分）：结合案例…`），
                # 抄写版与题干版常有括号/顿号差异，故用归一化后的**双向包含**判断，
                # 命中就不把它当答案正文，否则每条答案开头都会多一段题干。
                t = norm_for_hash(txt)
                qn = norm_for_hash(slot["q"] or "")
                an = norm_for_hash(slot["answer"] or "")
                if txt and t and t not in qn and qn not in t and t not in an:
                    slot["answer"] = (slot["answer"] + " " + txt).strip() \
                        if slot["answer"] else txt
            elif slot["q"]:
                # 题干续行（排版把问题拆成两行）
                blk["mode"] = f"q{num}"
                slot["q"] = (slot["q"] + " " + txt).strip() if txt else slot["q"]
            else:
                blk["mode"] = f"q{num}"
                slot["q"] = txt
            continue

        mode = blk["mode"]
        if mode == "bg":
            blk["background"] = (blk["background"] + " " + line).strip()
        elif mode and mode[0] == "q":
            num = int(mode[1:])
            slot = _sub_slot(blk, num)
            # 软切分排版（计算大题）：答案紧跟在题干后且没有 `----解析` 标记，
            # 靠「编号项 + 无提问动词」判断答案起点。只在 meta 显式开启时生效，
            # 避免污染有明确标记的排版（案例专题/仿真模拟案例）。
            if meta.get("soft_answer_split") and _looks_like_answer_item(slot["q"], line):
                blk["mode"] = f"a{num}"
                blk["_answered"][num] = True
                slot["answer"] = line
            else:
                slot["q"] = (slot["q"] + " " + line).strip()
        elif mode and mode[0] == "a":
            num = int(mode[1:])
            slot = _sub_slot(blk, num)
            # 解析段把问题拆两行抄写（`【问题三】（3分）：` + 下一行才是问题正文）时，
            # 【问题N】那行的 txt 为空、抄写正文本行才到 —— 此时答案还是空的，
            # 与题干重复的行不能计入答案。
            if not slot["answer"]:
                ln = norm_for_hash(line)
                qn = norm_for_hash(slot["q"] or "")
                if ln and qn and (ln in qn or qn in ln):
                    continue
            slot["answer"] = (slot["answer"] + " " + line).strip()
        elif blk["subs"]:
            pass                     # 无归属文本（页眉/装饰）丢弃
        else:
            blk["background"] = (blk["background"] + " " + line).strip()

    items = []
    for k in order:
        blk = blocks[k]
        if not blk["subs"]:
            continue                 # 无子问题（纯图形作业）→ 不可判分，不入库
        subs = []
        answered = 0
        for s in blk["subs"]:
            if s["answer"]:
                answered += 1
            subs.append({"q": s["q"], "answer": s["answer"], "points": _points_of(s["q"])})
        background = blk["background"].strip()
        if len(background) < 30:
            continue
        domain = ""
        for cand in (k[2], k[1], k[0], meta.get("source_file", "")):
            doms = _domains_of(cand)
            if doms:
                domain = doms[0]
                break
        if not domain:
            doms = _domains_of(background[:200] + " " + subs[0]["q"])
            domain = doms[0] if doms else (meta.get("domain") or "")
        items.append({
            "title": f"{k[0]} {k[1]}".strip() if k[0] else k[1],
            "domain": domain,
            "domain_text": k[2],
            # 章节与知识域必须自洽（域=资源管理 而 章节=第17章干系人管理 会让前端
            # 「按章节筛选」和「按域统计」互相矛盾），故优先用域反查章节。
            "chapter": chapter_of(domain) or chapter_of(k[2]) or meta.get("chapter") or "",
            "deck": k[0],
            "background": background,
            "sub_questions": subs,
            "answered": answered,
            "source_kind": blk.get("source_kind") or meta.get("sub") or "",
            "source_file": blk.get("source_file") or meta.get("source_file") or "",
            "raw_marks": sorted(set(blk["marks"]))[:2],
        })
    for x in items:
        x["fingerprint"] = fingerprint(x["background"],
                                       "".join(s["q"] for s in x["sub_questions"]))
    return {"items": items, "blocks": len(blocks), "store": store,
            "answered": sum(1 for x in items if x["answered"]),
            "no_answer": sum(1 for x in items if not x["answered"])}


def parse_case_files(files: list) -> dict:
    """跨文件解析案例分析（files = [(path, rel, is_answer_file), ...]）

    实测部分练习把「题目」与「答案」拆成两个 PDF。共用一个块存储、按顺序解析，
    答案文件会把答案灌进同一块；条目归属第一个（题目）文件。
    """
    store = None
    out = {"items": [], "blocks": 0}
    for path, rel, is_answer in files:
        try:
            lines = flatten(read_pdf(path))
        except Exception as e:
            return {"items": [], "blocks": 0, "error": f"读取失败：{type(e).__name__}: {e}"}
        if not lines:
            continue
        meta = {"source_file": rel, "sub": classify(rel)["sub"],
                "domain": _first_domain(rel), "chapter": chapter_of(rel),
                "deck": deck_of(rel), "is_answer_file": bool(is_answer)}
        out = parse_case_lines(lines, meta, store)
        store = out["store"]
    out.pop("store", None)
    return out


_Q_VERBS = ("请", "说明", "简述", "指出", "描述", "分析", "写出", "列出",
            "计算", "判断", "阐述", "论述", "结合", "哪些", "什么", "如何", "是否")
_ITEM_NUM = re.compile(r"^[（(]?\s*\d{1,2}\s*[)）]\s*(.*)$")


def _looks_like_answer_item(question: str, line: str) -> bool:
    """判断该行是否是「答案」的开头（仅在软切分排版下使用）

    依据：题干已攒够长度（否则首行就被误判成答案），本行是编号项（`（1）…`），
    且开头没有提问动词 —— 题干项几乎必带「请计算/请指出/说明…」。
    """
    if len((question or "").strip()) < 12:
        return False
    m = _ITEM_NUM.match((line or "").strip())
    if not m:
        return False
    body = m.group(1)
    if not body:
        return False
    return not any(v in body[:12] for v in _Q_VERBS)


def _sub_slot(blk: dict, num: int) -> dict:
    """取/建子问题槽位（问题可能跨行出现，需要按题号归并）"""
    blk.setdefault("_answered", {})
    for s in blk["subs"]:
        if s["num"] == num:
            return s
    s = {"num": num, "q": "", "answer": ""}
    blk["subs"].append(s)
    return s


_POINTS_RE = re.compile(r"[（(]\s*(\d{1,2})\s*分\s*[)）]")


def _points_of(text: str) -> int:
    m = _POINTS_RE.search(text or "")
    return int(m.group(1)) if m else 0


# ── 论文题解析 ──

_ESSAY_TITLE = re.compile(r"^题目\s*[\-\u2014\u2013]{2,}\s*(.+)$")
_ESSAY_ASK = re.compile(r"请以.+?为题")
_ESSAY_REQ = re.compile(r"^\s*(\d{1,2})\s*[、.,:]\s*(\S.*)$")


def parse_essay_lines(lines: list, meta: dict) -> dict:
    """解析论文练习题 → {"items": [...]}

    一份 PDF 一道论文题：`题目----论信息系统项目的XXX` → 背景段 → 「请以…为题，分别从以下
    三个方面进行论述：」→ 编号要求（1、2、3，可能带（1）（2）（3）子项）。
    """
    if not lines:
        return {"items": [], "reason": "空文本"}
    title = ""
    background = []
    asks = []
    seen_ask = False
    head = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not title:
            m = _ESSAY_TITLE.match(line)
            if m:
                title = m.group(1).strip()
                continue
        if _ESSAY_ASK.search(line):
            seen_ask = True
            tail = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            if tail:
                asks.append(tail)
            continue
        if seen_ask:
            asks.append(line)
        elif title:
            background.append(line)
        else:
            head.append(line)

    if not title:
        # 兜底：用文件名里的「----XXX」或首个非空行
        fname = (meta.get("source_file") or "").rsplit("/", 1)[-1]
        m = re.search(r"----\s*([^\-]{2,20})\.pdf$", fname)
        title = f"论信息系统项目的{m.group(1)}" if m else (lines[0].strip() if lines else "")

    requirements = []
    buf = None
    for line in asks:
        m = _ESSAY_REQ.match(line)
        if m:
            if buf:
                requirements.append(buf.strip())
            buf = f"{m.group(1)}、{m.group(2)}"
        elif buf is not None:
            buf += " " + line
    if buf:
        requirements.append(buf.strip())

    text = " ".join(background).strip()
    if not title or not requirements:
        return {"items": [], "reason": "标题或要求缺失（排版不符预期）"}

    doms = _domains_of((meta.get("source_file") or "") + " " + title)
    if not doms:
        doms = _domains_of(text)
    item = {
        "title": title,
        "domain": doms[0] if doms else (meta.get("domain") or ""),
        "chapter": meta.get("chapter") or chapter_of(title),
        "deck": meta.get("deck") or "",
        "background": text,
        "requirements": requirements,
        "source_kind": meta.get("sub") or "",
        "source_file": meta.get("source_file") or "",
    }
    item["fingerprint"] = fingerprint(title, text[:200])
    return {"items": [item]}


# ── 知识点解析 ──

_CH_HEAD = re.compile(r"^第\s*(\d{1,2})\s*章[\s\u3000]*(.*)$")
_SEC_HEAD = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(\S.{1,40})$")
_FILL_LINE = re.compile(r"[（(]\s*[）)]")
# 括号里已有内容（即「带答案版」的特征）；与 _FILL_LINE 互斥使用
_FILL_FILLED = re.compile(r"[（(][^）)]+[）)]")
# 合并「无答案版 + 带答案版」后，正文里两段之间的分隔标记（前端据此折叠答案）
FILL_ANS_SEP = "\n\n【答案】\n"


def parse_knowledge_lines(lines: list, meta: dict, pages: list = None) -> dict:
    """解析知识点类资料 → {"items":[{"title","content","chapter","kind"}]}

    排版差异很大，采用「标题切分 + 正文聚合」的稳妥策略：
    - 命中 `第N章 XXX` 或 `N.M 小节名` 就另起一张卡片，标题即该行；
    - 其余行归入当前卡片正文（保留换行，便于阅读）；
    - 卡片正文过短（< 20 字）的丢弃，避免产生一堆只有标题的空卡。
    填空辅助记忆清单按行拆成独立条目（每一行本身就是一条自测题）。

    `pages` 为 `read_pdf()` 的原始分页结果，只有填空清单用得上：那份资料**自带两版**
    （前几页无答案、后几页带答案），必须按页切分才能合并，靠 `lines` 分不出边界。
    不传 `pages` 时退化为旧行为（全篇按行成条），老调用方不受影响。
    """
    kind = meta.get("sub") or KN_LIST
    if kind == KN_RECITE:
        return _parse_fill(lines, meta, pages=pages)
    if kind in (KN_MINDMAP,):
        return _parse_mindmap(lines, meta)
    if kind == KN_SLIDE:
        return _parse_slide(lines, meta)

    cards = []
    title = ""
    buf = []
    chapter = ""

    def push():
        nonlocal title, buf
        content = "\n".join(buf).strip()
        # 正文要求 ≥20 个中文字：课件/表格残留的「√ / 12 / —」碎片不成卡
        if title and len(content) >= 20 and _cjk_len(content) >= 20:
            cards.append({"title": title, "content": content, "chapter": chapter})
        buf = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = _CH_HEAD.match(line)
        if m:
            push()
            chapter = _strip_dash(line)
            title = _strip_dash(line)
            continue
        m = _SEC_HEAD.match(line)
        if m and len(line) <= 40:
            push()
            title = line
            continue
        buf.append(line)
    push()

    if not cards:
        text = "\n".join(lines).strip()
        if len(text) >= 40:
            cards.append({"title": _fallback_title(meta), "content": text,
                          "chapter": chapter})

    items = []
    for c in cards:
        chunks = _split_long(c["content"], MAX_CARD_CHARS)
        for idx, chunk in enumerate(chunks, 1):
            title = c["title"] if len(chunks) == 1 else f"{c['title']}（{idx}/{len(chunks)}）"
            items.append({
                "title": title[:200],
                "summary": re.sub(r"\s+", " ", chunk)[:180],
                "content": chunk,
                "chapter": c["chapter"],
                "domain": (meta.get("domain") or ""),
                "kind": kind,
                "source_file": meta.get("source_file") or "",
            })
    for x in items:
        if not x["domain"]:
            x["domain"] = _first_domain(x["chapter"] + " " + x["title"] + " "
                                        + (meta.get("source_file") or ""))
        if not x["chapter"] and x["domain"]:
            x["chapter"] = chapter_of(x["domain"])
        x["fingerprint"] = fingerprint(x["title"], x["content"][:400])
    return {"items": items}


# 单张知识点卡片的正文上限：教材整章正文可达数万字，切成多张便于阅读与前端渲染
MAX_CARD_CHARS = 4000


def _split_long(text: str, limit: int) -> list:
    """按段落边界把超长正文切成若干块（优先在换行处切，避免截断标题与条目）"""
    text = (text or "").strip()
    if len(text) <= limit:
        return [text]
    chunks = []
    buf = ""
    for line in text.split("\n"):
        if buf and len(buf) + len(line) + 1 > limit:
            chunks.append(buf.strip())
            buf = line
        else:
            buf = (buf + "\n" + line) if buf else line
    if buf.strip():
        chunks.append(buf.strip())
    return chunks or [text]


def _fill_skel(text: str) -> str:
    """填空条目骨架：抹掉括号内容与所有标点空白，用于对齐「空版 / 答案版」同一道题

    抹掉括号内容后，两版同一道题的骨架只差 PDF 断行位置，difflib 才配得准。
    """
    s = re.sub(r"[（(][^）)]*[）)]", "", text or "")
    return re.sub(r"[\W_]+", "", s)


def fill_is_blank_item(text: str) -> bool:
    """条目是否属于「无答案版」：正文里还留着空括号 `（）`

    存量数据修复脚本（`tools/fix_gx_recite_merge.py`）用它把库里的旧行切成两版：
    它与页级判据等价 —— 带答案版的页面里一个空括号都没有，所以「含空括号」即无答案版。
    """
    return bool(_FILL_LINE.search(text or ""))


def _fill_split_pages(pages: list):
    """按页切出填空清单的两版 → (无答案版页, 带答案版页)；结构不符返回 None

    实测 32/32 份「填空辅助记忆清单」都是：前若干页无答案（整页含空括号 `（）`），
    其后是带答案版（整页不含空括号、且含带内容的括号），且进入答案版后不再回头。
    所以判据取「整页是否含空括号」——按页判比分边界干净，不会把版切错。
    """
    k = 0
    for page in pages:
        t = "\n".join(page)
        if _FILL_FILLED.search(t) and not _FILL_LINE.search(t):
            break
        k += 1
    if k == 0 or k >= len(pages):
        return None
    return pages[:k], pages[k:]


def _fill_groups(blank_items: list, ans_items: list) -> list:
    """把「空版 / 答案版」条目配对 → `[[空版条目...], 答案版条目 or None]`

    为什么不按下标硬配：两版条目顺序一致，但 PDF 断行不同会出现「空版拆成 2 条、
    答案版并成 1 条」（第 1 章「车联网的 3 层体系」就是这样），硬配会让其后条目全部错位。
    故用**骨架序列**做 difflib 对齐。

    单独抽出来是为了让存量数据修复脚本（`tools/fix_gx_recite_merge.py`）复用同一套配对规则
    —— 两处必须一致，否则「重导入」与「就地修复」会得到不同结果。
    """
    ka = [_fill_skel(x["content"]) for x in blank_items]
    kb = [_fill_skel(x["content"]) for x in ans_items]
    groups = []       # [[空版条目...], 答案版条目 or None]
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, ka, kb, autojunk=False).get_opcodes():
        if tag == "insert":                       # 答案版多出来的条目
            for j in range(j1, j2):
                groups.append([[], ans_items[j]])
            continue
        if tag == "delete":                       # 空版多出来的条目 → 并进上一条
            for i in range(i1, i2):
                if groups:
                    groups[-1][0].append(blank_items[i])
                else:
                    groups.append([[blank_items[i]], None])
            continue
        n = min(i2 - i1, j2 - j1)                 # equal / replace 里成对的部分
        for d in range(n):
            groups.append([[blank_items[i1 + d]], ans_items[j1 + d]])
        for i in range(i1 + n, i2):
            if groups:
                groups[-1][0].append(blank_items[i])
            else:
                groups.append([[blank_items[i]], None])
        for j in range(j1 + n, j2):
            groups.append([[], ans_items[j]])
    return groups


def _fill_merge(blank_items: list, ans_items: list) -> list:
    """「无答案版」与「带答案版」配对合并成一条知识点

    配对结果分三种：
    - 两版都有   → 一条，正文 = 空版 + `【答案】` + 答案版（自测与答案都不丢）
    - 只有答案版 → 一条（原样保留）
    - 只有空版   → 一条（答案版漏了它：宁可留空，也不悄悄丢内容）
    """
    merged = []
    for blanks, ans in _fill_groups(blank_items, ans_items):
        if ans is None:
            item = dict(blanks[0])
            item["content"] = "\n".join(x["content"] for x in blanks)
        elif not blanks:
            item = dict(ans)
        else:
            ask = "\n".join(x["content"] for x in blanks)
            item = dict(ans)
            item["content"] = ask + FILL_ANS_SEP + ans["content"]
            # 标题取空版：空版一定有空括号可断句，「两化融合，是指（信息化）和…」这类
            # 带答案版没有断点，会被整段当成标题
            item["title"] = blanks[0]["title"] or ans["title"]
            item["summary"] = ask[:180]
            item["has_blank"] = True
        # 正文变了必须重算指纹：否则与未合并版撞同一指纹，重导入时不会更新
        item["fingerprint"] = fingerprint(item["content"])
        merged.append(item)
    return merged


def _parse_fill(lines: list, meta: dict, pages: list = None) -> dict:
    """填空辅助记忆清单：先按句末标点把**断句碎片**合并成完整条目，再取前段作短标题

    坑 1：PDF 每个条目常被拆成 2~3 个物理行（`…其中，（）安全是一种静` / `态安全；（）安全…`），
    按行成条会产出大量半句碎片 —— 用户看到的就是「知识点页很乱」。
    标题另做裁剪（截到 `----`/`（）`/冒号前），列表才读得下去；全文仍保留在正文里。

    坑 2（2026-09-28 修）：**同一份 PDF 自带两版** —— 前几页无答案、后几页带答案。
    原先整篇按行成条，于是每个知识点落库两条：一条全是 `（）`、一条带答案；
    用户点开空的那条只看到一串空括号，反馈「空没填上」。
    修法：按页切两版 → 各自成条 → 按序配对**合并成一条**（正文 = 空版 + 【答案】 + 答案版）。
    """
    if pages and not lines:
        lines = flatten(pages)      # 只给了分页结果时兜底出行，避免落进空列表
    if pages:
        split = _fill_split_pages(pages)
        if split:
            blank_pages, ans_pages = split
            blank_items = _fill_items(flatten(blank_pages), meta)["items"]
            ans_items = _fill_items(flatten(ans_pages), meta)["items"]
            if blank_items and ans_items:
                return {"items": _fill_merge(blank_items, ans_items)}
    return _fill_items(lines, meta)


def _fill_items(lines: list, meta: dict) -> dict:
    """单版填空清单 → 条目（合并断行碎片 + 裁短标题）"""
    entries, cur, chapter = [], "", ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = _CH_HEAD.match(line)
        if m and len(line) <= 40:
            if cur:
                entries.append(cur)
                cur = ""
            chapter = _strip_dash(line)
            continue
        # 小节标题行（无填空括号、无标点、很短）→ 只作上下文，不成条目
        if (not _FILL_LINE.search(line) and len(line) <= 20
                and not re.search(r"[；。，、！？]", line)):
            if cur:
                entries.append(cur)
                cur = ""
            continue
        if not cur:
            cur = line
        elif cur[-1] in _FILL_END:
            entries.append(cur)
            cur = line
        elif _FILL_START.match(line) and _FILL_LINE.search(line) and len(line) > 10:
            entries.append(cur)     # 带序号且带填空 → 新条目
            cur = line
        else:
            cur += line            # 续行：PDF 在同一句中断行
        if cur and cur[-1] in _FILL_END:
            entries.append(cur)
            cur = ""
    if cur:
        entries.append(cur)

    items = []
    for text in entries:
        if len(text) < 8:
            continue
        items.append({
            "title": _fill_title(text),
            "summary": text[:180],
            "content": text,
            "chapter": chapter,
            "domain": meta.get("domain") or "",
            "kind": KN_RECITE,
            "has_blank": bool(_FILL_LINE.search(text)),
            "source_file": meta.get("source_file") or "",
        })
    for x in items:
        if not x["domain"]:
            x["domain"] = _first_domain(chapter + " " + (meta.get("source_file") or ""))
        if not x["chapter"] and x["domain"]:
            x["chapter"] = chapter_of(x["domain"])
        x["fingerprint"] = fingerprint(x["content"])
    return {"items": items}


_FILL_END = "；;。！？!?：:"
_FILL_START = re.compile(r"^(?:\d{1,3}\s*[、.．)）]|[（(]\s*\d{1,2}\s*[)）]|第\s*\d{1,2}\s*章)")
# 标题裁剪：在「填空提示/破折号/冒号」处断开，再去掉结尾的是/为等虚词
_FILL_CUT = re.compile(r"(?:----|——|--|[:：]|\s*[（(]\s*[）)])")
_FILL_TAIL = re.compile(r"(?:是指|指的是|包括|分别是|是|为|有)$")


def _fill_title(text: str) -> str:
    """填空条目的短标题：截到填空提示前，并去掉「是/为/包括」等结尾虚词"""
    t = _FILL_CUT.split(text or "")[0].strip(" -—·、,，。;；:")
    t = _FILL_TAIL.sub("", t).strip()
    if len(t) < 4:
        t = (text or "")[:40]
    return t[:60]


def _parse_slide(lines: list, meta: dict) -> dict:
    """课堂课件讲义：PDF 把每页文本直接抽出来，含大量页码/√ 表格碎片/重复页眉页脚

    清洗规则（这是「知识点页很乱」的另一半根因）：
    1. 纯符号行（`√ / 15~20`、`— 12 —`）丢弃；
    2. 中文字数 < 6 的行丢弃（课件里大量图注、装饰字）；
    3. 出现 ≥8 词的短行视为页眉页脚丢弃；
    4. 无 `第N章` 小节标题的整份课件合并成一张卡（标题取课次名），按 MAX_CARD_CHARS 切块。
    质量天然弱于清单/速记，故 kind 单列 `slide`，前端默认不混进主列表。
    """
    counter, chapter, title, buf, cards = {}, "", "", [], []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        counter[line] = counter.get(line, 0) + 1

    def flush():
        """收尾当前缓冲：够长就成卡（<20 字视为上一页的尾巴，并进上一张卡而不是丢掉）"""
        nonlocal buf
        body = "\n".join(buf).strip()
        buf = []
        if not body:
            return
        if _cjk_len(body) >= 20:
            cards.append({"title": title or _deck_name(meta), "body": body, "chapter": chapter})
        elif cards:
            cards[-1]["body"] += "\n" + body

    for raw in lines:
        line = raw.strip()
        if not line or _SLIDE_JUNK.match(line) or _cjk_len(line) < 6:
            continue
        if len(line) < 40 and counter.get(line, 0) >= 8:
            continue
        m = _CH_HEAD.match(line)
        if m and len(line) <= 40:
            flush()
            chapter = _slide_chapter(line)
            title, buf = _strip_dash(line), []
            continue
        buf.append(line)
    flush()

    items = []
    for c in cards:
        chunks = _split_long(c["body"], MAX_CARD_CHARS)
        for idx, chunk in enumerate(chunks, 1):
            t = c["title"] if len(chunks) == 1 else f"{c['title']}（{idx}/{len(chunks)}）"
            items.append({
                "title": t[:200],
                "summary": re.sub(r"\s+", " ", chunk)[:180],
                "content": chunk,
                # 只认卡片自己记录的章节：不能用循环末尾的 chapter 兜底（会把最后一张卡的
                # 章节套到前面所有卡上，即「第零课课件显示成第6章」的由来）
                "chapter": c.get("chapter") or "",
                "domain": meta.get("domain") or "",
                "kind": KN_SLIDE,
                "source_file": meta.get("source_file") or "",
            })
    for x in items:
        # 课件不按正文猜知识域：一页 PPT 常列出全部章节，猜出来就是噪声（宁可为空）
        if not x["domain"] and x["chapter"]:
            x["domain"] = _first_domain(x["chapter"])
        x["fingerprint"] = fingerprint(x["title"], x["content"][:400])
    return {"items": items}


_SLIDE_JUNK = re.compile(r"^[\s\d√✓✗×\-—–·、,，.。:：;；/|\\()（）\[\]【】<>《》%+*=_~\"'`]+$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _cjk_len(text: str) -> int:
    return len(_CJK_RE.findall(text or ""))


def _slide_chapter(line: str) -> str:
    """课件里的 `第N章 XXX` 只有与考纲一致时才当章节，否则留空

    坑：乐凯课件沿用自己的章号（如「第18章 职业道德规范」），直接归一会被套到考纲
    第18章「绩效域」上 → 章节筛选里一堆假命中。章号或章名对不上就宁可留空。
    """
    m = _CH_HEAD.match(line or "")
    if not m:
        return ""
    label = chapter_of(line)
    if not label:
        return ""
    no = int(m.group(1))
    name = label.split(" ", 1)[-1] if " " in label else ""
    return label if (label.startswith("第%d章" % no) and name and name in line) else ""


def _deck_name(meta: dict) -> str:
    """课件卡片标题：取课次目录名（`61. 乐凯2605软考高项--第61课--仿真模拟（六）选择题-5.16`）"""
    parts = (meta.get("source_file") or "").split("/")
    for seg in reversed(parts[:-1]):
        if re.match(r"^\d+\s*[.\s]", seg):
            return re.sub(r"^.*?--", "", seg)[:80] or seg[:80]
    fname = _fallback_title(meta)
    return fname[:80]


def _parse_mindmap(lines: list, meta: dict) -> dict:
    """思维导图：一页一小节，整页文本作为一张 ITO 卡片（顺序是排版流，保留原样）"""
    text = "\n".join(lines).strip()
    if len(text) < 20:
        return {"items": [], "reason": "导图文本过少（可能为纯图）"}
    title = lines[0].strip()[:200] if lines else _fallback_title(meta)
    domain = _first_domain(title + " " + (meta.get("source_file") or ""))
    item = {
        "title": title,
        "summary": re.sub(r"\s+", " ", text)[:180],
        "content": text,
        "chapter": title,
        "domain": domain or (meta.get("domain") or ""),
        "kind": KN_MINDMAP,
        "source_file": meta.get("source_file") or "",
    }
    item["fingerprint"] = fingerprint(title, text[:400])
    return {"items": [item]}


# 目录名 → 知识域 的补充映射：有些资料目录用的是**课程专题名**而非考纲章节名，
# 考纲表查不到就会让整批条目 domain 为空（曾致 48 条填空速记全无知识域）。
DIR_DOMAIN_HINTS = (
    ("信息系统安全管理", "信息技术发展"),   # 第四版第 2 章「信息安全」相关专题
    ("信息安全", "信息技术发展"),
)


def _first_domain(text: str) -> str:
    doms = _domains_of(text)
    if doms:
        return doms[0]
    for frag, dom in DIR_DOMAIN_HINTS:
        if frag in (text or ""):
            return dom
    return ""


def _fallback_title(meta: dict) -> str:
    fname = (meta.get("source_file") or "").rsplit("/", 1)[-1]
    return re.sub(r"\.pdf$", "", fname, flags=re.I)[:200]


# ── 统一入口 ──

def parse_file(path, rel_path: str = "") -> dict:
    """解析单个资料文件（按分类分派），返回 {"category","items","stats","error"}

    永不抛异常：解析失败以 error 字段返回，让批量导入能继续跑完并给出完整报告。
    """
    rel = rel_path or path.name
    info = classify(rel)
    meta = {
        "source_file": rel,
        "sub": info["sub"],
        "category": info["category"],
        "domain": "",
    }
    result = {"source_file": rel, "category": info["category"], "sub": info["sub"],
              "reason": info["reason"], "items": [], "stats": {}, "error": ""}
    if info["category"] == CAT_OTHER:
        result["reason"] = info["reason"] + "（仅归档）"
        return result
    try:
        pages = read_pdf(path)
    except Exception as e:
        result["error"] = f"读取失败：{type(e).__name__}: {e}"
        return result
    if not pages:
        result["error"] = "无可用文本（可能为扫描件）"
        return result
    lines = flatten(pages)

    # 文件名里的域作为兜底（章号最可靠）；套卷名单独存，用于同题号跨套卷区分
    meta["domain"] = _first_domain(rel)
    meta["chapter"] = chapter_of(rel)
    meta["deck"] = deck_of(rel)

    try:
        if info["category"] == CAT_CHOICE:
            out = parse_choice_lines(lines, meta)
            # 「计算专题」目录里混着两种排版：计算型选择题（带 A/B/C/D 选项）与
            # 计算大题（带【问题N】）。按解析结果择优，否则一种排版会被整份白丢。
            if info["sub"] == SK_CALC:
                alt = parse_case_lines(lines, dict(meta, soft_answer_split=True))
                if len(alt.get("items") or []) > len(out.get("items") or []):
                    out = alt
                    result["parser_switched"] = True
        elif info["category"] == CAT_CASE:
            out = parse_case_lines(lines, meta)
            if not out.get("items"):
                alt = parse_choice_lines(lines, meta)
                if alt.get("items"):
                    out = alt
                    result["parser_switched"] = True
        elif info["category"] == CAT_ESSAY:
            out = parse_essay_lines(lines, meta)
        else:
            out = parse_knowledge_lines(lines, meta, pages=pages)
    except Exception as e:
        result["error"] = f"解析异常：{type(e).__name__}: {e}"
        return result

    result["items"] = out.get("items") or []
    # store 是跨文件配对的中间态（体积大且不可序列化），不进统计
    result["stats"] = {k: v for k, v in out.items() if k not in ("items", "store")}
    result["stats"]["pages"] = len(pages)
    result["stats"]["items"] = len(result["items"])
    return result
