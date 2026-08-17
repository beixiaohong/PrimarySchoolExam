"""每日试卷采集（本地 SQLite 版，每日一个文件）

与 tools/collect_papers.py（写 MySQL 主库）不同，本脚本把每天抓到的新卷写入
独立的本地 SQLite 文件：

    data/papers_YYYY-MM-DD.sqlite

需求对照（用户要求）：
- 来源：第一试卷网 https://www.shijuan1.com
- 数量：每天约 200 份新卷（--daily-limit，默认 200）
- 去重：按 source_url 去重，且跨天不重复抓取（持久化 registry：
       data/scrape_registry.sqlite，并兜底扫描已有 daily 文件）
- 年份：仅最近 10 年（标题年份过滤，YEAR_MIN）
- 学段优先级：初中 → 小学 → 高中（STAGE_CAP 配额保证小/高中都覆盖）
- 学科：九大学科全覆盖（ORDERED_CATEGORY_MAP 按学段重排）
- AI 答案：采集后调用 AI（智谱 GLM 等，复用 app.services.ai）补全 correct_answer，
          已有来源答案不覆盖；限流时连续失败即优雅放弃，绝不死循环刷接口
- 入库：试卷转 HTML 富文本（base64 内联图片）存 papers / paper_questions

复用既有能力：app.services.paper_crawler 的爬取/下载/转换/年份过滤/分类重排，
app.services.question_parser 的题文解析，app.services.answer_generator 的单题 AI 补全。
存储层为独立 SQLite，不触碰 MySQL 共享层。
"""
import argparse
import os
import sys
import time
import sqlite3
import traceback
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models.paper import Paper, PaperQuestion  # noqa: E402
from app.services.question_parser import parse_paper  # noqa: E402
from app.services.answer_generator import generate_answer_for, ai_enabled  # noqa: E402

# ── 复用采集原语（爬取/下载/转换/年份过滤/分类重排）──
from app.services.paper_crawler import (  # noqa: E402
    get_paper_list, get_download_url, download_file, extract_and_clean,
    convert_document_to_html, _select_exam_doc, _safe_remove, ensure_dir,
    KEEP_EXTENSIONS, DOWNLOAD_DIR, EXTRACT_DIR, CLEAN_DIR, TEMP_HTML_DIR,
    ORDERED_CATEGORY_MAP, GRADE_STAGE, STAGE_CAP, PER_CATEGORY_CAP,
    DAILY_MAX_PAPERS, parse_year, YEAR_MIN, CURRENT_YEAR,
)

# ── 路径与配额 ──
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_PATH = DATA_DIR / "scrape_registry.sqlite"

REQUEST_INTERVAL = 0       # 单轮之间休眠（本脚本一轮即退出，无需循环休眠）
DOWNLOAD_DELAY = 1         # 每份试卷下载后休眠（秒），降低被封风险
MAX_HTML_CHARS = 12 * 1024 * 1024  # 单卷 HTML 上限 12MB，超出仅记元信息

# AI 答案补全保护：连续失败达到阈值即判定 AI 暂不可用，放弃本次补全，避免死循环刷接口
MAX_CONSECUTIVE_FAILS = 10


# ========== 跨天去重 registry ==========
def _registry_conn():
    conn = sqlite3.connect(str(REGISTRY_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scraped ("
        "source_url TEXT PRIMARY KEY, paper_date TEXT, stage TEXT, "
        "subject TEXT, grade TEXT, stored_file TEXT)"
    )
    return conn


def load_scraped_set():
    """构建『已采集』source_url 集合：registry + 已有 daily 文件（兜底）。

    返回 set；同时尽力从 MySQL 主库种子历史已采集卷，避免重复下载。
    """
    scraped = set()
    # 1) registry（主记录）
    if REGISTRY_PATH.exists():
        try:
            c = sqlite3.connect(str(REGISTRY_PATH))
            for (u,) in c.execute("SELECT source_url FROM scraped"):
                scraped.add(u)
            c.close()
        except Exception:
            pass
    # 2) 已有 daily 文件（兜底，防止 registry 损坏丢记录）
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("papers_*.sqlite"):
            try:
                c = sqlite3.connect(str(f))
                for (u,) in c.execute("SELECT source_url FROM papers"):
                    if u:
                        scraped.add(u)
                c.close()
            except Exception:
                pass
    # 3) MySQL 主库种子（历史已在主库采集的卷），尽力而为，失败跳过
    try:
        from sqlalchemy import text
        from app.database import engine
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT source_url FROM papers "
                     "WHERE source_url IS NOT NULL AND source_url <> ''")
            ).fetchall()
        for r in rows:
            if r[0]:
                scraped.add(r[0])
        print(f"  (已从 MySQL 主库种子 {len(rows)} 条历史 source_url，避免重复抓取)")
    except Exception as e:
        print(f"  (MySQL 种子跳过：{e})")
    return scraped


def mark_scraped(source_url, paper_date, stage, subject, grade, stored_file):
    try:
        c = _registry_conn()
        c.execute(
            "INSERT OR IGNORE INTO scraped "
            "(source_url, paper_date, stage, subject, grade, stored_file) "
            "VALUES (?,?,?,?,?,?)",
            (source_url, paper_date, stage, subject, grade, stored_file),
        )
        c.commit()
        c.close()
    except Exception:
        pass


# ========== 每日 SQLite 引擎 ==========
def daily_db_path(d: date) -> Path:
    return DATA_DIR / f"papers_{d.isoformat()}.sqlite"


def make_daily_engine(d: date):
    path = daily_db_path(d)
    ensure_dir(str(path.parent))
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    # 仅建采集两张表（复用模型定义；MEDIUMTEXT 在 sqlite dialect 自动降级 TEXT）
    Base.metadata.create_all(bind=eng, tables=[Paper.__table__, PaperQuestion.__table__])
    return eng, path


# ========== 入库（每日 SQLite，按 source_url 去重） ==========
def _upsert_paper(session, subject, grade, title, source_url, download_url, html_content, year):
    existing = session.execute(
        select(Paper).where(Paper.source_url == source_url)
    ).scalar_one_or_none()
    if existing:
        existing.html_content = html_content or existing.html_content
        existing.subject = subject
        existing.grade = grade
        existing.title = title
        if year:
            existing.year = year
        session.commit()
        return existing.id, False
    paper = Paper(
        subject=subject, grade=grade, title=title,
        source_url=source_url, download_url=download_url,
        html_content=html_content or "", answers="",
        total_questions=0, year=year,
    )
    session.add(paper)
    session.commit()
    return paper.id, True


def _store_questions(session, paper_id, html_content):
    paper = session.get(Paper, paper_id)
    grade = paper.grade if paper else ""
    subject = paper.subject if paper else ""
    questions, answers_text = parse_paper(html_content)
    session.execute(
        PaperQuestion.__table__.delete().where(PaperQuestion.paper_id == paper_id)
    )
    seq = 0
    for q in questions:
        seq += 1
        options = ""
        try:
            options = __import__("json").dumps(q['options'], ensure_ascii=False) if q['options'] else ""
        except Exception:
            options = ""
        image_b64 = "\n".join(q['images']) if q['images'] else ""
        session.add(PaperQuestion(
            paper_id=paper_id, seq=seq,
            section=q['section'], section_idx=q['section_idx'], qnum=q['qnum'],
            qtype=q['type'],
            question_text=q['text'], question_html=q['html'],
            options=options, correct_answer=q['answer'] or "",
            image_base64=image_b64,
            grade=grade or "", subject=subject or "",
        ))
    if paper:
        paper.total_questions = len(questions)
        paper.answers = answers_text or paper.answers
    session.commit()
    return len(questions)


def store_paper_full(session_factory, subject, grade, title, source_url,
                     download_url, html_content, year):
    if html_content and len(html_content) > MAX_HTML_CHARS:
        print(f"    ⚠️ HTML 过大（约 {len(html_content)//1024//1024}MB），超出 12MB 上限，仅记录元信息")
        html_content = ""
    with session_factory() as session:
        paper_id, is_new = _upsert_paper(
            session, subject, grade, title, source_url, download_url, html_content, year)
        q_count = _store_questions(session, paper_id, html_content) if html_content else 0
    return paper_id, is_new, q_count


# ========== AI 答案补全（每日文件，best-effort） ==========
def fill_paper_answers(session_factory, paper_id, state):
    """为单卷未作答的题目调 AI 补全；受全局 budget 与连续失败阈值约束。

    state: {'processed','ok','skipped','consecutive','budget_left','give_up'}
    - DB 会话在 AI 调用前已关闭（外部阻塞调用不持连接）；
    - 单题失败计入 consecutive，达 MAX_CONSECUTIVE_FAILS 即置 give_up 退出。
    """
    if state.get("give_up"):
        return
    if state["budget_left"] is not None and state["budget_left"] <= 0:
        return
    with session_factory() as s:
        rows = s.query(PaperQuestion).filter(
            PaperQuestion.paper_id == paper_id,
            (PaperQuestion.correct_answer == None) | (PaperQuestion.correct_answer == ""),
        ).all()
    if not rows:
        return
    for pq in rows:
        if state.get("give_up"):
            break
        if state["budget_left"] is not None and state["budget_left"] <= 0:
            break
        ans = generate_answer_for(pq)  # 此刻无 DB 会话持有，符合「外部调用不持连接」铁律
        if ans is None:
            state["skipped"] += 1
            state["consecutive"] += 1
            if state["consecutive"] >= MAX_CONSECUTIVE_FAILS:
                print(f"    ⚠️ 连续 {MAX_CONSECUTIVE_FAILS} 题 AI 失败（多为限流/超时），"
                      f"判定 AI 暂不可用，放弃本次补全，剩余题目留待后续运行")
                state["give_up"] = True
                break
            time.sleep(2)
            continue
        state["consecutive"] = 0
        state["ok"] += 1
        state["processed"] += 1
        if state["budget_left"] is not None:
            state["budget_left"] -= 1
        # 短会话写回答案（单独会话，写完即关）
        try:
            with session_factory() as s2:
                obj = s2.get(PaperQuestion, pq.id)
                if obj and not obj.correct_answer:
                    obj.correct_answer = "[AI生成] " + ans
                    s2.commit()
        except Exception:
            pass


# ========== 历史遗留/积压答案补全（跨所有 daily 文件） ==========
def backfill_files(file_paths, backlog_cap=0):
    """扫描给定 daily 文件（建议按日期从旧到新），补齐空答案。

    - 复用 fill_paper_answers（外部调用不持连接，符合铁律）；
    - 受 backlog_cap 预算 + 连续失败守卫约束；
    - backlog_cap=0 表示不限额（仍受连续失败守卫约束）。
    返回 (processed, ok, skipped)。
    """
    if not ai_enabled():
        print("🤖 AI 不可用，跳过积压补答（试卷已入库，答案留待后续运行）")
        return 0, 0, 0
    budget = backlog_cap if backlog_cap and backlog_cap > 0 else None
    state = {"processed": 0, "ok": 0, "skipped": 0,
             "consecutive": 0, "budget_left": budget, "give_up": False}
    files_done = 0
    files_total_empty = 0
    for f in file_paths:
        if state["give_up"] or (state["budget_left"] is not None and state["budget_left"] <= 0):
            break
        try:
            eng = create_engine(f"sqlite:///{f}", connect_args={"check_same_thread": False})
            SF = sessionmaker(bind=eng, autoflush=False, autocommit=False)
        except Exception as e:
            print(f"  ⚠️ 无法打开 {f.name}，跳过：{e}")
            continue
        with SF() as s:
            ne = s.query(PaperQuestion).filter(
                (PaperQuestion.correct_answer == None) | (PaperQuestion.correct_answer == "")).count()
        if ne == 0:
            continue
        files_total_empty += ne
        files_done += 1
        print(f"\n📁 {f.name}：待补 {ne} 题")
        with SF() as s:
            pids = [r[0] for r in s.query(PaperQuestion.paper_id).filter(
                (PaperQuestion.correct_answer == None) | (PaperQuestion.correct_answer == "")).distinct()]
        for pid in pids:
            if state["give_up"] or (state["budget_left"] is not None and state["budget_left"] <= 0):
                break
            fill_paper_answers(SF, pid, state)
    print(f"\n🔁 积压补答完成：处理文件 {files_done} 个（含待补 {files_total_empty} 题）；"
          f"本次处理 {state['processed']}，成功 {state['ok']}，跳过 {state['skipped']}")
    return state["processed"], state["ok"], state["skipped"]


def all_daily_files():
    """返回 data/papers_*.sqlite，按日期从旧到新排序（历史优先）。"""
    files = sorted(DATA_DIR.glob("papers_*.sqlite"),
                   key=lambda p: p.name)
    return files


# ========== 主流程 ==========
def run(d: date, daily_limit=DAILY_MAX_PAPERS, answer_cap=0, max_pages=2,
        fill_answers=True, backlog_cap=0, subjects=None):
    ensure_dir(str(DOWNLOAD_DIR))
    ensure_dir(str(EXTRACT_DIR))
    ensure_dir(str(CLEAN_DIR))
    ensure_dir(str(TEMP_HTML_DIR))

    eng, db_path = make_daily_engine(d)
    SessionFactory = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    paper_date = d.isoformat()

    scraped = load_scraped_set()
    print(f"📁 本日 SQLite 文件：{db_path}")
    print(f"🗂 已采集去重集合大小：{len(scraped)}（含历史 MySQL / 历史 daily 文件）")
    print(f"📌 本日采集上限 {daily_limit} 份新卷（学段优先级 初中→小学→高中；"
          f"学段配额 初中{STAGE_CAP['初中']}/小学{STAGE_CAP['小学']}/高中{STAGE_CAP['高中']}；"
          f"单(学科,年级)上限 {PER_CATEGORY_CAP}；仅 {YEAR_MIN} 年起，近 {CURRENT_YEAR - YEAR_MIN} 年）")

    collected_total = 0
    new_paper_ids = []
    stage_collected = {k: 0 for k in STAGE_CAP}
    cat_count = {}  # (subject, grade) -> 今日已采数

    started = datetime.now()
    # 按学段优先级（初中→小学→高中）重排分类，保证优先采集初中、各学科均衡覆盖
    for subject_name, grade_name, url_suffix in ORDERED_CATEGORY_MAP:
        if subjects and subject_name not in subjects:
            continue
        if collected_total >= daily_limit:
            break
        stage = GRADE_STAGE.get(grade_name, "初中")
        if stage_collected.get(stage, 0) >= STAGE_CAP.get(stage, 10):
            continue
        if cat_count.get((subject_name, grade_name), 0) >= PER_CATEGORY_CAP:
            continue

        print(f"\n📚 [{datetime.now():%Y-%m-%d %H:%M:%S}] 处理: {subject_name} - {grade_name}（{stage}）")
        try:
            papers = get_paper_list(url_suffix, max_pages=max_pages)
        except Exception as e:
            print(f"  ❌ 列表获取异常，跳过本类：{type(e).__name__}: {e}")
            traceback.print_exc()
            continue
        if not papers:
            print(f"  ⚠️ 该分类无（近10年）试卷，跳过")
            continue
        print(f"  找到 {len(papers)} 份（近10年），本类最多采 {PER_CATEGORY_CAP} 份")

        new_count = 0
        for paper in papers:
            if collected_total >= daily_limit:
                break
            if new_count >= PER_CATEGORY_CAP:
                break
            source_url = paper['detail_url']
            if source_url in scraped:
                print(f"  ⏭ 已采集，跳过: {paper['title'][:40]}")
                continue
            try:
                download_url = get_download_url(source_url)
                if not download_url:
                    continue
                archive_path = download_file(download_url, str(DOWNLOAD_DIR))
                if not archive_path:
                    continue
                kept_files = extract_and_clean(
                    archive_path, str(EXTRACT_DIR), str(CLEAN_DIR), KEEP_EXTENSIONS)
                if not kept_files:
                    continue

                for doc_path in _select_exam_doc(kept_files):
                    if collected_total >= daily_limit:
                        break
                    yr = parse_year(paper['title']) or 0
                    print(f"  📄 {paper['title'][:48]}")
                    html_content = convert_document_to_html(doc_path)
                    if html_content:
                        print(f"    ✅ 转换成功，HTML {len(html_content)} 字符")
                    else:
                        print(f"    ⚠️ 转换失败，仅记录元信息")
                    paper_id, _is_new, q_count = store_paper_full(
                        SessionFactory, subject_name, grade_name, paper['title'],
                        source_url, download_url, html_content, year=yr)
                    print(f"    📝 入库 ID={paper_id}，题目 {q_count} 道")
                    new_paper_ids.append(paper_id)
                    scraped.add(source_url)
                    mark_scraped(source_url, paper_date, stage, subject_name, grade_name, str(db_path))
                    _safe_remove(doc_path)

                for f in kept_files:
                    _safe_remove(f)
                _safe_remove(archive_path)

                new_count += 1
                collected_total += 1
                stage_collected[stage] = stage_collected.get(stage, 0) + 1
                cat_count[(subject_name, grade_name)] = cat_count.get((subject_name, grade_name), 0) + 1
                time.sleep(DOWNLOAD_DELAY)
            except BaseException as e:
                print(f"  ⚠️ 处理试卷异常，跳过: {paper['title'][:40]} -> {type(e).__name__}: {e}")
                traceback.print_exc()
                try:
                    if 'archive_path' in dir() and archive_path:
                        _safe_remove(archive_path)
                except BaseException:
                    pass
                continue

        print(f"  ✅ {subject_name}-{grade_name} 完成，新增 {new_count} 份"
              f"（本次累计 {collected_total}/{daily_limit}）")

    print(f"\n✅ 采集阶段完成：本次新增 {collected_total} 份试卷（耗时 {datetime.now()-started}）")

    # ── 阶段二：AI 答案补全（best-effort，受 budget + 连续失败守卫约束）──
    if fill_answers and new_paper_ids:
        if not ai_enabled():
            print("🤖 AI 不可用，跳过答案补全（试卷已入库，答案留待后续运行）")
        else:
            budget = answer_cap if answer_cap and answer_cap > 0 else None
            state = {"processed": 0, "ok": 0, "skipped": 0,
                     "consecutive": 0, "budget_left": budget, "give_up": False}
            print(f"\n🤖 为本次新采集的 {len(new_paper_ids)} 份试卷补全 AI 答案"
                  f"{('（本日上限 ' + str(budget) + ' 题）') if budget else '（不限额）'}...")
            af_start = datetime.now()
            for pid in new_paper_ids:
                if state["give_up"] or (state["budget_left"] is not None and state["budget_left"] <= 0):
                    break
                fill_paper_answers(SessionFactory, pid, state)
            print(f"  🤖 答案补全：处理 {state['processed']}，成功 {state['ok']}，"
                  f"跳过 {state['skipped']}（耗时 {datetime.now()-af_start}）")

    # ── 阶段三：历史遗留/积压补答（跨所有 daily 文件，含本日超出 answer-cap 的剩余）──
    # 保证『历史遗留的未答题目』也能逐步补上；所有 daily 文件按日期从旧到新优先级处理。
    if backlog_cap and backlog_cap > 0 and ai_enabled():
        print(f"\n🔁 阶段三：补齐历史/积压未答题目（预算 {backlog_cap} 题）...")
        bl_start = datetime.now()
        bf = all_daily_files()
        backfill_files(bf, backlog_cap=backlog_cap)
        print(f"  ⏱ 积压补答耗时 {datetime.now()-bl_start}")

    print_stats(SessionFactory, db_path)
    return new_paper_ids


def print_stats(SessionFactory, db_path):
    with SessionFactory() as s:
        papers = s.query(Paper).count()
        questions = s.query(PaperQuestion).count()
        with_img = s.query(PaperQuestion).filter(PaperQuestion.image_base64 != "").count()
        with_ans = s.query(PaperQuestion).filter(PaperQuestion.correct_answer != "").count()
        # 学段分布
        from sqlalchemy import case
        stage_expr = case(
            {g: st for g, st in GRADE_STAGE.items()}, value=Paper.grade, else_="其他")
        dist = {}
        for st, cnt in s.query(stage_expr, func.count(Paper.id)).group_by(stage_expr).all():
            dist[st] = cnt
    print(f"\n📊 本日文件 {db_path.name} 统计：")
    print(f"   试卷 {papers} 份 | 题目 {questions} 道（含图 {with_img} | 含答案 {with_ans}）")
    print(f"   学段分布：初中 {dist.get('初中',0)} / 小学 {dist.get('小学',0)} / 高中 {dist.get('高中',0)}")
    miss = questions - with_ans
    if miss:
        print(f"   ⚠️ 仍有 {miss} 道题目待补答案（限流时留待后续运行补全）")


def main():
    parser = argparse.ArgumentParser(description="每日试卷采集（本地 SQLite 版，每日一个文件）")
    parser.add_argument("--date", default=None,
                        help="指定日期 YYYY-MM-DD（默认今天）；决定 SQLite 文件名")
    parser.add_argument("--daily-limit", type=int, default=DAILY_MAX_PAPERS,
                        help="本日采集新卷上限（默认 200）")
    parser.add_argument("--answer-cap", type=int, default=0,
                        help="本日 AI 答案补全上限（0=不限额，受连续失败守卫约束）")
    parser.add_argument("--max-pages", type=int, default=2,
                        help="每个 (学科,年级) 分类最多翻页数（默认 2，覆盖约6份新卷足够）")
    parser.add_argument("--no-answers", action="store_true",
                        help="仅采集入库，不调用 AI 补全答案")
    parser.add_argument("--backlog-cap", type=int, default=0,
                        help="每日运行结束后，跨所有 daily 文件补齐历史/积压未答题目的预算"
                             "（0=不补；与 --answer-cap 独立）")
    parser.add_argument("--fill-backlog", action="store_true",
                        help="独立模式：仅补齐所有 daily 文件里的未答题目（不采集新卷）")
    parser.add_argument("--subjects", default=None,
                        help="仅采集指定学科（逗号分隔，如 历史,地理,生物），用于补齐缺失学科；"
                             "不影响去重与年份过滤")
    args = parser.parse_args()

    if args.fill_backlog:
        # 独立补答模式：扫描所有 daily 文件，补齐空答案（预算由 --backlog-cap 决定）
        cap = args.backlog_cap if args.backlog_cap and args.backlog_cap > 0 else 5000
        print(f"🔁 独立积压补答模式：扫描所有 daily 文件，预算 {cap} 题")
        backfill_files(all_daily_files(), backlog_cap=cap)
        return

    d = date.fromisoformat(args.date) if args.date else date.today()
    subjects = set(s.strip() for s in args.subjects.split(",")) if args.subjects else None
    run(d, daily_limit=args.daily_limit, answer_cap=args.answer_cap,
        max_pages=args.max_pages, fill_answers=not args.no_answers,
        backlog_cap=args.backlog_cap, subjects=subjects)


if __name__ == "__main__":
    main()
