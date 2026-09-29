#!/usr/bin/env python
"""高项知识点清单：按 PDF 真实排版重解析正文，产出离线回填补丁（不连数据库）

背景
----
知识点清单 PDF 用 `----` 表示层级（「主题----术语----描述」），而 `gx_parse` 是按行
平铺的，层级信息在入库那一刻就丢了 —— 线上正文是一整坨连写的句子，没法读。

`gx_pdf_tree` 能从 PDF 坐标还原出层级树，但还原后的**行**与线上**卡片**不是一一对应
（实测 36 份资料没有一份是「一页一张卡」，130 页 vs 102 卡这种是常态）。所以本工具
先做对齐，再产出补丁。

对齐为什么用「字符多重集重合度」
--------------------------------
新旧正文的差异只在三处：删掉 `----`、加缩进空格、加项目符号 `•`。按「只保留中日韩
文字与字母数字」归一化后，两边的字符**多重集几乎完全相同** —— 所以集合重合度既是
极好的判据，又天然免疫「一行拆成多行 / 多行并成一行」。

只靠重合度会张冠李戴（同章节不同页的内容本来就相似），所以再叠一层约束：卡片与页
都是按资料顺序排列的，用**单调 DP** 把页序列切成若干连续段分配给各卡片，最大化总
重合度。这样既不会跳页，也不会把顺序搞反。

用法
----
    # 全量生成补丁（只写文件，不连库）
    .venv/Scripts/python.exe tools/gx_rebuild_list.py

    # 只跑一份做抽查
    .venv/Scripts/python.exe tools/gx_rebuild_list.py --only 第2章

产出
----
`data/gx_content_patch.json`：每条记录带 `old_fingerprint`（线上行的身份）与重解析后的
`content`/`summary`/`fingerprint`。**线上不重新导入，只按指纹就地更新**，因此不会多出
或丢失卡片，已读记录（`gx_knowledge_reads`）也不会断链。

安全边界
--------
- 对齐分数过低或新正文明显变短的卡片一律**跳过不写补丁**（宁可留旧内容，也不能把
  正文改没）。
- 本工具只读 PDF、只写 JSON，全程不连数据库 —— 与 `gx_pack.py` 同一套分工。
"""
import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_sibling(name):
    """tools/ 不是 package，按路径加载同级模块（与 gx_pack.py 同一手法）"""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, name + ".py")
    spec = importlib.util.spec_from_file_location("_gx_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


gx = _load_sibling("gx_parse")
tree = _load_sibling("gx_pdf_tree")
fitz = tree.fitz

DEFAULT_ROOT = os.path.join("temp", "软考【高项】2026年5月班备考资料")
DEFAULT_OUT = os.path.join("data", "gx_content_patch.json")

# 一张卡片最多吃掉几页的**下限**。真正用多少页是算出来的：
# 有的资料整份只切出 1~2 张卡（如第25课 16 页 → 2 卡），固定上限会让第一张卡
# 吃不下后面几页，于是「对齐分数过低」被整份跳过。所以按 页数/卡数 动态放宽。
MAX_SPAN = 4
# 对齐分数下限：低于此值说明卡片与页根本不是同一段内容，跳过不回填。
MIN_SCORE = 0.45
# 新正文归一化长度至少要有旧正文的这个比例，否则判定为「内容被截掉」，跳过。
MIN_KEEP = 0.5


# ── 归一化与相似度 ──────────────────────────────────────────────────────

# 正文页判据：本工具的目标是还原 `----` 表达的层级，封面、目录、版尾这些页里
# 根本没有层级符，让它们参与对齐只会把水印文字灌进正文（实测封面卡对齐分数仅
# 0.46，正文页都是 1.0）。没有层级符的页一律不参与，留着旧内容更安全。
BODY_RE = re.compile(r"[-—]{2,}")

def norm_chars(text):
    """只保留中日韩文字与字母数字 —— `----`、缩进空格、`•` 全部消失，新旧两侧可比"""
    return [c for c in (text or "")
            if c.isalnum() or "\u4e00" <= c <= "\u9fff"]


def char_counter(text):
    return Counter(norm_chars(text))


def overlap_score(a, b):
    """多重集 Jaccard：交集计数 / 并集计数。

    用多重集而不是集合，是为了让「同一个字出现 5 次 vs 3 次」这种长度差异也计入，
    避免长段落靠字表重合骗到高分。
    """
    if not a or not b:
        return 0.0
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / union if union else 0.0


# ── 单调 DP 对齐 ────────────────────────────────────────────────────────

def span_for(n_pages, n_cards):
    """单张卡允许的页数上限：页数/卡数 再加 2 页余量，至少 MAX_SPAN。

    130 页 102 卡 → 4（对齐快）；10 页 1 卡 → 12（否则那张卡吃不下整份）。
    """
    if n_cards <= 0:
        return MAX_SPAN
    import math
    return max(MAX_SPAN, int(math.ceil(n_pages / n_cards)) + 2)


def align(cards, pages, max_span=MAX_SPAN):
    """把按资料顺序排好的页分给按顺序排好的卡片。

    `cards`/`pages` 均为归一化后的 Counter 列表（顺序即资料顺序）。
    返回 (分段, 各卡分数)：分段元素为 (lo, hi) 半开区间，表示第 i 张卡吃掉
    pages[lo:hi]；空段 (j, j) 表示该卡没分到页。
    """
    max_span = max(1, int(max_span))
    n, m = len(cards), len(pages)
    # 段计数器缓存：seg[j][k] = pages[j-k:j] 合并后的 Counter
    seg = [[Counter() for _ in range(max_span + 1)] for _ in range(m + 1)]
    for j in range(1, m + 1):
        seg[j][0] = Counter()
        acc = Counter()
        for k in range(1, max_span + 1):
            idx = j - k
            if idx < 0:
                break
            acc = acc + pages[idx]
            seg[j][k] = acc

    NEG = float("-inf")
    # dp[i][j]：前 i 张卡用掉前 j 页的最大总分
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    choice = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(0, m + 1):
            best, bestk = NEG, 0
            for k in range(0, min(max_span, j) + 1):
                prev = dp[i - 1][j - k]
                if prev == NEG:
                    continue
                s = overlap_score(cards[i - 1], seg[j][k]) if k else 0.0
                if prev + s > best:
                    best, bestk = prev + s, k
            dp[i][j] = best
            choice[i][j] = bestk
    # 末段：优先把页**全部用完**。
    # 不能像常规 LCS 那样「剩下的页没人吃也行」——多重集 Jaccard 会因为重复字而
    # 惩罚「一张卡吃多页」（整章只有 1 张卡时，吃 3 页的分数反而低于吃 1 页），
    # 结果后面几页被丢掉、正文少一大截。强制用完即可；被 BODY_RE 置空的封面/目录
    # 页是空计数器，塞进来也不影响内容。只有确实吃不完（span 太窄）才退让。
    if dp[n][m] != NEG:
        end_j = m
    else:
        end_j = max(range(m + 1), key=lambda j: dp[n][j])

    spans = [(0, 0)] * n
    scores = [0.0] * n
    j = end_j
    for i in range(n, 0, -1):
        k = choice[i][j]
        spans[i - 1] = (j - k, j)
        scores[i - 1] = overlap_score(cards[i - 1], seg[j][k]) if k else 0.0
        j -= k
    return spans, scores


# ── 单份资料的重解析 ────────────────────────────────────────────────────

def rebuild_pdf(path, rel):
    """重解析一份知识点清单 PDF，返回补丁条目列表（含跳过的记录）。

    返回 (entries, skipped, info)：
      entries —— 可安全回填的记录
      skipped —— 判定为不安全、不写进补丁的记录（带原因）
    """
    res = gx.parse_file(str(path), rel)
    items = res.get("items") or []
    if not items:
        return [], [], {"pages": 0, "cards": 0, "ok": 0, "skipped": 0, "note": "旧解析无卡片"}

    page_text = tree.pdf_pages_text(path)
    with fitz.open(str(path)) as doc:
        n_pages = doc.page_count
        raw_pages = [doc[i].get_text("text") or "" for i in range(n_pages)]
    # 缺页补空串：跨页续行的页不会产生顶层节点，其正文已并入上一页。
    # 非正文页（封面/目录/版尾）同样置空 —— 不参与对齐，也不进正文。
    pages = [(page_text.get(i + 1) or "") if BODY_RE.search(raw_pages[i]) else ""
             for i in range(n_pages)]

    card_ctr = [char_counter(it.get("content") or "") for it in items]
    page_ctr = [char_counter(t) for t in pages]
    spans, scores = align(card_ctr, page_ctr, span_for(len(pages), len(items)))

    entries, skipped = [], []
    for i, it in enumerate(items):
        lo, hi = spans[i]
        new_content = "\n".join(t for t in pages[lo:hi] if t).strip()
        old_content = it.get("content") or ""
        sc = scores[i]
        if not new_content:
            skipped.append({"title": it.get("title"), "reason": "未匹配到页", "score": sc})
            continue
        if sc < MIN_SCORE:
            skipped.append({"title": it.get("title"), "reason": "对齐分数过低",
                            "score": round(sc, 3)})
            continue
        keep = len(norm_chars(new_content)) / max(1, len(norm_chars(old_content)))
        if keep < MIN_KEEP:
            skipped.append({"title": it.get("title"),
                            "reason": "新正文明显变短（可能漏页）",
                            "score": round(sc, 3), "keep": round(keep, 2)})
            continue
        title = it.get("title") or ""
        entries.append({
            "source_file": rel,
            "chapter": it.get("chapter") or "",
            "domain": it.get("domain") or "",
            "kind": it.get("kind") or "",
            "title": title,
            "old_fingerprint": it.get("fingerprint") or "",
            "new_fingerprint": gx.fingerprint(title, new_content[:400]),
            "summary": _summary_of(new_content),
            "content": new_content,
            "pages": [lo + 1, hi],
            "score": round(sc, 3),
            "keep": round(keep, 3),
            "old_len": len(old_content),
            "new_len": len(new_content),
        })
    info = {"pages": n_pages, "cards": len(items), "ok": len(entries),
            "skipped": len(skipped)}
    return entries, skipped, info


def _summary_of(text):
    """与 gx_parse 保持一致的摘要算法（列表页展示用）"""
    import re
    return re.sub(r"\s+", " ", text)[:180]


# ── 主流程 ──────────────────────────────────────────────────────────────

def iter_list_pdfs(root, name_filter="知识点清单"):
    """列出资料目录下归类为「知识点/清单」的 PDF（相对路径，POSIX 风格）

    `name_filter` 再卡一道文件名：光看 classify 会把「考生模拟练习平台操作指南」
    这类文件也判成知识点清单，它们没有 `----` 层级，重解析无意义。
    """
    root = os.path.abspath(root)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if not fn.lower().endswith(".pdf"):
                continue
            if name_filter and name_filter not in fn:
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
            info = gx.classify(rel)
            if info.get("category") == gx.CAT_KNOWLEDGE and info.get("sub") == gx.KN_LIST:
                out.append(rel)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description="知识点清单 PDF 重解析 → 离线回填补丁")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="备考资料目录")
    ap.add_argument("--out", default=DEFAULT_OUT, help="补丁输出路径")
    ap.add_argument("--only", default="", help="只处理路径含该关键字的资料（抽查用）")
    ap.add_argument("--quiet", action="store_true", help="不逐份打印")
    args = ap.parse_args()

    bad = gx.taxonomy_check()
    if bad:
        raise SystemExit("考纲归一不可用，已中止（否则知识域会为空）：%s" % bad)

    rels = iter_list_pdfs(args.root)
    if args.only:
        rels = [r for r in rels if args.only in r]
    if not rels:
        raise SystemExit("没有匹配的知识点清单 PDF（root=%s only=%s）" % (args.root, args.only))

    all_entries, all_skipped, files = [], [], []
    for rel in rels:
        path = os.path.join(os.path.abspath(args.root), rel)
        entries, skipped, info = rebuild_pdf(path, rel)
        all_entries.extend(entries)
        all_skipped.extend(skipped)
        files.append({"source_file": rel, **info})
        if not args.quiet:
            print("  %-56s 页%3d 卡%3d → 回填%3d 跳过%2d"
                  % (rel.rsplit("/", 1)[-1][:56], info["pages"], info["cards"],
                     info["ok"], info["skipped"]))
            for s in skipped:
                print("     跳过：%-28s %s" % (str(s.get("title"))[:28], s.get("reason")))

    payload = {
        "generated_by": "tools/gx_rebuild_list.py",
        "rules": {"max_span": MAX_SPAN, "min_score": MIN_SCORE, "min_keep": MIN_KEEP},
        "files": files,
        "entries": all_entries,
        "skipped": all_skipped,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print("-" * 70)
    print("资料 %d 份，卡片 %d 条 → 可回填 %d 条，跳过 %d 条"
          % (len(files), sum(f["cards"] for f in files), len(all_entries), len(all_skipped)))
    if all_entries:
        worst = min(e["score"] for e in all_entries)
        print("最低对齐分数 %.3f（≥ %.2f 才写补丁）" % (worst, MIN_SCORE))
    print("补丁已写入：%s" % out)


if __name__ == "__main__":
    raise SystemExit(main())
