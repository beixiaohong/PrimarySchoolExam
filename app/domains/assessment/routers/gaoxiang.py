"""软考高项备考路由（assessment 域，挂载于 /api/gx）

面向非学生成人用户（软考高级·信息系统项目管理师）。与小学侧完全独立：
不挂 check_quiet_hours（成人晚间备考是核心场景），科目/年级维度也不共享。

题目来源两条腿：
1. **AI 动态生成**（`source=ai`）：题库没有的题型/域现场出题并落库，复用不重复扣费；
2. **备考资料导入**（`source=import`）：本地 `tools/gx_pack.py` 解析 602 个文件得到
   4500+ 条题目/知识点，线上 `tools/import_gx_materials.py` 按指纹幂等入库。
   出题默认「资料导入优先」，资料不够才 AI 补。

端点一览：
- GET  /domains                知识域清单（24 章）+ 题型
- GET  /catalog                可选筛选项（资料子类 / 章节 / 套卷）
- GET  /materials              资料归档清单（分类与解析审计）
- GET  /knowledge              知识点列表（?domain=&chapter=&kind=&q=）
- GET  /knowledge/{kid}        知识点详情
- POST /knowledge/generate     AI 生成知识域知识点并落库
- POST /quiz/generate          刷题出题（?scope=wrong 错题重练；支持来源/章节筛选）
- POST /quiz/submit            提交选择题作答（服务端判分 + 错题闭环 + 进度）
- GET  /case/list              案例题列表（资料导入）
- GET  /case/{qid}             案例题详情
- POST /case/generate          AI 出案例分析大题（落库）
- POST /case/grade             AI 批改案例作答（低于 60 自动入错题本）
- GET  /essay/list             论文题列表
- GET  /essay/{qid}            论文题详情（题目 + 论述要求）
- POST /essay/grade            AI 论文四维评分（低于 60 自动入错题本）
- GET  /wrong                  错题本（?kind=choice|case|essay 分栏）
- POST /wrong/analyze          AI 错因分析（懒生成 + 缓存复用）
- POST /wrong/master           手动标记错题已掌握
- GET  /progress               分知识域学习进度

铁律遵守：AI 调用一律在 DB 会话之外；会话只在「取数」与「写库」两端短暂持有
（`SessionLocal()` + finally close），绝不跨 AI 调用持有连接。
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.domains.assessment.services import gaoxiang as gx
from app.models.gaoxiang import (GxKnowledge, GxQuestion, GxWrong, GxCaseGrade,
                                 GxAttempt, GxMaterial)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["高项备考"])


class UserIdReq(BaseModel):
    user_id: str


class KnowledgeGenReq(UserIdReq):
    domain: str


class QuizGenReq(UserIdReq):
    domain: str = ""                   # 留空 = 不限知识域（配合资料筛选刷整套资料）
    qtype: str = gx.QTYPE_SINGLE      # single / multi
    count: int = 5
    source_kind: str = ""              # 每日一练 / 章节练习 / 仿真模拟 / 冲刺汇总 / 计算专题
    chapter: str = ""                  # 规范章节名（如 第12章 项目质量管理）
    scope: str = ""                    # ""=常规刷题；"wrong"=错题重练
    source: str = "all"                # all=资料题优先、不足 AI 补（默认）；import=只用资料题


class QuizSubmitReq(UserIdReq):
    answers: list                      # [{question_id, answer, duration_ms}]


class WrongMasterReq(UserIdReq):
    question_id: int


class WrongAnalyzeReq(UserIdReq):
    question_id: int = 0               # 指定单题；0 = 批量取最近未分析的错题
    limit: int = 3                     # 批量时最多分析几题（每次调用限量，避免长事务）
    force: bool = False                # True=忽略缓存重新分析


class CaseGenReq(UserIdReq):
    domain: str


class CaseGradeReq(UserIdReq):
    question_id: int = None            # 现场临时出题（未落库）时为空
    question_text: str = ""
    user_answer: str = ""


class EssayGradeReq(UserIdReq):
    question_id: int
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


def _load_options(raw):
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


# ── 静态清单 / 筛选项 / 资料审计 ──

@router.get("/domains", summary="知识域清单（考纲 24 章）")
def list_domains():
    return {"domains": gx.GX_DOMAINS, "qtypes": list(gx.QTYPES),
            "chapters": [{"no": no, "name": name, "label": gx.chapter_label(no)}
                         for no, name in gx.GX_CHAPTERS],
            "wrong_kinds": list(gx.WRONG_KINDS),
            "pass_score": gx.SUBJECTIVE_PASS_SCORE}


@router.get("/catalog", summary="可选筛选项（资料子类 / 章节 / 套卷）")
def catalog(db: Session = Depends(get_db)):
    """给前端下拉用：只列出**库里真有条目**的筛选项，避免用户选了空结果

    按 (source_kind, chapter) 聚合计数，单次 group by 完成，不做 N 次 count。
    """
    from sqlalchemy import func
    rows = (db.query(GxQuestion.source_kind, GxQuestion.chapter,
                     GxQuestion.qtype, func.count(GxQuestion.id))
            .group_by(GxQuestion.source_kind, GxQuestion.chapter, GxQuestion.qtype)
            .all())
    kinds, chapters, qtypes = {}, {}, {}
    for sk, ch, qt, n in rows:
        qt = qt or gx.QTYPE_SINGLE
        if qt in gx.SUBJECTIVE_QTYPES:
            # 案例/论文单独入口，不计入「选择题」筛选项
            qtypes[qt] = qtypes.get(qt, 0) + n
            continue
        qtypes[qt] = qtypes.get(qt, 0) + n
        if sk:
            kinds[sk] = kinds.get(sk, 0) + n
        if ch:
            chapters[ch] = chapters.get(ch, 0) + n
    # 知识点维度单独聚合：知识点页按「资料类型」分组浏览，需要真实存在的 kind 及其条数
    krows = (db.query(GxKnowledge.kind, GxKnowledge.chapter, func.count(GxKnowledge.id))
             .group_by(GxKnowledge.kind, GxKnowledge.chapter).all())
    k_kinds, k_chapters = {}, {}
    for kk, kch, n in krows:
        kk = kk or gx.KN_LIST
        k_kinds[kk] = k_kinds.get(kk, 0) + n
        if kch:
            k_chapters[kch] = k_chapters.get(kch, 0) + n
    return {
        "source_kinds": sorted(({"value": k, "count": v} for k, v in kinds.items()),
                               key=lambda x: -x["count"]),
        "chapters": sorted(({"value": k, "count": v} for k, v in chapters.items()),
                           key=lambda x: x["value"]),
        "qtypes": qtypes,
        # 知识点：类型（label 给前端直接展示，避免前端再维护一份中文映射）；
        # 顺序按「越像知识点卡片越靠前」，而不是条数 —— 课件几千条也不该排在速记前面
        "knowledge_kinds": sorted(
            ({"value": k, "label": gx.knowledge_kind_label(k), "count": v}
             for k, v in k_kinds.items()),
            key=lambda x: (gx.KN_ORDER.index(x["value"])
                           if x["value"] in gx.KN_ORDER else 99, -x["count"])),
        "knowledge_chapters": sorted(({"value": k, "count": v} for k, v in k_chapters.items()),
                                     key=lambda x: x["value"]),
    }


@router.get("/materials", summary="资料归档清单（分类与解析审计）")
def materials(category: str = "", sub_kind: str = "", limit: int = 500,
              db: Session = Depends(get_db)):
    from sqlalchemy import func
    agg = (db.query(GxMaterial.category, GxMaterial.sub_kind,
                    func.count(GxMaterial.id), func.sum(GxMaterial.items))
           .group_by(GxMaterial.category, GxMaterial.sub_kind).all())
    summary = [{"category": c, "sub_kind": s, "files": int(n), "items": int(t or 0)}
               for c, s, n, t in agg]
    q = db.query(GxMaterial)
    if category:
        q = q.filter(GxMaterial.category == category)
    if sub_kind:
        q = q.filter(GxMaterial.sub_kind == sub_kind)
    rows = q.order_by(GxMaterial.category, GxMaterial.rel_path) \
            .limit(max(1, min(int(limit or 500), 2000))).all()
    return {"summary": summary, "count": len(rows), "items": [
        {"id": m.id, "rel_path": m.rel_path, "category": m.category,
         "sub_kind": m.sub_kind, "title": m.title, "ext": m.ext,
         "items": m.items, "skipped": m.skipped, "error": m.error,
         "reason": m.reason} for m in rows]}


# ── 知识点 ──

@router.get("/knowledge", summary="知识点列表")
def list_knowledge(user_id: str, domain: str = "", chapter: str = "", kind: str = "",
                   q: str = "", limit: int = 200, db: Session = Depends(get_db)):
    query = db.query(GxKnowledge)
    if domain:
        _check_domain(domain)
        query = query.filter(GxKnowledge.domain == domain)
    if chapter:
        query = query.filter(GxKnowledge.chapter == chapter)
    if kind:
        query = query.filter(GxKnowledge.kind == kind)
    if q:
        like = f"%{q}%"
        query = query.filter(GxKnowledge.title.like(like) | GxKnowledge.content.like(like))
    rows = query.order_by(GxKnowledge.domain, GxKnowledge.chapter,
                          GxKnowledge.seq, GxKnowledge.id) \
                .limit(max(1, min(int(limit or 200), 500))).all()
    # 已读标记：一次 IN 查询取集合，避免逐条查询（N+1）
    read_ids = gx.read_knowledge_ids(db, user_id, [k.id for k in rows])
    return {"items": [{"id": k.id, "domain": k.domain, "code": k.code,
                       "title": k.title, "summary": k.summary,
                       "chapter": k.chapter, "kind": k.kind,
                       "source_file": k.source_file,
                       "read": k.id in read_ids} for k in rows]}


@router.get("/knowledge/{kid}", summary="知识点详情")
def knowledge_detail(kid: int, user_id: str, db: Session = Depends(get_db)):
    k = db.get(GxKnowledge, kid)
    if k is None:
        raise HTTPException(404, "知识点不存在")
    # 打开即记为已读（幂等，service 内保证「仅首次才 +1」）。
    # GET 带写副作用在这里可接受：唯一写入是「插一行已读」，重复请求结果相同；
    # 且前端只在用户点击时拉详情（无预取/无轮询），不会把没看过的标成已读。
    first_read = gx.mark_knowledge_read(db, user_id, k.id, k.domain)
    db.commit()
    return {"id": k.id, "domain": k.domain, "code": k.code, "title": k.title,
            "summary": k.summary, "content": k.content, "chapter": k.chapter,
            "kind": k.kind, "source_file": k.source_file,
            "read": True, "first_read": first_read}


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
    dom = req.domain or "项目管理概论"
    resp = _call_ai(req.user_id, gx.QUIZ_SYSTEM_PROMPT,
                    f"请出 {need} 道{label}题（知识域：{dom}）。",
                    max_tokens=2200)
    parsed = gx.parse_questions((resp or {}).get("text", ""))[:need]
    if not parsed:
        return []
    db = SessionLocal()
    try:
        ids = []
        for p in parsed:
            row = GxQuestion(domain=dom, qtype=qtype, question=p["question"],
                             options_json=None, answer=p["answer"], analysis=p["analysis"])
            if p["options"]:
                row.options_json = json.dumps(p["options"], ensure_ascii=False)
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.commit()
    finally:
        db.close()
    _consume_tokens(req.user_id, resp, biz="gx_quiz")
    return ids


@router.post("/quiz/generate", summary="刷题出题（资料题库优先，不足 AI 补）")
def quiz_generate(req: QuizGenReq):
    """不依赖 Depends(get_db)：AI 补题写库后需回读新行，请求级会话在
    REPEATABLE READ 下快照冻结读不到 —— 全程用独立短会话（与铁律一致）。
    """
    if req.domain:
        _check_domain(req.domain)
    if req.qtype not in (gx.QTYPE_SINGLE, gx.QTYPE_MULTI):
        raise HTTPException(400, "qtype 只能是 single 或 multi（案例题走 /case/list）")
    if req.scope not in ("", "wrong"):
        raise HTTPException(400, "scope 只能是空或 wrong")
    count = max(1, min(int(req.count or 5), 20))

    # 1) 题库优选（短会话一）。scope=wrong 时**不再过滤「未做过」**，否则错题永远刷不到。
    picked = []
    s1 = SessionLocal()
    try:
        picked = gx.quiz_pick(s1, req.user_id, domain=req.domain, qtype=req.qtype,
                              source_kind=req.source_kind, chapter=req.chapter,
                              scope=req.scope, count=count)
        picked_ids = [r.id for r in picked]
        payload = [{"id": r.id, "qtype": r.qtype, "question": r.question,
                    "options": _load_options(r.options_json),
                    "chapter": r.chapter, "source_kind": r.source_kind,
                    "deck": r.deck} for r in picked]
    finally:
        s1.close()

    # 2) 常规刷题且资料题不够时，AI 补生成落库（错题重练不补：补出来不是错题）
    ai_added = 0
    if req.scope != "wrong" and req.source != "import" and len(payload) < count:
        new_ids = _gen_questions(req, count - len(payload))
        ai_added = len(new_ids)
        if new_ids:
            s2 = SessionLocal()
            try:
                for r in s2.query(GxQuestion).filter(GxQuestion.id.in_(new_ids)) \
                          .order_by(GxQuestion.id).all():
                    payload.append({"id": r.id, "qtype": r.qtype, "question": r.question,
                                    "options": _load_options(r.options_json),
                                    "chapter": r.chapter, "source_kind": r.source_kind,
                                    "deck": r.deck})
            finally:
                s2.close()

    return {"domain": req.domain, "qtype": req.qtype, "scope": req.scope or "normal",
            "count": len(payload), "ai_added": ai_added, "questions": payload}


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
        # 主观题不走此端点判分（走 /case/grade 与 /essay/grade 的 AI 批改）
        if question.qtype in gx.SUBJECTIVE_QTYPES:
            raise HTTPException(400, f"题 {qid} 是{gx.qtype_label(question.qtype)}，"
                                     f"请走批改端点")
        out = gx.record_choice_attempt(db, req.user_id, question,
                                       str(a.get("answer") or ""),
                                       a.get("duration_ms") or 0)
        results.append({"question_id": qid, "found": True, **out})
    wrong_n = sum(1 for r in results if r.get("judged") and not r.get("is_correct"))
    return {"results": results, "wrong_count": wrong_n}


# ── 案例 / 论文（资料导入的题目） ──

@router.get("/case/list", summary="案例题列表")
def case_list(user_id: str, domain: str = "", source_kind: str = "", chapter: str = "",
              limit: int = 50, db: Session = Depends(get_db)):
    return {"items": _list_questions(db, gx.QTYPE_CASE, domain, source_kind, chapter,
                                    limit)}


@router.get("/case/{qid}", summary="案例题详情")
def case_detail(qid: int, user_id: str, db: Session = Depends(get_db)):
    return _question_detail(db, qid, gx.QTYPE_CASE)


@router.get("/essay/list", summary="论文题列表")
def essay_list(user_id: str, domain: str = "", source_kind: str = "", chapter: str = "",
               limit: int = 50, db: Session = Depends(get_db)):
    return {"items": _list_questions(db, gx.QTYPE_ESSAY, domain, source_kind, chapter,
                                    limit)}


@router.get("/essay/{qid}", summary="论文题详情（题目 + 论述要求）")
def essay_detail(qid: int, user_id: str, db: Session = Depends(get_db)):
    return _question_detail(db, qid, gx.QTYPE_ESSAY)


def _list_questions(db, qtype, domain, source_kind, chapter, limit):
    q = db.query(GxQuestion).filter(GxQuestion.qtype == qtype)
    if domain:
        _check_domain(domain)
        q = q.filter(GxQuestion.domain == domain)
    if source_kind:
        q = q.filter(GxQuestion.source_kind == source_kind)
    if chapter:
        q = q.filter(GxQuestion.chapter == chapter)
    rows = q.order_by(GxQuestion.domain, GxQuestion.chapter, GxQuestion.seq,
                      GxQuestion.id).limit(max(1, min(int(limit or 50), 200))).all()
    out = []
    for r in rows:
        subs = _load_options(r.sub_questions) or []
        out.append({"id": r.id, "title": r.title, "domain": r.domain,
                    "chapter": r.chapter, "source_kind": r.source_kind,
                    "deck": r.deck, "source_file": r.source_file,
                    "sub_count": len(subs),
                    "background": (r.question or "")[:200]})
    return out


def _question_detail(db, qid, qtype):
    r = db.get(GxQuestion, qid)
    if r is None:
        raise HTTPException(404, "题目不存在")
    if r.qtype != qtype:
        raise HTTPException(400, "题型不匹配")
    return {"id": r.id, "title": r.title, "domain": r.domain, "chapter": r.chapter,
            "qtype": r.qtype, "source_kind": r.source_kind, "deck": r.deck,
            "background": r.question or "", "options": _load_options(r.options_json),
            "sub_questions": _load_options(r.sub_questions),
            "analysis": r.analysis or "", "source_file": r.source_file}


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
        row.sub_questions = json.dumps(case["sub_questions"], ensure_ascii=False)
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

ESSAY_GRADE_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）论文阅卷老师。
按四个维度评分（各维度 0-100 分，总分为加权）：
1. relevance（切题与完整性，权重 35%）：是否按题目三个方面论述、要点是否齐全；
2. structure（结构与管理过程，权重 25%）：项目管理过程/工具技术描述是否准确规范；
3. practice（项目实践与真实性，权重 25%）：项目背景是否具体可信、有真实数据与细节；
4. writing（文字表达与字数，权重 15%）：行文流畅、字数是否达到 2000 字以上要求。
只输出一个 JSON 对象，不要输出任何其他文字：
{{"rubric": [{{"dim": "relevance", "score": 0-100, "comment": "评语"}},
            {{"dim": "structure", "score": 0-100, "comment": "评语"}},
            {{"dim": "practice", "score": 0-100, "comment": "评语"}},
            {{"dim": "writing", "score": 0-100, "comment": "评语"}}],
 "feedback": "总体反馈与改进建议（可换行）"}}"""


def _subjective_grade_common(user_id, question_id, question_text, user_answer,
                             system, prompt, parser, kind, biz):
    """案例/论文批改的公共编排（AI 在会话外，落库用独立短会话）

    低于及格线（SUBJECTIVE_PASS_SCORE）会**自动入错题本**，供后续「错题重练」。
    """
    resp = _call_ai(user_id, system, prompt, max_tokens=2000)
    data = parser((resp or {}).get("text", ""))
    if not data or (data.get("score") is None and not (data.get("feedback") or "")):
        raise HTTPException(502, "AI 批改失败了，稍后再试一次吧")
    score = data.get("score")
    db2 = SessionLocal()
    try:
        db2.add(GxCaseGrade(user_id=user_id, question_id=question_id,
                            question_text=question_text, user_answer=user_answer,
                            score=score or 0, feedback=data.get("feedback") or "",
                            kind=kind,
                            rubric_json=(json.dumps(data["rubric"], ensure_ascii=False)
                                         if data.get("rubric") else None)))
        wrong_info = {"passed": None, "added": False}
        if question_id:
            qrow = db2.get(GxQuestion, question_id)
            if qrow is not None:
                gx._bump_progress(db2, user_id, qrow.domain or gx.GX_DOMAINS[0],
                                  case_count=1)
                wrong_info = gx.record_subjective_grade(db2, user_id, qrow, kind,
                                                       score or 0)
        db2.commit()
    finally:
        db2.close()
    _consume_tokens(user_id, resp, biz=biz)
    return {"score": score, "feedback": data.get("feedback") or "",
            "rubric": data.get("rubric") or [], "pass_score": gx.SUBJECTIVE_PASS_SCORE,
            "in_wrong_book": bool(wrong_info.get("passed") is False)}


@router.post("/case/grade", summary="AI 批改案例作答（低于 60 自动入错题本）")
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
    return _subjective_grade_common(req.user_id, req.question_id, question_text,
                                   user_answer, CASE_GRADE_SYSTEM_PROMPT, prompt,
                                   lambda t: _case_parse(t), gx.WK_CASE, "gx_case")


def _case_parse(text):
    """案例批改输出解析（复用 _extract_json，缺 score 但有 feedback 也算成功）"""
    data = gx._extract_json(text)
    if not isinstance(data, dict):
        return None
    try:
        score = max(0, min(100, int(data.get("score")))) if data.get("score") is not None \
            else None
    except (TypeError, ValueError):
        score = None
    return {"score": score, "feedback": (data.get("feedback") or "").strip(),
            "rubric": []}


@router.post("/essay/grade", summary="AI 论文四维评分（低于 60 自动入错题本）")
def essay_grade(req: EssayGradeReq, db: Session = Depends(get_db)):
    user_answer = (req.user_answer or "").strip()
    if len(user_answer) < 100:
        raise HTTPException(400, "论文正文太短了，至少写 100 字再提交批改吧")
    q = db.get(GxQuestion, req.question_id)
    if q is None:
        raise HTTPException(404, "题目不存在")
    if q.qtype != gx.QTYPE_ESSAY:
        raise HTTPException(400, "该题不是论文题")
    prompt = gx.build_essay_grade_prompt(q, user_answer)
    question_text = (q.title or "") + "\n" + (q.question or "")
    return _subjective_grade_common(req.user_id, req.question_id, question_text,
                                   user_answer, ESSAY_GRADE_SYSTEM_PROMPT, prompt,
                                   gx.parse_essay_grade, gx.WK_ESSAY, "gx_essay")


# ── 错题本 ──

@router.get("/wrong", summary="错题本（?kind=choice|case|essay 分栏）")
def wrong_list(user_id: str, kind: str = "", include_mastered: bool = False,
               db: Session = Depends(get_db)):
    q = db.query(GxWrong).filter(GxWrong.user_id == user_id)
    if not include_mastered:
        q = q.filter(GxWrong.is_mastered.is_(False))
    if kind:
        if kind not in gx.WRONG_KINDS:
            raise HTTPException(400, f"kind 可选：{'/'.join(gx.WRONG_KINDS)}")
        q = q.filter(GxWrong.kind == kind)
    rows = q.order_by(GxWrong.last_wrong_at.desc()).limit(200).all()
    items = []
    counts = {k: 0 for k in gx.WRONG_KINDS}
    for w in rows:
        question = db.get(GxQuestion, w.question_id)
        if question is None:
            continue
        wk = w.kind or gx.KIND_OF_QTYPE.get(question.qtype, gx.WK_CHOICE)
        counts[wk] = counts.get(wk, 0) + 1
        items.append({
            "id": w.id, "question_id": w.question_id,
            "domain": question.domain, "qtype": question.qtype, "kind": wk,
            "chapter": question.chapter, "source_kind": question.source_kind,
            "title": question.title,
            "question": (question.question or "")[:300],
            "options": _load_options(question.options_json),
            "sub_questions": _load_options(question.sub_questions),
            "correct": question.answer or "",
            "analysis": question.analysis or "",
            "user_answer": w.user_answer, "wrong_count": w.wrong_count,
            "correct_streak": w.correct_streak,
            "is_mastered": w.is_mastered,
            "best_score": w.best_score or 0, "last_score": w.last_score or 0,
            "wrong_reason": w.wrong_reason or "",
            "reason_at": w.reason_at.isoformat() if w.reason_at else None,
        })
    return {"items": items, "count": len(items), "by_kind": counts}


@router.post("/wrong/analyze", summary="AI 错因分析（懒生成 + 缓存复用）")
def wrong_analyze(req: WrongAnalyzeReq):
    """把「答错→分析→入库→后续重练」闭环补齐

    设计取舍：**懒生成**而不是在判分时同步分析。判分必须快（一次提交最多 20 题），
    而 AI 分析每题要几秒；同步做会让提交接口超时。前端在答错后立即调本端点，
    用户感知上就是「做完立刻有分析」；分析结果落 `gx_wrongs.wrong_reason` 缓存，
    再看错题本不再重复扣费。

    会话策略：先用短会话挑出待分析题并**取出全部文本**，关掉会话后再调 AI，
    最后开新短会话写回 —— 全程不持连接等外部调用（硬性铁律）。
    """
    limit = max(1, min(int(req.limit or 3), 5))
    picked = []
    s1 = SessionLocal()
    try:
        rows = db_wrong_query(s1, req).limit(limit).all()
        for w in rows:
            question = s1.get(GxQuestion, w.question_id)
            if question is None:
                continue
            picked.append({"wrong_id": w.id, "question_id": question.id,
                           "qtype": question.qtype,
                           "question": question.question or "",
                           "options_json": question.options_json,
                           "answer": question.answer or "",
                           "analysis": question.analysis or "",
                           "sub_questions": question.sub_questions or "",
                           "user_answer": w.user_answer or ""})
    finally:
        s1.close()
    if not picked:
        return {"analyzed": 0, "items": [], "message": "没有需要分析的错题"}

    out = []
    for p in picked:
        # 用一个临时对象复用 prompt 构造函数（避免为纯文本再写一份）
        stub = GxQuestion(domain="", qtype=p["qtype"], question=p["question"],
                          options_json=p["options_json"], answer=p["answer"],
                          analysis=p["analysis"], sub_questions=p["sub_questions"] or None)
        prompt = gx.build_wrong_analysis_prompt(stub, p["user_answer"])
        resp = _call_ai(req.user_id, gx.WRONG_ANALYSIS_PROMPT, prompt, max_tokens=900)
        data = gx.parse_wrong_analysis((resp or {}).get("text", ""))
        if not data.get("analysis"):
            out.append({"question_id": p["question_id"], "ok": False})
            continue
        _consume_tokens(req.user_id, resp, biz="gx_wrong")
        text = (f"【{data.get('reason_type') or '其它'}】{data['analysis']}"
                + (f"\n记忆锚点：{data['tips']}" if data.get("tips") else ""))
        out.append({"question_id": p["question_id"], "ok": True,
                    "reason_type": data.get("reason_type") or "",
                    "analysis": data["analysis"], "tips": data.get("tips") or ""})
        text_out = text
        s2 = SessionLocal()
        try:
            row = s2.get(GxWrong, p["wrong_id"])
            if row is not None:
                row.wrong_reason = text_out
                row.reason_at = datetime.now()
                s2.commit()
        finally:
            s2.close()
    return {"analyzed": sum(1 for x in out if x.get("ok")), "items": out}


def db_wrong_query(db, req):
    """待分析错题：指定题优先；否则取最近答错且未分析过的"""
    q = db.query(GxWrong).filter(GxWrong.user_id == req.user_id)
    if req.question_id:
        return q.filter(GxWrong.question_id == req.question_id)
    if not req.force:
        q = q.filter(GxWrong.wrong_reason.is_(None))
    return q.order_by(GxWrong.last_wrong_at.desc())


@router.post("/wrong/master", summary="标记错题已掌握")
def wrong_master(req: WrongMasterReq, db: Session = Depends(get_db)):
    ok = gx.mark_mastered(db, req.user_id, req.question_id)
    if not ok:
        raise HTTPException(404, "错题不存在或已掌握")
    return {"question_id": req.question_id, "is_mastered": True}


# ── 进度 ──

@router.get("/progress", summary="分知识域学习进度")
def progress(user_id: str, db: Session = Depends(get_db)):
    return gx.progress_overview(db, user_id)
