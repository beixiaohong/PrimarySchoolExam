"""试卷采集引擎（已合并进主项目）

把原 demo/crawler.py 的能力整合进主项目：
- 爬取第一试卷网列表/下载链接、下载压缩包、解压；
- 用 LibreOffice 把 doc/docx/pdf 转成 HTML（图片 base64 内联）；
- 入库到主库 primary_school.db 的 papers / paper_questions 表；
- 按 source_url 去重，**已采集过的试卷不再采集**；
- 转换后删除 doc 原件（不使用 doc 保存，只保留 HTML 富文本）。

运行方式：python tools/collect_papers.py [--once] [--migrate-demo] [--stats]
"""
import os
import re
import time
import json
import hashlib
import zipfile
import shutil
import subprocess
import base64
import random
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

from sqlalchemy import select, func

from app.config import BASE_DIR
from app.database import SessionLocal
from app.models.paper import Paper, PaperQuestion
from app.services.question_parser import parse_paper

# requests / bs4 / mammoth / pdfplumber / rarfile 等重依赖延迟导入：
# 仅在本模块真正发起网络请求或解析文档时才加载，避免「仅引用即拉起网络依赖」
# 触发运行环境对 import 的拦截。
_REQUESTS = None
_BS4 = None


def _requests():
    global _REQUESTS
    if _REQUESTS is None:
        import requests
        _REQUESTS = requests
    return _REQUESTS


def _bs4():
    global _BS4
    if _BS4 is None:
        try:
            from bs4 import BeautifulSoup
            _BS4 = BeautifulSoup
        except Exception:  # pragma: no cover
            _BS4 = False
    return _BS4


def _lazy(modname):
    """通用延迟导入：mammoth / pdfplumber / rarfile。"""
    import importlib
    try:
        return importlib.import_module(modname)
    except Exception:
        return None


def _soffice_bin():
    """定位 LibreOffice 的 soffice 可执行文件（优先显式路径，回退 PATH）。"""
    import shutil as _sh
    candidates = [
        os.environ.get("LIBREOFFICE_SOFFICE"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "soffice",
    ]
    for c in candidates:
        if not c:
            continue
        if os.path.exists(c):
            return c
        p = _sh.which(c)
        if p:
            return p
    return "soffice"

# ========== 站点与采集参数 ==========
BASE_URL = "https://www.shijuan1.com"

# 学科前缀（首页导航实测）：语文sjyw / 数学sjsx / 英语sjyy / 物理sjwl /
# 化学sjhx / 政治sjzz / 历史sjls / 地理sjdl / 生物sjsw
SUBJECT_PREFIX = [
    ("语文", "sjyw"), ("数学", "sjsx"), ("英语", "sjyy"), ("物理", "sjwl"),
    ("化学", "sjhx"), ("政治", "sjzz"), ("历史", "sjls"), ("地理", "sjdl"), ("生物", "sjsw"),
]
# 年级后缀（首页导航实测）：小学 1-6 / 初中 7-9 / 中考 zk / 高中 g1-g3
GRADE_SUFFIX = [
    ("一年级", "1"), ("二年级", "2"), ("三年级", "3"), ("四年级", "4"),
    ("五年级", "5"), ("六年级", "6"), ("七年级", "7"), ("八年级", "8"),
    ("九年级", "9"), ("中考", "zk"), ("高一", "g1"), ("高二", "g2"), ("高三", "g3"),
]


def build_subject_grade_map():
    """生成 (学科, 年级, 列表页URL后缀) 全量组合；空分类在采集时自动跳过。"""
    out = []
    for subj, prefix in SUBJECT_PREFIX:
        for grade, suffix in GRADE_SUFFIX:
            out.append((subj, grade, f"/a/{prefix}{suffix}/"))
    return out


# 全量九科 ×（一年级~高三 + 中考）。实际采集受下方采样上限控制。
SUBJECT_GRADE_MAP = build_subject_grade_map()

# 采样控制：用户要求总计不到一百份，且各学科/年级尽量均衡覆盖。
# 通过「确定性打散 + 总量上限 + 每类上限」实现。
GLOBAL_MAX_PAPERS = 90     # 全局采集试卷总数上限（< 100）
PER_CATEGORY_MAX = 2       # 单个 (学科,年级) 分类最多采集份数
SHUFFLE_SEED = 20260812    # 确定性打散种子，保证各学科/年级均衡覆盖

REQUEST_INTERVAL = 30      # 多轮之间的休眠（秒）
MAX_PAGES_PER_SUBJECT = 20
DOWNLOAD_DELAY = 1         # 每份试卷下载后休眠（秒）
KEEP_EXTENSIONS = {'.doc', '.docx', '.pdf'}

# 工作目录（处理完即清理，不长期保存 doc 原件）。加入 .gitignore。
CACHE_DIR = BASE_DIR / ".paper_cache"
DOWNLOAD_DIR = CACHE_DIR / "downloads"
EXTRACT_DIR = CACHE_DIR / "extracted"
CLEAN_DIR = CACHE_DIR / "cleaned"
TEMP_HTML_DIR = CACHE_DIR / "html_temp"


# ========== 基础工具 ==========
def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def safe_filename(text):
    return re.sub(r'[\\/*?:"<>|]', '_', text)


def get_html(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = _requests().get(url, headers=headers, timeout=30)
        resp.encoding = 'gb2312'
        return resp.text
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return None


# ========== HTML 转换（图片 base64 内联） ==========
def convert_with_libreoffice(input_file, output_dir):
    ensure_dir(output_dir)
    cmd = [_soffice_bin(), "--headless", "--convert-to", "html", "--outdir", str(output_dir), str(input_file)]
    try:
        # 用 errors='ignore' 容忍 soffice 输出中的非 UTF-8 字节，避免 UnicodeDecodeError
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        html_file = Path(output_dir) / (base_name + ".html")
        if html_file.exists():
            return str(html_file)
        for f in os.listdir(output_dir):
            if f.endswith(".html") and f.startswith(base_name):
                return str(Path(output_dir) / f)
        return None
    except Exception:
        return None


def convert_docx_mammoth(input_file):
    mammoth = _lazy("mammoth")
    if mammoth is None:
        return None
    try:
        with open(input_file, 'rb') as f:
            return mammoth.convert_to_html(f).value
    except Exception:
        return None


def convert_pdf_text(input_file):
    pdfplumber = _lazy("pdfplumber")
    if pdfplumber is None:
        return None
    try:
        parts = []
        with pdfplumber.open(input_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    for line in text.split('\n'):
                        line = line.strip()
                        if line:
                            parts.append(f"<p>{line}</p>")
                for table in page.extract_tables():
                    if table:
                        rows = ["<tr>" + "".join(f"<td>{c or ''}</td>" for c in row) + "</tr>" for row in table]
                        parts.append("<table border='1' cellpadding='5'>" + "".join(rows) + "</table>")
        return "\n".join(parts) if parts else None
    except Exception:
        return None


def embed_images_as_base64(html_file):
    """读取 HTML 文件，将外部图片转为 base64 内联（LibreOffice 通常已内联，此为兜底）。"""
    if not os.path.exists(html_file):
        return None
    with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    bs4 = _bs4()
    if not bs4:
        return html
    soup = bs4(html, 'html.parser')
    base_dir = os.path.dirname(html_file)
    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                '.gif': 'image/gif', '.bmp': 'image/bmp', '.svg': 'image/svg+xml'}
    for img in soup.find_all('img'):
        src = img.get('src')
        if not src or src.startswith('data:'):
            continue
        img_path = src if os.path.isabs(src) else os.path.join(base_dir, src)
        if os.path.exists(img_path):
            try:
                with open(img_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(img_path)[1].lower()
                img['src'] = f"data:{mime_map.get(ext, 'image/png')};base64,{b64}"
            except Exception:
                pass
    return str(soup)


def convert_document_to_html(file_path):
    """文档 -> 自包含 HTML（图片 base64 内联）。失败返回 None。"""
    ext = os.path.splitext(file_path)[1].lower()
    html_file = convert_with_libreoffice(file_path, str(TEMP_HTML_DIR))
    if html_file:
        return embed_images_as_base64(html_file)
    if ext == '.docx':
        # LibreOffice 失败时回退到 mammoth（convert_docx_mammoth 内部懒加载 mammoth）
        return convert_docx_mammoth(file_path)
    if ext == '.pdf':
        return convert_pdf_text(file_path)
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f"<pre>{f.read()}</pre>"
    except Exception:
        return None


# ========== 试卷列表 / 下载链接 ==========
# 详情页链接：/a/<学科前缀><年级后缀>/<数字>.html（覆盖所有学科与年级，不再写死 sjyw）
DETAIL_RE = re.compile(r'^/a/[a-z]+\d*/\d+\.html$')
# 分页链接：list_<分类id>_<页码>.html（如 list_106_2.html），从页面动态提取
LIST_PAGE_RE = re.compile(r'list_\d+_\d+\.html')


def get_paper_list(subject_grade_url, max_pages=MAX_PAGES_PER_SUBJECT):
    """获取某 (学科,年级) 分类下的试卷列表（自动翻页，动态提取分页链接）。"""
    papers = []
    seen = set()

    # 第 1 页 = 分类根；并从中动态提取后续分页链接（不再写死 list_727）
    page_urls = [f"{BASE_URL}{subject_grade_url}"]
    first_html = get_html(page_urls[0])
    bs4 = _bs4()
    if first_html and bs4:
        soup = bs4(first_html, 'lxml')
        for a in soup.find_all('a', href=LIST_PAGE_RE):
            h = a.get('href')
            if h:
                page_urls.append(urljoin(BASE_URL, h))
    # 去重并按 URL 长度/字典序稳定排序，限制页数
    page_urls = sorted(set(page_urls), key=lambda u: (len(u), u))[:max_pages]

    for idx, page_url in enumerate(page_urls, 1):
        print(f"    📄 获取第 {idx} 页: {page_url}")
        html = get_html(page_url)
        bs4 = _bs4()
        if not html or not bs4:
            continue
        soup = bs4(html, 'lxml')
        links = soup.find_all('a', href=DETAIL_RE)
        if not links:
            links = soup.select('td a[href^="/a/"]')
        if not links:
            break
        for a in links:
            href = a.get('href')
            if not href or not DETAIL_RE.match(href):
                continue
            title = a.get_text(strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            papers.append({'title': title, 'detail_url': urljoin(BASE_URL, href)})
        time.sleep(1)
    return papers


def get_download_url(detail_url):
    html = get_html(detail_url)
    bs4 = _bs4()
    if not html or not bs4:
        return None
    soup = bs4(html, 'lxml')
    ul = soup.find('ul', class_='downurllist')
    if ul:
        a = ul.find('a')
        if a and a.get('href'):
            href = a['href']
            return href if href.startswith('http') else urljoin(BASE_URL, href)
    for a in soup.find_all('a'):
        if '本地下载' in a.get_text(strip=True):
            href = a.get('href')
            if href:
                return urljoin(BASE_URL, href)
    matches = re.findall(r'(https?://[^\s"\']*?/uploads/soft/[^\s"\']+\.(?:rar|zip|doc|docx|pdf))', html, re.I)
    return matches[0] if matches else None


def download_file(url, save_dir):
    ensure_dir(save_dir)
    filename = safe_filename(os.path.basename(url.split('?')[0]) or f"download_{int(time.time())}")
    filepath = os.path.join(save_dir, filename)
    if os.path.exists(filepath):
        return filepath
    try:
        resp = _requests().get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60, stream=True)
        resp.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return filepath
    except Exception as e:
        print(f"    ❌ 下载失败: {e}")
        return None


def extract_and_clean(archive_path, extract_dir, clean_dir, keep_exts):
    ext = os.path.splitext(archive_path)[1].lower()
    base_name = os.path.splitext(os.path.basename(archive_path))[0]
    target_dir = os.path.join(extract_dir, base_name)
    ensure_dir(target_dir)
    try:
        if ext == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(target_dir)
        elif ext == '.rar':
            rarfile = _lazy("rarfile")
            if rarfile is None:
                print("    ⚠️ 无法解压 .rar，请安装 rarfile")
                return None
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(target_dir)
        else:
            dest = os.path.join(clean_dir, os.path.basename(archive_path))
            ensure_dir(clean_dir)
            shutil.copy2(archive_path, dest)
            return [dest]
    except Exception as e:
        print(f"    ❌ 解压失败: {e}")
        return None

    kept = []
    for root, _, files in os.walk(target_dir):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.splitext(f)[1].lower() in keep_exts:
                rel = os.path.relpath(root, extract_dir)
                dest_dir = os.path.join(clean_dir, rel)
                ensure_dir(dest_dir)
                dest_path = os.path.join(dest_dir, f)
                counter = 1
                while os.path.exists(dest_path):
                    name, ext2 = os.path.splitext(f)
                    dest_path = os.path.join(dest_dir, f"{name}_{counter}{ext2}")
                    counter += 1
                shutil.copy2(fp, dest_path)
                kept.append(dest_path)
    return kept


# ========== 入库（主库，按 source_url 去重） ==========
def _upsert_paper(session, subject, grade, title, source_url, download_url, html_content, answers):
    """按 source_url 去重；存在则更新内容，返回 (paper_id, is_new)。"""
    existing = session.execute(
        select(Paper).where(Paper.source_url == source_url)
    ).scalar_one_or_none()
    if existing:
        existing.html_content = html_content or existing.html_content
        existing.answers = answers if answers is not None else existing.answers
        existing.subject = subject
        existing.grade = grade
        existing.title = title
        session.commit()
        return existing.id, False
    paper = Paper(
        subject=subject, grade=grade, title=title,
        source_url=source_url, download_url=download_url,
        html_content=html_content or "", answers=answers or "",
        total_questions=0,
    )
    session.add(paper)
    session.commit()
    return paper.id, True


def _store_questions(session, paper_id, html_content):
    """解析题目并写入 paper_questions（幂等：先删后插），更新题数。"""
    questions, answers_text = parse_paper(html_content)
    session.execute(
        PaperQuestion.__table__.delete().where(PaperQuestion.paper_id == paper_id)
    )
    seq = 0
    for q in questions:
        seq += 1
        options = json.dumps(q['options'], ensure_ascii=False) if q['options'] else ""
        image_b64 = "\n".join(q['images']) if q['images'] else ""
        session.add(PaperQuestion(
            paper_id=paper_id, seq=seq,
            section=q['section'], section_idx=q['section_idx'], qnum=q['qnum'],
            qtype=q['type'],
            question_text=q['text'], question_html=q['html'],
            options=options, correct_answer=q['answer'] or "",
            image_base64=image_b64,
        ))
    paper = session.get(Paper, paper_id)
    if paper:
        paper.total_questions = len(questions)
        paper.answers = answers_text or paper.answers
    session.commit()
    return len(questions)


def store_paper_full(subject, grade, title, source_url, download_url, html_content):
    """对外封装：去重入库 + 解析题目。返回 (paper_id, is_new, q_count)。"""
    with SessionLocal() as session:
        paper_id, is_new = _upsert_paper(
            session, subject, grade, title, source_url, download_url, html_content, None)
        q_count = _store_questions(session, paper_id, html_content) if html_content else 0
        return paper_id, is_new, q_count


# ========== 主采集循环 ==========
def run_collection(once=False):
    ensure_dir(DOWNLOAD_DIR)
    ensure_dir(EXTRACT_DIR)
    ensure_dir(CLEAN_DIR)
    ensure_dir(TEMP_HTML_DIR)

    # 确定性打散分类顺序，使采样在「各学科 / 各年级」间均衡覆盖
    categories = list(SUBJECT_GRADE_MAP)
    random.Random(SHUFFLE_SEED).shuffle(categories)

    collected_total = 0
    while True:
        try:
            for subject_name, grade_name, url_suffix in categories:
                if collected_total >= GLOBAL_MAX_PAPERS:
                    break
                print(f"\n📚 [{datetime.now():%Y-%m-%d %H:%M:%S}] 处理: {subject_name} - {grade_name}")
                papers = get_paper_list(url_suffix)
                if not papers:
                    print(f"  ⚠️ 该分类无试卷（可能不存在），跳过")
                    continue
                print(f"  找到 {len(papers)} 份试卷，本类最多采 {PER_CATEGORY_MAX} 份")

                new_count = 0
                for paper in papers:
                    if collected_total >= GLOBAL_MAX_PAPERS:
                        break
                    if new_count >= PER_CATEGORY_MAX:
                        break
                    source_url = paper['detail_url']
                    # 去重：已采集过的不再采集
                    with SessionLocal() as session:
                        if session.execute(
                            select(Paper.id).where(Paper.source_url == source_url)
                        ).first():
                            print(f"  ⏭ 已采集，跳过: {paper['title']}")
                            continue

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

                    for doc_path in kept_files:
                        if collected_total >= GLOBAL_MAX_PAPERS:
                            break
                        print(f"  📄 {paper['title']}")
                        html_content = convert_document_to_html(doc_path)
                        if html_content:
                            print(f"    ✅ 转换成功，HTML 长度: {len(html_content)} 字符")
                        else:
                            print(f"    ⚠️ 转换失败，仅记录元信息")
                        paper_id, _is_new, q_count = store_paper_full(
                            subject_name, grade_name, paper['title'],
                            source_url, download_url, html_content)
                        print(f"    📝 入库试卷 ID={paper_id}，题目 {q_count} 道")

                        # 不使用 doc 保存：转换入库后删除原件
                        try:
                            os.remove(doc_path)
                        except Exception:
                            pass

                    # 删除压缩包，避免长期占用磁盘
                    try:
                        os.remove(archive_path)
                    except Exception:
                        pass

                    new_count += 1
                    collected_total += 1
                    time.sleep(DOWNLOAD_DELAY)

                print(f"  ✅ {subject_name}-{grade_name} 完成，新增 {new_count} 份（累计 {collected_total}/{GLOBAL_MAX_PAPERS}）")

            if once or collected_total >= GLOBAL_MAX_PAPERS:
                print("\n✅ 单次采集完成（--once 或已达总量上限）")
                break
            print(f"\n💤 本轮完成，等待 {REQUEST_INTERVAL} 秒...")
            time.sleep(REQUEST_INTERVAL)

        except KeyboardInterrupt:
            print("\n🛑 用户中断，退出")
            break
        except Exception as e:
            print(f"❌ 异常: {e}")
            if once:
                break
            time.sleep(REQUEST_INTERVAL)


# ========== 迁移 demo 已采集试卷到主库 ==========
def migrate_demo_papers(demo_db_path=None):
    """把 demo/learning.db 中已采集的试卷（含 HTML）迁入主库，确保不再重复采集。"""
    if demo_db_path is None:
        demo_db_path = BASE_DIR / "demo" / "learning.db"
    if not os.path.exists(demo_db_path):
        print(f"⚠️ 未找到 demo 数据库: {demo_db_path}")
        return 0, 0

    import sqlite3
    src = sqlite3.connect(str(demo_db_path))
    cur = src.cursor()

    # course_id -> (subject, grade)
    course_map = {}
    try:
        for cid, sid, gid in cur.execute(
            "SELECT c.id, c.subject_id, c.grade_id FROM courses c"):
            sname = cur.execute("SELECT name FROM subjects WHERE id=?", (sid,)).fetchone()
            gname = cur.execute("SELECT name FROM grades WHERE id=?", (gid,)).fetchone()
            course_map[cid] = (sname[0] if sname else "", gname[0] if gname else "")
    except Exception as e:
        print(f"  ⚠️ 读取 course 映射失败: {e}")
        course_map = {}

    rows = cur.execute(
        "SELECT id, course_id, title, source_url, download_url, html_content, answers, total_questions "
        "FROM papers WHERE html_content IS NOT NULL"
    ).fetchall()
    src.close()

    migrated = 0
    q_total = 0
    with SessionLocal() as session:
        for pid, course_id, title, source_url, download_url, html_content, answers, total in rows:
            subject, grade = course_map.get(course_id, ("", ""))
            paper_id, is_new = _upsert_paper(
                session, subject, grade, title, source_url or f"demo:{pid}",
                download_url or "", html_content, answers)
            if is_new:
                migrated += 1
            q = _store_questions(session, paper_id, html_content)
            q_total += q
    print(f"✅ 迁移完成：新增试卷 {migrated} 份，解析题目 {q_total} 道")
    return migrated, q_total


def print_stats():
    with SessionLocal() as session:
        papers = session.execute(select(func.count(Paper.id))).scalar() or 0
        questions = session.execute(select(func.count(PaperQuestion.id))).scalar() or 0
        with_img = session.execute(
            select(func.count(PaperQuestion.id)).where(PaperQuestion.image_base64 != "")
        ).scalar() or 0
        with_ans = session.execute(
            select(func.count(PaperQuestion.id)).where(PaperQuestion.correct_answer != "")
        ).scalar() or 0
    print(f"📊 题库统计：试卷 {papers} 份 | 题目 {questions} 道（含图 {with_img} | 含答案 {with_ans}）")


if __name__ == "__main__":
    run_collection(once=True)
