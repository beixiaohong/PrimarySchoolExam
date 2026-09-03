"""D2 内容域：题目-知识点标注服务（S2-M2 / 07-技术实施方案 §3.2.1 / §4.4 / §10.C）

职责：
- 知识点树查询（parent_id 层级嵌套）
- 标注队列（待标注题目）、提交标注（人工）、批量导入（CSV/JSON）
- 标注进度统计（覆盖率，按学科）
- 知识点新增/编辑（POST /api/admin/content/kp）
- AI 预标注（DeepSeek-only，遵守持连铁律：短会话读 → 关闭 → 调 AI → 短会话写）

对外经 `app.domains.content.contracts` 暴露给后台路由（import-linter 合规）。
跨域调用 AI 网关仅经 `app.domains.platform.contracts`（与 answer_generator 同范式）。

持连铁律：所有 AI 调用（`predict_kp_for_question` / `ai_annotate_questions`）绝不在
持有 DB 会话时进行——`ai_annotate_questions` 显式「读(短会话)→关→调 AI→写(短会话)」。
"""
import json
import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.models.exam import Question
from app.models.kp_map import QuestionKpMap
from app.domains.platform.contracts import chat, ai_any_enabled

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# ───────────────────────── 知识点树 / 编辑 ─────────────────────────

def get_kp_tree(db: Session, subject: str = "", grade: int = 0) -> list:
    """返回知识点树（按 parent_id 层级嵌套为 children）。"""
    q = db.query(KnowledgePoint)
    if subject:
        q = q.filter(KnowledgePoint.subject == subject)
    if grade:
        q = q.filter(KnowledgePoint.grade == grade)
    nodes = q.order_by(KnowledgePoint.subject, KnowledgePoint.sort_order,
                       KnowledgePoint.id).all()
    by_id = {}
    for n in nodes:
        by_id[n.id] = {
            "id": n.id, "subject": n.subject, "grade": n.grade, "title": n.title,
            "code": n.code or "", "parent_id": n.parent_id or 0,
            "status": n.status or "active", "children": [],
        }
    roots = []
    for n in by_id.values():
        parent = by_id.get(n["parent_id"]) if n["parent_id"] else None
        if parent:
            parent["children"].append(n)
        else:
            roots.append(n)
    return roots


def create_or_update_kp(db: Session, data: dict, kp_id: int = None) -> KnowledgePoint:
    """新增或编辑知识点（POST /api/admin/content/kp）。
    data 接受模型字段名：subject/grade/unit/title/summary/content/examples/
    difficulty/source/parent_id/code/sort_order/status/textbook_ver。
    """
    if kp_id:
        kp = db.get(KnowledgePoint, kp_id)
        if not kp:
            raise ValueError("知识点不存在")
    else:
        kp = KnowledgePoint()
        db.add(kp)
    fields = ("subject", "grade", "unit", "title", "summary", "content", "examples",
              "difficulty", "source", "parent_id", "code", "sort_order", "status",
              "textbook_ver")
    for f in fields:
        if f in data:
            setattr(kp, f, data[f])
    kp.updated_at = datetime.now()
    db.flush()
    return kp


# ───────────────────────── 标注队列 / 提交 / 导入 ─────────────────────────

def get_annotation_queue(db: Session, subject: str = "", source_table: str = "questions",
                         page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    """待标注题目队列：questions 中尚无 question_kp_map 行的题目（分页）。"""
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    subq = db.query(QuestionKpMap.question_id).filter(
        QuestionKpMap.source_table == source_table)
    q = db.query(Question).filter(~Question.id.in_(subq))
    if subject:
        q = q.filter(Question.subject == subject)
    total = q.count()
    rows = q.order_by(Question.id).offset((page - 1) * page_size).limit(page_size).all()
    items = [{
        "question_id": r.id, "subject": r.subject, "category": r.category or "",
        "type_name": r.type_name or "", "question": (r.question or "")[:500],
    } for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def submit_annotation(db: Session, source_table: str, question_id: int,
                      kp_ids: list, annotated_by: str = "",
                      is_primary_first: bool = True) -> int:
    """提交（人工）标注：删除该题目旧标注，按 kp_ids 顺序重建（首项主知识点）。"""
    clean = list(dict.fromkeys([int(x) for x in kp_ids if x]))
    if not clean:
        raise ValueError("至少选择一个知识点")
    db.query(QuestionKpMap).filter(
        QuestionKpMap.source_table == source_table,
        QuestionKpMap.question_id == question_id).delete()
    added = 0
    for idx, kp_id in enumerate(clean):
        is_primary = 1 if (is_primary_first and idx == 0) else 0
        db.add(QuestionKpMap(
            source_table=source_table, question_id=question_id, kp_id=kp_id,
            is_primary=is_primary, weight=1.00 if is_primary else 0.50,
            source="manual", confidence=1.000,
            annotated_by=annotated_by or "", reviewed_by="", status="active"))
        added += 1
    return added


def batch_import(db: Session, rows: list, annotated_by: str = "import") -> dict:
    """批量导入标注（CSV/JSON 行）。每行：source_table/question_id/kp_id/
    is_primary/weight/source/confidence。唯一约束命中则跳过。

    注：SessionLocal 关闭了 autoflush，故用 in-memory seen 集合做「批内去重」，
    避免同一批次内的重复行因未 flush 而躲过 DB 唯一性预检、最终触发 IntegrityError。
    """
    added = skipped = 0
    errors = []
    seen = set()  # (source_table, question_id, kp_id)
    for i, row in enumerate(rows):
        try:
            source_table = row.get("source_table") or "questions"
            question_id = int(row["question_id"])
            kp_id = int(row["kp_id"])
            key = (source_table, question_id, kp_id)
            if key in seen:
                skipped += 1
                continue
            is_primary = int(row.get("is_primary", 1) or 1)
            weight = float(row.get("weight", 1.00 if is_primary else 0.50))
            exists = db.query(QuestionKpMap.id).filter(
                QuestionKpMap.source_table == source_table,
                QuestionKpMap.question_id == question_id,
                QuestionKpMap.kp_id == kp_id).first()
            if exists:
                skipped += 1
                seen.add(key)
                continue
            db.add(QuestionKpMap(
                source_table=source_table, question_id=question_id, kp_id=kp_id,
                is_primary=is_primary, weight=weight,
                source=row.get("source") or "batch_import",
                confidence=float(row.get("confidence", 1.000)),
                annotated_by=annotated_by, reviewed_by="", status="active"))
            added += 1
            seen.add(key)
        except Exception as e:
            errors.append({"row": i, "error": str(e)})
    return {"added": added, "skipped": skipped, "errors": errors}


def get_annotation_stats(db: Session, source_table: str = "questions") -> dict:
    """标注进度统计：总量 / 已标注量 / 覆盖率（按学科）。"""
    total = db.query(Question).count()
    annotated = db.query(func.count(func.distinct(QuestionKpMap.question_id))).filter(
        QuestionKpMap.source_table == source_table).scalar() or 0
    coverage = round(annotated / total * 100, 1) if total else 0.0
    by_subject = []
    for subj, cnt in db.query(Question.subject, func.count(Question.id)).group_by(
            Question.subject).all():
        ann = db.query(func.count(func.distinct(QuestionKpMap.question_id))).filter(
            QuestionKpMap.source_table == source_table,
            QuestionKpMap.question_id.in_(
                db.query(Question.id).filter(Question.subject == subj))).scalar() or 0
        by_subject.append({
            "subject": subj, "total": cnt, "annotated": ann,
            "coverage": round(ann / cnt * 100, 1) if cnt else 0.0,
        })
    return {"total": total, "annotated": annotated, "coverage": coverage,
            "by_subject": by_subject}


# ───────────────────────── AI 预标注（持连铁律） ─────────────────────────

def predict_kp_for_question(question_text: str, catalog: list) -> list:
    """调用 AI 预测知识点（cheap 模型）。catalog: [{id, title, subject}]。
    返回 [{kp_id, confidence}]。不持有 DB 会话。
    """
    if not ai_any_enabled():
        logger.info("AI 未启用，跳过预标注")
        return []
    if not catalog:
        return []
    cat_text = "\n".join(f"{c['id']}: [{c['subject']}] {c['title']}" for c in catalog)
    system = (
        "你是 K12 题库的知识点标注助手。给定题目与可选知识点清单，"
        "请判断题目涉及哪些知识点，仅从清单中选择。输出 JSON 数组，"
        "每项含 kp_id(整数) 与 confidence(0~1 两位小数)。"
        "若无合适知识点输出空数组 []。只输出 JSON，不要解释。"
    )
    user = f"可选知识点清单：\n{cat_text}\n\n题目：\n{question_text[:1500]}"
    try:
        res = chat(system, user, max_tokens=600)
    except Exception as e:  # AI 异常不应中断批量任务
        logger.warning("AI 预标注调用异常：%s", e)
        return []
    if not res:
        return []
    text = res.get("text") if isinstance(res, dict) else str(res)
    if not text:
        return []
    return _parse_kp_json(text, {c["id"] for c in catalog})


def _parse_kp_json(text: str, valid_ids: set) -> list:
    """从 AI 文本中提取 JSON 数组，过滤非法 kp_id，约束 confidence。"""
    try:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        arr = json.loads(text[start:end + 1])
        out = []
        for item in arr:
            try:
                kp_id = int(item.get("kp_id"))
            except (TypeError, ValueError):
                continue
            if kp_id not in valid_ids:
                continue
            conf = float(item.get("confidence", 0.8))
            conf = max(0.0, min(1.0, round(conf, 3)))
            out.append({"kp_id": kp_id, "confidence": conf})
        return out
    except Exception:
        return []


def ai_annotate_questions(question_ids: list, annotated_by: str = "ai",
                          source_table: str = "questions") -> dict:
    """对一批题目做 AI 预标注（持连铁律：读→关→AI→写）。

    仅当题目尚无任何标注时才写入 ai_pred 行，绝不覆盖人工标注。
    返回 {processed, predicted, skipped_ai, failed}。
    """
    if not ai_any_enabled():
        return {"processed": 0, "predicted": 0, "skipped_ai": True, "failed": 0}
    # 1) 短会话：读题目 + 全量知识点目录
    with SessionLocal() as db:
        qs = db.query(Question).filter(Question.id.in_(question_ids)).all()
        questions = [{"id": q.id, "subject": q.subject or "",
                      "question": q.question or ""} for q in qs]
        all_kps = db.query(KnowledgePoint).all()
    # 2) 无会话：逐题调 AI
    results = []
    for q in questions:
        catalog = [{"id": k.id, "title": k.title, "subject": k.subject}
                   for k in all_kps if k.subject == q["subject"]]
        preds = predict_kp_for_question(q["question"], catalog)
        results.append((q["id"], preds))
    # 3) 短会话：写回（仅填补未标注题）
    # 注意：本会话由 ai_annotate_questions 自管，写完后必须 commit，否则 with 退出
    # 回滚导致标注丢失（持连铁律：读/写各自独立短会话，写会话显式提交）。
    predicted = 0
    with SessionLocal() as db:
        for qid, preds in results:
            if not preds:
                continue
            exists = db.query(QuestionKpMap.id).filter(
                QuestionKpMap.source_table == source_table,
                QuestionKpMap.question_id == qid).first()
            if exists:
                continue
            for idx, p in enumerate(preds):
                is_primary = 1 if idx == 0 else 0
                db.add(QuestionKpMap(
                    source_table=source_table, question_id=qid, kp_id=p["kp_id"],
                    is_primary=is_primary, weight=1.00 if is_primary else 0.50,
                    source="ai_pred", confidence=p["confidence"],
                    annotated_by=annotated_by, reviewed_by="", status="active"))
                predicted += 1
        db.commit()
    return {"processed": len(questions), "predicted": predicted,
            "skipped_ai": False, "failed": 0}
