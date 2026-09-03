"""管理后台：知识点标注工作台（D2 内容域标注）

接口（挂 /api/admin 前缀，统一 require_perm 鉴权 + 审计落库）：
- GET  /content/kp/tree              知识点树（层级嵌套）            content:view
- POST /content/kp                   新增/编辑知识点                 content:manage
- GET  /content/annotation/queue     待标注题目队列                  content:annotate
- POST /content/annotation           提交标注（支持单题/批量）        content:annotate
- POST /content/annotation/ai-predict AI 预标注（返回建议，不落库）    content:annotate
- POST /content/annotation/import    CSV/行批量导入标注              content:annotate
- GET  /content/annotation/stats     标注进度统计                    content:view

服务实现位于 D2 内容域 app.domains.content.services.kp_annotation，
本模块仅经 app.domains.content.contracts 暴露的函数触达（import-linter 合规）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.exam import Question
from app.models.paper import PaperQuestion
from app.models.middle import MiddleQuestion
from app.models.knowledge import KnowledgePoint

from . import router
from .common import _audit, _require_admin
from app.core.permissions import require_perm
from app.domains.content import contracts as content_contracts

logger = logging.getLogger("admin.annotation")


# ═══════════════ 请求模型 ═══════════════

class KpSaveReq(BaseModel):
    kp_id: int | None = None  # 有值=编辑，无值=新增
    subject: str
    grade: int = 7
    unit: str = ""
    title: str
    summary: str = ""
    content: str = ""
    examples: str = ""
    parent_id: int = 0
    code: str = ""
    sort_order: int = 0
    status: str = "active"
    textbook_ver: str = ""


class AnnotationSubmitReq(BaseModel):
    source_table: str = "questions"
    question_id: int | None = None
    kp_ids: list[int] = []
    # 批量：[{question_id, kp_ids}]；与单题字段互斥，优先用批量
    annotations: list[dict] | None = None
    annotated_by: str = ""


class AiPredictReq(BaseModel):
    source_table: str = "questions"
    question_id: int | None = None
    question_text: str = ""  # 可选；缺省时按 source_table+question_id 回查


class AnnotationImportReq(BaseModel):
    # 行导入：[{source_table, question_id, kp_id, is_primary, weight, source, confidence}]
    rows: list[dict] = []
    annotated_by: str = ""


# ═══════════════ 辅助：按 source_table 回查题干 ═══════════════

def _load_question_text(db: Session, source_table: str, question_id: int) -> str:
    if source_table == "paper_questions":
        q = db.get(PaperQuestion, question_id)
        return (q.question_text or "") if q else ""
    if source_table == "middle_questions":
        q = db.get(MiddleQuestion, question_id)
        return (q.question_text or "") if q else ""
    q = db.get(Question, question_id)
    return (q.question or "") if q else ""


# ═══════════════ 知识点树 ═══════════════

@router.get("/content/kp/tree", summary="知识点树（层级嵌套）")
def kp_tree(subject: str = "", grade: int = 0,
            db: Session = Depends(get_db),
            admin: Admin = Depends(require_perm("content:view"))):
    tree = content_contracts.get_kp_tree(db, subject=subject, grade=grade)
    return {"tree": tree, "total": len(tree)}


# ═══════════════ 新增/编辑知识点 ═══════════════

@router.post("/content/kp", summary="新增/编辑知识点")
def save_kp(req: KpSaveReq, db: Session = Depends(get_db),
            admin: Admin = Depends(require_perm("content:manage"))):
    subject = (req.subject or "").strip()
    title = (req.title or "").strip()
    if not subject:
        raise HTTPException(400, "学科不能为空")
    if not title:
        raise HTTPException(400, "知识点标题不能为空")
    if not (1 <= req.grade <= 9):
        raise HTTPException(400, "年级需在 1-9 之间")
    data = {
        "subject": subject[:20], "grade": req.grade,
        "unit": (req.unit or "").strip()[:100], "title": title[:200],
        "summary": (req.summary or "").strip()[:500],
        "content": req.content or "", "examples": req.examples or "",
        "parent_id": max(0, int(req.parent_id or 0)),
        "code": (req.code or "").strip()[:64],
        "sort_order": int(req.sort_order or 0),
        "status": (req.status or "active")[:16],
        "textbook_ver": (req.textbook_ver or "").strip()[:32],
    }
    kp = content_contracts.create_or_update_kp(db, data, kp_id=req.kp_id)
    db.commit()
    _audit(db, admin, "kp_save", f"kp:{kp.id}",
           f"{'编辑' if req.kp_id else '新增'}知识点 {subject} G{req.grade} {title}")
    return {"id": kp.id, "ok": True}


# ═══════════════ 待标注队列 ═══════════════

@router.get("/content/annotation/queue", summary="待标注题目队列")
def annotation_queue(subject: str = "", source_table: str = "questions",
                     page: int = 1, page_size: int = 100,
                     db: Session = Depends(get_db),
                     admin: Admin = Depends(require_perm("content:annotate"))):
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 100
    queue = content_contracts.get_annotation_queue(
        db, subject=subject, source_table=source_table, page=page, page_size=page_size)
    return queue


# ═══════════════ 提交标注（单题/批量） ═══════════════

@router.post("/content/annotation", summary="提交标注（可批量）")
def submit_annotation(req: AnnotationSubmitReq, db: Session = Depends(get_db),
                      admin: Admin = Depends(require_perm("content:annotate"))):
    annotated_by = (req.annotated_by or admin.username or "admin")[:64]
    items = []
    if req.annotations:
        for it in req.annotations:
            qid = int(it.get("question_id"))
            kp_ids = [int(x) for x in it.get("kp_ids", [])]
            if qid and kp_ids:
                items.append((req.source_table, qid, kp_ids))
    elif req.question_id and req.kp_ids:
        items.append((req.source_table, int(req.question_id),
                      [int(x) for x in req.kp_ids]))
    if not items:
        raise HTTPException(400, "缺少有效的 question_id/kp_ids")
    added = 0
    for source_table, qid, kp_ids in items:
        added += content_contracts.submit_annotation(
            db, source_table, qid, kp_ids, annotated_by=annotated_by)
    db.commit()
    _audit(db, admin, "annotation_submit", f"q:{items[0][1]}",
           f"提交标注 {len(items)} 题，新增 {added} 条映射")
    return {"ok": True, "questions": len(items), "added": added}


# ═══════════════ AI 预标注（建议，不落库） ═══════════════

@router.post("/content/annotation/ai-predict", summary="AI 预标注（返回建议）")
def ai_predict(req: AiPredictReq, db: Session = Depends(get_db),
               admin: Admin = Depends(require_perm("content:annotate"))):
    text = (req.question_text or "").strip()
    if not text and req.question_id:
        text = _load_question_text(db, req.source_table, int(req.question_id))
    if not text:
        raise HTTPException(400, "缺少题干（question_text 或 question_id）")
    # 构建知识点目录（按学科裁剪，降低 prompt 噪声）
    catalog = [{"id": k.id, "title": k.title, "subject": k.subject}
               for k in db.query(KnowledgePoint).all()]
    preds = content_contracts.predict_kp_for_question(text, catalog)
    return {"predictions": preds or []}


# ═══════════════ 批量导入 ═══════════════

@router.post("/content/annotation/import", summary="批量导入标注")
def import_annotation(req: AnnotationImportReq, db: Session = Depends(get_db),
                      admin: Admin = Depends(require_perm("content:annotate"))):
    if not req.rows:
        raise HTTPException(400, "rows 不能为空")
    annotated_by = (req.annotated_by or admin.username or "import")[:64]
    res = content_contracts.batch_import_kp(db, req.rows, annotated_by=annotated_by)
    db.commit()
    _audit(db, admin, "annotation_import", "annotation",
           f"导入标注 {len(req.rows)} 行，新增 {res.get('added', 0)}，"
           f"跳过 {res.get('skipped', 0)}，错误 {len(res.get('errors', []))}")
    return {"ok": True, **res}


# ═══════════════ 标注进度统计 ═══════════════

@router.get("/content/annotation/stats", summary="标注进度统计")
def annotation_stats(source_table: str = "questions",
                     db: Session = Depends(get_db),
                     admin: Admin = Depends(require_perm("content:view"))):
    stats = content_contracts.get_annotation_stats(db, source_table=source_table)
    return stats
