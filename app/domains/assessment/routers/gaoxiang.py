"""软考高项备考路由（assessment 域，挂载于 /api/gx）

面向非学生成人用户（软考高级·信息系统项目管理师）。与小学侧完全独立：
不挂 check_quiet_hours（成人晚间备考是核心场景），科目/年级维度也不共享。

端点一览：
- GET  /domains                十大知识域清单（静态）
- GET  /knowledge              知识点列表（?domain=&user_id=）
- GET  /knowledge/{kid}        知识点详情
- POST /knowledge/generate     AI 生成知识域知识点并落库（复用不重复扣费）
- POST /quiz/generate          刷题出题：题库优先，不足 AI 补（落库）
- POST /quiz/submit            提交选择题作答（服务端判分 + 错题闭环 + 进度）
- GET  /wrong                  错题列表（?user_id=，含已掌握可选）
- POST /wrong/master           手动标记错题已掌握
- POST /case/generate          AI 出案例分析大题（落库）
- POST /case/grade             AI 批改案例作答（评分 + 逐条反馈）
- GET  /progress               分知识域学习进度（?user_id=）

铁律遵守：AI 调用在 DB 会话之外；成功后才开短会话落库并按 token 扣钻
（计费失败不阻断，与全站一致）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.domains.assessment.services import gaoxiang as gx
from app.models.gaoxiang import GxKnowledge, GxQuestion, GxWrong, GxCaseGrade, GxAttempt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["高项备考"])


class UserIdReq(BaseModel):
    user_id: str


class KnowledgeGenReq(UserIdReq):
    domain: str


class QuizGenReq(UserIdReq):
    domain: str
    qtype: str = gx.QTYPE_SINGLE      # single / multi
    count: int = 5


class QuizSubmitReq(UserIdReq):
    answers: list                      # [{question_id, answer, duration_ms}]


class WrongMasterReq(UserIdReq):
    question_id: int


class CaseGenReq(UserIdReq):
    domain: str


class CaseGradeReq(UserIdReq):
    question_id: int = None            # 现场临时出题（未落库）时为空
    question_text: str = ""
    user_answer: str = ""


def _check_domain(domain: str) -> str:
    if domain not in gx.GX_DOMAINS:
        raise HTTPException(400, f"知识域可选：{'/'.join(gx.GX_DOMAINS)}")
    return domain


def _consume_tokens(user_id: str, resp: dict, biz: str) -> None:
    """按 token 扣钻（短会话；失败不阻断 —— 与 ai_quiz 等全站行为一致）"""
    try:
        from app.domains.commerce.contracts import DiamondService
        db = SessionLocal()
        try:
            DiamondService.consume(db, user_id,
                                   (resp or {}).get("prompt_tokens", 0),
                                   (resp or {}).get("completion_tokens", 0),
                                   biz=biz)
        finally:
            db.close()
    except Exception:
        pass


def _call_ai(user_id: str, system: str, user: str, max_tokens: int,
             retries: int = 2):
    """AI 调用（不持 DB 连接），失败返回 None"""
    from app.domains.platform.contracts import chat_with
    for _ in range(retries):
        resp = chat_with(user_id, system, user, max_tokens=max_tokens)
        if resp and (resp.get("text") or "").strip():
            return resp
    return None


# ── 静态清单 ──

@router.get("/domains", summary="知识域清单")
def list_domains():
    return {"domains": gx.GX_DOMAINS, "qtypes": list(gx.QTYPES)}


# ── 知识点 ──

@router.get("/knowledge", summary="知识点列表")
def list_knowledge(user_id: str, domain: str = "", db: Session = Depends(get_db)):
    q = db.query(GxKnowledge)
    if domain:
        _check_domain(domain)
        q = q.filter(GxKnowledge.domain == domain)
    rows = q.order_by(GxKnowledge.domain, GxKnowledge.id).all()
    return {"items": [{"id": k.id, "domain": k.domain, "code": k.code,
                       "title": k.title, "summary": k.summary} for k in rows]}


@router.get("/knowledge/{kid}", summary="知识点详情")
def knowledge_detail(kid: int, user_id: str, db: Session = Depends(get_db)):
    k = db.get(GxKnowledge, kid)
    if k is None:
        raise HTTPException(404, "知识点不存在")
    return {"id": k.id, "domain": k.domain, "code": k.code, "title": k.title,
            "summary": k.summary, "content": k.content}


@router.post("/knowledge/generate", summary="AI 生成知识域知识点")
def generate_knowledge(req: KnowledgeGenReq):
    _check_domain(req.domain)
    # AI 调用在会话外（可能重试 2 次），不占数据库连接
    resp = _call_ai(
        req.user_id, gx.KNOWLEDGE_SYSTEM_PROMPT,
        f"请生成「{req.domain}」知识域的核心知识点卡片 4-6 个。", max_tokens=2000)
    points = gx.parse_knowledge((resp or {}).get("text", ""))
    if not points:
        raise HTTPException(502, "AI 生成失败了，稍后再试一次吧")

    db = SessionLocal()
    try:
        # 按 (domain, title) 去重：AI 重复生成时只补新的，旧的保留（复用不重复扣费）
        exist = {t for (t,) in db.query(GxKnowledge.title)
                 .filter(GxKnowledge.domain == req.domain).all()}
        added = 0
        for p in points:
            if p["title"] in exist:
                continue
            db.add(GxKnowledge(domain=req.domain, code=p["code"], title=p["title"],
                               summary=p["summary"], content=p["content"]))
            added += 1
        db.commit()
    finally:
        db.close()
    _consume_tokens(req.user_id, resp, biz="gx_knowledge")
    return {"domain": req.domain, "generated": len(points), "added": added}


# ── 刷题 ──

def _gen_questions(req: QuizGenReq, need: int) -> list:
    """AI 补生成 need 道题并落库（会话外调 AI，短会话写库）"""
    qtype = req.qtype
    label = "单选" if qtype == gx.QTYPE_SINGLE else "多选"
    resp = _call_ai(req.user_id, gx.QUIZ_SYSTEM_PROMPT,
                    f"请出 {need} 道{label}题（知识域：{req.domain}）。",
                    max_tokens=2200)
    parsed = gx.parse_questions((resp or {}).get("text", ""))[:need]
    if not parsed:
        return []
    db = SessionLocal()
    try:
        ids = []
        for p in parsed:
            row = GxQuestion(domain=req.domain, qtype=qtype, question=p["question"],
                             options_json=None, answer=p["answer"], analysis=p["analysis"])
            if p["options"]:
                import json as _json
                row.options_json = _json.dumps(p["options"], ensure_ascii=False)
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.commit()
    finally:
        db.close()
    _consume_tokens(req.user_id, resp, biz="gx_quiz")
    return ids


@router.post("/quiz/generate", summary="刷题出题（题库优先，不足 AI 补）")
def quiz_generate(req: QuizGenReq):
    """不依赖 Depends(get_db)：AI 补题写库后需回读新行，请求级会话在
    REPEATABLE READ 下快照冻结读不到 —— 全程用独立短会话（与铁律一致）。"""
    _check_domain(req.domain)
    if req.qtype not in (gx.QTYPE_SINGLE, gx.QTYPE_MULTI):
        raise HTTPException(400, "qtype 只能是 single 或 multi（案例题走 /case/generate）")
    count = max(1, min(int(req.count or 5), 10))

    # 1) 题库优先（短会话一）：取该用户在此题型/知识域下未做过的题
    picked_ids = []
    s1 = SessionLocal()
    try:
        done = {r[0] for r in s1.query(GxAttempt.question_id)
                .filter(GxAttempt.user_id == req.user_id).all()}
        rows = (s1.query(GxQuestion.id)
                .filter(GxQuestion.domain == req.domain, GxQuestion.qtype == req.qtype)
                .order_by(GxQuestion.id).all())
        picked_ids = [r[0] for r in rows if r[0] not in done][:count]
    finally:
        s1.close()

    # 2) 不足则 AI 补生成落库（会话外调 AI；_gen_questions 内部用独立会话写库）
    if len(picked_ids) < count:
        picked_ids.extend(_gen_questions(req, count - len(picked_ids)))

    # 3) 短会话二回读（能读到 AI 刚落库的新行）
    items = []
    s2 = SessionLocal()
    try:
        import json as _json
        for r in s2.query(GxQuestion).filter(GxQuestion.id.in_(picked_ids)) \
                   .order_by(GxQuestion.id).all():
            try:
                options = _json.loads(r.options_json) if r.options_json else None
            except ValueError:
                options = None
            items.append({"id": r.id, "qtype": r.qtype, "question": r.question,
                          "options": options})
    finally:
        s2.close()
    return {"domain": req.domain, "qtype": req.qtype, "count": len(items), "questions": items}


@router.post("/quiz/submit", summary="提交选择题作答（服务端判分）")
def quiz_submit(req: QuizSubmitReq, db: Session = Depends(get_db)):
    if not req.answers:
        raise HTTPException(400, "answers 不能为空")
    results = []
    for a in req.answers[:20]:
        try:
            qid = int(a.get("question_id"))
        except (TypeError, ValueError):
            raise HTTPException(400, "question_id 非法")
        question = db.get(GxQuestion, qid)
        if question is None:
            results.append({"question_id": qid, "found": False})
            continue
        # 案例题不走此端点判分（走 /case/grade 的 AI 批改）
        if question.qtype == gx.QTYPE_CASE:
            raise HTTPException(400, f"题 {qid} 是案例题，请走 /case/grade 批改")
        out = gx.record_choice_attempt(db, req.user_id, question,
                                       str(a.get("answer") or ""),
                                       a.get("duration_ms") or 0)
        results.append({"question_id": qid, "found": True, **out})
    return {"results": results}


# ── 错题本 ──

@router.get("/wrong", summary="错题列表")
def wrong_list(user_id: str, include_mastered: bool = False,
               db: Session = Depends(get_db)):
    q = db.query(GxWrong).filter(GxWrong.user_id == user_id)
    if not include_mastered:
        q = q.filter(GxWrong.is_mastered.is_(False))
    rows = q.order_by(GxWrong.last_wrong_at.desc()).limit(100).all()
    items = []
    for w in rows:
        question = db.get(GxQuestion, w.question_id)
        if question is None:
            continue
        import json as _json
        try:
            options = _json.loads(question.options_json) if question.options_json else None
        except ValueError:
            options = None
        items.append({"id": w.id, "question_id": w.question_id,
                      "domain": question.domain, "qtype": question.qtype,
                      "question": question.question, "options": options,
                      "user_answer": w.user_answer, "wrong_count": w.wrong_count,
                      "correct_streak": w.correct_streak,
                      "is_mastered": w.is_mastered})
    return {"items": items, "count": len(items)}


@router.post("/wrong/master", summary="标记错题已掌握")
def wrong_master(req: WrongMasterReq, db: Session = Depends(get_db)):
    ok = gx.mark_mastered(db, req.user_id, req.question_id)
    if not ok:
        raise HTTPException(404, "错题不存在或已掌握")
    return {"question_id": req.question_id, "is_mastered": True}


# ── 案例分析 ──

@router.post("/case/generate", summary="AI 出案例分析大题")
def case_generate(req: CaseGenReq):
    _check_domain(req.domain)
    resp = _call_ai(req.user_id, gx.CASE_SYSTEM_PROMPT,
                    f"请出一道「{req.domain}」知识域的案例分析大题。", max_tokens=2400)
    case = gx.parse_case((resp or {}).get("text", ""))
    if not case:
        raise HTTPException(502, "AI 生成失败了，稍后再试一次吧")

    qid = None
    db = SessionLocal()
    try:
        row = GxQuestion(domain=req.domain, qtype=gx.QTYPE_CASE,
                         question=case["background"], options_json=None,
                         answer="", analysis="")
        import json as _json
        row.sub_questions = _json.dumps(case["sub_questions"], ensure_ascii=False)
        db.add(row)
        db.commit()
        qid = row.id
    finally:
        db.close()
    _consume_tokens(req.user_id, resp, biz="gx_case")
    return {"question_id": qid, "domain": req.domain,
            "background": case["background"],
            "sub_questions": [{"q": s["q"], "points": s["points"]}
                              for s in case["sub_questions"]]}


CASE_GRADE_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）案例分析题的阅卷老师。
按参考答案要点批改考生作答，要求：
1. 每个子问题按要点给分，最后汇总为 0-100 的总分（按各子问题分值加权）；
2. 反馈具体到要点：命中的要点、遗漏的要点、答错/多余的内容、改进建议；
3. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"score": 0-100整数, "feedback": "逐条反馈文字（可换行）"}}"""


@router.post("/case/grade", summary="AI 批改案例作答")
def case_grade(req: CaseGradeReq, db: Session = Depends(get_db)):
    question_text = (req.question_text or "").strip()
    user_answer = (req.user_answer or "").strip()
    sub_json = None
    if req.question_id:
        q = db.get(GxQuestion, req.question_id)
        if q is None:
            raise HTTPException(404, "题目不存在")
        if q.qtype != gx.QTYPE_CASE:
            raise HTTPException(400, "该题不是案例题")
        if not question_text:
            question_text = q.question or ""
        sub_json = q.sub_questions
    if not question_text or not user_answer:
        raise HTTPException(400, "题干与作答均不能为空")

    prompt = (f"题干与背景材料：\n{question_text}\n\n"
              + (f"参考答案要点（仅供阅卷）：\n{sub_json}\n\n" if sub_json else "")
              + f"考生作答：\n{user_answer}\n\n请按要点批改并输出 JSON。")
    resp = _call_ai(req.user_id, CASE_GRADE_SYSTEM_PROMPT, prompt, max_tokens=1600)
    data = gx._extract_json((resp or {}).get("text", ""))
    try:
        score = max(0, min(100, int(data.get("score")))) if data else None
    except (TypeError, ValueError):
        score = None
    feedback = ((data or {}).get("feedback") or "").strip()
    if score is None and not feedback:
        raise HTTPException(502, "AI 批改失败了，稍后再试一次吧")

    db2 = SessionLocal()
    try:
        db2.add(GxCaseGrade(user_id=req.user_id, question_id=req.question_id,
                            question_text=question_text, user_answer=user_answer,
                            score=score or 0, feedback=feedback))
        if req.question_id:
            qrow = db2.get(GxQuestion, req.question_id)
            gx._bump_progress(db2, req.user_id,
                              qrow.domain if qrow else gx.GX_DOMAINS[0],
                              case_count=1)
        db2.commit()
    finally:
        db2.close()
    _consume_tokens(req.user_id, resp, biz="gx_case")
    return {"score": score, "feedback": feedback}


# ── 进度 ──

@router.get("/progress", summary="分知识域学习进度")
def progress(user_id: str, db: Session = Depends(get_db)):
    return gx.progress_overview(db, user_id)
