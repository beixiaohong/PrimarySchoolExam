"""试卷题目解析器（主项目版，可被 app 任意模块/CLI 复用）

从试卷 HTML（docx 经 LibreOffice 转出的富文本）中解析出题目，并按
「大题序号 + 小题号」把『参考答案』区的内容自动关联到每道题。

解析层级：
    大题（一、二、三、...)
      └─ 小题（1. 2. 3. ...)
            └─ 子项（（1）（2）...，并入所属小题文本）
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
QNUM_RE = re.compile(r'^([0-9]{1,3})[\.\．、]')
OPTION_RE = re.compile(r'^[A-Da-d][\.．、]')
# 纯拼音行（仅拉丁字母/声调符/空格，无汉字）——用于净化题干
PINYIN_RE = re.compile(r'^[a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü\s]+$')
HAS_CJK = re.compile(r'[一-鿿]')
ANSWER_HEAD_RE = re.compile(r'参考答案|答\s*案')
BASE64_IMG_RE = re.compile(r'data:image/[^"\']+?;base64,[^"\']+?', re.I)
BLOCK_TAGS = ['p', 'table', 'h1', 'h2', 'h3', 'h4', 'li', 'img']


def _norm(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def _html_to_lines(html_content):
    """HTML -> 去空白后的非空行列表。"""
    bs4 = _bs4()
    if not bs4:
        return [l.strip() for l in html_content.split("\n") if l.strip()]
    soup = bs4(html_content, 'lxml')
    text = soup.get_text("\n")
    return [l.strip() for l in text.split("\n") if l.strip()]


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
    """行 -> 层级结构 sections。大题(一、)开新 section；小题号(1.)开新 question。"""
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
    if re.search(r'_{2,}|（\s*）|填空|连线|选词', stem):
        return 'fill_blank', None
    return 'qa', None


def _join_answer(lines):
    if not lines:
        return None
    txt = "\n".join(lines).strip()
    txt = re.sub(r'^\d{1,3}[\.\．、]\s*', '', txt)
    return txt or None


def _attach_rich_html(html_content, questions):
    """为每道题附加 html 片段与 base64 图片列表（通过块级对齐实现）。"""
    if not _bs4() or not html_content:
        for q in questions:
            q['html'] = "<p>%s</p>" % _html.escape(q['text'])
            q['images'] = []
        return

    try:
        soup = _bs4()(html_content, 'lxml')
        body = soup.body or soup
        blocks = []
        for el in body.find_all(BLOCK_TAGS):
            bhtml = str(el)
            blocks.append({
                'html': bhtml,
                'text': el.get_text(' ', strip=True),
                'imgs': BASE64_IMG_RE.findall(bhtml),
            })
        full_norm = _norm("\n".join(b['text'] for b in blocks))
        for q in questions:
            qtext = _norm(q['text'])
            start = full_norm.find(qtext)
            if start < 0:
                q['html'] = "<p>%s</p>" % _html.escape(q['text'])
                q['images'] = []
                continue
            end = start + len(qtext)
            pos = 0
            sel = []
            for b in blocks:
                seg = _norm(b['text'])
                seg_start = pos
                seg_end = pos + len(seg)
                if seg_end > start and seg_start < end:
                    sel.append(b)
                pos = seg_end + 1
                if seg_start > end:
                    break
            if not sel:
                sel = [b for b in blocks if qtext in _norm(b['text'])]
            if sel:
                q['html'] = "".join(b['html'] for b in sel)
                imgs = []
                for b in sel:
                    imgs.extend(b['imgs'])
                q['images'] = imgs
            else:
                q['html'] = "<p>%s</p>" % _html.escape(q['text'])
                q['images'] = []
    except Exception:
        for q in questions:
            q['html'] = "<p>%s</p>" % _html.escape(q['text'])
            q['images'] = []


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
            ans = ans_exact.get((sec['idx'], q['qnum']))
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
