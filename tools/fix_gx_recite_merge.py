#!/usr/bin/env python
"""填空速记：把「无答案版 + 带答案版」两版条目就地合并（一次性存量数据修复）

问题
----
「填空辅助记忆清单」PDF 自带两版：前几页无答案、后几页带答案。旧解析整篇按行成条，
两版都收，于是每个知识点在 `gx_knowledge` 里落**两条** —— 一条全是 `（）`、一条带答案。
用户点开空的那条只看到一串空括号，反馈「空没填上」。

修复
----
解析器已改为「按页切两版 → 按序配对合并成一条」（`tools/gx_parse.py::_parse_fill`），
但**已入库的旧数据不会自己变**，本脚本对库内已有的行做同样的合并：

    空版行 + 答案版行  →  保留答案版那一行（正文 = 空版 + `【答案】` + 答案版，
                                           标题与摘要取空版），空版行删除

不依赖源 PDF —— 服务器上不一定留着备考资料，纯按库内数据重建。
配对规则与解析器**共用** `gx_parse._fill_groups`，保证「就地修复」与「重新导入」结果一致。

幂等
----
正文已含 `【答案】` 的来源文件整组跳过；重复执行第二次是空操作。

用法（在服务器部署目录执行）
--------------------------
    python tools/fix_gx_recite_merge.py                      # 预演：只统计 + 抽样
    python tools/fix_gx_recite_merge.py --source-like 第1章   # 只预演某一章
    python tools/fix_gx_recite_merge.py --apply              # 实际写入

为什么必须去线上跑
----------------
本地 `.env` 指向的是线上库的克隆（`192.168.2.158`），写它属明令禁止；
写线上库（`115.29.213.131`）只允许在服务器本机用部署目录的 venv 执行。
"""
import argparse
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import gx_parse as gx                       # noqa: E402  （需先补 sys.path）
from app.database import SessionLocal       # noqa: E402
from app.models.gaoxiang import GxKnowledge as K   # noqa: E402


def plan_file(rows: list):
    """一组同源 recite 行 → (更新列表, 待删行, 跳过原因)

    `rows` 必须按 seq/id 升序（即原始资料里的先后顺序）——旧导入是先落「无答案版」
    再落「带答案版」，所以第一段含空括号的行就是空版，其余是答案版。
    """
    if any(gx.FILL_ANS_SEP.strip() in (r.content or "") for r in rows):
        return [], [], "已合并过"

    flags = [gx.fill_is_blank_item(r.content) for r in rows]
    k = 0
    while k < len(flags) and flags[k]:
        k += 1
    if k == 0 or k >= len(flags):
        return [], [], "不是两版结构"

    # 用带下标的轻量 dict 喂给解析器：分组结果才能映射回数据库行
    blanks = [{"content": r.content or "", "title": r.title or "",
               "summary": r.summary or "", "_i": i} for i, r in enumerate(rows[:k])]
    answers = [{"content": r.content or "", "title": r.title or "",
                "summary": r.summary or "", "_i": i} for i, r in enumerate(rows[k:])]

    updates, deletes = [], []
    for idx, (bits, ans) in enumerate(gx._fill_groups(blanks, answers)):
        if ans is None:
            # 空版独有：答案版漏了这一条，没有可比对的答案，保留原样（只是序号归位）
            # 顺手把它转成完整知识点，去掉题目形式
            row = rows[bits[0]["_i"]]
            full = gx._fill_to_full(row.content or "")
            updates.append((row, {
                "seq": idx,
                "content": full,
                "summary": full[:500],
                "fingerprint": gx.fingerprint(full),
                "kind": gx.KN_LIST,
            }))
            continue
        arow = rows[k + ans["_i"]]
        full = gx._fill_to_full(arow.content or "")
        if not bits:
            # 答案版独有：直接转完整知识点
            updates.append((arow, {
                "seq": idx,
                "content": full,
                "summary": full[:500],
                "fingerprint": gx.fingerprint(full),
                "kind": gx.KN_LIST,
            }))
            continue
        ask = "\n".join(b["content"] for b in bits)
        updates.append((arow, {
            "content": full,
            "title": (bits[0]["title"] or arow.title or "")[:200],
            "summary": full[:500],
            # 正文变了 → 指纹必须重算：否则与新导入版本撞同一指纹，重导入不会更新
            "fingerprint": gx.fingerprint(full),
            "seq": idx,
            "kind": gx.KN_LIST,
        }))
        # 空版行删掉；车联网那类「空版拆 2 条」的情况会把两条一起并进来
        deletes.extend(rows[b["_i"]] for b in bits)
    return updates, deletes, ""


def _masked_db(db):
    """只回显「主机/库名」，绝不打印口令 —— 让人一眼确认自己连的是哪台库"""
    url = db.get_bind().url
    return "%s:%s/%s" % (url.host or "?", url.port or "?", url.database or "?")


def _count_blank_only(db, source_like=""):
    """库里还剩多少「只空无答」的 recite 条目（合并后应为 0）"""
    q = db.query(K).filter(K.kind == gx.KN_RECITE,
                           K.source_file.isnot(None), K.source_file != "")
    if source_like:
        q = q.filter(K.source_file.like("%" + source_like + "%"))
    return sum(1 for r in q.all()
               if gx.fill_is_blank_item(r.content)
               and gx.FILL_ANS_SEP.strip() not in (r.content or ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description="填空速记两版合并（存量数据修复）")
    ap.add_argument("--apply", action="store_true", help="实际写入（默认只预演）")
    ap.add_argument("--source-like", default="", help="只处理 source_file 含该子串的来源")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个来源文件（试跑）")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        print("目标库 = %s" % _masked_db(db))
        q = (db.query(K)
             .filter(K.kind == gx.KN_RECITE, K.source_file.isnot(None), K.source_file != "")
             .order_by(K.source_file, K.seq, K.id))
        if args.source_like:
            q = q.filter(K.source_file.like("%" + args.source_like + "%"))
        rows = q.all()
        if not rows:
            # 幂等：已修复过的数据 kind 会变成 list，再次查询自然为空 —— 这是成功，不是失败
            print("没有找到 kind=recite 且 source_file 非空的条目 —— 已修复或无待修复数据")
            return 0

        by_file = {}
        for r in rows:
            by_file.setdefault(r.source_file, []).append(r)
        files = sorted(by_file.items())
        if args.limit:
            files = files[:args.limit]

        before_blank = [r for r in rows if gx.fill_is_blank_item(r.content)]
        print("命中条目 = %d 条（其中含空括号的 %d 条）｜ 来源文件 = %d 份"
              % (len(rows), len(before_blank), len(by_file)))

        n_merged = n_deleted = n_updated = 0
        skipped = {}
        failures = []
        samples = []
        for sf, rs in files:
            updates, deletes, note = plan_file(rs)
            if note:
                skipped[note] = skipped.get(note, 0) + 1
                continue
            merged_here = [p for _, p in updates if "content" in p]
            n_merged += len(merged_here)
            n_deleted += len(deletes)
            n_updated += len(updates)
            if len(samples) < 3 and merged_here:
                samples.append((sf, merged_here[0]["content"][:260]))
            if not args.apply:
                continue
            try:
                for row, payload in updates:
                    for key, val in payload.items():
                        setattr(row, key, val)
                for row in deletes:
                    db.delete(row)
                db.commit()
            except Exception as e:                       # noqa: BLE001
                db.rollback()
                failures.append((sf, "%s: %s" % (type(e).__name__, e)))

        print("-" * 68)
        print("合并来源文件 = %d 份｜待更新行 = %d（其中真合并 = %d）｜待删空版行 = %d"
              % (len(files) - sum(skipped.values()), n_updated, n_merged, n_deleted))
        for note, cnt in sorted(skipped.items(), key=lambda kv: -kv[1]):
            print("  跳过：%s × %d" % (note, cnt))
        if samples:
            print("--- 样例（合并后正文前 260 字）---")
            for sf, c in samples:
                print("  ▸ %s" % os.path.basename(sf))
                print("    %s" % c.replace("\n", " / "))
        if failures:
            print("🚨 失败 %d 份（已回滚，可重跑）：" % len(failures))
            for sf, err in failures[:5]:
                print("   %s → %s" % (os.path.basename(sf), err))

        if args.apply:
            left = _count_blank_only(db, args.source_like)
            print("写入完成。库内剩余「只空无答」条目 = %d（期望 0）" % left)
        else:
            print("【预演】未写入任何数据。确认无误后加 --apply 执行。")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
