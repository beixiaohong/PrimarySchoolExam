"""试卷题目解析器（主项目版，可被 app 任意模块/CLI 复用）

从试卷 HTML（docx 经 LibreOffice 转出的富文本）中解析出题目，并按
「大题序号 + 小题号」把『参考答案』区的内容自动关联到每道题。

解析层级：
    大题（一、二、三、...)
      └─ 小题（1. 2. 3. ... 或 （1）（2）...）
            └─ 子项（并入所属小题文本）
题型判定：
    - 含 >=2 个 A./B./C./D. 选项  -> choice（选择题）
    - 含 ____ / （ ）/ 填空 / 连线 -> fill_blank（填空/连线）
    - 其它                          -> qa（问答/书写）
答案关联：参考答案区与题目使用相同「大题+小题」编号，按 (大题序号, 小题号)
          精确匹配；单小题大题（如连线题）回退到该大题的答案块。

富文本与图片：
    - 每道题额外产出 `html`（自包含 HTML 片段，含 base64 内联图片）与
      `images`（base64 data URI 列表），满足「题目以 HTML 富文本 + base64 图片保存」。
"""
import re
import html as _html

# bs4 延迟导入：模块被 import 时不强制依赖，仅在真正解析 HTML 时才加载，
# 避免仅引用本模块（如只读题目）也拉起重依赖。
_HAS_BS4 = None


def _bs4():
    global _HAS_BS4
    if _HAS_BS4 is None:
        try:
            from bs4 import BeautifulSoup
            _HAS_BS4 = BeautifulSoup
        except Exception:  # pragma: no cover
            _HAS_BS4 = False
    return _HAS_BS4

# ---------- 正则 ----------
SECTION_RE = re.compile(r'^([一二三四五六七八九十]+)、')
# 小题号：1. / 1． / 1、 以及 （1） / (1) 全角半角括号，统一提取数字
QNUM_RE = re.compile(r'^[（(]?([0-9]{1,3})[）)\.\．、]')
OPTION_RE = re.compile(r'^[A-Da-d][\.．、]')
# 纯拼音行（仅拉丁字母/声调符/空格，无汉字）——用于净化题干
PINYIN_RE = re.compile(r'^[a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü\s]+$')
HAS_CJK = re.compile(r'[一-鿿]')
# 答案小节标题：必须是真正的「参考答案」区，避免命中题干里的
# "请将答案填在答题纸上" 等（那种会把试卷从中间错误切分、整段丢题）。
# 规则：
#   1) 含"参考答案"（题干从不会写"参考答案"）；
#   2) 整行就是"答案/答案：/【答案】"；
#   3) 整行以"答案"结尾（如"高二化学12月考试答案"），但前面不能是
#      『的/请/写/填/…』等动词介词——以此排除"请将答案填在…""本题的答案是"。
ANSWER_HEAD_RE = re.compile(
    r'参考\s*答案'
    r'|^\s*【?答\s*案】?\s*[:：]?\s*$'
    r'|^\s*.*?(?<![的请写出填写找选下上中见是于对为与和及])答\s*案\s*[】)）]?\s*$'
)
# 答案区自己的大题标题（与正文一样支持全角句号 一．）
ANSWER_SECTION_RE = re.compile(r'^([一二三四五六七八九十]+)[、．.]')
# 紧凑选择答案：1A2B3C / 1.A 2.B / （1）A —— 提取 (题号, 字母)
# 注意：不限制前导字符，以兼容『10D11D12B』这类数字紧跟字母的连写；
# 误匹配风险极低（答案区罕见『数字+ABCD』的无关文本）。
COMPACT_CHOICE_RE = re.compile(r'([0-9]{1,3})(?:\s*[\.\．、])?\s*([A-Da-d])')
BRACKET_CHOICE_RE = re.compile(r'（\s*([0-9]{1,3})\s*）\s*([A-Da-d])')
# 文本答案：17答：… / （1）要点… —— 提取 (题号, 答案文本)
TEXTANS_RE = re.compile(r'(?:^|[^0-9])([0-9]{1,3})\s*答\s*[:：]\s*(.*?)$')
TEXTANS2_RE = re.compile(r'（\s*([0-9]{1,3})\s*）\s*(.+?)$')
BASE64_IMG_RE = re.compile(r'data:image/[^"\']+?;base64,[^"\']+?', re.I)
BLOCK_TAGS = ['p', 'table', 'h1', 'h2', 'h3', 'h4', 'li', 'img', 'div']
# 用于「块级叶子」切行的标签集合
_BLOCK_SPLIT = {'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'td', 'th',
                'tr', 'table', 'article', 'section', 'br'}
_IMG_MARK = '\u0001'  # 图片块在全文归一串中的占位符，使其可被定位


def _norm(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def _html_to_lines(html_content):
    """HTML -> 去空白后的非空逻辑行列表。

    关键修复：LibreOffice 把每个文本片段包进独立 <font>/<span>，若用
    soup.get_text('\\n') 会在『每个文本节点间』插入换行，导致题号（如 '1'）
    与 '、' 被拆成两行、整张卷只认到 1 题。

    改为：按『块级叶子元素』切行——同一块内的行内片段拼接成一行，仅在
    真正的块级边界（p/div/td/li/...）处换行，从而重建出
    '1、在（ ）里填上相同的数。53–（ ）=33...' 这样的完整逻辑行。
    """
    bs4 = _bs4()
    if not bs4:
        return [l.strip() for l in html_content.split("\n") if l.strip()]
    soup = bs4(html_content, 'lxml')
    body = soup.body or soup
    # <br> 视为块内换行
    for br in body.find_all('br'):
        br.replace_with('\n')
    out = []
    for el in body.find_all(['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4',
                             'td', 'th', 'tr', 'table', 'article', 'section']):
        # 仅取叶子块：自身不含块级后代，避免嵌套重复计数
        if any(d.name in _BLOCK_SPLIT for d in el.descendants):
            continue
        txt = el.get_text('', strip=True)
        if txt:
            out.append(txt)
    return [l for l in out if l]


def _split_answer(lines):
    for i, l in enumerate(lines):
        if ANSWER_HEAD_RE.search(l):
            return lines[:i], lines[i + 1:]
    return lines, []


def _clean_pinyin(lines):
    out = []
    for l in lines:
        if PINYIN_RE.match(l) and not HAS_CJK.search(l):
            continue
        out.append(l)
    return out


def _presplit_sections(lines):
    """若某行『大题标题』与后续内容同行（如 一、1.动 快乐），拆成两行避免题号被吞。"""
    out = []
    for line in lines:
        m = SECTION_RE.match(line)
        if m and m.end() < len(line):
            out.append(line[:m.end()])
            rest = line[m.end():].strip()
            if rest:
                out.append(rest)
        else:
            out.append(line)
    return out


def _tokenize(lines):
    """行 -> 层级结构 sections。大题(一、)开新 section；小题号(1. /（1）)开新 question。"""
    lines = _presplit_sections(lines)
    sections = []
    cur_sec = None
    cur_q = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        msec = SECTION_RE.match(line)
        if msec:
            cur_sec = {'idx': len(sections) + 1, 'label': msec.group(1),
                       'questions': [], 'loose': []}
            sections.append(cur_sec)
            cur_q = None
            continue
        mq = QNUM_RE.match(line)
        if mq:
            if cur_sec is None:
                cur_sec = {'idx': 1, 'label': '', 'questions': [], 'loose': []}
                sections.append(cur_sec)
            cur_q = {'qnum': int(mq.group(1)), 'lines': [line]}
            cur_sec['questions'].append(cur_q)
            continue
        if cur_sec is None:
            continue
        if cur_q is not None:
            cur_q['lines'].append(line)
        else:
            cur_sec['loose'].append(line)
    return sections


def _extract_options(stem):
    """从题干抽取 A./B./C./D. 选项（支持同行多选项与逐行选项）。"""
    opts = []
    for line in stem.split("\n"):
        s = line.strip()
        if not s:
            continue
        for p in re.split(r'(?=[A-Da-d][\.．、])', s):
            p = p.strip()
            if OPTION_RE.match(p):
                opts.append(p)
    return opts


def _classify(stem):
    opts = _extract_options(stem)
    if len(opts) >= 2:
        return 'choice', opts
    if re.search(r'_{2,}|（\s*）|填空|连线|选词|（\s*）\s*里|（\s*）\s*中', stem):
        return 'fill_blank', None
    return 'qa', None


def _join_answer(lines):
    if not lines:
        return None
    txt = "\n".join(lines).strip()
    txt = re.sub(r'^\d{1,3}[\.\．、]\s*', '', txt)
    return txt or None


def _attach_rich_html(html_content, questions):
    """为每道题附加 html 片段与 base64 图片列表。

    采用『文档顺序区间』：定位题干文本在全文归一串中的起始位置，取从本题
    起始块到下一题起始块之间的所有块（含图片块），从而把题干与相邻的配图
    一起归入该题；图片块用占位符参与定位，避免漏图。
    """
    if not _bs4() or not html_content:
        for q in questions:
            q['html'] = "<p>%s</p>" % _html.escape(q['text'])
            q['images'] = []
        return

    try:
        soup = _bs4()(html_content, 'lxml')
        body = soup.body or soup
        blocks = []
        spans = []
        cursor = 0
        for el in body.find_all(BLOCK_TAGS):
            bhtml = str(el)
            btext = el.get_text(' ', strip=True)
            imgs = BASE64_IMG_RE.findall(bhtml)
            if btext:
                norm = _norm(btext)
            elif imgs:
                norm = _IMG_MARK
            else:
                continue
            blocks.append({'html': bhtml, 'text': norm, 'imgs': imgs})
            spans.append((cursor, cursor + len(norm)))
            cursor += len(norm) + 1
        full_norm = ' '.join(b['text'] for b in blocks)

        for qi, q in enumerate(questions):
            qtext = _norm(q['text'])
            start = full_norm.find(qtext)
            if start < 0:
                q['html'] = "<p>%s</p>" % _html.escape(q['text'])
                q['images'] = []
                continue
            # 本题起始块索引
            si = 0
            for i, (s, e) in enumerate(spans):
                if s <= start < e or (s == e and s <= start):
                    si = i
                    break
            # 下一题起始块索引（作为本题终点）
            ei = len(blocks)
            if qi + 1 < len(questions):
                nq = _norm(questions[qi + 1]['text'])
                ns = full_norm.find(nq)
                if ns > start:
                    for i, (s, e) in enumerate(spans):
                        if s <= ns < e or (s == e and s <= ns):
                            ei = i
                            break
            sel = blocks[si:ei] if ei > si else blocks[si:si + 1]
            q['html'] = "".join(b['html'] for b in sel)
            imgs = []
            for b in sel:
                imgs.extend(b['imgs'])
            q['images'] = imgs
    except Exception:
        for q in questions:
            q['html'] = "<p>%s</p>" % _html.escape(q['text'])
            q['images'] = []


def _extract_compact_answers(answer_block):
    """从答案区行列表提取 (大题序号, 小题号) -> 字母/文本 的映射（兜底增强）。

    兼容：
      - 紧凑选择答案 '选择题：1A2B3C4D…24B'、'1.A 2.B'、'（1）A'
      - 文本答案 '17答：…'、'（1）要点…'
    大题序号随答案区的『一．/一、』递增；无标题内容归入第 1 大题。
    仅在结构化 ans_exact 缺失时作为兜底，绝不覆盖已正确匹配的答案。
    """
    ans_choice = {}
    ans_text = {}
    cur_sec = 0
    if not answer_block:
        return ans_choice, ans_text
    for raw in answer_block:
        line = raw.strip()
        if not line:
            continue
        msec = ANSWER_SECTION_RE.match(line)
        if msec:
            cur_sec += 1
            rest = line[msec.end():]
            for num, letter in COMPACT_CHOICE_RE.findall(rest):
                ans_choice[(cur_sec, int(num))] = letter.upper()
            continue
        sec = cur_sec if cur_sec >= 1 else 1
        for num, letter in COMPACT_CHOICE_RE.findall(line):
            ans_choice[(sec, int(num))] = letter.upper()
        for num, letter in BRACKET_CHOICE_RE.findall(line):
            ans_choice[(sec, int(num))] = letter.upper()
        for num, txt in TEXTANS_RE.findall(line):
            ans_text[(sec, int(num))] = txt.strip()
        for num, txt in TEXTANS2_RE.findall(line):
            ans_text.setdefault((sec, int(num)), txt.strip())
    return ans_choice, ans_text


def parse_paper(html_content):
    """解析一份试卷 HTML。

    返回 (questions, answers_text)
      questions: [ {section, section_idx, qnum, type, text, options(list|None),
                     answer, html, images(list)} ]
      answers_text: 整段参考答案原文
    """
    if not html_content:
        return [], None
    lines = _html_to_lines(html_content)
    body, answer_block = _split_answer(lines)
    body_secs = _tokenize(body)
    ans_secs = _tokenize(answer_block) if answer_block else []

    # 建立答案索引
    ans_exact = {}
    ans_loose = {}
    for sec in ans_secs:
        for q in sec['questions']:
            ans_exact[(sec['idx'], q['qnum'])] = _join_answer(q['lines'])
        if sec['loose']:
            ans_loose[sec['idx']] = "\n".join(sec['loose']).strip()

    # 紧凑答案扫描：从答案区直接按 (大题, 小题) 提取选择字母与文本答案，
    # 兼容『选择题：1A2B3C…』『（1）A』『17答：…』等连写/错位格式。
    ans_choice, ans_text = _extract_compact_answers(answer_block)
    # 扁平答案区（无大题标题）按全局题号兜底，兼容正文大题序号与答案区不对齐的情况
    ans_choice_global = {num: letter for (_s, num), letter in ans_choice.items()}

    questions = []
    for sec in body_secs:
        qs = sec['questions']
        if not qs and sec['loose']:
            qs = [{'qnum': 0, 'lines': sec['loose']}]
        qcount = len(qs)
        for q in qs:
            stem_lines = _clean_pinyin(q['lines'])
            stem = "\n".join(stem_lines).strip()
            if not stem:
                continue
            qtype, options = _classify(stem)
            # 选择题优先用紧凑扫描（避免『1A2B3C』被整串挂到第1题）
            if qtype == 'choice':
                ans = (ans_choice.get((sec['idx'], q['qnum']))
                       or ans_choice_global.get(q['qnum'])
                       or ans_exact.get((sec['idx'], q['qnum'])))
            else:
                ans = ans_exact.get((sec['idx'], q['qnum'])) or ans_text.get((sec['idx'], q['qnum']))
            if ans is None and qcount == 1:
                ans = ans_loose.get(sec['idx'])
            questions.append({
                'section': sec['label'],
                'section_idx': sec['idx'],
                'qnum': q['qnum'],
                'type': qtype,
                'text': stem,
                'options': options,           # list 或 None
                'answer': ans,
                'html': '',
                'images': [],
            })

    _attach_rich_html(html_content, questions)

    answers_text = "\n".join(answer_block).strip() if answer_block else None
    return questions, answers_text


if __name__ == "__main__":
    import sqlite3
    from app.config import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT id, html_content FROM papers WHERE html_content IS NOT NULL LIMIT 1").fetchone()
    conn.close()
    if row:
        qs, ans = parse_paper(row[1])
        print(f"试卷 {row[0]} 解析出 {len(qs)} 道题，参考答案长度 {len(ans) if ans else 0}")
        for q in qs[:5]:
            print(f"  [{q['type']}] {q['section']}-{q['qnum']}: {q['text'][:40]!r} | 图={len(q['images'])}")
