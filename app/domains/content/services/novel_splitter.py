"""小说 TXT 解析：编码探测 + 自动分章 + 流式分块

后台上传 TXT 后由本模块把纯文本解析成「章节 / 文本块」列表：

- **能分章**：识别出 `第一章 xxx` / `Chapter 1` / `卷三` / `序章` 等标题行 →
  返回 `mode='chapter'`，前端出目录、下滑按章加载。
- **不能分章**（txt 无章节标记，或标记太少/太密不像真章节）→ 返回
  `mode='stream'`，按段落聚合切成固定大小的文本块，前端下滑按块流式加载、无缝拼接。

判定保守优先：宁可判成 stream（阅读照样能下滑读完整本），也不要把正文里
偶然出现的「第一集」误判成章节，导致目录被切成几百条垃圾条目。
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── 编码探测顺序 ──
# 中文 txt 常见：UTF-8 BOM / UTF-8 / GBK(GB2312) / GB18030 / Big5。
# 逐个尝试解码，取第一个「无异常且中文占比合理」的结果；全部失败则用
# GB18030 + errors='ignore' 兜底（宁可丢个别乱码字符，也不要整个文件读不出来）。
_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "gb18030", "big5")

# ── 章节标题正则 ──
# 只匹配「整行就是标题」的情况（长度 <= 80），避免正文中的片语被误判。
# 组 1=序号（可能为空），组 2=标题正文
_CH_RE = [
    # 第X章 / 第X节 / 第X回 / 第X集 / 第X篇 / 第X部（中文或阿拉伯数字序号）
    re.compile(r'^\s*第\s*([0-9零一二三四五六七八九十百千万两]{1,12})\s*[章节節回集篇部话話]\s*'
               r'[：:、．\.·\-—\s]*(.{0,60}?)\s*$'),
    # 卷X / 第X卷（单独列，因为「卷」常与「章」混排）
    re.compile(r'^\s*(?:第)?\s*卷\s*([0-9零一二三四五六七八九十百千万两]{1,12})\s*'
               r'[：:、．\.·\-—\s]*(.{0,60}?)\s*$'),
    # Chapter 1 / CHAPTER I
    re.compile(r'^\s*(?:chapter|Chapter|CHAPTER)\s+([0-9IVXLC]{1,7})\s*'
               r'[：:、．\.·\-—\s]*(.{0,60}?)\s*$'),
    # 序章 / 楔子 / 尾声 / 后记 / 番外 / 终章 / 自序 / 序言（无序号的特殊章节）
    re.compile(r'^\s*(序章|楔子|引子|尾声|后记|番外|终章|序言|自序|开篇)\s*'
               r'[：:、．\.·\-—\s]*(.{0,60}?)\s*$'),
]

# 分章成立的下限：至少这么多条标题
_MIN_CHAPTERS = 3
# 单章平均字数下限：低于此值说明标题匹配过密（多半是误判）。
# 取 100 是为了兼容短章/段子合集类作品，再低则基本可判定为误匹配。
_MIN_AVG_WORDS = 100
# 单章平均字数上限：高于此值说明标题太少（正文里零星几个「第三章」），目录无意义
_MAX_AVG_WORDS = 100_000
# 标题行最大长度（超过就不像标题）
_MAX_TITLE_LEN = 80

# 流式分块：单块目标字数（中文按字符计）
CHUNK_SIZE = 2000
# 单块硬上限：单个超长段落切到这里也强制断开
CHUNK_HARD_MAX = 4000


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """把 TXT 原始字节解码为文本，返回 (text, encoding)。

    策略：按 _ENCODINGS 顺序尝试，用「解码成功 + 中文字符占比 > 5%」判定是否命中；
    全都不理想时，取 GB18030 + errors='ignore' 兜底。
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        # 明确 BOM：直接按 UTF-8 解，省一轮探测
        return raw.decode("utf-8-sig", errors="ignore"), "utf-8-sig"

    best = None
    for enc in _ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        ratio = _cjk_ratio(text)
        if ratio > 0.05:
            return text, enc
        # 记下第一个能解出来的，作为无中文时的候选（如纯英文 txt）
        if best is None:
            best = (text, enc)

    if best:
        return best
    # 兜底：GB18030 覆盖几乎所有中文编码，忽略个别坏字节
    return raw.decode("gb18030", errors="ignore"), "gb18030"


def _cjk_ratio(text: str) -> float:
    """中文字符占比（采样前 5000 字，避免大文件全量扫描）"""
    sample = text[:5000]
    if not sample:
        return 0.0
    cjk = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(sample)


def normalize(text: str) -> str:
    """统一换行与空白：CRLF/CR→LF，去掉行尾空格，压缩 3 连以上空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 全角空格转半角（常见于网文 txt）
    text = text.replace("\u3000", "  ")
    lines = [ln.rstrip() for ln in text.split("\n")]
    # 压掉连续空行（>2 个连续空行压成 1 个）
    out, blank = [], 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(ln)
    return "\n".join(out)


def _match_title(line: str) -> str | None:
    """一行是否像章节标题，是则返回规范化标题（含序号），否则 None。"""
    s = line.strip()
    if not s or len(s) > _MAX_TITLE_LEN:
        return None
    for rx in _RE_ALL:
        m = rx.match(s)
        if m:
            # 标题正文为空时（如裸「第一章」），就用序号补一个可读标题
            title = (m.group(2) or "").strip()
            full = m.group(0).strip()
            return full if full else title
    return None


_RE_ALL = _CH_RE


def split_chapters(text: str) -> list[tuple[str, str]] | None:
    """尝试按章节标题切分，返回 [(title, content), ...]；判定不成立时返回 None。

    判定条件（全部满足才算能分章）：
    1. 命中的标题行 >= _MIN_CHAPTERS；
    2. 平均单章字数在 [_MIN_AVG_WORDS, _MAX_AVG_WORDS] 之间；
    3. 首个标题出现在全文前 30%（否则说明前面有一大段无标题正文，目录对不上）。
    """
    lines = text.split("\n")
    hits: list[tuple[int, str]] = []  # (行号, 标题)
    for i, ln in enumerate(lines):
        t = _match_title(ln)
        if t:
            hits.append((i, t))

    if len(hits) < _MIN_CHAPTERS:
        return None

    # 首个标题之前算作「前言/序」：若占比 > 30% 认为目录不可靠
    if hits[0][0] > max(30, len(lines) * 0.3):
        return None

    total_words = sum(len(ln.strip()) for ln in lines if ln.strip())
    avg = total_words / len(hits)
    if avg < _MIN_AVG_WORDS or avg > _MAX_AVG_WORDS:
        return None

    chapters: list[tuple[str, str]] = []
    # 第一个标题之前的正文：作为「前言」附加到第一章之前（不单独成章，避免目录噪音）
    for n, (ln_no, title) in enumerate(hits):
        end = hits[n + 1][0] if n + 1 < len(hits) else len(lines)
        body = "\n".join(lines[ln_no + 1:end]).strip()
        if not body:
            # 空章（连续两个标题）：保留标题但正文留空，前端显示「（本章无内容）」
            pass
        chapters.append((title, body))

    # 过滤掉尾部全空章节（txt 末尾常有多余的标题行）
    while chapters and not chapters[-1][1]:
        chapters.pop()
    if len(chapters) < _MIN_CHAPTERS:
        return None

    # 前缀正文（首个标题之前的）并入第一章开头，避免丢内容
    head = "\n".join(lines[: hits[0][0]]).strip()
    if head and chapters:
        t0, c0 = chapters[0]
        chapters[0] = (t0, (head + "\n\n" + c0).strip())

    return chapters


def split_stream(text: str, chunk_size: int = CHUNK_SIZE) -> list[tuple[str, str]]:
    """无法分章时：按段落聚合切成固定大小文本块。返回 [(空标题, 块内容), ...]。

    切分规则以保证阅读连贯为前提：
    - 优先在段落边界（空行）断开；
    - 单段超 chunk_size 时按句子（。！？；及换行）继续切；
    - 仍超过 CHUNK_HARD_MAX 的硬切（极端长段无标点）。
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not paragraphs:
        return []

    blocks: list[str] = []
    buf = ""
    for p in paragraphs:
        # 段落本身就超大 → 先切碎再走常规聚合
        for piece in _split_long_paragraph(p, chunk_size):
            if not buf:
                buf = piece
            elif len(buf) + len(piece) + 2 <= chunk_size:
                buf = buf + "\n\n" + piece
            else:
                blocks.append(buf)
                buf = piece
    if buf:
        blocks.append(buf)
    return [("", b) for b in blocks]


def _split_long_paragraph(p: str, chunk_size: int) -> list[str]:
    """把超长段落按句子切成 <= chunk_size 的片段"""
    if len(p) <= chunk_size:
        return [p]
    if len(p) <= CHUNK_HARD_MAX and "\n" not in p:
        # 在 CHUNK_HARD_MAX 内且无换行：允许整段成块，避免把一段切得支离破碎
        return [p]

    parts: list[str] = []
    buf = ""
    # 按句末标点切（保留标点）
    for seg in re.findall(r"[^\n。！？!?；;]*[\n。！？!?；;]*", p):
        if not seg:
            continue
        if len(buf) + len(seg) <= chunk_size:
            buf += seg
        else:
            if buf:
                parts.append(buf)
            buf = seg
        # 兜底：超长无标点片段硬切
        while len(buf) > CHUNK_HARD_MAX:
            parts.append(buf[:CHUNK_HARD_MAX])
            buf = buf[CHUNK_HARD_MAX:]
    if buf:
        parts.append(buf)
    return [x for x in parts if x.strip()] or [p]


def parse_txt(raw: bytes, *, chunk_size: int = CHUNK_SIZE) -> dict:
    """TXT 解析总入口：字节 → {mode, encoding, chapters:[(title, content)], word_count}

    - mode='chapter'：自动分章成功，chapters 为章节列表；
    - mode='stream' ：未识别到可靠章节，chapters 为等大文本块（title 为空）。
    """
    text, enc = decode_bytes(raw)
    text = normalize(text)

    chapters = split_chapters(text)
    mode = "chapter" if chapters else "stream"
    if not chapters:
        chapters = split_stream(text, chunk_size)

    word_count = sum(len(c or "") for _, c in chapters)
    logger.info("[novel] 解析完成 encoding=%s mode=%s 段数=%d 字数=%d",
                enc, mode, len(chapters), word_count)
    return {
        "mode": mode,
        "encoding": enc,
        "chapters": chapters,
        "word_count": word_count,
    }
