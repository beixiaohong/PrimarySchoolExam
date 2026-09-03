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
import traceback
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

from sqlalchemy import select, func

from app.config import BASE_DIR
from app.database import collection_session, init_collection_db
from app.models.paper import Paper, PaperQuestion
from app.domains.content.services.question_parser import parse_paper

# ========== 跨日去重注册表（持久化已抓 URL，确保「之前没抓过的」跨天生效） ==========
# 每日 SQLite 数据文件是「当天」独立的（见 tools/collect_daily.py），因此不能用
# 每日库内的 Paper.source_url 做去重（否则每天都会把同一批卷子重新抓一遍）。
# 这里用一份与每日文件解耦的持久化 SQLite 记录所有曾抓过的 source_url，
# 由 paper_crawler 在抓取前查询、抓取后写入，跨天/跨进程均生效。
import sqlite3 as _sqlite3

REGISTRY_PATH = BASE_DIR / "data" / "scrape_registry.sqlite"
_registry_conn = None


def _registry_conn_get():
    """懒加载注册表连接（进程级单例），确保表存在。"""
    global _registry_conn
    if _registry_conn is None:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _registry_conn = _sqlite3.connect(str(REGISTRY_PATH), timeout=30)
        _registry_conn.execute(
            "CREATE TABLE IF NOT EXISTS scraped ("
            "url TEXT PRIMARY KEY, day TEXT, subject TEXT, grade TEXT, "
            "title TEXT, ts TEXT)"
        )
        _registry_conn.commit()
    return _registry_conn


def is_scraped(url):
    """该 source_url 是否已在历史中抓过（跨天去重核心）。"""
    if not url:
        return False
    try:
        cur = _registry_conn_get().execute("SELECT 1 FROM scraped WHERE url=?", (url,))
        return cur.fetchone() is not None
    except Exception:
        return False


def mark_scraped(url, day, subject, grade, title):
    """记录已抓 URL（幂等，重复写入忽略）。"""
    if not url:
        return
    try:
        _registry_conn_get().execute(
            "INSERT OR IGNORE INTO scraped(url, day, subject, grade, title, ts) "
            "VALUES(?,?,?,?,?,?)",
            (url, day, subject, grade, title, datetime.now().isoformat(timespec="seconds")))
        _registry_conn_get().commit()
    except Exception:
        pass


def count_scraped_today(subject, grade, day):
    """当日该 (学科,年级) 已抓份数（用于 PER_CATEGORY_CAP 每日配额）。"""
    try:
        cur = _registry_conn_get().execute(
            "SELECT COUNT(*) FROM scraped WHERE subject=? AND grade=? AND day=?",
            (subject, grade, day))
        return cur.fetchone()[0]
    except Exception:
        return 0


def seed_registry_from_staging(staging_path=None):
    """从既有 staging 库（data/collected_staging.sqlite）导入 source_url，
    避免切换到每日文件后把历史已采卷又抓一遍。仅当注册表尚未种子化时执行。"""
    if is_scraped("__seeded__marker__"):
        return 0
    if staging_path is None:
        staging_path = BASE_DIR / "data" / "collected_staging.sqlite"
    if not os.path.exists(str(staging_path)):
        return 0
    try:
        src = _sqlite3.connect(str(staging_path), timeout=30)
        rows = src.execute(
            "SELECT source_url, subject, grade, title FROM papers "
            "WHERE source_url IS NOT NULL AND source_url <> ''"
        ).fetchall()
        src.close()
    except Exception:
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    n = 0
    for url, subject, grade, title in rows:
        try:
            _registry_conn_get().execute(
                "INSERT OR IGNORE INTO scraped(url, day, subject, grade, title, ts) "
                "VALUES(?,?,?,?,?,?)",
                (url, "legacy", subject or "", grade or "", title or "", today))
            n += 1
        except Exception:
            pass
    # 写入种子标记，避免重复 seed（也作为一条普通记录，不影响去重）
    try:
        _registry_conn_get().execute(
            "INSERT OR IGNORE INTO scraped(url, day, subject, grade, title, ts) "
            "VALUES(?,?,?,?,?,?)", ("__seeded__marker__", "legacy", "", "", "", today))
    except Exception:
        pass
    _registry_conn_get().commit()
    print(f"🌱 已从历史 staging 库导入 {n} 条已抓记录到跨日注册表")
    return n


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


# 全量九科 ×（一年级~高三 + 中考），按学段优先级（初中→小学→高中）重排。
SUBJECT_GRADE_MAP = build_subject_grade_map()

# ── 学段优先级（用户要求：优先初中，再小学，最后高中）──
GRADE_STAGE = {
    "七年级": "初中", "八年级": "初中", "九年级": "初中", "中考": "初中",
    "一年级": "小学", "二年级": "小学", "三年级": "小学",
    "四年级": "小学", "五年级": "小学", "六年级": "小学",
    "高一": "高中", "高二": "高中", "高三": "高中",
}
STAGE_PRIORITY = ["初中", "小学", "高中"]


def build_ordered_category_map():
    """按学段优先级重排分类（初中→小学→高中），保证优先采集初中。

    关键修复（2026-08-17）：改为「年级外层、学科内层」轮转，
    即每个年级内九科依次轮转（语文,数学,...,生物），保证每日配额切片
    （前 N 个分类）一定能覆盖全部九大学科，而不是被靠前的学科（语文/数学…）
    把 200 份额度吃光、导致历史/地理/生物永远采不到。
    """
    by_stage = {s: [] for s in STAGE_PRIORITY}
    for stage in STAGE_PRIORITY:
        grades = [(g, suf) for (g, suf) in GRADE_SUFFIX
                  if GRADE_STAGE.get(g, "初中") == stage]
        for grade, suffix in grades:
            for subj, prefix in SUBJECT_PREFIX:
                by_stage[stage].append((subj, grade, f"/a/{prefix}{suffix}/"))
    ordered = []
    for s in STAGE_PRIORITY:
        ordered.extend(by_stage[s])
    return ordered


ORDERED_CATEGORY_MAP = build_ordered_category_map()

# ── 采集配额（用户要求：每天约 200 份新卷，每学科均衡覆盖；仅最近 10 年）──
CURRENT_YEAR = datetime.now().year
YEAR_MIN = CURRENT_YEAR - 10      # 仅采集最近 10 年（如 2026 -> 2016 起）
DAILY_MAX_PAPERS = 200           # 每日采集新卷上限（约 200 份/天）
PER_CATEGORY_CAP = 6             # 单个 (学科,年级) 分类每日最多采集份数（保证各学科均衡）
# 学段每日配额：保证「初中优先」且小学/高中也都能覆盖到（否则 200 额度会被初中吃光，高中永远采不到）
# 合计 200 = 初中 120 + 小学 50 + 高中 30
STAGE_CAP = {"初中": 120, "小学": 50, "高中": 30}

# 年份解析：从标题提取 4 位年份，过滤掉 10 年前的旧卷
_YEAR_RE = re.compile(r'(?:19|20)\d{2}')


def parse_year(title):
    """从标题解析年份；无法识别返回 None（视为近期，不误删）。"""
    m = _YEAR_RE.search(title or "")
    if m:
        y = int(m.group())
        if 1990 <= y <= CURRENT_YEAR + 1:
            return y
    return None


def within_year_window(title):
    """标题含明确年份且小于最近 10 年下限的，判为过期卷（跳过）。"""
    y = parse_year(title)
    return y is None or y >= YEAR_MIN

REQUEST_INTERVAL = 30      # 多轮之间的休眠（秒）
MAX_PAGES_PER_SUBJECT = 20
DOWNLOAD_DELAY = 1         # 每份试卷下载后休眠（秒）
KEEP_EXTENSIONS = {'.doc', '.docx', '.pdf'}

# 单卷 HTML 上限 12MB：超出会突破 MySQL max_allowed_packet 导致连接中断
# （实测一张 55MB 数学卷写入即触发 Lost connection）。超大部分仅记录元信息、
# 题目置 0，并仍按 source_url 去重，避免续跑时反复崩溃。
MAX_HTML_CHARS = 12 * 1024 * 1024

# 工作目录（处理完即清理，不长期保存 doc 原件）。加入 .gitignore。
CACHE_DIR = BASE_DIR / ".paper_cache"
DOWNLOAD_DIR = CACHE_DIR / "downloads"
EXTRACT_DIR = CACHE_DIR / "extracted"
CLEAN_DIR = CACHE_DIR / "cleaned"
TEMP_HTML_DIR = CACHE_DIR / "html_temp"


# ========== 基础工具 ==========
def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def _safe_remove(path):
    """尽量删除临时文件；删除失败（含安全删除拦截、权限问题）一律忽略，不影响主流程。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except BaseException:
        pass


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
        # 不捕获 soffice 的 stdout/stderr：Windows 下其 stderr 含非 UTF-8 字节，
        # 用 text 模式捕获会让读取线程抛 UnicodeDecodeError（虽不致命但刷屏且可能拖慢）。
        # 我们本不消费其输出，只检查产物 HTML 是否存在即可。
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    """读取 HTML 文件，将外部图片转为 base64 内联（LibreOffice 通常已内联，此为兜底）。

    注意：LibreOffice 导出的 <img src> 多为 URL 编码文件名（如 %E4%BA%BA..._html_xxx.png），
    而磁盘上是解码后的中文名，故解析前需 urllib.parse.unquote，否则找不到文件导致 0 内联。
    """
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
    from urllib.parse import unquote
    for img in soup.find_all('img'):
        src = img.get('src')
        if not src or src.startswith('data:'):
            continue
        rel = unquote(src)                      # URL 编码 -> 磁盘实际文件名
        img_path = src if os.path.isabs(src) else os.path.join(base_dir, rel)
        if not os.path.exists(img_path):
            # 兜底：直接以原始 src 拼接再试一次
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
    """文档 -> 自包含 HTML（图片 base64 内联）。失败返回 None。

    优先级：LibreOffice（覆盖 doc/docx/pdf 等）→ mammoth(.docx) →
    pdfplumber(.pdf)。旧版 .doc（OLE 二进制）在缺少 LibreOffice 时无法可靠
    转为 HTML，直接返回 None（仅记录元信息、不存二进制乱码）。
    """
    ext = os.path.splitext(file_path)[1].lower()
    html_file = convert_with_libreoffice(file_path, str(TEMP_HTML_DIR))
    if html_file:
        return embed_images_as_base64(html_file)
    if ext == '.docx':
        # LibreOffice 失败时回退到 mammoth（convert_docx_mammoth 内部懒加载 mammoth）
        return convert_docx_mammoth(file_path)
    if ext == '.pdf':
        return convert_pdf_text(file_path)
    if ext == '.doc':
        # 旧版 .doc 为 OLE 二进制，无 LibreOffice 无法可靠转换，返回 None（仅记录元信息）
        return None
    # 其余（.txt/.html 等）按纯文本兜底
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
    # 年份过滤：仅保留最近 10 年（标题无年份者视为近期，不过滤）
    filtered = [p for p in papers if within_year_window(p['title'])]
    if len(filtered) != len(papers):
        print(f"    🗓 年份过滤：{len(papers)} -> {len(filtered)} 份（仅保留 {YEAR_MIN} 年起）")
    return filtered


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
def _upsert_paper(session, subject, grade, title, source_url, download_url, html_content, answers, year=0):
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
        if year:
            existing.year = year
        session.commit()
        return existing.id, False
    paper = Paper(
        subject=subject, grade=grade, title=title,
        source_url=source_url, download_url=download_url,
        html_content=html_content or "", answers=answers or "",
        total_questions=0, year=year,
    )
    session.add(paper)
    session.commit()
    return paper.id, True


def _store_questions(session, paper_id, html_content):
    """解析题目并写入 paper_questions（幂等：先删后插），更新题数。

    每题冗余写入所属试卷的 grade/subject，便于「按年级+学科+题型」独立抽题，
    无需在查询时 JOIN papers。
    """
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
        options = json.dumps(q['options'], ensure_ascii=False) if q['options'] else ""
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


def store_paper_full(subject, grade, title, source_url, download_url, html_content, year=0):
    """对外封装：去重入库 + 解析题目。返回 (paper_id, is_new, q_count)。

    超大 HTML（> MAX_HTML_CHARS）会超出 MySQL max_allowed_packet 导致连接中断，
    此类试卷仅记录元信息（html_content 置空、题目 0），并仍按 source_url 去重，
    避免重复采集时再次触发崩溃。
    """
    if html_content and len(html_content) > MAX_HTML_CHARS:
        print(f"    ⚠️ HTML 过大（约 {len(html_content)//1024//1024}MB），超出上限 "
              f"{MAX_HTML_CHARS//1024//1024}MB，仅记录元信息以规避 MySQL 包大小限制")
        html_content = ""
    with collection_session() as session:
        paper_id, is_new = _upsert_paper(
            session, subject, grade, title, source_url, download_url, html_content, None, year=year)
        q_count = _store_questions(session, paper_id, html_content) if html_content else 0
        return paper_id, is_new, q_count


# ========== 主采集循环 ==========
_ANSWER_HINT = ("答案", "答", "解析", "详解", "key", "Key", "KEY")
_EXAM_HINT = ("试卷", "试题", "练习", "期中", "期末", "月考", "中考", "高考", "模拟", "测验", "单元")


def _select_exam_doc(kept_files):
    """从解压出的文档中挑选最像「试卷正文」的一份（避开答案/解析），避免答案覆盖试卷。

    返回单文件路径列表（复用既有单卷入库逻辑）。无文档返回空列表。
    """
    if not kept_files:
        return []
    if len(kept_files) == 1:
        return kept_files
    candidates = []
    for p in kept_files:
        n = os.path.basename(p)
        if any(h in n for h in _ANSWER_HINT):
            continue
        candidates.append(p)
    if candidates:
        return [candidates[0]]
    return [kept_files[0]]


def run_collection(once=False, daily_limit=DAILY_MAX_PAPERS,
                   fill_answers_after=False, answer_cap=0):
    """按日采集最新试卷入库（去重、年份过滤、学段优先级）。

    参数：
      once: 跑一轮即退出（自动化每日用）。
      daily_limit: 本日最多采集的新卷数（默认 200，约 200 份/天）。
      fill_answers_after: 采集后是否调用 AI 优先补全新卷答案（再继续全局空缺）。
      answer_cap: 全局答案补全每日上限（0 表示仅补新卷，不补历史空缺）。
    返回：本次新增的试卷 id 列表（供后续优先补全答案）。
    """
    from app.database import init_collection_db
    init_collection_db()

    # 批量补答案属离线定时任务（非在线请求路径），放宽全局节流以提升吞吐
    # （在线接口仍保持 AI_THROTTLE_SEC 防限流；此处仅作用于本批处理进程）。
    if fill_answers_after:
        try:
            import app.domains.platform.services.ai as _ai_mod
            _ai_mod.AI_THROTTLE_SEC = 0.2
        except Exception:
            pass
        # 开局先补一次当日库内「已入库但尚未有答案」的试卷（含本日早些时候已采集、
        # 或因中断续跑遗留的卷子），保证随采随补、可断点续传。
        try:
            from app.domains.content.services.answer_generator import fill_missing_answers
            print("🤖 开局先补当日库内已有试卷的缺失答案...")
            fill_missing_answers()
        except BaseException as e:
            print(f"⚠️ 开局答案补全异常（不影响采集）: {type(e).__name__}: {e}")

    ensure_dir(DOWNLOAD_DIR)
    ensure_dir(EXTRACT_DIR)
    ensure_dir(CLEAN_DIR)
    ensure_dir(TEMP_HTML_DIR)

    remaining_quota = daily_limit
    print(f"📌 本日采集上限 {remaining_quota} 份新卷（学段优先级：初中→小学→高中；"
          f"学段配额 初中{STAGE_CAP['初中']}/小学{STAGE_CAP['小学']}/高中{STAGE_CAP['高中']}；"
          f"仅最近 {CURRENT_YEAR - YEAR_MIN} 年，{YEAR_MIN} 年起）")

    # 按学段优先级（初中→小学→高中）重排分类，保证优先采集初中、各学科均衡覆盖
    categories = ORDERED_CATEGORY_MAP

    collected_total = 0
    new_paper_ids = []
    stage_collected = {k: 0 for k in STAGE_CAP}
    while True:
        try:
            for subject_name, grade_name, url_suffix in categories:
                if collected_total >= remaining_quota:
                    break
                # 学段每日配额：保证初中优先且小学/高中也覆盖到（否则 200 额度被初中吃光，高中采不到）
                stage = GRADE_STAGE.get(grade_name, "初中")
                if stage_collected.get(stage, 0) >= STAGE_CAP.get(stage, 10):
                    continue
                # 当日 (学科,年级) 配额：基于跨日注册表统计「今日」已抓份数，
                # 因为每日 SQLite 文件是独立的（不能用库内 created_at 计数，否则永远为 0
                # 导致该分类每天都被重新抓、且破坏「优先初中」的学段优先级）。
                today_str = datetime.now().strftime("%Y-%m-%d")
                if count_scraped_today(subject_name, grade_name, today_str) >= PER_CATEGORY_CAP:
                    continue
                print(f"\n📚 [{datetime.now():%Y-%m-%d %H:%M:%S}] 处理: {subject_name} - {grade_name}")
                papers = get_paper_list(url_suffix)
                if not papers:
                    print(f"  ⚠️ 该分类无（近10年）试卷，跳过")
                    continue
                print(f"  找到 {len(papers)} 份（近10年）试卷，本类最多采 {PER_CATEGORY_CAP} 份")

                new_count = 0
                for paper in papers:
                    if collected_total >= remaining_quota:
                        break
                    if new_count >= PER_CATEGORY_CAP:
                        break
                    source_url = paper['detail_url']
                    # 跨日去重：注册表已记录的 source_url 不再采集（之前抓过的，
                    # 包括历史 staging 库与之前任意一天的每日文件中的卷子）。
                    if is_scraped(source_url):
                        print(f"  ⏭ 已采集（注册表），跳过: {paper['title']}")
                        continue

                    # 单份试卷处理异常时跳过并续跑（自动化每日任务不能因一份坏卷中断）
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

                        # 优先取「试卷正文」文档，避开答案/解析（避免答案覆盖试卷）
                        for doc_path in _select_exam_doc(kept_files):
                            if collected_total >= remaining_quota:
                                break
                            yr = parse_year(paper['title']) or 0
                            print(f"  📄 {paper['title']}")
                            html_content = convert_document_to_html(doc_path)
                            if html_content:
                                print(f"    ✅ 转换成功，HTML 长度: {len(html_content)} 字符")
                            else:
                                print(f"    ⚠️ 转换失败，仅记录元信息")
                            paper_id, _is_new, q_count = store_paper_full(
                                subject_name, grade_name, paper['title'],
                                source_url, download_url, html_content, year=yr)
                            print(f"    📝 入库试卷 ID={paper_id}，题目 {q_count} 道")
                            new_paper_ids.append(paper_id)
                            # 写入跨日注册表：确保「之前没抓过的」跨天生效
                            mark_scraped(source_url, today_str, subject_name, grade_name, paper['title'])

                            # 采集后即时补该卷 AI 答案（增量、随采随补，避免「全部采完再统一补」
                            # 时若中途中断导致整批卷子无答案；AI 调用期间不持 DB 连接）。
                            if fill_answers_after:
                                try:
                                    from app.domains.content.services.answer_generator import fill_missing_answers
                                    fill_missing_answers(paper_ids=[paper_id])
                                except BaseException as e:
                                    print(f"  ⚠️ 该卷答案补全异常（不影响入库）: {type(e).__name__}: {e}")

                            # 不使用 doc 保存：转换入库后删除原件
                            _safe_remove(doc_path)

                        # 删除压缩包与多余文档，避免长期占用磁盘
                        for f in kept_files:
                            _safe_remove(f)
                        _safe_remove(archive_path)

                        new_count += 1
                        collected_total += 1
                        stage_collected[stage] = stage_collected.get(stage, 0) + 1
                        time.sleep(DOWNLOAD_DELAY)
                    except BaseException as e:
                        print(f"  ⚠️ 处理试卷异常，跳过: {paper['title']} -> {type(e).__name__}: {e}")
                        traceback.print_exc()
                        try:
                            if 'archive_path' in dir() and archive_path:
                                _safe_remove(archive_path)
                        except BaseException:
                            pass
                        continue

                print(f"  ✅ {subject_name}-{grade_name} 完成，新增 {new_count} 份（本次累计 {collected_total}/{remaining_quota}）")

            if once or collected_total >= remaining_quota:
                print(f"\n✅ 单次采集完成（--once 或已达本日上限 {remaining_quota}），新增 {collected_total} 份")
                break
            print(f"\n💤 本轮完成，等待 {REQUEST_INTERVAL} 秒...")
            time.sleep(REQUEST_INTERVAL)

        except KeyboardInterrupt:
            print("\n🛑 用户中断，退出")
            break
        except BaseException as e:
            print(f"❌ 主循环异常: {type(e).__name__}: {e}")
            traceback.print_exc()
            if once:
                break
            time.sleep(REQUEST_INTERVAL)

    # 采集后优先为新卷补全 AI 答案（受每日上限约束，避免无限制消耗）
    # 单独 try 包裹：AI 补全异常绝不影响已采集试卷。
    if fill_answers_after and new_paper_ids:
        from app.domains.content.services.answer_generator import fill_missing_answers
        # 批量补答案属离线定时任务（非在线请求路径），放宽全局节流以提升吞吐
        # （在线接口仍保持 AI_THROTTLE_SEC 防限流；此处仅作用于本批处理进程）。
        try:
            import app.domains.platform.services.ai as _ai_mod
            _ai_mod.AI_THROTTLE_SEC = 0.2
        except Exception:
            pass
        cap = answer_cap if answer_cap and answer_cap > 0 else None
        print(f"\n🤖 为当日 SQLite 内全部缺失答案的试卷补全 AI 答案"
              f"{('（本日上限 ' + str(cap) + ' 题）') if cap else '（不限额）'}...")
        try:
            # 当日 SQLite 仅含本日采集的试卷，故「全局补全」（不限 paper_ids）即覆盖全部当日卷，
            # 包括本轮之前已入库的当日卷的剩余空缺；已含答案的题目会被自动跳过。
            fill_missing_answers(limit=cap)
        except BaseException as e:
            print(f"⚠️ AI 答案补全异常（不影响已采集试卷）: {type(e).__name__}: {e}")
            traceback.print_exc()

    return new_paper_ids


def print_stats():
    with collection_session() as session:
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
