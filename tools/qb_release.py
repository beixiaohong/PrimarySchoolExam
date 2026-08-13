#!/usr/bin/env python
"""题库更新脚本生成 / 应用（参考 app/migrations 的版本管理思路）

背景
----
本地通过 tools/collect_papers.py 持续采集试卷到「本地 MySQL」；当要把「新增的题库」
同步到「线上 MySQL」时，用本工具产出一份带版本号的更新脚本，手动传到线上执行即可。

子命令
------
  python tools/qb_release.py generate            # 本地：增量抽取未导出的 papers + paper_questions
                                                #   → 生成 qb_versions/NNN_*.py（按 source_url 记录已导出）
  python tools/qb_release.py generate --dry-run # 仅预览，不写文件、不记录
  python tools/qb_release.py apply              # 线上：按版本顺序执行未应用的 qb_versions/*.py（幂等 upsert）

设计要点
--------
- 仅覆盖「采集式题库」papers + paper_questions（即“本地获取的题库”）。
- 增量：本地用 qb_export_state 表记录已导出的 source_url；generate 只导出未导出的部分。
- 幂等 upsert：线上按 source_url 定位/写入 papers，再按 (paper_id, seq) 定位/写入题目，
  规避本地与线上 paper_id 自增不一致导致的错位（绝不依赖本地 id）。
- qb_versions/ 已加入 .gitignore：生成本地留存、手动传线上，不进 git 仓库。
- 数据库：强制 MySQL（与线上一致）；连接信息复用 .env（DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME）。
"""
import argparse
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

# 强制 MySQL（本项目已移除 SQLite），且须在 import app 前设置
os.environ["DB_DRIVER"] = "mysql"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text, bindparam  # noqa: E402

from app.database import SessionLocal  # noqa: E402

QBV_DIR = ROOT / "qb_versions"
PAPER_COLS = ("subject", "grade", "title", "source_url", "download_url",
              "html_content", "answers", "total_questions", "year", "semester")
Q_COLS = ("seq", "section", "section_idx", "qnum", "qtype", "grade", "subject",
          "question_text", "question_html", "options", "correct_answer", "image_base64")

# 生成文件中的 upgrade 函数体（__PAPERS__ 占位符会被替换为数据字面量）
UPGRADE_BODY = '''def upgrade(db):
    from sqlalchemy import text
    PAPERS = __PAPERS__

    for p in PAPERS:
        params = {k: p[k] for k in (
            "subject", "grade", "title", "source_url", "download_url",
            "html_content", "answers", "total_questions", "year", "semester")}
        row = db.execute(text("SELECT id FROM papers WHERE source_url=:s"),
                         {"s": p["source_url"]}).first()
        if row:
            pid = row[0]
            db.execute(text(
                "UPDATE papers SET subject=:subject, grade=:grade, title=:title, "
                "source_url=:source_url, download_url=:download_url, html_content=:html_content, "
                "answers=:answers, total_questions=:total_questions, year=:year, semester=:semester "
                "WHERE id=:id"), {**params, "id": pid})
        else:
            res = db.execute(text(
                "INSERT INTO papers (subject, grade, title, source_url, download_url, "
                "html_content, answers, total_questions, year, semester) "
                "VALUES (:subject, :grade, :title, :source_url, :download_url, "
                ":html_content, :answers, :total_questions, :year, :semester)"), params)
            pid = res.lastrowid
        for q in p["questions"]:
            ex = db.execute(text("SELECT id FROM paper_questions WHERE paper_id=:pid AND seq=:seq"),
                             {"pid": pid, "seq": q["seq"]}).first()
            if ex:
                db.execute(text(
                    "UPDATE paper_questions SET section=:section, section_idx=:section_idx, "
                    "qnum=:qnum, qtype=:qtype, grade=:grade, subject=:subject, "
                    "question_text=:question_text, question_html=:question_html, "
                    "options=:options, correct_answer=:correct_answer, image_base64=:image_base64 "
                    "WHERE id=:id"), {**q, "id": ex[0]})
            else:
                db.execute(text(
                    "INSERT INTO paper_questions (paper_id, seq, section, section_idx, qnum, "
                    "qtype, grade, subject, question_text, question_html, options, "
                    "correct_answer, image_base64) "
                    "VALUES (:paper_id, :seq, :section, :section_idx, :qnum, :qtype, "
                    ":grade, :subject, :question_text, :question_html, :options, "
                    ":correct_answer, :image_base64)"), {**q, "paper_id": pid})
    db.flush()
'''


def _ensure_dir():
    QBV_DIR.mkdir(exist_ok=True)


def _next_version():
    _ensure_dir()
    max_n = 0
    for p in QBV_DIR.glob("[0-9][0-9][0-9]_*.py"):
        try:
            max_n = max(max_n, int(p.name[:3]))
        except ValueError:
            pass
    return f"{max_n + 1:03d}"


def _ensure_export_state(db):
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS qb_export_state ("
        "source_url VARCHAR(512) NOT NULL PRIMARY KEY, "
        "version VARCHAR(100) NOT NULL, "
        "exported_at DATETIME)"))


def _ensure_applied(db):
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS qb_migrations ("
        "id INT AUTO_INCREMENT PRIMARY KEY, "
        "version VARCHAR(100) NOT NULL UNIQUE, "
        "applied_at DATETIME)"))


def generate(grade=None, subject=None, dry_run=False):
    """本地：抽取未导出的采集式题库，生成一份版本化更新脚本。"""
    _ensure_dir()
    with SessionLocal() as db:
        _ensure_export_state(db)
        exported = {r[0] for r in db.execute(text("SELECT source_url FROM qb_export_state"))}

        sql = "SELECT id, " + ", ".join(PAPER_COLS) + " FROM papers " \
              "WHERE source_url IS NOT NULL AND source_url <> '' "
        params = {}
        if grade:
            sql += "AND grade = :grade "
            params["grade"] = grade
        if subject:
            sql += "AND subject = :subject "
            params["subject"] = subject
        if exported:
            sql += "AND source_url NOT IN :exported "
            params["exported"] = tuple(exported)
        sql += "ORDER BY id"
        stmt = text(sql)
        # 关键：text() 默认不会展开元组，必须显式 expanding=True，
        # 否则 NOT IN :exported 在多元素（甚至单元素）时会报错。
        if exported:
            stmt = stmt.bindparams(bindparam("exported", expanding=True))
        rows = db.execute(stmt, params).mappings().all()

        papers = []
        for r in rows:
            pid = r["id"]
            qs = db.execute(
                text("SELECT " + ", ".join(Q_COLS) + " FROM paper_questions WHERE paper_id=:pid ORDER BY seq"),
                {"pid": pid}).mappings().all()
            p = {k: r[k] for k in PAPER_COLS}
            p["questions"] = [{k: q[k] for k in Q_COLS} for q in qs]
            papers.append(p)

    if not papers:
        print("无新增题库（所有 papers 已导出，或过滤条件下无未导出试卷）。")
        return None

    import pprint
    version = _next_version()
    slug = datetime.now().strftime("%Y%m%d")
    fname = f"{version}_{slug}.py"
    nq = sum(len(p["questions"]) for p in papers)
    papers_literal = pprint.pformat(papers, width=120, sort_dicts=False)
    header = (
        f'"""{version}（tools/qb_release.py generate 自动生成）\n'
        f'导出时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}\n'
        f'内容：{len(papers)} 份试卷 / {nq} 道采集题目（papers + paper_questions）。\n'
        f'应用：线上执行 `python tools/qb_release.py apply`。\n\n'
        f'upsert 策略：按 source_url 定位/写入 papers，再按 (paper_id, seq) 定位/写入题目，\n'
        f'避免使用本地自增 id，规避本地与线上 paper_id 不一致。\n'
        f'"""\n\n'
    )
    content = header + UPGRADE_BODY.replace("__PAPERS__", papers_literal)
    out = QBV_DIR / fname

    if dry_run:
        print(f"[dry-run] 将生成 {out}：{len(papers)} 份试卷 / {nq} 题（未写入）")
        return None

    out.write_text(content, encoding="utf-8")

    # 记录已导出，保证下一次 generate 只产出增量
    with SessionLocal() as db:
        _ensure_export_state(db)
        now = datetime.now()
        for p in papers:
            db.execute(text(
                "INSERT INTO qb_export_state (source_url, version, exported_at) "
                "VALUES (:s, :v, :t) ON DUPLICATE KEY UPDATE version=:v, exported_at=:t"),
                {"s": p["source_url"], "v": version, "t": now})
        db.commit()

    print(f"已生成 {out}：{len(papers)} 份试卷 / {nq} 题")
    print("   传到线上后执行：python tools/qb_release.py apply")
    return out


def apply():
    """线上：按版本顺序执行未应用的 qb_versions/*.py（幂等 upsert）。"""
    _ensure_dir()
    files = sorted(QBV_DIR.glob("[0-9][0-9][0-9]_*.py"))
    if not files:
        print("qb_versions/ 下没有可执行的更新脚本（先在本地产出再传过来）。")
        return

    with SessionLocal() as db:
        _ensure_applied(db)
        applied = {r[0] for r in db.execute(text("SELECT version FROM qb_migrations"))}
        for f in files:
            ver = f.stem
            if ver in applied:
                continue
            spec = importlib.util.spec_from_file_location(f"qb_{ver}", str(f))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.upgrade(db)
            db.execute(text("INSERT INTO qb_migrations (version, applied_at) VALUES (:v, :t)"),
                       {"v": ver, "t": datetime.now()})
            db.commit()
            print(f"已应用 {ver}")
    print("题库更新应用完成。")


def main():
    """命令行入口：generate / apply 两个子命令。"""
    ap = argparse.ArgumentParser(description="题库更新脚本生成 / 应用（MySQL-only）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="本地增量抽取未导出题库，生成更新脚本")
    g.add_argument("--grade", default=None, help="仅导出指定年级（如 一年级）")
    g.add_argument("--subject", default=None, help="仅导出指定学科（如 数学）")
    g.add_argument("--dry-run", action="store_true", help="仅预览，不写文件、不记录")

    sub.add_parser("apply", help="线上按版本顺序应用未执行的更新脚本")

    args = ap.parse_args()
    if args.cmd == "generate":
        generate(grade=args.grade, subject=args.subject, dry_run=args.dry_run)
    elif args.cmd == "apply":
        apply()


if __name__ == "__main__":
    main()
