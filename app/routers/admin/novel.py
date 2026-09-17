"""后台 - 小说站管理（TXT 上传导入 / 上下架 / 章节维护）

挂在 `/api/admin/novel/*`（共享 `app.routers.admin.router`，管理员 Bearer 鉴权）。

导入流程：`POST /upload` 收 TXT → 落原件到 output/novel_sources/ → 解析分章
（能分章则分，不能则按块流式切片）→ 建 Novel + 批量写 NovelChapter。
解析与写库全程在本请求内完成（纯 CPU + DB，无外部阻塞调用，可安全持有连接）。

注意：本模块属管理后台路由（`app/routers/admin/**`），按 .importlinter 白名单
可直接调用各域 contracts，这里只用到内容域的 TXT 解析服务。
"""
import logging
import os
import re
import uuid
from datetime import datetime

from fastapi import Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
# 跨域一律经内容域 contracts（.importlinter 白名单：admin -> *.contracts）
from app.domains.content.contracts import parse_novel_txt
from app.models.novel import Novel, NovelChapter, NovelReadProgress
from app.schemas.novel import NovelImportResult, NovelUpdate, ChapterUpdate

from . import router
from .common import _require_admin, _audit

logger = logging.getLogger(__name__)

# TXT 原件存放目录（与读者端常量保持一致，便于重解析）
NOVEL_SOURCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "output", "novel_sources")

# 上传限制
MAX_FILE_BYTES = 20 * 1024 * 1024      # 20MB（超长网文也够用）
ALLOWED_EXT = (".txt",)
# 批量写库分批大小（避免单事务过大）
BATCH_SIZE = 500


def _safe_name(name: str) -> str:
    """去掉路径分隔符与奇怪字符，防目录穿越"""
    name = os.path.basename(name or "")
    name = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", name)
    return name[:120] or "untitled.txt"


def _word_count(s: str) -> int:
    """字数：去掉所有空白后计字符数（中文按字、英文按字符）"""
    return len(re.sub(r"\s+", "", s or ""))


# ───────────────── 上传导入 ─────────────────
@router.post("/novel/upload", response_model=NovelImportResult, summary="上传 TXT 导入小说")
async def upload_novel(
    file: UploadFile = File(..., description="TXT 文件（UTF-8/GBK 自动识别）"),
    title: str = Form("", description="书名，留空则取文件名"),
    author: str = Form("", description="作者"),
    category: str = Form("", description="分类"),
    intro: str = Form("", description="简介"),
    cover_url: str = Form("", description="封面 URL"),
    status: str = Form("serial", description="serial=连载 / finished=完本"),
    enabled: bool = Form(True, description="是否立即上架"),
    db: Session = Depends(get_db),
    admin=Depends(_require_admin),
):
    """上传 TXT：自动探测编码 → 自动分章（分不了则按块流式切片）→ 入库。

    返回 mode=chapter 表示成功识别章节；mode=stream 表示按块流式加载。
    """
    fname = _safe_name(file.filename or "")
    if not fname.lower().endswith(ALLOWED_EXT):
        raise HTTPException(400, "只支持 .txt 文件")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "文件为空")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(400, f"文件过大（上限 {MAX_FILE_BYTES // 1024 // 1024}MB）")

    # 落原件（保留可重解析的源）
    os.makedirs(NOVEL_SOURCE_DIR, exist_ok=True)
    stored = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{fname}"
    stored_path = os.path.join(NOVEL_SOURCE_DIR, stored)
    with open(stored_path, "wb") as f:
        f.write(raw)

    parsed = parse_novel_txt(raw)
    chapters = parsed["chapters"]
    if not chapters:
        raise HTTPException(400, "未能解析出任何文本内容，请检查文件编码或内容")

    book_title = (title or "").strip() or os.path.splitext(fname)[0] or "未命名"

    novel = Novel(
        title=book_title[:200],
        author=(author or "")[:100],
        category=(category or "")[:50],
        cover_url=(cover_url or "")[:500],
        intro=intro or "",
        chapter_mode=parsed["mode"],
        status=status if status in ("serial", "finished", "draft") else "serial",
        word_count=parsed["word_count"],
        chapter_count=len(chapters),
        enabled=bool(enabled),
        source_file=os.path.join("output", "novel_sources", stored),
    )
    db.add(novel)
    db.flush()  # 拿到 novel.id

    # 批量写章节：分批提交，避免超大书单事务撑爆 undo log
    total_words = 0
    for i, (ch_title, content) in enumerate(chapters, start=1):
        wc = _word_count(content)
        total_words += wc
        db.add(NovelChapter(
            novel_id=novel.id,
            idx=i,
            title=(ch_title or "")[:300],
            content=content,
            word_count=wc,
        ))
        if i % BATCH_SIZE == 0:
            db.flush()
    novel.word_count = total_words
    novel.chapter_count = len(chapters)
    db.commit()
    db.refresh(novel)

    _audit(db, admin, "novel.upload", str(novel.id),
           f"导入小说《{novel.title}》 mode={parsed['mode']} 段数={len(chapters)} 字数={total_words}")

    return {
        "id": novel.id,
        "title": novel.title,
        "mode": parsed["mode"],
        "encoding": parsed["encoding"],
        "chapter_count": len(chapters),
        "word_count": total_words,
    }


# ───────────────── 列表 / 详情 ─────────────────
@router.get("/novel/list", summary="后台小说列表")
def admin_list_novels(
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    admin=Depends(_require_admin),
):
    q = db.query(Novel)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(Novel.title.like(kw) | Novel.author.like(kw))
    total = q.count()
    rows = (q.order_by(Novel.id.desc())
            .offset(max(0, (page - 1) * page_size)).limit(page_size).all())
    items = [{
        "id": n.id, "title": n.title, "author": n.author or "",
        "category": n.category or "", "chapter_mode": n.chapter_mode,
        "status": n.status, "enabled": bool(n.enabled),
        "chapter_count": n.chapter_count or 0, "word_count": n.word_count or 0,
        "view_count": n.view_count or 0, "sort_order": n.sort_order or 0,
        "created_at": n.created_at,
    } for n in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/novel/{novel_id}/chapters", summary="后台章节列表（正文预览，可按需取全文）")
def admin_list_chapters(
    novel_id: int,
    offset: int = 0,
    limit: int = 50,
    preview: int = 60,
    with_content: bool = False,
    db: Session = Depends(get_db),
    admin=Depends(_require_admin),
):
    """章节列表。默认只回 preview 截断（列表页轻量）；编辑单章时传
    with_content=true 拿完整正文（limit 请同时传 1，避免一次拖回整本书）。
    """
    q = db.query(NovelChapter).filter(NovelChapter.novel_id == novel_id)
    total = q.count()
    rows = q.order_by(NovelChapter.idx.asc()).offset(offset).limit(limit).all()
    items = []
    for c in rows:
        item = {
            "id": c.id, "idx": c.idx, "title": c.title or "",
            "word_count": c.word_count or 0,
        }
        if with_content:
            item["content"] = c.content or ""
        else:
            item["preview"] = (c.content or "")[:preview]
        items.append(item)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


# ───────────────── 编辑 / 删除 ─────────────────
@router.patch("/novel/{novel_id}", summary="修改小说元信息")
def admin_update_novel(novel_id: int, body: NovelUpdate,
                       db: Session = Depends(get_db),
                       admin=Depends(_require_admin)):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n:
        raise HTTPException(404, "小说不存在")
    for field in ("title", "author", "category", "cover_url", "intro",
                  "status", "enabled", "sort_order"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(n, field, val)
    db.commit()
    _audit(db, admin, "novel.update", str(novel_id), f"修改小说《{n.title}》")
    return {"ok": True, "id": novel_id}


@router.post("/novel/{novel_id}/toggle", summary="上架/下架")
def admin_toggle_novel(novel_id: int, db: Session = Depends(get_db),
                       admin=Depends(_require_admin)):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n:
        raise HTTPException(404, "小说不存在")
    n.enabled = not bool(n.enabled)
    db.commit()
    _audit(db, admin, "novel.toggle", str(novel_id),
           f"《{n.title}》{'上架' if n.enabled else '下架'}")
    return {"ok": True, "enabled": bool(n.enabled)}


@router.patch("/novel/{novel_id}/chapter/{chapter_id}", summary="修改章节")
def admin_update_chapter(novel_id: int, chapter_id: int, body: ChapterUpdate,
                         db: Session = Depends(get_db),
                         admin=Depends(_require_admin)):
    c = (db.query(NovelChapter)
         .filter(NovelChapter.id == chapter_id, NovelChapter.novel_id == novel_id)
         .first())
    if not c:
        raise HTTPException(404, "章节不存在")
    if body.title is not None:
        c.title = body.title[:300]
    if body.content is not None:
        c.content = body.content
        c.word_count = _word_count(body.content)
        # 同步书的总字数（避免编辑后统计失真）
        total = (db.query(NovelChapter.word_count)
                 .filter(NovelChapter.novel_id == novel_id).all())
        n = db.query(Novel).filter(Novel.id == novel_id).first()
        if n:
            n.word_count = sum(x[0] or 0 for x in total)
    db.commit()
    return {"ok": True, "id": chapter_id}


@router.delete("/novel/{novel_id}/chapter/{chapter_id}", summary="删除章节")
def admin_delete_chapter(novel_id: int, chapter_id: int,
                         db: Session = Depends(get_db),
                         admin=Depends(_require_admin)):
    c = (db.query(NovelChapter)
         .filter(NovelChapter.id == chapter_id, NovelChapter.novel_id == novel_id)
         .first())
    if not c:
        raise HTTPException(404, "章节不存在")
    db.delete(c)
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if n:
        n.chapter_count = max(0, (n.chapter_count or 1) - 1)
        n.word_count = max(0, (n.word_count or 0) - (c.word_count or 0))
    db.commit()
    return {"ok": True, "id": chapter_id}


@router.delete("/novel/{novel_id}", summary="删除小说（含章节与阅读记录）")
def admin_delete_novel(novel_id: int, db: Session = Depends(get_db),
                       admin=Depends(_require_admin)):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n:
        raise HTTPException(404, "小说不存在")
    title = n.title
    db.query(NovelChapter).filter(NovelChapter.novel_id == novel_id).delete()
    db.query(NovelReadProgress).filter(NovelReadProgress.novel_id == novel_id).delete()
    db.delete(n)
    db.commit()
    _audit(db, admin, "novel.delete", str(novel_id), f"删除小说《{title}》")
    return {"ok": True, "id": novel_id}
