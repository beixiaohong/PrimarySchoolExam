#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""高项「知识点清单」PDF 的排版还原：按缩进坐标重建层级树，输出带层级的正文。

背景
----
`tools/gx_parse.py::read_pdf()` 用 `page.get_text("text")` 抽取正文，得到的是
「主题----子项----描述」用横线连起来的**扁平字符串**：层级信息在入库那一刻就丢了，
前端只能把整页糊成一大段（2026-09-29 用户反馈「完全不可用」）。

PDF 里真正的层级是**缩进**。实测同一父节点下的兄弟项，左边界 x0 几乎相同
（直接附加存储DAS=164.0 / 网络附加存储NAS=162.9，差 1.1pt），而不同层级之间
相差 60pt 以上（3种数据结构模型=143.0 / 层次模型（树结构）=264.4）。

因此本模块：
1. 用 fitz 的 `rawdict` 拿到**每个字符的精确 x0**（项目已依赖 PyMuPDF，不引入新包）；
2. 一行按 `----` 切成若干段，段 x0 = 段首字符的真实坐标；
3. 用**单调栈**建树：x0 相近（<= 兄弟容差）视为兄弟，x0 明显偏左则回退到父级。

产出的正文形如::

    网络存储3种技术
      • 直接附加存储DAS
        无需网络、直连、很难扩展、处理和传输能力低、无存储操作系统；
      • 网络附加存储NAS
        需要网络、网络连接、扩展性强、共享存取、提供文件系统功能；

两级缩进 = 一级层级，`•/◦/▪` 表示第 1/2/3 级，描述不加符号、比所属术语再深一级。

用法::

    from tools.gx_pdf_tree import pdf_pages_text
    texts = pdf_pages_text(pdf_path)      # {页码: 该页的层级文本}
"""
import re
from pathlib import Path

import fitz

# ── 可调参数（实测标定，一般不用改）───────────────────────────────────────
SIB_TOL = 12.0      # 兄弟判定容差：x0 差 <= 该值视为同级（实测同级差 < 10pt）
CONT_GAP = 32.0     # 与上一行的 y 间距 <= 该值才算续行（实测行距 26pt）
MERGE_GAP = 12.0    # y 间距 <= 该值的视觉行合并成一行（把上标吸回正文）
DASH_MIN = 2        # 连续几个横线算层级分隔符
GAP_RATIO = 0.25    # 行内相邻字符间距 > 字号 * 该值 → 补一个空格
NOISE_LEN = 4       # 整行（含横线）文本长度 <= 该值 → 视为上标/页码噪声丢弃
HEADER_Y = 36.0     # y0 小于该值且像「第N章」→ 页眉
FOOTER_MARGIN = 40.0  # 距页底小于该值的短行 → 页码

MARKERS = ("•", "◦", "▪")   # 第 1/2/3 级的条目符号
INDENT = "  "               # 一级缩进

_DASH_RE = re.compile(r"[-—]{%d,}" % DASH_MIN)
_DASH_CHARS = set("-—")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HEADER_RE = re.compile(r"^第\s*\d{1,2}\s*章")


def _is_desc(text: str) -> bool:
    """判断一段更像「描述」还是「术语」。

    PDF 里术语短、不带句读；描述长或带句末标点。判据偏保守：宁可把长术语
    误判成描述（少一层嵌套），也不要把描述当成术语（多出一个莫名其妙的层级）。
    """
    if len(text) >= 18:
        return True
    if re.search(r"[。；：]$", text):
        return True
    if text.count("、") + text.count(",") + text.count("，") >= 2:
        return True
    return False


class Node:
    """层级树节点。level=-1 表示虚拟根。"""

    __slots__ = ("text", "desc", "children", "level", "pno", "_x0")

    def __init__(self, text, level, pno):
        self.text = text
        self.level = level
        self.pno = pno
        self.desc = ""
        self.children = []
        self._x0 = -1e9        # 虚拟根没有坐标，取负无穷保证任何段都不会与它判兄弟

    def is_root(self):
        return self.level < 0


def _row_from_lines(lines, min_size=None):
    """把若干 fitz 视觉行合并后拆成「是否含分隔符 + [(x0, 文本), ...]」。

    `lines` 通常是「同一视觉行 + 它的上标/下标」：fitz 按 baseline 分行，
    `Km²` 的 2、`Gb·s⁻¹` 的 -1 会单独成行，把一整句劈成两段，
    后半段因为没有 `----` 前缀就被当成上一条的描述，层级全乱。

    返回 (y0, raw, has_dash, segs, avg_size)；无有效内容时返回 None。

    注意：只有**连续 >= DASH_MIN 个**横线才算分隔符。上标/负号常带单个 `-`
    （如 `b.s -1`），单个横线切开会把描述切碎。
    """
    chars = []
    y_top = None
    for line in lines:
        bbox = line.get("bbox") or (0, 0, 0, 0)
        y_top = bbox[1] if y_top is None else min(y_top, bbox[1])
        for span in line.get("spans", ()):
            size = span.get("size") or 10.0
            if min_size and size < min_size:
                continue
            for ch in span.get("chars", ()):
                c = ch.get("c")
                if not c or not c.strip():
                    continue
                cb = ch.get("bbox") or (0, 0, 0, 0)
                chars.append((cb[0], cb[2], size, c))
    if not chars:
        return None
    chars.sort(key=lambda t: t[0])

    # 拼整行文本：相邻字符间距过大 → 补空格（PDF 用坐标而非空格表示词距）
    buf = []
    prev_x1 = None
    for x0, x1, size, c in chars:
        if prev_x1 is not None and x0 - prev_x1 > size * GAP_RATIO:
            buf.append((" ", x0))
        buf.append((c, x0))
        prev_x1 = x1
    raw = "".join(t for t, _ in buf).strip()
    if not raw:
        return None

    # 先定位「连续横线」区间，再按区间切段
    seps = []
    i = 0
    while i < len(buf):
        if buf[i][0] in _DASH_CHARS:
            j = i
            while j < len(buf) and buf[j][0] in _DASH_CHARS:
                j += 1
            if j - i >= DASH_MIN:
                seps.append((i, j))
            i = j
        else:
            i += 1

    segs = []
    start = 0
    for a, b in seps:
        txt = "".join(t for t, _ in buf[start:a]).strip()
        if txt:
            segs.append((buf[start][1], txt))
        start = b
    txt = "".join(t for t, _ in buf[start:]).strip()
    if txt:
        segs.append((buf[start][1], txt))

    avg_size = sum(c[2] for c in chars) / len(chars)
    return y_top or 0.0, raw, bool(seps), segs, avg_size


def page_rows(page):
    """取一页的视觉行，已过滤页眉/页码噪声。返回 [(y0, raw, has_dash, segs, size)]。

    行 = 若干个 y 相近的 fitz 视觉行合并而成（含上标/下标，见 `_row_from_lines`）。
    """
    height = page.rect.height

    # 收集所有视觉行，按 y 聚类：上标/下标的 baseline 与正文只差几 pt，
    # 必须吸回同一行，否则一整句会被劈成两段（后半段因为没有 `----` 前缀
    # 会被当成上一条的描述，层级全乱）。
    lines = []
    for block in page.get_text("rawdict").get("blocks", ()):
        if block.get("type") != 0:          # 0 = 文本块，1 = 图片块
            continue
        for line in block.get("lines", ()):
            lines.append(line)
    if not lines:
        return []
    lines.sort(key=lambda l: (l.get("bbox") or (0, 0, 0, 0))[1])

    groups = []
    for line in lines:
        y0 = (line.get("bbox") or (0, 0, 0, 0))[1]
        if groups and y0 - groups[-1][0] <= MERGE_GAP:
            groups[-1][1].append(line)
        else:
            groups.append((y0, [line]))

    rows = []
    for y0, ls in groups:
        got = _row_from_lines(ls)
        if not got:
            continue
        _y, raw, has_dash, segs, size = got
        if len(raw) <= NOISE_LEN:               # 过短（页码、孤立数字）
            continue
        if y0 < HEADER_Y and _HEADER_RE.match(raw):
            continue
        if y0 > height - FOOTER_MARGIN and not _CJK_RE.search(raw):
            continue
        rows.append((y0, raw, has_dash, segs, size))
    rows.sort(key=lambda r: r[0])
    return rows


def build_tree(rows, pno=None):
    """用单调栈把行序列建成层级树。

    每次调用处理**一页**：层级栈不跨页。原因有两个：
    - 每页的缩进列是独立排版的，跨页比较会把封面标题（居中，x0 偏大）
      之类的噪声当成兄弟，进而把正经主题弹到根层；
    - 入库粒度本来就是「每页一张卡片」，按页建树与之一致，回填不会错位。
    """
    root = Node("", -1, None)
    stack = [root]
    last = root
    last_y = None

    for _idx, (y0, raw, has_dash, segs, _size) in enumerate(rows):
        # 续行判定：紧接上一行（行距实测约 26pt）且没有回退（跨页时 y 会变小）。
        # 跨卡片/跨页的标题行间距很大，必须识别成新条目，否则会被吞成上一条的描述。
        cont = last_y is not None and 0 <= y0 - last_y <= CONT_GAP

        # 无分隔符的续行 = 上一个术语的描述（PDF 里描述换行后与术语同缩进）
        if not has_dash and cont:
            text = raw.strip()
            if text and not last.is_root():
                last.desc = (last.desc + " " + text).strip()
            last_y = y0
            continue
        last_y = y0

        n = len(segs)
        for i, (x0, text) in enumerate(segs):
            if not text:
                continue
            # 行末段且像描述 → 归入上一个节点的描述，不建节点
            if i == n - 1 and n > 1 and _is_desc(text):
                if not last.is_root():
                    last.desc = (last.desc + " " + text).strip()
                continue

            # 单调栈定层级。两级判断，缺一不可：
            #   1) x0 明显偏左 → 一定是上级，回退；
            #   2) 与栈顶同级、或**与父节点已有的兄弟同级** → 也是同级，回退一级。
            # 第 2 条是关键：PDF 有排版噪声，同级兄弟的 x0 并不严格相等
            # （OSI 七层里「数据链路层」212.2 就比其它层的 235.4 偏左 23pt），
            # 只跟栈顶比会把后续兄弟误判成上一项的子级。
            while len(stack) > 1 and x0 < stack[-1]._x0 - SIB_TOL:
                stack.pop()
            if len(stack) > 1:
                parent = stack[-2]
                if abs(x0 - stack[-1]._x0) <= SIB_TOL:
                    stack.pop()
                elif any(abs(x0 - s._x0) <= SIB_TOL
                         for s in parent.children if s is not stack[-1]):
                    stack.pop()
            node = Node(text, len(stack) - 1, pno)
            node._x0 = x0
            stack[-1].children.append(node)
            stack.append(node)
            last = node

    return root


def node_lines(node, out):
    """把树拍平成 [(level, 文本, 是否描述)]，供渲染使用。"""
    if node.is_root():
        for ch in node.children:
            node_lines(ch, out)
        return
    out.append((node.level, node.text, False))
    if node.desc:
        out.append((node.level + 1, node.desc, True))
    for ch in node.children:
        node_lines(ch, out)


def render_lines(lines):
    """[(level, text, is_desc)] → 缩进文本。"""
    buf = []
    for level, text, is_desc in lines:
        pad = INDENT * level
        if is_desc:
            buf.append(pad + text)
        elif level > 0:
            buf.append(pad + MARKERS[min(level - 1, len(MARKERS) - 1)] + " " + text)
        else:
            buf.append(text)
    return "\n".join(buf)


def pdf_page_trees(pdf_path):
    """重解析一份 PDF，返回 [(页码, 该页的顶层节点列表)]。

    与 `gx_parse` 现有「每页一张卡片」的粒度对齐，便于按页回填。
    """
    pdf_path = Path(pdf_path)
    out = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc, 1):
            rows = page_rows(page)
            if not rows:
                continue
            root = build_tree(rows, pno=i)
            if root.children:
                out.append((i, root.children))
    return out


def pdf_pages_text(pdf_path):
    """重解析一份知识点清单 PDF，返回 {页码(从1开始): 该页的层级文本}。"""
    pages = {}
    for pno, tops in pdf_page_trees(pdf_path):
        out = []
        for top in tops:
            node_lines(top, out)
        if out:
            pages[pno] = render_lines(out)
    return pages


def pdf_full_text(pdf_path):
    """整份 PDF 的层级文本（不分页），用于快速预览效果。"""
    chunks = []
    for _pno, tops in pdf_page_trees(pdf_path):
        out = []
        for top in tops:
            node_lines(top, out)
        if out:
            chunks.append(render_lines(out))
    return "\n".join(chunks)
