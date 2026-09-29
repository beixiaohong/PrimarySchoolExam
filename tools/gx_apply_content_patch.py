#!/usr/bin/env python
"""高项知识点正文回填：把 `gx_rebuild_list.py` 产出的补丁写进数据库（只在服务器本机跑）

为什么要有这一步
----------------
知识点清单 PDF 的层级信息在入库时就丢了（详见 gx_pdf_tree 的说明），线上正文是一整坨
连写的句子。重解析能还原层级，但重解析要读 PDF，而线上服务器没有那份 3.7G 资料。
所以链路是：

    本地  tools/gx_rebuild_list.py         → data/gx_content_patch.json （只读 PDF，只写文件）
    线上  tools/gx_apply_content_patch.py  → MySQL                      （只读补丁，只写库）

更新方式：按 `old_fingerprint` **就地更新同一行**，不改主键。因此
- 不会多出/丢失卡片，列表结构与数量完全不变；
- `gx_knowledge_reads`（已读记录）按 knowledge_id 关联，不受影响；
- 重复执行幂等：已经回填过的行其指纹已是 new_fingerprint，会被判为「已回填」跳过。

用法
----
    # 先干跑，看命中率（默认就是干跑，不写库）
    python tools/gx_apply_content_patch.py

    # 确认命中率没问题再落库
    python tools/gx_apply_content_patch.py --apply

安全边界
--------
- 干跑是**默认值**，必须显式 `--apply` 才写库 —— 避免手滑。
- 只认指纹，不认序号：指纹对不上就跳过并报告，绝不按位置瞎改。
- **一次性集合预检**（`_plan`），而不是逐条查库。这是吃过亏的地方：
  逐条判断时，本批里另一条还没写入、指纹仍是旧值，于是「新指纹已被占用」查不出来，
  干跑报「冲突 0」，真写库却撞唯一索引 1062（`ux_gx_knowledge_fingerprint`）。
  现在先把所有相关指纹一次性捞出来，在内存里连同「本批内部互相冲突」一起判。
- 写库按 `--batch` 分批提交；单条撞唯一索引只回滚该批并跳过，不让整批崩。
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BATCH = 50
DEFAULT_PATCH = os.path.join("data", "gx_content_patch.json")


def selfcheck(entries):
    """补丁自检：新指纹必须两两不同。返回 [(重复条目, 首次出现的条目), ...]

    2026-09-29 之前的补丁没有做过碰撞消解，里面存在「不同行算出同一新指纹」的情况。
    直接拿去 `--apply` 会在写库时撞唯一索引 1062，而**干跑查不出来**（逐条查时另一条
    还挂着旧指纹）。这里先拦下来并给出重生成命令 —— 比让它默默跳过十几条、用户
    以为回填完了要强。
    """
    seen, dups = {}, []
    for e in entries:
        fp = (e.get("new_fingerprint") or "").strip()
        if not fp:
            continue
        if fp in seen:
            dups.append((e, seen[fp]))
        else:
            seen[fp] = e
    return dups


def _plan(db, GxKnowledge, entries):
    """一次性把「谁能更新、谁冲突、谁已回填、谁没对上」算清楚。

    返回 (可更新列表, 统计)。可更新列表元素为 (行对象, 条目)。
    """
    old_fps = {e.get("old_fingerprint") for e in entries if e.get("old_fingerprint")}
    new_fps = {e.get("new_fingerprint") for e in entries if e.get("new_fingerprint")}

    # 库里这些指纹分别被哪一行占用（只取需要的列，别把整个表拉回来）
    owner = {}
    if old_fps or new_fps:
        rows = db.query(GxKnowledge.id, GxKnowledge.fingerprint).filter(
            GxKnowledge.fingerprint.in_(old_fps | new_fps)).all()
        for rid, fp in rows:
            owner.setdefault(fp, []).append(rid)

    # 第一遍：把每条条目定位到线上那一行（找不到就分派到「已回填 / 未命中」）
    cand, stats = [], {"update": 0, "already": 0, "miss": 0,
                       "conflict": 0, "empty_fp": 0, "inner": 0}
    miss_samples = []
    for e in entries:
        old_fp = (e.get("old_fingerprint") or "").strip()
        new_fp = (e.get("new_fingerprint") or "").strip()
        if not old_fp or not new_fp:
            stats["empty_fp"] += 1
            continue
        ids = owner.get(old_fp) or []
        if not ids:
            # 查不到 old → 可能已回填过（现在就是新指纹）
            if owner.get(new_fp):
                stats["already"] += 1
            else:
                stats["miss"] += 1
                if len(miss_samples) < 10:
                    miss_samples.append(e)
            continue
        cand.append((ids[0], e, new_fp))

    # 同一行被本批多条盯上（去重前的补丁会有）→ 只更新一次
    seen_rid, uniq = set(), []
    for rid, e, new_fp in cand:
        if rid in seen_rid:
            stats["already"] += 1
            continue
        seen_rid.add(rid)
        uniq.append((rid, e, new_fp))

    # 本批内部：同一个新指纹被几「行」盯上。必须按行去重后再数 —— 直接数条目会把
    # 「两条补丁指向同一行」误判成冲突，结果一行都更新不了。
    fp_rids = defaultdict(set)
    for rid, _e, new_fp in uniq:
        fp_rids[new_fp].add(rid)

    plan, conflict_samples = [], []
    for rid, e, new_fp in uniq:
        rids = fp_rids[new_fp]
        # 撞唯一索引的两种来源：库里别行已占用 / 本批内还有别的行要用这个新指纹
        taken = [i for i in (owner.get(new_fp) or []) if i != rid]
        others = rids - {rid}
        if others and rid != min(rids):
            # 本批内部竞争同一个指纹：只放行 id 最小的一行（按 id 而非遍历顺序，
            # 保证结果确定）。其余保持原样 —— 宁可留旧内容，也不能让整批崩。
            stats["conflict"] += 1
            stats["inner"] += 1
            if len(conflict_samples) < 10:
                conflict_samples.append((e, len(taken), True))
            continue
        if taken:
            stats["conflict"] += 1
            if len(conflict_samples) < 10:
                conflict_samples.append((e, len(taken), False))
            continue
        plan.append((rid, e))
        stats["update"] += 1

    return plan, stats, miss_samples, conflict_samples


def main():
    ap = argparse.ArgumentParser(description="知识点正文回填（按指纹就地更新）")
    ap.add_argument("--patch", default=DEFAULT_PATCH, help="补丁 JSON 路径")
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只干跑）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（抽查用）")
    ap.add_argument("--batch", type=int, default=BATCH, help="每批提交条数")
    args = ap.parse_args()

    path = Path(args.patch)
    if not path.exists():
        raise SystemExit("补丁文件不存在：%s\n请先在资料所在的机器上跑 tools/gx_rebuild_list.py"
                         % path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries") or []
    if args.limit:
        entries = entries[:args.limit]
    if not entries:
        raise SystemExit("补丁里没有条目，无需处理")

    dups = selfcheck(entries)
    if dups:
        print("-" * 68)
        print("补丁自检失败：有 %d 条新指纹重复，直接写库会撞唯一索引 1062。" % len(dups))
        for e, first in dups[:8]:
            print("  %-26s %-40s 与「%s」撞车"
                  % ((e.get("title") or "")[:26],
                     (e.get("source_file") or "").rsplit("/", 1)[-1][:40],
                     (first.get("source_file") or "").rsplit("/", 1)[-1][:30]))
        raise SystemExit(
            "\n这是旧版补丁（未做碰撞消解）。请在本机重新生成后重传：\n"
            "    .venv/Scripts/python.exe tools/gx_rebuild_list.py\n"
            "再跑：python %s --apply" % os.path.relpath(__file__, ROOT))

    from sqlalchemy.exc import IntegrityError

    from app.database import SessionLocal            # 延迟导入：干跑也要连库，但别在 argparse 前
    from app.models.gaoxiang import GxKnowledge

    db = SessionLocal()
    written = failed = 0
    fail_samples = []
    try:
        plan, stats, miss_samples, conflict_samples = _plan(db, GxKnowledge, entries)

        if args.apply and plan:
            for i, (rid, e) in enumerate(plan, 1):
                try:
                    row = db.get(GxKnowledge, rid)
                    if row is None:
                        continue
                    row.content = e.get("content") or ""
                    row.summary = (e.get("summary") or "")[:500]
                    row.fingerprint = e.get("new_fingerprint")
                    db.flush()
                    written += 1
                except IntegrityError:
                    db.rollback()          # 只回滚本批，已提交的批次不受影响
                    failed += 1
                    if len(fail_samples) < 10:
                        fail_samples.append(e)
                    continue
                if i % args.batch == 0:
                    db.commit()
                    print("  进度 %d/%d" % (i, len(plan)))
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("-" * 68)
    print("模式：%s" % ("写库" if args.apply else "干跑（加 --apply 才会写库）"))
    print("补丁条目 %d" % len(entries))
    print("  将更新   %d" % stats["update"])
    print("  已回填   %d（幂等跳过）" % stats["already"])
    print("  指纹冲突 %d（新指纹会撞唯一索引，已跳过）"
          % stats["conflict"])
    if stats["inner"]:
        print("            其中 %d 条是补丁内部互相冲突（逐条查库查不出来，必须集合预检）"
              % stats["inner"])
    print("  指纹缺失 %d" % stats["empty_fp"])
    print("  未命中   %d" % stats["miss"])
    if args.apply:
        print("  实际写入 %d，写入失败 %d" % (written, failed))

    if conflict_samples:
        print("\n冲突样例（这些行保持原样，不会写坏）：")
        for e, n_taken, inner in conflict_samples:
            why = "补丁内部冲突" if inner else "被另外 %d 行占用" % n_taken
            print("  %-28s %-44s %s"
                  % ((e.get("title") or "")[:28],
                     (e.get("source_file") or "").rsplit("/", 1)[-1][:44], why))
    if fail_samples:
        print("\n写入失败样例（已回滚该批，其它批次不受影响）：")
        for e in fail_samples:
            print("  %-28s %s" % ((e.get("title") or "")[:28],
                                  (e.get("source_file") or "").rsplit("/", 1)[-1][:44]))
    if miss_samples:
        print("\n未命中样例（说明线上数据与本地重算不一致，不要强行写入）：")
        for e in miss_samples:
            print("  %-28s %s" % ((e.get("title") or "")[:28],
                                  (e.get("source_file") or "").rsplit("/", 1)[-1][:44]))
    if not args.apply and stats["update"]:
        print("\n确认「未命中/冲突」都很少再执行："
              "python tools/gx_apply_content_patch.py --apply")


if __name__ == "__main__":
    raise SystemExit(main())
