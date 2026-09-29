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
- 新指纹若已被**其它行**占用（会撞唯一索引），跳过该条，不让整批失败。
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BATCH = 200
DEFAULT_PATCH = os.path.join("data", "gx_content_patch.json")


def main():
    ap = argparse.ArgumentParser(description="知识点正文回填（按指纹就地更新）")
    ap.add_argument("--patch", default=DEFAULT_PATCH, help="补丁 JSON 路径")
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只干跑）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（抽查用）")
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

    from app.database import SessionLocal            # 延迟导入：干跑也要连库，但别在 argparse 前
    from app.models.gaoxiang import GxKnowledge

    db = SessionLocal()
    updated = already = miss = conflict = empty_fp = 0
    miss_samples = []
    try:
        for i, e in enumerate(entries, 1):
            old_fp = (e.get("old_fingerprint") or "").strip()
            new_fp = (e.get("new_fingerprint") or "").strip()
            if not old_fp or not new_fp:
                empty_fp += 1
                continue
            row = db.query(GxKnowledge).filter(GxKnowledge.fingerprint == old_fp).first()
            if row is None:
                # 已回填过 → 现在是新指纹；都查不到才是真没对上
                if db.query(GxKnowledge.id).filter(
                        GxKnowledge.fingerprint == new_fp).first():
                    already += 1
                else:
                    miss += 1
                    if len(miss_samples) < 10:
                        miss_samples.append(e)
                continue
            if new_fp != old_fp and db.query(GxKnowledge.id).filter(
                    GxKnowledge.id != row.id,
                    GxKnowledge.fingerprint == new_fp).first():
                conflict += 1
                continue
            if args.apply:
                row.content = e.get("content") or ""
                row.summary = (e.get("summary") or "")[:500]
                row.fingerprint = new_fp
            updated += 1
            if args.apply and i % BATCH == 0:
                db.commit()
                print("  进度 %d/%d" % (i, len(entries)))
        if args.apply:
            db.commit()
    finally:
        db.close()

    print("-" * 68)
    print("模式：%s" % ("写库" if args.apply else "干跑（加 --apply 才会写库）"))
    print("补丁条目 %d" % len(entries))
    print("  将更新   %d" % updated)
    print("  已回填   %d（幂等跳过）" % already)
    print("  指纹冲突 %d（新指纹被其它行占用，已跳过）" % conflict)
    print("  指纹缺失 %d" % empty_fp)
    print("  未命中   %d" % miss)
    if miss_samples:
        print("\n未命中样例（说明线上数据与本地重算不一致，不要强行写入）：")
        for e in miss_samples:
            print("  %-30s %s" % ((e.get("title") or "")[:30],
                                  (e.get("source_file") or "").rsplit("/", 1)[-1][:46]))
    if not args.apply and updated:
        print("\n确认「未命中」很少再执行：python tools/gx_apply_content_patch.py --apply")


if __name__ == "__main__":
    raise SystemExit(main())
