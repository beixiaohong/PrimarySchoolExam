"""多 AI 联合校对服务（D6 决议）：机器先行、人工兜底

流程：
- 取待校对内容（review_status=pending 的 middle_questions / reading_passages）
- 至少 2 个独立供应商独立审阅（默认 zhipu + relay，均为免费链独立供应商）
  各自给出 verdict(pass/fail) + 理由
- 汇总：全部 pass → approved（可进出题池）
        存在 fail 或意见不一 → conflict（进管理后台人工审核队列）
- 人工裁决：approved / rejected（rejected 剔出出题池）

AI 不可用（未配置 Key / 超时）时该供应商跳过；若没有供应商响应则保留 pending 待重试。
"""
import json
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.content_review import ContentReview
from ..models.middle import MiddleQuestion
from ..models.reading import ReadingPassage
from ..services import ai as ai_svc

logger = logging.getLogger(__name__)

# 两个独立供应商（均为免费链，互不影响）
REVIEW_PROVIDERS = ["zhipu", "relay"]

CONTENT_MODELS = {
    "middle_question": MiddleQuestion,
    "reading_passage": ReadingPassage,
}


def _extract_json(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                return None
    return None


def _content_text(content_type: str, obj) -> str:
    """拼装待校对内容的文本描述（供 AI 审阅）"""
    if content_type == "middle_question":
        try:
            opts = json.loads(obj.options_json or "[]")
        except Exception:
            opts = []
        return (
            f"【学科】{obj.subject}（{obj.grade}年级）\n"
            f"【题干】{obj.question}\n"
            f"【选项】{chr(10).join(opts)}\n"
            f"【标准答案】{obj.answer}\n"
            f"【解析】{obj.analysis or '（无）'}"
        )
    if content_type == "reading_passage":
        try:
            qs = json.loads(obj.questions_json or "[]")
        except Exception:
            qs = []
        qtxt = "\n".join(
            f"{i+1}. [{q.get('type')}] {q.get('question')} 答案：{q.get('answer')}"
            for i, q in enumerate(qs)
        )
        return f"【篇名】{obj.title}（{obj.grade}年级·{obj.subject}）\n【正文】{obj.passage}\n【题目】\n{qtxt}"
    return ""


def _review_prompt() -> str:
    return (
        "你是题库质量审核老师。请判断下面这道题目/篇目的「题干正确性、答案正确性、"
        "干扰项有效性、年级/难度标注匹配」是否合格。只输出 JSON，不要多余解释："
        '{"verdict": "pass" 或 "fail", "comment": "一句话审核意见，fail 时说明问题"}'
    )


def run_reviews(db: Session, content_types: list = None, limit: int = 50,
                user_id: str = "admin") -> dict:
    """批量触发多 AI 校对；返回 {reviewed, approved, conflict}"""
    types = content_types or list(CONTENT_MODELS.keys())
    reviewed = approved = conflict = 0
    for ctype in types:
        model = CONTENT_MODELS.get(ctype)
        if not model:
            continue
        rows = db.query(model).filter(model.review_status == "pending").limit(limit).all()
        for obj in rows:
            ok = _review_one(db, ctype, obj.id, user_id)
            if ok:
                reviewed += 1
                if (model == MiddleQuestion and db.query(MiddleQuestion).filter(MiddleQuestion.id == obj.id).first().review_status == "approved") or \
                   (model == ReadingPassage and db.query(ReadingPassage).filter(ReadingPassage.id == obj.id).first().review_status == "approved"):
                    approved += 1
                else:
                    conflict += 1
    return {"reviewed": reviewed, "approved": approved, "conflict": conflict}


def _review_one(db: Session, content_type: str, content_id: int, user_id: str) -> bool:
    model = CONTENT_MODELS[content_type]
    obj = db.query(model).filter(model.id == content_id).first()
    if not obj:
        return False
    text = _content_text(content_type, obj)
    prompt = _review_prompt()

    verdicts = []
    comments = []
    for p in REVIEW_PROVIDERS:
        result = ai_svc.chat_with(user_id, prompt, "待审内容：\n" + text, provider=p, max_tokens=400)
        if not result or not result.get("text"):
            continue
        data = _extract_json(result["text"])
        if not data or "verdict" not in data:
            continue
        v = "pass" if str(data.get("verdict")).lower().startswith("pass") else "fail"
        verdicts.append(v)
        comments.append(f"[{p}] {data.get('comment', '')}")
        db.add(ContentReview(
            content_type=content_type, content_id=content_id,
            provider=p, model=result.get("model", ""),
            verdict=v, comment=data.get("comment", ""),
        ))

    # 汇总规则
    if not verdicts:
        # 无供应商响应，保留 pending 待重试
        db.commit()
        return False
    if "fail" in verdicts or len(set(verdicts)) > 1:
        obj.review_status = "conflict"
    else:
        obj.review_status = "approved"
    db.commit()
    return True


def list_reviews(db: Session, status: str = "conflict", page: int = 1,
                 page_size: int = 20) -> dict:
    """审核队列：列出某状态的内容（含预览 + 各 AI 意见）"""
    items = []
    total = 0
    for ctype, model in CONTENT_MODELS.items():
        q = db.query(model).filter(model.review_status == status)
        total += q.count()
    rows_all = []
    for ctype, model in CONTENT_MODELS.items():
        for obj in db.query(model).filter(model.review_status == status).all():
            rows_all.append((ctype, obj))
    start = max(0, (page - 1) * page_size)
    page_rows = rows_all[start:start + page_size]

    for ctype, obj in page_rows:
        reviews = db.query(ContentReview).filter(
            ContentReview.content_type == ctype,
            ContentReview.content_id == obj.id,
        ).order_by(ContentReview.id.desc()).all()
        preview = _content_text(ctype, obj)
        items.append({
            "content_type": ctype,
            "content_id": obj.id,
            "review_status": obj.review_status,
            "preview": preview[:300],
            "reviews": [{"provider": r.provider, "verdict": r.verdict,
                         "comment": r.comment, "model": r.model} for r in reviews],
        })
    return {"status": status, "total": total, "page": page, "page_size": page_size, "items": items}


def resolve_review(db: Session, content_type: str, content_id: int, verdict: str) -> dict:
    """人工裁决：approved / rejected"""
    if verdict not in ("approved", "rejected"):
        return {"ok": False, "error": "verdict 仅支持 approved/rejected"}
    model = CONTENT_MODELS.get(content_type)
    if not model:
        return {"ok": False, "error": "未知内容类型"}
    obj = db.query(model).filter(model.id == content_id).first()
    if not obj:
        return {"ok": False, "error": "内容不存在"}
    obj.review_status = verdict
    # 记录一条人工裁决
    db.add(ContentReview(
        content_type=content_type, content_id=content_id,
        provider="human", model="", verdict=verdict,
        comment=f"人工裁决：{verdict}",
    ))
    db.commit()
    return {"ok": True, "content_type": content_type, "content_id": content_id,
            "review_status": verdict}
