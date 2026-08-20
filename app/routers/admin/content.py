"""管理后台：内容管理（词库 / 诗词库 / 语法知识点 / 采集试卷）

需求：试卷采集和知识点采集与录入机制——后台可配置词库、诗词库、知识点，
并查看/管理自动采集的试卷（papers/paper_questions）。

- 词库：词书 CRUD + 词书内单词 CRUD + 批量导入（文本粘贴）
- 诗词库：classical_texts CRUD（自动生成分行 JSON）
- 语法知识点：grammar_points CRUD（含练习题只读）
- 采集试卷：papers 列表/详情/删除（自动采集子系统的后台管理视图）
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.classical import ClassicalText
from app.models.grammar import GrammarPoint, GrammarExercise
from app.models.paper import Paper, PaperQuestion
from app.models.problem_type import ProblemCategory, ProblemType
from app.models.word import Word, WordBook

from . import router
from .common import _audit, _require_admin

logger = logging.getLogger("admin.content")


# ═══════════════ 词库（英语词书 + 单词） ═══════════════

class BookReq(BaseModel):
    name: str
    grade: int = 6
    semester: str = "上"
    publisher: str = "人教版PEP"
    textbook_id: int = 0


class WordReq(BaseModel):
    word: str
    phonetic: str = ""
    pos: str = ""
    meaning: str
    unit: str = ""
    difficulty: int = 1
    tags: str = ""


class WordImportReq(BaseModel):
    text: str  # 每行：单词|音标|词性|释义（或 单词 空格 释义）


@router.get("/books", summary="词书列表（按年级/教材版本/关键字）")
def list_books(grade: int = 0, textbook_id: int = 0, keyword: str = "",
               db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    q = db.query(WordBook)
    if grade > 0:
        q = q.filter(WordBook.grade == grade)
    if textbook_id > 0:
        q = q.filter(WordBook.textbook_id == textbook_id)
    kw = keyword.strip()
    if kw:
        q = q.filter(WordBook.name.like(f"%{kw}%"))
    rows = q.order_by(WordBook.grade, WordBook.semester, WordBook.id).all()
    ids = [b.id for b in rows]
    counts = dict(db.query(Word.book_id, func.count(Word.id)).filter(
        Word.book_id.in_(ids)).group_by(Word.book_id).all()) if ids else {}
    return {"items": [{
        "id": b.id, "name": b.name, "grade": b.grade, "semester": b.semester,
        "publisher": b.publisher or "", "textbook_id": b.textbook_id or 0,
        "word_count": counts.get(b.id, 0),
    } for b in rows]}


@router.post("/books", summary="新增词书")
def create_book(req: BookReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "词书名不能为空")
    if not (1 <= req.grade <= 9):
        raise HTTPException(400, "年级需在 1-9 之间")
    dup = db.query(WordBook).filter(WordBook.name == name).first()
    if dup:
        raise HTTPException(400, f"词书「{name}」已存在")
    b = WordBook(name=name[:100], grade=req.grade,
                 semester=(req.semester or "上")[:10],
                 publisher=(req.publisher or "人教版PEP")[:50],
                 textbook_id=req.textbook_id or None)
    db.add(b)
    db.commit()
    _audit(db, admin.user_id, "book_create", f"新增词书 {name}")
    return {"id": b.id, "ok": True}


@router.put("/books/{bid}", summary="编辑词书")
def update_book(bid: int, req: BookReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    b = db.query(WordBook).get(bid)
    if not b:
        raise HTTPException(404, "词书不存在")
    b.name = (req.name or "").strip()[:100]
    b.grade, b.semester = req.grade, (req.semester or "上")[:10]
    b.publisher = (req.publisher or "人教版PEP")[:50]
    b.textbook_id = req.textbook_id or None
    db.commit()
    _audit(db, admin.user_id, "book_update", f"编辑词书 id={bid}")
    return {"ok": True}


@router.delete("/books/{bid}", summary="删除词书（级联删除其下单词）")
def delete_book(bid: int, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    b = db.query(WordBook).get(bid)
    if not b:
        raise HTTPException(404, "词书不存在")
    from app.models.vocab import VocabProgress
    bound = db.query(VocabProgress).filter(
        VocabProgress.word_id.in_(
            db.query(Word.id).filter(Word.book_id == bid))).count()
    if bound > 0:
        raise HTTPException(400, f"该词书下有 {bound} 条学习进度记录，删除会丢失进度，请谨慎（可先停用）")
    db.delete(b)  # cascade 删单词
    db.commit()
    _audit(db, admin.user_id, "book_delete", f"删除词书 id={bid} ({b.name})")
    return {"ok": True}


@router.get("/books/{bid}/words", summary="词书内单词列表")
def list_words(bid: int, keyword: str = "", page: int = 1, page_size: int = 50,
               db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    q = db.query(Word).filter(Word.book_id == bid)
    kw = keyword.strip()
    if kw:
        q = q.filter(func.lower(Word.word).like(f"%{kw.lower()}%"))
    total = q.count()
    rows = q.order_by(Word.unit, Word.id).offset(
        max(0, (page - 1) * page_size)).limit(min(page_size, 200)).all()
    return {"total": total, "items": [{
        "id": w.id, "word": w.word, "phonetic": w.phonetic or "",
        "pos": w.pos or "", "meaning": w.meaning, "unit": w.unit or "",
        "difficulty": w.difficulty or 1, "tags": w.tags or "",
    } for w in rows]}


@router.post("/books/{bid}/words", summary="词书内新增单词")
def create_word(bid: int, req: WordReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    b = db.query(WordBook).get(bid)
    if not b:
        raise HTTPException(404, "词书不存在")
    word = (req.word or "").strip()
    meaning = (req.meaning or "").strip()
    if not word or not meaning:
        raise HTTPException(400, "单词与释义必填")
    dup = db.query(Word).filter(Word.book_id == bid, Word.word == word).first()
    if dup:
        raise HTTPException(400, f"该词书已存在单词「{word}」")
    w = Word(book_id=bid, word=word[:100], phonetic=(req.phonetic or "")[:100],
             pos=(req.pos or "")[:20], meaning=meaning[:200],
             unit=(req.unit or "")[:50], difficulty=req.difficulty,
             tags=(req.tags or "")[:200])
    db.add(w)
    b.word_count = db.query(Word).filter(Word.book_id == bid).count() + 1
    db.commit()
    return {"id": w.id, "ok": True}


@router.put("/words/{wid}", summary="编辑单词")
def update_word(wid: int, req: WordReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    w = db.query(Word).get(wid)
    if not w:
        raise HTTPException(404, "单词不存在")
    word = (req.word or "").strip()
    if not word:
        raise HTTPException(400, "单词不能为空")
    dup = db.query(Word).filter(Word.book_id == w.book_id, Word.word == word,
                                Word.id != wid).first()
    if dup:
        raise HTTPException(400, f"该词书已存在单词「{word}」")
    w.word = word[:100]
    w.phonetic, w.pos, w.meaning = (req.phonetic or "")[:100], (req.pos or "")[:20], (req.meaning or "")[:200]
    w.unit, w.difficulty, w.tags = (req.unit or "")[:50], req.difficulty, (req.tags or "")[:200]
    db.commit()
    return {"ok": True}


@router.delete("/words/{wid}", summary="删除单词")
def delete_word(wid: int, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    w = db.query(Word).get(wid)
    if not w:
        raise HTTPException(404, "单词不存在")
    from app.models.vocab import VocabProgress
    bound = db.query(VocabProgress).filter(VocabProgress.word_id == wid).count()
    if bound > 0:
        raise HTTPException(400, "该单词有学习进度记录，删除会丢失进度")
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.post("/books/{bid}/words/import", summary="批量导入单词")
def import_words(bid: int, req: WordImportReq, db: Session = Depends(get_db),
                 admin: Admin = Depends(_require_admin)):
    """每行一条：`word|音标|词性|释义`（或 `word 释义`），空行/重复自动跳过。"""
    b = db.query(WordBook).get(bid)
    if not b:
        raise HTTPException(404, "词书不存在")
    added = skipped = 0
    existing = {w.word for w in db.query(Word).filter(Word.book_id == bid).all()}
    for line in (req.text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2:
            word, meaning = parts[0], parts[1]
            phonetic = parts[2] if len(parts) > 2 else ""
            pos = parts[3] if len(parts) > 3 else ""
        else:
            seg = line.split(maxsplit=1)
            if len(seg) < 2:
                continue
            word, meaning = seg[0], seg[1]
            phonetic = pos = ""
        if not word or not meaning or word in existing:
            skipped += 1
            continue
        db.add(Word(book_id=bid, word=word[:100], phonetic=phonetic[:100],
                    pos=pos[:20], meaning=meaning[:200]))
        existing.add(word)
        added += 1
    b.word_count = db.query(Word).filter(Word.book_id == bid).count()
    db.commit()
    _audit(db, admin.user_id, "words_import",
           f"词书 {b.name} 导入 {added} 个，跳过 {skipped} 个")
    return {"ok": True, "added": added, "skipped": skipped}


# ═══════════════ 诗词库 ═══════════════

class ClassicalReq(BaseModel):
    title: str
    author: str = ""
    dynasty: str = ""
    text_type: str = "poem"
    grade: int = 3
    semester: str = "全"
    unit: str = ""
    content: str
    tags: str = ""


def _build_lines(content: str) -> str:
    """按行切分全文并生成分行 JSON（空行剔除）。"""
    lines = [ln.strip() for ln in (content or "").splitlines() if ln.strip()]
    return json.dumps(lines, ensure_ascii=False)


@router.get("/classicals", summary="诗词库列表")
def list_classicals(grade: int = 0, keyword: str = "",
                    db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    q = db.query(ClassicalText)
    if grade > 0:
        q = q.filter(ClassicalText.grade == grade)
    kw = keyword.strip()
    if kw:
        q = q.filter(func.concat(ClassicalText.title, ClassicalText.author).like(f"%{kw}%"))
    rows = q.order_by(ClassicalText.grade, ClassicalText.id).all()
    return {"items": [{
        "id": t.id, "title": t.title, "author": t.author, "dynasty": t.dynasty,
        "text_type": t.text_type, "grade": t.grade, "semester": t.semester,
        "unit": t.unit or "", "content": t.content,
        "line_count": len((t.lines_json or "[]")) // 2, "tags": t.tags or "",
    } for t in rows]}


@router.post("/classicals", summary="新增诗词篇目")
def create_classical(req: ClassicalReq, db: Session = Depends(get_db),
                     admin: Admin = Depends(_require_admin)):
    title = (req.title or "").strip()
    content = (req.content or "").strip()
    if not title or not content:
        raise HTTPException(400, "篇名与正文必填")
    dup = db.query(ClassicalText).filter(ClassicalText.title == title).first()
    if dup:
        raise HTTPException(400, f"篇目「{title}」已存在")
    t = ClassicalText(title=title[:200], author=(req.author or "")[:100],
                      dynasty=(req.dynasty or "")[:50],
                      text_type=(req.text_type or "poem")[:20],
                      grade=req.grade, semester=(req.semester or "全")[:10],
                      unit=(req.unit or "")[:100], content=content,
                      lines_json=_build_lines(content),
                      tags=(req.tags or "")[:200])
    db.add(t)
    db.commit()
    _audit(db, admin.user_id, "classical_create", f"新增诗词 {title}")
    return {"id": t.id, "ok": True}


@router.put("/classicals/{cid}", summary="编辑诗词篇目")
def update_classical(cid: int, req: ClassicalReq, db: Session = Depends(get_db),
                     admin: Admin = Depends(_require_admin)):
    t = db.query(ClassicalText).get(cid)
    if not t:
        raise HTTPException(404, "篇目不存在")
    t.title = (req.title or "").strip()[:200]
    t.author, t.dynasty = (req.author or "")[:100], (req.dynasty or "")[:50]
    t.text_type = (req.text_type or "poem")[:20]
    t.grade, t.semester = req.grade, (req.semester or "全")[:10]
    t.unit = (req.unit or "")[:100]
    t.content = (req.content or "").strip()
    t.lines_json = _build_lines(t.content)
    t.tags = (req.tags or "")[:200]
    db.commit()
    _audit(db, admin.user_id, "classical_update", f"编辑诗词 id={cid}")
    return {"ok": True}


@router.delete("/classicals/{cid}", summary="删除诗词篇目")
def delete_classical(cid: int, db: Session = Depends(get_db),
                     admin: Admin = Depends(_require_admin)):
    t = db.query(ClassicalText).get(cid)
    if not t:
        raise HTTPException(404, "篇目不存在")
    from app.models.classical import ClassicalProgress
    bound = db.query(ClassicalProgress).filter(ClassicalProgress.text_id == cid).count()
    if bound > 0:
        raise HTTPException(400, f"该篇目有 {bound} 条学习进度记录，删除会丢失进度")
    db.delete(t)
    db.commit()
    _audit(db, admin.user_id, "classical_delete", f"删除诗词 id={cid} ({t.title})")
    return {"ok": True}


# ═══════════════ 语法知识点 ═══════════════

class GrammarReq(BaseModel):
    name: str
    code: str
    grade: int = 3
    category: str = "时态"
    description: str = ""
    examples: str = ""


@router.get("/grammar-points", summary="语法知识点列表")
def list_grammar_points(grade: int = 0, keyword: str = "",
                        db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    q = db.query(GrammarPoint)
    if grade > 0:
        q = q.filter(GrammarPoint.grade == grade)
    kw = keyword.strip()
    if kw:
        q = q.filter(GrammarPoint.name.like(f"%{kw}%"))
    rows = q.order_by(GrammarPoint.grade, GrammarPoint.id).all()
    return {"items": [{
        "id": g.id, "name": g.name, "code": g.code, "grade": g.grade,
        "category": g.category, "description": g.description,
        "examples": g.examples, "exercise_count": 0,
    } for g in rows]}


@router.post("/grammar-points", summary="新增语法点")
def create_grammar(req: GrammarReq, db: Session = Depends(get_db),
                   admin: Admin = Depends(_require_admin)):
    name = (req.name or "").strip()
    code = (req.code or "").strip()
    if not name or not code:
        raise HTTPException(400, "名称与编码必填")
    dup = db.query(GrammarPoint).filter(GrammarPoint.code == code).first()
    if dup:
        raise HTTPException(400, f"编码「{code}」已存在")
    g = GrammarPoint(name=name[:100], code=code[:50], grade=req.grade,
                     category=(req.category or "时态")[:50],
                     description=(req.description or "")[:500],
                     examples=req.examples or "")
    db.add(g)
    db.commit()
    _audit(db, admin.user_id, "grammar_create", f"新增语法点 {name}")
    return {"id": g.id, "ok": True}


@router.put("/grammar-points/{gid}", summary="编辑语法点")
def update_grammar(gid: int, req: GrammarReq, db: Session = Depends(get_db),
                   admin: Admin = Depends(_require_admin)):
    g = db.query(GrammarPoint).get(gid)
    if not g:
        raise HTTPException(404, "语法点不存在")
    g.name = (req.name or "").strip()[:100]
    g.grade, g.category = req.grade, (req.category or "时态")[:50]
    g.description = (req.description or "")[:500]
    g.examples = req.examples or ""
    db.commit()
    return {"ok": True}


@router.delete("/grammar-points/{gid}", summary="删除语法点（级联其练习题）")
def delete_grammar(gid: int, db: Session = Depends(get_db),
                   admin: Admin = Depends(_require_admin)):
    g = db.query(GrammarPoint).get(gid)
    if not g:
        raise HTTPException(404, "语法点不存在")
    db.query(GrammarExercise).filter(GrammarExercise.grammar_point_id == gid).delete()
    db.delete(g)
    db.commit()
    _audit(db, admin.user_id, "grammar_delete", f"删除语法点 id={gid}")
    return {"ok": True}


# ═══════════════ 知识点汇总（题型分类只读） ═══════════════

@router.get("/knowledge-points", summary="知识点汇总（题型分类 + 语法点）")
def knowledge_points(db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    cats = db.query(ProblemCategory).order_by(ProblemCategory.id).all()
    types = db.query(ProblemType).order_by(ProblemType.category_id, ProblemType.id).all()
    by_cat = {}
    for t in types:
        by_cat.setdefault(t.category_id, []).append({
            "id": t.id, "name": t.name, "code": t.code,
            "min_grade": t.min_grade, "max_grade": t.max_grade,
            "difficulty": t.difficulty, "is_active": bool(getattr(t, "is_active", True)),
        })
    return {
        "categories": [{"id": c.id, "name": c.name, "code": c.code or ""} for c in cats],
        "types_by_category": by_cat,
        "grammar_total": db.query(GrammarPoint).count(),
    }


# ═══════════════ 采集试卷管理（papers / paper_questions） ═══════════════

@router.get("/collected-papers", summary="采集试卷列表")
def list_collected_papers(keyword: str = "", subject: str = "", page: int = 1,
                          page_size: int = 20, db: Session = Depends(get_db),
                          admin: Admin = Depends(_require_admin)):
    q = db.query(Paper)
    kw = keyword.strip()
    if kw:
        q = q.filter(Paper.title.like(f"%{kw}%"))
    if subject:
        q = q.filter(Paper.subject == subject)
    total = q.count()
    rows = q.order_by(Paper.id.desc()).offset(
        max(0, (page - 1) * page_size)).limit(min(page_size, 100)).all()
    ids = [p.id for p in rows]
    counts = dict(db.query(PaperQuestion.paper_id, func.count(PaperQuestion.id)).filter(
        PaperQuestion.paper_id.in_(ids)).group_by(PaperQuestion.paper_id).all()) if ids else {}
    return {"total": total, "items": [{
        "id": p.id, "title": p.title, "subject": p.subject,
        "grade": p.grade, "source": p.source or "",
        "question_count": counts.get(p.id, 0),
        "created_at": str(p.created_at)[:16] if p.created_at else "",
    } for p in rows]}


@router.get("/collected-papers/{pid}", summary="采集试卷详情（题目列表）")
def collected_paper_detail(pid: int, db: Session = Depends(get_db),
                           admin: Admin = Depends(_require_admin)):
    p = db.query(Paper).get(pid)
    if not p:
        raise HTTPException(404, "试卷不存在")
    qs = db.query(PaperQuestion).filter(PaperQuestion.paper_id == pid).order_by(
        PaperQuestion.id).all()
    return {
        "id": p.id, "title": p.title, "subject": p.subject, "grade": p.grade,
        "source": p.source or "", "created_at": str(p.created_at)[:16] if p.created_at else "",
        "questions": [{
            "id": q.id, "seq": q.seq,
            "question": (q.question_text or "")[:200],
            "answer": (q.correct_answer or "")[:100],
            "question_type": q.qtype or "",
        } for q in qs],
    }


@router.delete("/collected-papers/{pid}", summary="删除采集试卷")
def delete_collected_paper(pid: int, db: Session = Depends(get_db),
                           admin: Admin = Depends(_require_admin)):
    p = db.query(Paper).get(pid)
    if not p:
        raise HTTPException(404, "试卷不存在")
    db.query(PaperQuestion).filter(PaperQuestion.paper_id == pid).delete()
    db.delete(p)
    db.commit()
    _audit(db, admin.user_id, "paper_delete", f"删除采集试卷 id={pid} ({p.title})")
    return {"ok": True}
