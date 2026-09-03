"""将本地采集的试卷（data/papers_*.sqlite）解析题目/答案/解析后，导入线上 MySQL。

设计要点
--------
- 读取 data/papers_*.sqlite 全部 papers/paper_questions，按 source_url 去重合并；
- 线上已存在的 source_url（papers 表）跳过；只导入新增试卷（本次 1344 份）；
- 解析优先：缺答案的题先 re-parse 试卷 HTML 的参考答案区，仍缺再用 AI 兜底；
- explanation 列：答案文本含「解析/详解/解：」等标记时，拆分答案与解析分别存储；
- 直接写线上 MySQL（DATABASE_URL），幂等（按 source_url + 题号 seq）；
- 严守连接池规则：AI 调用前关闭 DB 连接，绝不持连期间发外部请求。

用法
----
  python tools/import_local_papers.py                  # 全量导入新增卷 + AI 补答案
  python tools/import_local_papers.py --dry-run       # 仅统计，不写库
  python tools/import_local_papers.py --limit-papers 5 --no-ai   # 试导 5 份（不调 AI）
  python tools/import_local_papers.py --no-ai         # 导入但不调 AI（缺答案留空）
  python tools/import_local_papers.py --ai-limit 200  # AI 补答案最多 200 题
"""
import os
import sys
import re
import json
import time
import sqlite3
import argparse
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)

import pymysql
from app.domains.content.services.question_parser import parse_paper
from app.domains.content.services.answer_generator import generate_answer_for, ai_enabled

# ---------- 解析/解答 工具 ----------
EXP_SPLIT_RE = re.compile(r'(解析|详解|【解析】|【详解】|解：|分析|点拨|思路)\s*[:：]?')


def split_explanation(ans):
    """答案文本含解析标记时拆成 (答案, 解析)；否则 (原答案, '')。"""
    if not ans:
        return ans, ""
    m = EXP_SPLIT_RE.search(ans)
    if not m:
        return ans, ""
    head = ans[:m.start()].strip()
    tail = ans[m.end():].strip()
    if not tail:
        return ans, ""
    return (head or ans), tail


def online_conn():
    return pymysql.connect(host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
                            user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                            database=os.environ["DB_NAME"], charset="utf8mb4",
                            connect_timeout=10, autocommit=False)


def build_local_dataset():
    """读取所有 dated sqlite，按 source_url 合并，返回 {source_url: paper_dict}。"""
    papers = {}
    for f in sorted(ROOT.glob("data/papers_*.sqlite")):
        conn = sqlite3.connect(f)
        conn.row_factory = sqlite3.Row
        for p in conn.execute("SELECT * FROM papers"):
            url = p["source_url"] or f"__empty__{f.name}#{p['id']}"
            qs = conn.execute("SELECT * FROM paper_questions WHERE paper_id=?",
                              (p["id"],)).fetchall()
            if url not in papers:
                papers[url] = {"meta": dict(p), "qs": {}}
            d = papers[url]
            for q in qs:
                seq = q["seq"]
                cur = d["qs"].get(seq)
                # 合并：保留答案更完整者
                if cur is None or (not (cur["correct_answer"] or "").strip()
                                   and (q["correct_answer"] or "").strip()):
                    d["qs"][seq] = dict(q)
        conn.close()
    return papers


def get_max_packet():
    conn = online_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT @@max_allowed_packet")
            return cur.fetchone()[0]
    finally:
        conn.close()


def import_structural(candidates, local, maxpkt, limit_papers=0, no_ai=False, no_reparse=False):
    """导入新增试卷结构与题目（含解析优先补答案 + explanation 拆分）。返回新增 paper_id 列表。"""
    if limit_papers:
        candidates = candidates[:limit_papers]
    safe = int(maxpkt * 0.5)  # 单条 SQL 语句安全上限（字节）
    paper_col = ["subject", "grade", "title", "source_url", "download_url",
                 "html_content", "answers", "total_questions", "year", "semester", "created_at"]
    q_col = ["paper_id", "seq", "section", "section_idx", "qnum", "qtype", "grade",
             "subject", "question_text", "question_html", "options", "correct_answer",
             "image_base64", "explanation"]

    conn = online_conn()
    new_pids = []
    inserted_papers = inserted_q = reparsed = 0
    try:
        for url in candidates:
            d = local[url]
            meta = d["meta"]
            html = meta.get("html_content") or ""
            # 解析优先：仅当本卷有缺答案题时才 re-parse（省时）
            reparse_map = {}
            need = any(not (q["correct_answer"] or "").strip() for q in d["qs"].values())
            if need and html and not no_reparse:
                try:
                    reparsed_qs, _ = parse_paper(html)
                    for rq in reparsed_qs:
                        reparse_map[(rq.get("section_idx"), rq.get("qnum"))] = rq
                except Exception:
                    reparsed_qs = []
            # 组装题目
            qrows = []
            for seq in sorted(d["qs"].keys()):
                q = d["qs"][seq]
                ans = (q.get("correct_answer") or "").strip()
                if not ans:
                    rq = reparse_map.get((q.get("section_idx"), q.get("qnum")))
                    if rq and (rq.get("answer") or "").strip():
                        ans = rq["answer"].strip()
                        reparsed += 1
                ans, expl = split_explanation(ans)
                qrows.append({
                    "paper_id": 0,
                    "seq": seq,
                    "section": q.get("section") or "",
                    "section_idx": q.get("section_idx") or 0,
                    "qnum": q.get("qnum") or 0,
                    "qtype": q.get("qtype") or "qa",
                    "grade": q.get("grade") or meta.get("grade") or "",
                    "subject": q.get("subject") or meta.get("subject") or "",
                    "question_text": q.get("question_text") or "",
                    "question_html": q.get("question_html") or "",
                    "options": q.get("options") or "",
                    "correct_answer": ans,
                    "image_base64": q.get("image_base64") or "",
                    "explanation": expl,
                })
            # 插入 paper（超大 html 超限则去 html 仅存元信息）
            pparams = {k: meta.get(k) for k in paper_col}
            if len(pparams.get("html_content") or "") > safe:
                pparams["html_content"] = ""
            pid = None
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO papers (subject,grade,title,source_url,download_url,"
                        "html_content,answers,total_questions,year,semester,created_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        [pparams[c] for c in paper_col])
                    pid = cur.lastrowid
            except pymysql.OperationalError as e:
                conn.rollback()
                if "max_allowed_packet" in str(e) or "Packet" in str(e):
                    pparams["html_content"] = ""
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO papers (subject,grade,title,source_url,download_url,"
                            "html_content,answers,total_questions,year,semester,created_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            [pparams[c] for c in paper_col])
                        pid = cur.lastrowid
                else:
                    raise
            if pid is None:
                continue
            # 插入题目（按累积字节大小分片，避免单包超 max_allowed_packet）
            buf, size = [], 0
            for r in qrows:
                r["paper_id"] = pid
                rbytes = sum(len(str(v)) for v in r.values())
                if buf and size + rbytes > safe:
                    _flush_questions(conn, q_col, buf)
                    inserted_q += len(buf)
                    buf, size = [], 0
                buf.append(r)
                size += rbytes
            if buf:
                _flush_questions(conn, q_col, buf)
                inserted_q += len(buf)
            conn.commit()
            new_pids.append(pid)
            inserted_papers += 1
            if inserted_papers % 50 == 0:
                print(f"  ... 已导入 {inserted_papers} 份 / {inserted_q} 题")
    finally:
        conn.close()

    print(f"[结构导入] 新增试卷 {inserted_papers} 份 / 题目 {inserted_q} 道"
          f"（解析优先找回答案 {reparsed} 题）")
    return new_pids


def _flush_questions(conn, q_col, buf):
    vals = [tuple(r[c] for c in q_col) for r in buf]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO paper_questions (paper_id,seq,section,section_idx,qnum,qtype,"
            "grade,subject,question_text,question_html,options,correct_answer,"
            "image_base64,explanation) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", vals)


def fill_missing_answers_online(limit=0):
    """为线上所有缺答案的题调 AI 补全。严守规则：取数后关闭连接再调 AI。"""
    batch_size = 100
    done = 0
    consecutive_fail = 0
    while True:
        conn = online_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, qtype, question_text, options, subject, seq FROM paper_questions "
                    "WHERE correct_answer IS NULL OR correct_answer='' "
                    "ORDER BY id LIMIT %s", (batch_size,))
                rows = cur.fetchall()
        finally:
            conn.close()
        if not rows:
            break
        updates = []
        for r in rows:
            qid, qtype, qtext, opts, subject, seq = r
            qobj = SimpleNamespace(qtype=qtype, question_text=qtext,
                                   options=opts, subject=subject, seq=seq)
            ans = generate_answer_for(qobj)
            if ans is None:
                consecutive_fail += 1
                if consecutive_fail >= 10:
                    print("  [AI] 连续 10 题失败，判定不可用，放弃本次补全")
                    return done
                # 抗限流：429/超时下逐级加大冷却，避免快速撞满 10 次保护而退出
                if consecutive_fail >= 6:
                    time.sleep(90)
                elif consecutive_fail >= 3:
                    time.sleep(30)
                else:
                    time.sleep(5)
                continue
            consecutive_fail = 0
            updates.append(("[AI生成] " + ans, qid))
            done += 1
            if limit and done >= limit:
                break
        if updates:
            conn = online_conn()
            try:
                with conn.cursor() as cur:
                    cur.executemany("UPDATE paper_questions SET correct_answer=%s WHERE id=%s",
                                    updates)
                conn.commit()
            finally:
                conn.close()
        if limit and done >= limit:
            break
        if len(rows) < batch_size:
            break
        time.sleep(1)
    print(f"[AI] 补全答案 {done} 题")
    return done


def main():
    ap = argparse.ArgumentParser(description="本地采集试卷 → 线上 MySQL（解析+导入+AI补答案）")
    ap.add_argument("--dry-run", action="store_true", help="仅统计，不写库")
    ap.add_argument("--limit-papers", type=int, default=0, help="最多导入多少份新增卷（0=全部）")
    ap.add_argument("--no-ai", action="store_true", help="不调用 AI 补答案")
    ap.add_argument("--no-reparse", action="store_true",
                    help="跳过 re-parse（已解析数据重解无收益时大幅加速）")
    ap.add_argument("--ai-only", action="store_true",
                    help="跳过结构导入，仅对线上所有缺答案的题调 AI 补全")
    ap.add_argument("--ai-limit", type=int, default=0, help="AI 补答案最多多少题（0=全部缺答案）")
    args = ap.parse_args()

    local = build_local_dataset()
    print(f"[本地] 唯一试卷 {len(local)} 份")

    # 线上已存在的 source_url + 确保 explanation 列
    conn = online_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT source_url FROM papers")
            online_urls = set(r[0] for r in cur.fetchall())
            try:
                cur.execute("ALTER TABLE paper_questions ADD COLUMN explanation TEXT")
                conn.commit()
                print("[线上] 已新增 explanation 列")
            except Exception:
                conn.rollback()  # 已存在则忽略
    finally:
        conn.close()

    candidates = [u for u in local if u not in online_urls]
    print(f"[候选] 新增（线上无）: {len(candidates)} 份")
    if args.limit_papers:
        candidates = candidates[:args.limit_papers]

    if args.dry_run:
        total_q = sum(len(local[u]["qs"]) for u in candidates)
        miss = sum(1 for u in candidates for q in local[u]["qs"].values()
                   if not (q["correct_answer"] or "").strip())
        print(f"[dry-run] 将导入 {len(candidates)} 份 / {total_q} 题（缺答案 {miss} 题，未写库）")
        return

    maxpkt = get_max_packet()
    print(f"[线上] max_allowed_packet = {maxpkt} 字节，单句安全上限 {int(maxpkt*0.5)}")

    if args.ai_only:
        if ai_enabled():
            fill_missing_answers_online(limit=args.ai_limit)
        else:
            print("[跳过] AI 不可用，未补答案")
        return

    new_pids = import_structural(candidates, local, maxpkt,
                                 limit_papers=args.limit_papers, no_ai=args.no_ai,
                                 no_reparse=args.no_reparse)

    if not args.no_ai and ai_enabled():
        fill_missing_answers_online(limit=args.ai_limit)
    elif args.no_ai:
        print("[跳过] AI 补答案（--no-ai）")
    else:
        print("[跳过] AI 不可用，未补答案")


if __name__ == "__main__":
    main()
