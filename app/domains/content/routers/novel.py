"""小说站 - 读者端 API（公开阅读，进度/书架需登录）

挂载在 `/api/novel`，**不强制登录**：书城、目录、正文对游客开放（小说站是内容门户，
登录门槛会把读者挡在门外）。只有「阅读进度 / 书架」两个写操作要求登录会话。

阅读加载模型（对应产品需求「下滑请求更多文本」）：
- `chapter_mode=chapter`：TXT 成功自动分章 → 目录可用，下滑按「章」拉取；
- `chapter_mode=stream` ：TXT 无法分章 → 按等大文本块切片，下滑按「块」流式拉取，
  前端不渲染章节标题、内容无缝拼接。
两种模式共用 `GET /{id}/read?from=&limit=`，前端只需维护 next 指针，一套代码。

依赖约束：本文件属 D2 内容域，跨域一律走 contracts（此处只用到 app.models /
app.database 等非域模块，无跨域调用）。
"""
import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models.novel import Novel, NovelChapter, NovelBookmark, NovelReadProgress, NovelComment
from app.models.user import User
from app.schemas.novel import (BookmarkCreate, CategoryItem, ChapterBrief,
                               ChapterContent, ChapterListResponse, NovelBrief,
                               NovelCommentCreate, NovelDetail, NovelListResponse,
                               ProgressUpdate, ReadResponse, ShelfUpdate)

logger = logging.getLogger(__name__)

router = APIRouter()

# 上传的 TXT 原件存放位置（后台导入时写入，便于后续重解析/排错）
NOVEL_SOURCE_DIR = os.path.join(str(BASE_DIR), "output", "novel_sources")

# 列表/目录分页上限，防止一次拖回整本书
MAX_PAGE_SIZE = 100
# 单次 /read 最多返回的段数（下滑一屏通常 1-2 段）
MAX_READ_LIMIT = 5


# ───────────────── 当前登录用户（可选） ─────────────────
def _optional_user(authorization: str = Header(default=""),
                   db: Session = Depends(get_db)) -> "User | None":
    """解析 Bearer token 拿到用户；无 token / 失效返回 None（不抛 401，游客可读）。"""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    user = db.query(User).filter(User.token == token).first()
    if not user:
        return None
    return user


def _require_user(authorization: str = Header(default=""),
                  db: Session = Depends(get_db)) -> User:
    """必须登录（书架 / 进度写操作）。"""
    user = _optional_user(authorization=authorization, db=db)
    if not user:
        raise HTTPException(401, "请先登录")
    return user


def _comment_safe(db: Session, text: str):
    """内容安全（D4 意图）：直接复用 IM 词库表 db_im_sensitive_words 单一数据源做拦截。

    说明：D9 冻结域（frozen）对其它域不暴露任何能力，敏感词*服务*（check_text）不可被
    内容域 import；此处仅读取共享词库表做最小匹配，避免重复维护词库。后续应将内容安全
    抽为跨域共享契约，再统一替换本 stopgap。命中任一启用词即拒绝发布。
    """
    from app.models.im import SensitiveWord
    low = (text or "").lower()
    for (w,) in db.query(SensitiveWord.word).filter(SensitiveWord.is_active.is_(True)).all():
        if w and w.strip() and w.strip().lower() in low:
            return False, w.strip()
    return True, None


def _brief(n: Novel, intro_len: int = 80) -> dict:
    """列表条目：简介截断，避免列表页传输整篇简介。"""
    intro = (n.intro or "").strip()
    if intro_len and len(intro) > intro_len:
        intro = intro[:intro_len] + "…"
    return {
        "id": n.id,
        "title": n.title,
        "author": n.author or "",
        "category": n.category or "",
        "cover_url": n.cover_url or "",
        "intro": intro,
        "chapter_mode": n.chapter_mode or "chapter",
        "status": n.status or "serial",
        "word_count": n.word_count or 0,
        "chapter_count": n.chapter_count or 0,
        "view_count": n.view_count or 0,
        "sort_order": n.sort_order or 0,
        "enabled": bool(n.enabled),
        "created_at": n.created_at,
        "updated_at": n.updated_at,
    }


# ───────────────── 书城 ─────────────────
@router.get("/categories", response_model=list[CategoryItem], summary="分类列表")
def list_categories(db: Session = Depends(get_db)):
    """返回已上架小说的分类及数量（空分类不返回）。"""
    rows = (db.query(Novel.category, func.count(Novel.id))
            .filter(Novel.enabled.is_(True))
            .group_by(Novel.category)
            .all())
    items = [{"category": c or "未分类", "count": n} for c, n in rows]
    items.sort(key=lambda x: (-x["count"], x["category"]))
    return items


@router.get("/list", response_model=NovelListResponse, summary="书城列表（分类/搜索/分页）")
def list_novels(
    category: str = Query("", description="分类过滤，空=全部"),
    keyword: str = Query("", description="书名/作者模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    sort: str = Query("latest", description="latest=最新上架 / hot=人气 / title=书名"),
    db: Session = Depends(get_db),
):
    q = db.query(Novel).filter(Novel.enabled.is_(True))
    if category:
        q = q.filter(Novel.category == category)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(Novel.title.like(kw) | Novel.author.like(kw))

    total = q.count()
    if sort == "hot":
        q = q.order_by(Novel.view_count.desc(), Novel.id.desc())
    elif sort == "title":
        q = q.order_by(Novel.title.asc())
    else:
        q = q.order_by(Novel.sort_order.asc(), Novel.id.desc())

    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_brief(n) for n in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/shelf", response_model=list[NovelBrief], summary="我的书架（需登录）")
def my_shelf(user: User = Depends(_require_user), db: Session = Depends(get_db)):
    rows = (db.query(NovelReadProgress)
            .filter(NovelReadProgress.user_id == user.user_id,
                    NovelReadProgress.in_shelf.is_(True))
            .order_by(NovelReadProgress.updated_at.desc())
            .all())
    out = []
    for p in rows:
        n = db.query(Novel).filter(Novel.id == p.novel_id).first()
        if n and n.enabled:
            out.append(_brief(n))
    return out


# ───────────────── 阅读榜单（公开，须置于 /{novel_id} 之前以免被 int 路由拦截） ─────────────────
@router.get("/rank", summary="阅读榜单（按人气 top N，公开）")
def reading_rank(top: int = Query(10, ge=1, le=50),
                 db: Session = Depends(get_db)):
    """热门小说榜：按 view_count 倒序取前 top 本（上架且仅汉字以上）。"""
    rows = (db.query(Novel)
            .filter(Novel.enabled.is_(True))
            .order_by(Novel.view_count.desc(), Novel.id.desc())
            .limit(top).all())
    return [_brief(n) for n in rows]


@router.get("/{novel_id}", response_model=NovelDetail, summary="小说详情")
def novel_detail(novel_id: int, db: Session = Depends(get_db),
                 authorization: str = Header(default="")):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n or not n.enabled:
        raise HTTPException(404, "小说不存在或已下架")

    # 人气 +1（条件更新，避免并发下丢更新）
    db.query(Novel).filter(Novel.id == novel_id).update(
        {Novel.view_count: (Novel.view_count or 0) + 1})
    db.commit()

    data = _brief(n, intro_len=0)  # 详情页给完整简介
    data["chapter_idx"] = 0
    data["in_shelf"] = False

    user = _optional_user(authorization=authorization, db=db)
    if user:
        p = (db.query(NovelReadProgress)
             .filter(NovelReadProgress.user_id == user.user_id,
                     NovelReadProgress.novel_id == novel_id)
             .first())
        if p:
            data["chapter_idx"] = p.chapter_idx or 0
            data["in_shelf"] = bool(p.in_shelf)
    return data


# ───────────────── 目录 ─────────────────
@router.get("/{novel_id}/chapters", response_model=ChapterListResponse,
            summary="章节目录（分页，不含正文）")
def list_chapters(
    novel_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """目录只返回元信息（标题/序号/字数），正文由 /read 按段拉取。

    stream 模式下目录同样可用（title 为空），便于读者跳转（前端可不展示）。
    """
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n or not n.enabled:
        raise HTTPException(404, "小说不存在或已下架")

    q = db.query(NovelChapter).filter(NovelChapter.novel_id == novel_id)
    total = q.count()
    rows = (q.order_by(NovelChapter.idx.asc())
            .offset(offset).limit(limit).all())
    return {
        "items": [{"id": c.id, "idx": c.idx, "title": c.title or "",
                   "word_count": c.word_count or 0} for c in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(rows) < total,
    }


# ───────────────── 阅读（下滑增量加载核心） ─────────────────
@router.get("/{novel_id}/read", response_model=ReadResponse,
            summary="按顺序拉取正文段（下滑加载）")
def read_chunks(
    novel_id: int,
    frm: int = Query(1, ge=1, alias="from", description="起始段号（从 1 开始）"),
    limit: int = Query(1, ge=1, le=MAX_READ_LIMIT, description="本次拉取段数"),
    db: Session = Depends(get_db),
):
    """下滑加载入口：返回 [from, from+limit) 段正文与下一段指针。

    - chapter 模式：一段 = 一章，前端渲染章节标题；
    - stream 模式：一段 = 一个文本块，title 为空，前端无缝拼接。
    """
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n or not n.enabled:
        raise HTTPException(404, "小说不存在或已下架")

    total = db.query(func.count(NovelChapter.id)).filter(
        NovelChapter.novel_id == novel_id).scalar() or 0
    if total == 0:
        return {"items": [], "total": 0, "next": None, "has_more": False}

    rows = (db.query(NovelChapter)
            .filter(NovelChapter.novel_id == novel_id,
                    NovelChapter.idx >= frm)
            .order_by(NovelChapter.idx.asc())
            .limit(limit).all())

    items = [{"id": c.id, "idx": c.idx, "title": c.title or "",
              "content": c.content or "", "word_count": c.word_count or 0}
             for c in rows]

    last_idx = rows[-1].idx if rows else frm
    has_more = last_idx < total
    return {
        "items": items,
        "total": total,
        "next": (last_idx + 1) if has_more else None,
        "has_more": has_more,
    }


# ───────────────── 进度 / 书架写入（需登录） ─────────────────
@router.post("/{novel_id}/progress", summary="保存阅读进度（需登录）")
def save_progress(novel_id: int, body: ProgressUpdate,
                  user: User = Depends(_require_user),
                  db: Session = Depends(get_db)):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n:
        raise HTTPException(404, "小说不存在")
    p = (db.query(NovelReadProgress)
         .filter(NovelReadProgress.user_id == user.user_id,
                 NovelReadProgress.novel_id == novel_id)
         .first())
    if not p:
        p = NovelReadProgress(user_id=user.user_id, novel_id=novel_id,
                              chapter_idx=body.chapter_idx, in_shelf=False)
        db.add(p)
    else:
        p.chapter_idx = body.chapter_idx
    db.commit()
    return {"ok": True, "chapter_idx": body.chapter_idx}


@router.post("/{novel_id}/shelf", summary="加入/移出书架（需登录）")
def toggle_shelf(novel_id: int, body: ShelfUpdate,
                 user: User = Depends(_require_user),
                 db: Session = Depends(get_db)):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n:
        raise HTTPException(404, "小说不存在")
    p = (db.query(NovelReadProgress)
         .filter(NovelReadProgress.user_id == user.user_id,
                 NovelReadProgress.novel_id == novel_id)
         .first())
    if not p:
        p = NovelReadProgress(user_id=user.user_id, novel_id=novel_id,
                              chapter_idx=1, in_shelf=body.in_shelf)
        db.add(p)
    else:
        p.in_shelf = body.in_shelf
    db.commit()
    return {"ok": True, "in_shelf": body.in_shelf}


# ───────────────── 书签（需登录） ─────────────────
@router.get("/{novel_id}/bookmarks", summary="我的书签列表（需登录）")
def list_bookmarks(novel_id: int, user: User = Depends(_require_user),
                   db: Session = Depends(get_db)):
    """返回本人在该书的书签，按章/段号升序；用于阅读器侧边栏与跳转。"""
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n:
        raise HTTPException(404, "小说不存在")
    rows = (db.query(NovelBookmark)
            .filter(NovelBookmark.user_id == user.user_id,
                    NovelBookmark.novel_id == novel_id)
            .order_by(NovelBookmark.chapter_idx.asc(), NovelBookmark.id.asc())
            .all())
    return [{
        "id": b.id,
        "novel_id": b.novel_id,
        "chapter_idx": b.chapter_idx,
        "note": b.note or "",
        "created_at": b.created_at,
    } for b in rows]


@router.post("/{novel_id}/bookmarks", summary="添加/更新书签（需登录）")
def add_bookmark(novel_id: int, body: BookmarkCreate,
                 user: User = Depends(_require_user),
                 db: Session = Depends(get_db)):
    """在该章/段打书签；同一 (user, novel, chapter_idx) 已存在则改为更新便签。"""
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n:
        raise HTTPException(404, "小说不存在")
    existing = (db.query(NovelBookmark)
                .filter(NovelBookmark.user_id == user.user_id,
                        NovelBookmark.novel_id == novel_id,
                        NovelBookmark.chapter_idx == body.chapter_idx)
                .first())
    if existing:
        existing.note = body.note or ""
        b = existing
    else:
        b = NovelBookmark(user_id=user.user_id, novel_id=novel_id,
                          chapter_idx=body.chapter_idx, note=body.note or "")
        db.add(b)
    db.commit()
    db.refresh(b)
    return {"ok": True, "id": b.id, "chapter_idx": b.chapter_idx,
            "note": b.note or ""}


@router.delete("/{novel_id}/bookmarks/{bid}", summary="删除书签（需登录）")
def delete_bookmark(novel_id: int, bid: int,
                    user: User = Depends(_require_user),
                    db: Session = Depends(get_db)):
    b = (db.query(NovelBookmark)
         .filter(NovelBookmark.id == bid,
                 NovelBookmark.user_id == user.user_id,
                 NovelBookmark.novel_id == novel_id)
         .first())
    if not b:
        raise HTTPException(404, "书签不存在")
    db.delete(b)
    db.commit()
    return {"ok": True}


# ───────────────── 评论（社区 UGC） ─────────────────
@router.get("/{novel_id}/comments", summary="小说评论列表（公开，仅展示 active）")
def list_comments(novel_id: int,
                  chapter_idx: int = Query(0, description="0=全书评论；>0=该章/段评论"),
                  page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100),
                  db: Session = Depends(get_db)):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n or not n.enabled:
        raise HTTPException(404, "小说不存在或已下架")
    q = db.query(NovelComment).filter(
        NovelComment.novel_id == novel_id, NovelComment.status == "active")
    if chapter_idx > 0:
        q = q.filter(NovelComment.chapter_idx == chapter_idx)
    total = q.count()
    rows = (q.order_by(NovelComment.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {
        "items": [{
            "id": c.id, "user_id": c.user_id, "content": c.content,
            "chapter_idx": c.chapter_idx, "like_count": c.like_count or 0,
            "created_at": c.created_at,
        } for c in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/{novel_id}/comments", summary="发布评论（需登录，含敏感词拦截）")
def add_comment(novel_id: int, body: NovelCommentCreate,
                user: User = Depends(_require_user),
                db: Session = Depends(get_db)):
    n = db.query(Novel).filter(Novel.id == novel_id).first()
    if not n or not n.enabled:
        raise HTTPException(404, "小说不存在或已下架")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "评论内容不能为空")
    ok, hit = _comment_safe(db, content)
    if not ok:
        raise HTTPException(400, f"评论包含不合适内容，请修改后再发（命中：{hit}）")
    c = NovelComment(user_id=user.user_id, novel_id=novel_id,
                     chapter_idx=max(0, body.chapter_idx), content=content)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"ok": True, "id": c.id, "user_id": c.user_id, "content": c.content,
            "chapter_idx": c.chapter_idx, "like_count": 0, "created_at": c.created_at}


@router.delete("/{novel_id}/comments/{cid}", summary="删除评论（仅本人，软删）")
def delete_comment(novel_id: int, cid: int,
                   user: User = Depends(_require_user),
                   db: Session = Depends(get_db)):
    c = (db.query(NovelComment)
         .filter(NovelComment.id == cid, NovelComment.novel_id == novel_id)
         .first())
    if not c:
        raise HTTPException(404, "评论不存在")
    if c.user_id != user.user_id:
        raise HTTPException(403, "只能删除自己的评论")
    c.status = "deleted"
    db.commit()
    return {"ok": True}
