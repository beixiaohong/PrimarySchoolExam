#!/usr/bin/env python
"""软考高项备考资料：数据包导入线上题库（只读数据包，只写数据库）

与 `tools/gx_pack.py` 的分工
---------------------------
    gx_pack.py   ：本地跑，读 PDF → 写 JSON 数据包（不碰 DB）
    本脚本       ：线上跑，读 JSON 数据包 → 写 MySQL（不解析 PDF）

为什么必须在线上执行
------------------
本地 `.env` 指向的是**线上库的克隆**（`192.168.2.158`），写它是明令禁止的。
线上库（`115.29.213.131`）只允许在服务器本机用部署目录的 venv 执行写操作。
所以标准流程是：本地 `gx_pack.py` → scp 数据包到服务器 → 服务器上跑本脚本。

用法（在服务器部署目录执行）
--------------------------
    python tools/import_gx_materials.py stats --pack-dir data/gx_materials
    python tools/import_gx_materials.py load  --pack-dir data/gx_materials --dry-run
    python tools/import_gx_materials.py load  --pack-dir data/gx_materials

幂等性
------
每条记录都带 `fingerprint`（内容指纹），导入按指纹 **存在即更新、不存在才插入**，
所以重复执行不会让题库翻倍，资料更新后重跑也能覆盖旧版本。

安全
----
`--dry-run` 只统计不落库；`load` 分批提交（每批 300 条），单批失败只回滚该批，
不会把已成功的批次一起丢掉。
"""
import argparse
import json
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

PACK_KNOWLEDGE = "pack_knowledge.json"
PACK_CHOICE = "pack_choice.json"
PACK_CASE = "pack_case.json"
PACK_ESSAY = "pack_essay.json"
# 参数化生成的计算题（tools/gx_calc_gen.py 产出）：结构与 pack_choice 完全一致，
# 单独成文件是为了不被 gx_pack.py 重跑时冲掉 —— 重导资料后这个文件仍在。
PACK_CALC_GEN = "pack_calc_gen.json"
MANIFEST = "manifest.json"

BATCH = 300


# ── 读取数据包 ──

def load_pack(pack_dir, name):
    path = os.path.join(pack_dir, name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_pack(pack_dir):
    """校验数据包完整性 —— 缺少 manifest 或四类全缺时直接报错，别猜"""
    if not os.path.isdir(pack_dir):
        raise SystemExit("数据包目录不存在：%s" % pack_dir)
    has_manifest = os.path.exists(os.path.join(pack_dir, MANIFEST))
    packs = {n: load_pack(pack_dir, n)
             for n in (PACK_KNOWLEDGE, PACK_CHOICE, PACK_CASE, PACK_ESSAY,
                       PACK_CALC_GEN)}
    present = {k: v for k, v in packs.items() if v}
    if not has_manifest and not present:
        raise SystemExit(
            "数据包目录里既没有 manifest.json 也没有 pack_*.json：%s\n"
            "先在本地生成数据包（tools/gx_pack.py），再传到服务器。" % pack_dir)
    return packs, (load_pack(pack_dir, MANIFEST) if has_manifest else None)


# ── 子命令：stats ──

def cmd_stats(args):
    packs, manifest = check_pack(args.pack_dir)
    print("数据包：%s" % os.path.abspath(args.pack_dir))
    if manifest:
        print("生成时间：%s    源目录：%s"
              % (manifest.get("generated_at"), manifest.get("source_root")))
        print("源文件 %d 个 → 解析单元 %d 组（跳过 %d）/ 成功 %d / 空 %d / 出错 %d"
              % (manifest.get("files_total"), manifest.get("groups"),
                 manifest.get("files_skipped"), manifest.get("files_parsed"),
                 manifest.get("files_empty"), manifest.get("files_error")))
        print("原始条目 %d → 去重后 %d" % (manifest.get("items_raw"),
                                           manifest.get("items_deduped")))
    print("-" * 68)
    print("%-22s %8s %10s %8s" % ("数据包", "条目", "有知识域", "有章节"))
    for name, payload in packs.items():
        if not payload:
            print("%-22s %8s" % (name, "（缺失）"))
            continue
        items = payload.get("items") or []
        dom = sum(1 for x in items if (x.get("domain") or "").strip())
        chap = sum(1 for x in items if (x.get("chapter") or "").strip())
        print("%-22s %8d %10d %8d" % (name, len(items), dom, chap))
        for cat, c in (payload.get("coverage") and {}).items() if False else ():
            pass
    cov = (manifest or {}).get("coverage") or {}
    if cov:
        print("-" * 68)
        print("字段覆盖率：")
        for cat, c in cov.items():
            print("   %-8s 条目 %5d  知识域 %5.1f%%  章节 %5.1f%%  有答案/子问题 %5d"
                  % (cat, c["items"], c["domain_pct"], c["chapter_pct"],
                     c["answer_or_subs"]))
    return 0


# ── 记录构造（纯函数，便于单测） ──

def _json_or_none(obj):
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def knowledge_row(it, seq):
    return {
        "fingerprint": it.get("fingerprint") or "",
        "domain": it.get("domain") or "",
        "title": (it.get("title") or "")[:200],
        "summary": (it.get("summary") or "")[:500],
        "content": it.get("content") or "",
        "source": "import",
        "chapter": (it.get("chapter") or "")[:50],
        "kind": (it.get("kind") or "")[:20],
        "source_file": (it.get("source_file") or "")[:500],
        "seq": it.get("seq") or seq,
    }


def _qtype_of(it, default="single"):
    """选择题型：答案字母多于 1 个 → 多选"""
    ans = (it.get("answer") or "").strip()
    if ans and len([c for c in ans if c.isalpha()]) > 1:
        return "multi"
    return default


def question_row(it, seq):
    """把数据包条目转成 gx_questions 的列字典

    三类共用一张表，差异只在 qtype 与几个文本列的落法：
      选择题：options_json 存选项数组，answer 存字母串；
      案例题：question 存背景材料，sub_questions 存 [{q,answer,points}]，无选项；
      论文题：title 存题目名，sub_questions 存论述要求（answer 留空，由 AI 批改）。
    """
    cat = it.get("category") or ""
    base = {
        "fingerprint": it.get("fingerprint") or "",
        "domain": it.get("domain") or "",
        "title": (it.get("title") or "")[:200],
        "chapter": (it.get("chapter") or "")[:50],
        "source_kind": (it.get("source_kind") or "")[:20],
        "source_file": (it.get("source_file") or "")[:500],
        "deck": (it.get("deck") or "")[:20],
        "seq": it.get("seq") or seq,
        "source": "import",
        "year": None,
    }
    if cat == "选择题练习":
        base.update({
            "qtype": _qtype_of(it),
            "question": it.get("question") or "",
            "options_json": _json_or_none(it.get("options") or []),
            "answer": it.get("answer") or "",
            "analysis": it.get("analysis") or "",
            "sub_questions": None,
        })
    elif cat == "案例分析练习":
        subs = [{"q": s.get("q") or "", "answer": s.get("answer") or "",
                 "points": s.get("points") or 0} for s in (it.get("sub_questions") or [])]
        base.update({
            "qtype": "case",
            "question": it.get("background") or "",
            "options_json": None,
            "answer": "",
            "analysis": "",
            "sub_questions": _json_or_none(subs),
        })
    else:                                   # 论文练习
        reqs = [{"q": r, "answer": "", "points": 0}
                for r in (it.get("requirements") or [])]
        base.update({
            "qtype": "essay",
            "question": it.get("background") or "",
            "options_json": None,
            "answer": "",
            "analysis": "",
            "sub_questions": _json_or_none(reqs),
        })
    return base


def material_rows(manifest):
    """manifest.files → gx_materials 行（分类与解析审计）"""
    rows = []
    for r in (manifest or {}).get("files") or []:
        rel = r.get("rel_path") or ""
        if not rel:
            continue
        fname = rel.rsplit("/", 1)[-1]
        stem = fname.rsplit(".", 1)[0] if "." in fname else fname
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        rows.append({
            "rel_path": rel[:500],
            "category": (r.get("category") or "")[:20],
            "sub_kind": (r.get("sub_kind") or "")[:20],
            "title": stem[:200],
            "ext": ext[:10],
            "size_bytes": int(r.get("size_bytes") or 0),
            "items": int(r.get("items") or 0),
            "reason": (r.get("reason") or "")[:300],
            "note": (r.get("note") or "")[:300],
            "skipped": (r.get("skipped") or "")[:300],
            "error": (r.get("error") or "")[:300],
        })
    return rows


# ── 入库（幂等：按 fingerprint 存在即更新） ──

def _upsert(db, model, rows, label, dry_run=False, log=None):
    """按 fingerprint 幂等写入，返回 (插入, 更新, 跳过)"""
    ins = upd = skip = 0
    fp_col = model.fingerprint
    for i, row in enumerate(rows, 1):
        fp = (row.get("fingerprint") or "").strip()
        if not fp:
            skip += 1
            continue
        existed = db.query(model.id).filter(fp_col == fp).first()
        if dry_run:
            if existed:
                upd += 1
            else:
                ins += 1
        elif existed:
            db.query(model).filter(model.id == existed[0]).update(
                row, synchronize_session=False)
            upd += 1
        else:
            db.add(model(**row))
            ins += 1
        if not dry_run and i % BATCH == 0:
            db.commit()
            if log:
                log("  %s 进度 %d/%d（新增 %d / 更新 %d）" % (label, i, len(rows), ins, upd))
    if not dry_run:
        db.commit()
    return ins, upd, skip


def cmd_load(args):
    packs, manifest = check_pack(args.pack_dir)
    from app.database import SessionLocal
    from app.models.gaoxiang import GxKnowledge, GxQuestion, GxMaterial

    kn = (packs.get(PACK_KNOWLEDGE) or {}).get("items") or []
    ch = (packs.get(PACK_CHOICE) or {}).get("items") or []
    # 参数化生成的计算题并入选择题一起导入（同样按 fingerprint 幂等）
    ch = ch + ((packs.get(PACK_CALC_GEN) or {}).get("items") or [])
    cs = (packs.get(PACK_CASE) or {}).get("items") or []
    es = (packs.get(PACK_ESSAY) or {}).get("items") or []
    if args.limit:
        kn, ch, cs, es = (x[:args.limit] for x in (kn, ch, cs, es))

    def log(msg):
        print(msg, flush=True)

    log("数据包：%s%s" % (os.path.abspath(args.pack_dir),
                        "（dry-run，不落库）" if args.dry_run else ""))
    log("待导入：知识点 %d / 选择题 %d / 案例题 %d / 论文题 %d，资料清单 %d"
        % (len(kn), len(ch), len(cs), len(es), len(material_rows(manifest))))

    db = SessionLocal()
    try:
        total = {}
        total["knowledge"] = _upsert(
            db, GxKnowledge, [knowledge_row(it, i) for i, it in enumerate(kn, 1)],
            "知识点", args.dry_run, log)
        q_rows = ([question_row(it, i) for i, it in enumerate(ch, 1)]
                  + [question_row(it, i) for i, it in enumerate(cs, 1)]
                  + [question_row(it, i) for i, it in enumerate(es, 1)])
        total["question"] = _upsert(db, GxQuestion, q_rows, "题目", args.dry_run, log)
        for r in material_rows(manifest):
            r["fingerprint"] = r["rel_path"]      # gx_materials 没有 fingerprint 列
        mat_rows = material_rows(manifest)
        total["material"] = _upsert_materials(db, GxMaterial, mat_rows,
                                             args.dry_run, log)

        log("-" * 60)
        for k, (a, b, c) in total.items():
            log("  %-10s 新增 %5d / 更新 %5d / 无指纹跳过 %d" % (k, a, b, c))
        if not args.dry_run:
            log("导入完成。")
    finally:
        db.close()
    return 0


def _upsert_materials(db, model, rows, dry_run=False, log=None):
    """资料清单按 rel_path 幂等（列表页要「这份资料解析出多少题」，必须能更新）"""
    ins = upd = 0
    for i, row in enumerate(rows, 1):
        rel = row.get("rel_path") or ""
        if not rel:
            continue
        existed = db.query(model.id).filter(model.rel_path == rel).first()
        row = {k: v for k, v in row.items() if k != "fingerprint"}
        if dry_run:
            if existed:
                upd += 1
            else:
                ins += 1
        elif existed:
            db.query(model).filter(model.id == existed[0]).update(
                row, synchronize_session=False)
            upd += 1
        else:
            db.add(model(**row))
            ins += 1
        if not dry_run and i % BATCH == 0:
            db.commit()
            if log:
                log("  资料清单进度 %d/%d" % (i, len(rows)))
    if not dry_run:
        db.commit()
    return ins, upd, 0


def cmd_materials(args):
    """列出线上已有资料的分类与解析情况（排查「某份资料有没有进来」）"""
    from app.database import SessionLocal
    from app.models.gaoxiang import GxMaterial
    db = SessionLocal()
    try:
        q = db.query(GxMaterial)
        if args.category:
            q = q.filter(GxMaterial.category == args.category)
        rows = q.order_by(GxMaterial.category, GxMaterial.rel_path).limit(args.limit).all()
        print("%-10s %-10s %6s  %s" % ("类别", "子类", "条目", "资料"))
        for r in rows:
            print("%-10s %-10s %6d  %s" % (r.category, r.sub_kind, r.items, r.rel_path))
        print("共 %d 行（limit=%d）" % (len(rows), args.limit))
    finally:
        db.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="软考高项备考资料：数据包导入")
    ap.add_argument("--pack-dir", default=os.path.join("data", "gx_materials"),
                    help="数据包目录（默认 data/gx_materials）")
    sub = ap.add_subparsers(dest="cmd")

    p_stats = sub.add_parser("stats", help="只看数据包统计，不连数据库")
    p_stats.set_defaults(func=cmd_stats)

    p_load = sub.add_parser("load", help="导入数据库（幂等）")
    p_load.add_argument("--dry-run", action="store_true", help="只统计不落库")
    p_load.add_argument("--limit", type=int, default=0, help="每类只取前 N 条（试跑）")
    p_load.set_defaults(func=cmd_load)

    p_mat = sub.add_parser("materials", help="列出线上已导入的资料清单")
    p_mat.add_argument("--category", default="", help="按类别过滤")
    p_mat.add_argument("--limit", type=int, default=200)
    p_mat.set_defaults(func=cmd_materials)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        args = ap.parse_args((argv or []) + ["stats"])
    if not os.path.isabs(args.pack_dir):
        args.pack_dir = os.path.join(_PROJ, args.pack_dir)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
