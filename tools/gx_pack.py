#!/usr/bin/env python
"""软考高项备考资料：本地解析打包（纯文件，不连数据库）

为什么拆成「打包」和「导入」两段
--------------------------------
线上 MySQL 是真实数据，本地 `.env` 指向的是**线上库的克隆**，写入被明令禁止。
所以整条链路拆成互不依赖的两段：

    本地  tools/gx_pack.py             → data/gx_materials/*.json   （只读资料、只写文件）
    线上  tools/import_gx_materials.py → MySQL                       （只读数据包、只写库）

好处：数据包可以直接 scp 到服务器执行，不需要在服务器上装 PDF 解析依赖，也不需要
把整套 3.7G 资料同步过去。

四类产出（用户口径）
--------------------
    知识点        pack_knowledge.json
    选择题练习    pack_choice.json
    案例分析练习  pack_case.json
    论文练习      pack_essay.json
    + manifest.json   全部源文件的分类 / 解析 / 去重报告（导入时同步写入 gx_materials 归档表）

用法
----
    python tools/gx_pack.py                          # 全量打包
    python tools/gx_pack.py --limit 20                # 只跑前 20 个文件（冒烟）
    python tools/gx_pack.py --root <资料目录> --out <输出目录>

约束
----
不导入项目 app 包、不读 .env —— 打包阶段完全离线，可在任意机器上跑。
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time

# 项目根必须在 sys.path 上：gx_parse 的 `_domains_of()` 要 import app 里的考纲表，
# 缺了它就静默返回空 —— 曾因此产出 7383 条「知识域全空」的数据包。
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

# ── 按路径加载同级模块（tools/ 不是 package，且 preflight.py 也用这种方式加载本文件）──


def _load_sibling(name):
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, name + ".py")
    spec = importlib.util.spec_from_file_location("_gx_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # 注册，避免同一模块被反复执行
    spec.loader.exec_module(mod)
    return mod


gx = _load_sibling("gx_parse")

# ── 常量 ──

DEFAULT_ROOT = os.path.join("temp", "软考【高项】2026年5月班备考资料")
DEFAULT_OUT = os.path.join("data", "gx_materials")

# 类别 → 数据包文件名
PACK_FILES = {
    gx.CAT_KNOWLEDGE: "pack_knowledge.json",
    gx.CAT_CHOICE: "pack_choice.json",
    gx.CAT_CASE: "pack_case.json",
    gx.CAT_ESSAY: "pack_essay.json",
}

# 「无解析 / 有解析」双版本：有解析版是超集（题目 + 答案 + 解析），无解析版跳过。
# 实测第34课无解析 19 条 / 有解析 21 条；第40课 12 / 18 —— 有解析版一律不差于无解析版。
_VARIANT_NO_ANS = re.compile(r"[-—]{2,}\s*无解析\s*$")
_VARIANT_ANS = re.compile(r"[-—]{2,}\s*有解析\s*$")
_ANSWER_SUFFIX = re.compile(r"[（(]\s*(答案|参考答案|解析)\s*[）)]\s*$")

# 参与跨文件配对的类别：案例练习把题目与答案拆成两个 PDF
_PAIRABLE = (gx.CAT_CASE,)


def _posix(rel):
    return str(rel).replace("\\", "/")


def walk(root):
    """列出资料目录下全部文件（相对路径，POSIX 风格，已排序）"""
    out = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            out.append(_posix(rel))
    return out


def _stem_of(rel):
    """文件名去扩展名（配对规则一律在 stem 上判，带 .pdf 判会全部落空）"""
    fn = rel.rsplit("/", 1)[-1]
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", fn)


def _pair_key(rel):
    """把「同一道题的不同文件」归到同一个 key

    处理两件事：
    1. 题目/答案分文件 —— `xxx.pdf` 与 `xxx（答案）.pdf`
    2. 无解析/有解析双版本 —— `xxx----无解析.pdf` 与 `xxx----有解析.pdf`
    返回 (key, 角色)，角色 ∈ {"q", "ans", "noans"}；无配对的普通文件角色是 "q"。
    """
    d, _fn = rel.rsplit("/", 1) if "/" in rel else ("", rel)
    stem = _stem_of(rel)
    role = "q"
    if _ANSWER_SUFFIX.search(stem):
        stem = _ANSWER_SUFFIX.sub("", stem).strip()
        role = "ans"
    elif _VARIANT_NO_ANS.search(stem):
        stem = _VARIANT_NO_ANS.sub("", stem).strip()
        role = "noans"
    elif _VARIANT_ANS.search(stem):
        stem = _VARIANT_ANS.sub("", stem).strip()
    return (d + "/" + stem) if d else stem, role


def plan(paths):
    """决定每个文件是「解析」还是「跳过」，并按需组成配对组

    返回 {"skip": {rel: 原因}, "groups": [[(rel, is_answer), ...], ...]}
    groups 里每个元素是一批要共用块存储解析的文件（题目在前、答案在后）。
    """
    skip = {}
    buckets = {}                      # key → {"cand": [(rel, role, cat)]}
    for rel in paths:
        info = gx.classify(rel)
        if info["category"] == gx.CAT_OTHER:
            skip[rel] = "归档类（%s），不解析" % (info["reason"] or "其他")
            continue
        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        if ext != "pdf":
            skip[rel] = "非 PDF（.%s），仅归档不解析" % ext
            continue
        key, role = _pair_key(rel)
        buckets.setdefault(key, []).append({"rel": rel, "role": role,
                                            "cat": info["category"]})

    groups = []
    for key in sorted(buckets):
        cand = buckets[key]
        # 无解析版：只在同 key 存在有解析版时才跳过（有解析版是题目+答案+解析的超集）。
        # 判据必须用 stem —— 之前的正则带 `$` 锚定却拿了整条带 `.pdf` 的路径去匹配，
        # 结果永远不成立，「无解析」版一路被照常解析，混进一批无答案的重复题。
        has_ans_variant = any(_VARIANT_ANS.search(_stem_of(c["rel"])) for c in cand)
        kept = []
        for c in cand:
            if has_ans_variant and _VARIANT_NO_ANS.search(_stem_of(c["rel"])):
                skip[c["rel"]] = "同目录存在「有解析」版（题目+答案+解析的超集），跳过避免重复"
                continue
            kept.append(c)
        if not kept:
            continue
        cat = kept[0]["cat"]
        if cat in _PAIRABLE and len(kept) > 1:
            # 题目在前、答案在后 —— 共用块存储才会把答案灌进题目块
            kept.sort(key=lambda c: (c["role"] == "ans", c["rel"]))
            groups.append([(c["rel"], c["role"] == "ans") for c in kept])
        else:
            for c in kept:
                groups.append([(c["rel"], False)])
    return {"skip": skip, "groups": groups}


# ── 去重 ──
# 同一道题常在不同资料里重复出现（08 冲刺资料大量复用 03/04 的题目）。
# 去重不能简单「留第一个」：打印版没有答案、无解析版没有解析，留下的必须是最全的那份。

def _choice_rank(it):
    return (1 if it.get("answer") else 0,
            len(it.get("analysis") or ""),
            len(it.get("options") or []),
            len(it.get("question") or ""))


def _case_rank(it):
    return (it.get("answered") or 0,
            len(it.get("background") or ""),
            sum(len(s.get("q") or "") + len(s.get("answer") or "")
                for s in (it.get("sub_questions") or [])))


def _essay_rank(it):
    return (len(it.get("requirements") or []),
            len(it.get("background") or ""))


def _knowledge_rank(it):
    return (1 if it.get("has_blank") else 0, len(it.get("content") or ""))


RANKERS = {
    gx.CAT_CHOICE: _choice_rank,
    gx.CAT_CASE: _case_rank,
    gx.CAT_ESSAY: _essay_rank,
    gx.CAT_KNOWLEDGE: _knowledge_rank,
}


def _fingerprint_of(cat, it):
    """题目指纹 —— 存进 DB 作幂等键，重复导入不会翻倍

    各类型「认同一道题」的判据不同：
      选择题：题干 + 选项字母顺序（答案与解析不算，打印版与带解析版必须同指纹）
      案例题：解析器已算好（背景 + 各子问题）
      论文题：解析器已算好（标题 + 背景前 200 字）
      知识点：标题 + 正文（解析器已算好）
    """
    if it.get("fingerprint"):
        return it["fingerprint"]
    if cat == gx.CAT_CHOICE:
        opts = "|".join(gx.norm_for_hash(o) for o in (it.get("options") or []))
        return gx.fingerprint(gx.norm_for_hash(it.get("question") or ""), opts)
    return gx.fingerprint(it.get("title") or "", gx.norm_for_hash(it.get("content") or ""))


def dedupe(cat, items):
    """按指纹去重，保留信息最全的那份，并把同题的其他出处记进 sources

    返回 (kept, stats)；stats = {"in": N, "out": M, "dups": K}
    """
    rank = RANKERS.get(cat)
    best = {}          # fp → item
    order = []         # 保持原顺序，便于人工抽查时定位
    for it in items:
        fp = _fingerprint_of(cat, it)
        it["fingerprint"] = fp
        if fp not in best:
            best[fp] = it
            it["sources"] = [it.get("source_file") or ""]
            order.append(fp)
            continue
        keep = best[fp]
        keep["sources"].append(it.get("source_file") or "")
        if rank and rank(it) > rank(keep):
            it["sources"] = sorted(set(keep["sources"]))
            best[fp] = it
    kept = [best[fp] for fp in order]
    for it in kept:
        it["sources"] = sorted(set(s for s in it.get("sources") or [] if s))
    return kept, {"in": len(items), "out": len(kept), "dups": len(items) - len(kept)}


# ── 主流程 ──

def _parse_group(root, group):
    """解析一个组（单文件或 题目/答案 配对），返回 (items, stats, error)"""
    if len(group) == 1:
        rel = group[0][0]
        r = gx.parse_file(os.path.join(root, rel), rel)
        items = r.get("items") or []
        if r["category"] == gx.CAT_CASE:
            items = _clean_case(items)
        return items, r.get("stats") or {}, r.get("error") or ""
    paths = [(os.path.join(root, rel), rel, is_ans) for rel, is_ans in group]
    r = gx.parse_case_files(paths)
    err = r.get("error") or ""
    items = _clean_case(r.get("items") or [])
    subs = sum(len(i.get("sub_questions") or []) for i in items)
    st = {"blocks": r.get("blocks", 0), "items": len(items), "sub_questions": subs,
          "answered": sum(1 for i in items if i.get("answered")),
          "paired": len(group)}
    return items, st, err


def _clean_case(items):
    """案例题兜底清洗：丢掉「选择题解析器误产出的无答案条目」

    案例解析器颗粒无收时 `parse_file` 会退回选择题解析器（有些案例资料确实按选择题
    排版）。但纯图形作业（单代号/双代号网络图）的文字只有表格碎片，会被切成
    「FS-2 FF-2 SS-2 SF-2 / 5天 3天」这种既无题干也无答案的假题。判据：是案例就该有
    子问题，退回选择题的则必须有标准答案，否则一律不算题。
    """
    out = []
    for it in items:
        if it.get("sub_questions") or (it.get("answer") or "").strip():
            out.append(it)
    return out


def pack(root, out_dir, limit=0, verbose=True):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise SystemExit("资料目录不存在：%s" % root)
    # 前置自检：考纲归一不可用就直接中止。
    # 否则会安静地跑完几分钟并产出一份「知识域全空」的数据包，而空域会让前端的
    # 知识域筛选、进度统计、错题归因全部失效 —— 早失败远好于晚发现。
    bad = gx.taxonomy_check()
    if bad:
        raise SystemExit(
            "考纲归一不可用，已中止（否则知识域会全部为空）：%s\n"
            "请在项目根目录用项目 venv 运行，例如：\n"
            "    .venv/Scripts/python.exe tools/gx_pack.py" % bad)
    paths = walk(root)
    if limit:
        paths = paths[:limit]
    plan_ = plan(paths)
    groups = plan_["groups"]
    skip = plan_["skip"]

    pools = {c: [] for c in PACK_FILES}
    file_rows = []
    n_parsed = n_empty = n_error = 0
    t0 = time.time()

    for idx, group in enumerate(groups, 1):
        items, stats, err = _parse_group(root, group)
        info = gx.classify(group[0][0])
        cat = info["category"]
        if err:
            n_error += 1
        elif not items:
            n_empty += 1
        else:
            n_parsed += 1
        if cat in pools:
            for i, it in enumerate(items, 1):
                it["category"] = cat
                it["sub_kind"] = info["sub"]
                # 序号保持在来源资料内的原始顺序（前端「按资料顺序刷题」要用）
                if not it.get("seq"):
                    it["seq"] = i
            pools[cat].extend(items)
        try:
            size = os.path.getsize(os.path.join(root, group[0][0]))
        except OSError:
            size = 0
        file_rows.append({
            "rel_path": group[0][0],
            "paired": [g[0] for g in group[1:]],
            "category": cat,
            "sub_kind": info["sub"],
            "note": info["note"],
            "reason": info["reason"],
            "size_bytes": size,
            "items": len(items),
            "stats": stats,
            "error": err,
        })
        if verbose and idx % 40 == 0:
            sys.stderr.write("  ... %d/%d 文件，已解析 %d 条\n"
                             % (idx, len(groups),
                                sum(len(v) for v in pools.values())))

    for rel, reason in sorted(skip.items()):
        info = gx.classify(rel)
        try:
            size = os.path.getsize(os.path.join(root, rel))
        except OSError:
            size = 0
        file_rows.append({
            "rel_path": rel, "paired": [], "category": info["category"],
            "sub_kind": info["sub"], "note": info["note"], "reason": info["reason"],
            "size_bytes": size, "items": 0, "stats": {}, "error": "",
            "skipped": reason,
        })

    # ── 去重 + 写盘 ──
    os.makedirs(out_dir, exist_ok=True)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    packs = {}
    total_in = total_out = 0
    coverage = {}
    for cat, fname in PACK_FILES.items():
        kept, st = dedupe(cat, pools[cat])
        total_in += st["in"]
        total_out += st["out"]
        # 字段覆盖率 —— 空域/空章节这类静默失败必须显式可见，否则前端筛选会悄悄失效
        n = len(kept) or 1
        coverage[cat] = {
            "items": len(kept),
            "domain": sum(1 for x in kept if (x.get("domain") or "").strip()),
            "chapter": sum(1 for x in kept if (x.get("chapter") or "").strip()),
            "deck": sum(1 for x in kept if (x.get("deck") or "").strip()),
            # 知识点用「有正文」，题目用「可判分（有答案或子问题）」，两类指标不同不可混看
            "content": sum(1 for x in kept if len((x.get("content") or "").strip()) >= 20),
            "answer_or_subs": sum(1 for x in kept
                                  if (x.get("answer") or "").strip()
                                  or x.get("sub_questions") or x.get("requirements")),
            "domain_pct": round(100.0 * sum(1 for x in kept
                                            if (x.get("domain") or "").strip()) / n, 1),
            "chapter_pct": round(100.0 * sum(1 for x in kept
                                             if (x.get("chapter") or "").strip()) / n, 1),
        }
        payload = {
            "schema": 1,
            "category": cat,
            "generated_at": now,
            "source_root": os.path.basename(root),
            "count": len(kept),
            "items": kept,
        }
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        packs[cat] = {"file": fname, "count": len(kept), "dedupe": st,
                      "size": os.path.getsize(os.path.join(out_dir, fname))}

    # ── 覆盖报告 ──
    by_cat = {}
    by_sub = {}
    for r in file_rows:
        c = by_cat.setdefault(r["category"], {"files": 0, "items": 0, "empty": 0,
                                               "error": 0, "skipped": 0})
        c["files"] += 1
        c["items"] += r["items"]
        if r.get("skipped"):
            c["skipped"] += 1
        elif r["error"]:
            c["error"] += 1
        elif not r["items"]:
            c["empty"] += 1
        k = (r["category"], r["sub_kind"])
        s = by_sub.setdefault("/".join(k), {"files": 0, "items": 0})
        s["files"] += 1
        s["items"] += r["items"]

    manifest = {
        "schema": 1,
        "generated_at": now,
        "source_root": os.path.basename(root),
        "elapsed_sec": round(time.time() - t0, 1),
        "files_total": len(paths),
        "files_parsed": n_parsed,
        "files_empty": n_empty,
        "files_error": n_error,
        "files_skipped": len(skip),
        "groups": len(groups),
        "items_raw": total_in,
        "items_deduped": total_out,
        "packs": packs,
        "coverage": coverage,
        "by_category": by_cat,
        "by_sub": by_sub,
        "files": file_rows,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    if verbose:
        _print_report(manifest, out_dir)
    return manifest


def _print_report(m, out_dir):
    print("")
    print("=" * 72)
    print("资料分类与解析结果    源目录：%s" % m["source_root"])
    print("=" * 72)
    print("文件 %d 个 → 解析单元 %d 组（跳过 %d）  耗时 %.1fs"
          % (m["files_total"], m["groups"], m["files_skipped"], m["elapsed_sec"]))
    print("解析成功 %d / 无条目 %d / 出错 %d"
          % (m["files_parsed"], m["files_empty"], m["files_error"]))
    print("-" * 72)
    print("%-8s %6s %8s %7s %6s %6s" % ("类别", "文件", "原始条目", "空解析", "出错", "归档"))
    for cat in (gx.CAT_KNOWLEDGE, gx.CAT_CHOICE, gx.CAT_CASE, gx.CAT_ESSAY, gx.CAT_OTHER):
        c = m["by_category"].get(cat)
        if not c:
            continue
        print("%-8s %6d %8d %7d %6d %6d"
              % (cat, c["files"], c["items"], c["empty"], c["error"], c["skipped"]))
    print("-" * 72)
    for cat, p in m["packs"].items():
        d = p["dedupe"]
        print("%-6s → %-20s %6d 条（原始 %d，去重 %d）  %.1f MB"
              % (cat, p["file"], p["count"], d["in"], d["dups"],
                 p["size"] / 1048576.0))
    print("合计：原始 %d 条 → 去重后 %d 条" % (m["items_raw"], m["items_deduped"]))
    print("-" * 72)
    print("字段覆盖率（空域/空章节会让前端筛选静默失效，务必盯住）：")
    for cat, c in (m.get("coverage") or {}).items():
        if cat == gx.CAT_KNOWLEDGE:
            extra = "有正文 %5d" % c["content"]
        else:
            extra = "可判分(有答案/子问题) %5d" % c["answer_or_subs"]
        print("   %-8s 条目 %5d  知识域 %5.1f%%  章节 %5.1f%%  套卷 %5d  %s"
              % (cat, c["items"], c["domain_pct"], c["chapter_pct"], c["deck"], extra))
    print("-" * 72)
    print("细类分布：")
    for k in sorted(m["by_sub"]):
        s = m["by_sub"][k]
        print("   %-28s %4d 文件 %6d 条" % (k, s["files"], s["items"]))
    empty = [r["rel_path"] for r in m["files"]
             if not r.get("skipped") and not r["error"] and not r["items"]]
    if empty:
        print("-" * 72)
        print("解析出 0 条目（%d，逐个人工确认是否扫描件）：" % len(empty))
        for rel in empty[:40]:
            print("   " + rel)
    print("=" * 72)
    print("输出目录：%s" % os.path.abspath(out_dir))


def main(argv=None):
    ap = argparse.ArgumentParser(description="软考高项备考资料：本地解析打包")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="资料根目录")
    ap.add_argument("--out", default=DEFAULT_OUT, help="数据包输出目录")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个文件（冒烟用）")
    ap.add_argument("--quiet", action="store_true", help="不打印报告")
    args = ap.parse_args(argv)
    # 相对路径按项目根解析，便于在任意 cwd 下调用
    proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _abs(p):
        return p if os.path.isabs(p) else os.path.join(proj, p)

    pack(_abs(args.root), _abs(args.out), limit=args.limit, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
