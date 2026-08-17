"""试卷生成（公共，不绑定用户）相关端点与辅助函数"""
import json
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from . import router
from app.database import get_db, SessionLocal
from app.models.exam import (
    ExamRecord, Question, WrongRecord, ExamAttempt, AttemptAnswer,
)
from app.schemas.exam import ExamCreateRequest
from app.services.middle_generator import MIDDLE_SUBJECTS


def _auto_difficulty(db: Session, user_id: str, subject: str) -> str:
    """按该科最近 5 次交卷平均分自动定难度档；无记录默认「综合」

    平均分口径：去掉未作答的空题，按「正确数/实际作答题数」折算百分制，
    避免空题拉低分数导致难度误判；整卷未作答的记录不计入平均。
    """
    attempts = db.query(ExamAttempt).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id, ExamRecord.subject == subject,
    ).order_by(ExamAttempt.id.desc()).limit(5).all()
    if not attempts:
        return "综合"
    # 逐题作答明细：统计每次实际作答题数与正确数（空题剔除）
    ans_rows = db.query(
        AttemptAnswer.attempt_id,
        func.count(AttemptAnswer.id),
        func.sum(case((AttemptAnswer.is_correct == True, 1), else_=0)),  # noqa: E712
    ).filter(
        AttemptAnswer.attempt_id.in_([a.id for a in attempts]),
        AttemptAnswer.user_answer != "",
        AttemptAnswer.user_answer.isnot(None),
    ).group_by(AttemptAnswer.attempt_id).all()
    stat_map = {aid: (answered, correct or 0) for aid, answered, correct in ans_rows}
    scores = []
    for a in attempts:
        answered, correct = stat_map.get(a.id, (0, 0))
        if answered <= 0:
            continue  # 整卷空题不计入平均
        scores.append(correct * 100 / answered)
    if not scores:
        return "综合"
    avg = sum(scores) / len(scores)
    if avg >= 80:
        return "拔高"
    if avg >= 70:
        return "提高"
    if avg >= 60:
        return "综合"
    return "基础"


def _wrong_type_counts(db: Session, user_id: str, subject: str) -> Dict[str, int]:
    """统计用户未掌握错题的题型分布 {type_code: 错题数}"""
    rows = db.query(Question.type_code, func.count(WrongRecord.id)).join(
        WrongRecord, WrongRecord.question_id == Question.id).filter(
        WrongRecord.user_id == user_id, Question.subject == subject,
        WrongRecord.is_mastered == False,  # noqa: E712
        Question.type_code != "",
    ).group_by(Question.type_code).all()
    return {c: n for c, n in rows if c}


def _random_type_quotas(total: int, all_types: List[str], difficulty: str,
                        hard_types: List[str]) -> Dict[str, int]:
    """随机部分的题型配额：难度档微调权重（拔高/提高偏应用题型，基础偏基础题型）"""
    if total < 1 or not all_types:
        return {}
    weights = {t: (2 if difficulty in ("拔高", "提高") else 1) if t in hard_types
               else (1 if difficulty in ("拔高", "提高") else 2) if difficulty == "基础"
               else 1 for t in all_types}
    tw = sum(weights.values()) or 1
    quotas = {t: int(total * weights[t] / tw) for t in all_types}
    # 余数补到权重最高的题型，保证总数 == total
    diff = total - sum(quotas.values())
    order = sorted(all_types, key=lambda t: weights[t], reverse=True)
    i = 0
    while diff > 0 and order:
        quotas[order[i % len(order)]] += 1
        diff -= 1
        i += 1
    return {t: n for t, n in quotas.items() if n > 0}


def _wrong_type_quotas(n30: int, wrong_counts: Dict[str, int],
                       valid_types: List[str]) -> Dict[str, int]:
    """错题题型部分配额：按错题数占比分配 n30 题量，仅限合法题型"""
    if n30 < 1:
        return {}
    wc = {t: n for t, n in wrong_counts.items() if t in valid_types}
    tw = sum(wc.values())
    if not wc or tw <= 0:
        return {}
    quotas = {t: int(n30 * n / tw) for t, n in wc.items()}
    diff = n30 - sum(quotas.values())
    order = sorted(wc, key=wc.get, reverse=True)
    i = 0
    while diff > 0 and order:
        quotas[order[i % len(order)]] += 1
        diff -= 1
        i += 1
    return {t: n for t, n in quotas.items() if n > 0}


@router.post("/generate", summary="生成试卷（Word下载，题目自动入库）")
def generate_exam(req: ExamCreateRequest, db: Session = Depends(get_db)):
    """
    生成完整试卷并返回Word文档下载。
    所有题目自动保存到 questions 表。
    试卷为公共资源，不绑定用户。

    连接池铁律：分段短会话——DB 读写（家长下限/难度/题型）用注入会话，
    读完立即关闭；试卷生成+Word 构建（CPU/IO，可能耗时数秒）在会话外进行，
    期间不占用任何数据库连接；最后用新短会话落库。避免在持有连接期间做
    长时间工作导致连接池耗尽、全站卡死。
    """
    # ── 阶段一：短会话读取（家长每科最少题数下限 + 自动难度档）──
    if req.user_id:
        from app.models.parent import ExamMinCount
        m = db.query(ExamMinCount).filter_by(user_id=req.user_id).first()
        if m:
            if req.subject == "数学":
                req.math_count = max(req.math_count, m.math_min or 0)
            elif req.subject == "英语":
                req.english_count = max(req.english_count, m.eng_min or 0)
            elif req.subject == "语文":
                req.english_count = max(req.english_count, m.chi_min or 0)
        # 难度由最近成绩自动定档（忽略客户端传入的 difficulty/题型筛选）
        req.difficulty = _auto_difficulty(db, req.user_id, req.subject)
    req.math_categories = None
    req.english_types = None
    # 读取完毕，立即释放连接（生成/构建期间不持连）
    db.close()

    # ── 阶段二：生成 + Word 构建（会话外，各自按需开短会话）──
    if req.subject == "数学":
        filepath, questions_data = _generate_math_exam(req)
    elif req.subject == "英语":
        filepath, questions_data = _generate_english_exam(req)
    elif req.subject == "语文":
        filepath, questions_data = _generate_chinese_exam(req)
    elif req.subject in MIDDLE_SUBJECTS:
        # 初中六科：仅 7-9 年级可出
        if req.grade < 7:
            raise HTTPException(400, f"{req.subject}为初中科目，需 7 年级及以上")
        filepath, questions_data = _generate_middle_exam(req)
    else:
        raise HTTPException(400, "学科仅支持：数学 / 英语 / 语文 / 物理 / 化学 / 生物 / 道德与法治 / 历史 / 地理")

    from datetime import datetime as _dt
    title = req.title or f"{_dt.now().strftime('%y%m%d%H%M%S')}{req.subject}{len(questions_data)}题{req.difficulty}卷"

    # ── 阶段三：新短会话落库（试卷记录 + 逐题入库）──
    with SessionLocal() as db:
        record = ExamRecord(
            subject=req.subject,
            title=title,
            grade=req.grade,
            difficulty=req.difficulty,
            config_json=json.dumps(req.model_dump(), ensure_ascii=False),
            file_path=filepath,
            question_count=len(questions_data),
        )
        db.add(record)
        db.flush()

        # 逐题入库
        for qd in questions_data:
            db.add(Question(
                exam_id=record.id,
                seq=qd["seq"],
                subject=req.subject,
                category=qd.get("category", ""),
                type_code=qd.get("type_code", ""),
                type_name=qd.get("type_name", ""),
                question=qd["question"],
                answer=qd.get("answer", ""),
                options_json=json.dumps(qd["options"], ensure_ascii=False) if qd.get("options") else "",
                image_path=qd.get("image_path", ""),
                audio_path=qd.get("audio_path", ""),
                difficulty=qd.get("difficulty", 1),
            ))

        db.commit()

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{title}.docx",
        headers={"X-Exam-Id": str(record.id)},
    )


def _generate_math_exam(req: ExamCreateRequest) -> tuple:
    """生成数学试卷，返回 (文件路径, 题目数据列表)

    70/30 分布：30% 题量按未掌握错题题型生成，其余随机。
    连接策略：题型可用性 + 错题分布所需 DB 查询包在短会话内；
    查询结束后关闭连接，后续 CPU 生成与 Word 构建完全不持连。
    """
    from app.services.math_generator import generate_math_problems, _get_available_types
    from app.services.docx_service import build_math_docx

    wrong_counts: Dict[str, int] = {}
    valid_types: List[str] = []
    # 短会话：仅取「可用题型」与「错题题型分布」，取完即关
    with SessionLocal() as db:
        avail = _get_available_types(db, req.grade, None, None) or []
        valid_types = [t["code"] for t in avail] or []
        if req.user_id and req.math_count >= 3:
            wrong_counts = _wrong_type_counts(db, req.user_id, req.subject)

    # ── 会话已关闭：以下纯 CPU，不占用连接 ──
    problems = []
    remaining = req.math_count
    if valid_types and wrong_counts and remaining >= 3:
        wq = _wrong_type_quotas(round(remaining * 0.3), wrong_counts, valid_types)
        if wq:
            problems = generate_math_problems(
                grade=req.grade,
                difficulty=req.difficulty,
                categories=None,
                problem_types=list(wq.keys()),
                count=sum(wq.values()),
                include_answer=True,
                db=None,
            )
            remaining -= len(problems)
    if remaining > 0:
        problems += generate_math_problems(
            grade=req.grade,
            difficulty=req.difficulty,
            categories=req.math_categories,
            problem_types=valid_types or None,
            count=remaining,
            include_answer=True,
            db=None,
        )
    filepath = build_math_docx(problems, req.grade, req.difficulty, title=req.title)

    questions_data = []
    for i, p in enumerate(problems, 1):
        questions_data.append({
            "seq": i,
            "category": p.category,
            "type_code": p.type_code,
            "type_name": p.type_name,
            "question": p.question,
            "answer": p.answer,
            "options": None,
            "difficulty": p.difficulty,
            "image_path": p.image_path,
        })
    return filepath, questions_data


def _build_typed_paper(target: int, types_used: List[str], gen_fn,
                       quotas: Dict[str, list] = None) -> Dict[str, list]:
    """按目标总题数精确生成分题型试卷（英语/语文共用）。

    - quotas 非空：按外部「题型→题数」配额生成（如 70/30 错题分布）
    - target < 题型数：只使用前 target 个题型，每题型 1 题
    - 否则：带余数均分（前 rem 个题型各多 1 题），保证总数 == target
    - 生成结果按题目文本去重；不足时向所有题型追加补齐（最多 3 轮）
    - 超出时从尾部裁剪（每题型至少保留 1 题）；空题型过滤
    gen_fn(types: List[str], count_per_type: int) -> Dict[str, list]
    """
    if target < 1:
        return {}
    if quotas:
        # 外部配额：过滤非法/零配额题型，types_used 取配额键（补齐轮用）
        quotas = {t: n for t, n in quotas.items() if t in types_used and n > 0}
        if quotas:
            types_used = list(quotas.keys())
        else:
            quotas = None
    if not quotas:
        if len(types_used) > target:
            types_used = types_used[:target]
        # 带余数均分配额
        base, rem = divmod(target, len(types_used)) if types_used else (0, 0)
        quotas = {t: base + (1 if i < rem else 0) for i, t in enumerate(types_used)}

    # 相同配额分组调用，减少生成器调用次数
    groups = {}
    for t, q in quotas.items():
        groups.setdefault(q, []).append(t)

    result: Dict[str, list] = {}
    seen = {t: set() for t in types_used}
    for q, types in groups.items():
        for etype, items in gen_fn(types, q).items():
            pool = result.setdefault(etype, [])
            if etype not in seen:
                seen[etype] = set()
            for it in items:
                qtext = it.get("question", "")
                if qtext and qtext in seen[etype]:
                    continue
                if qtext:
                    seen[etype].add(qtext)
                pool.append(it)

    # 总数不足：向各题型追加补齐（去重），最多 3 轮
    total = sum(len(v) for v in result.values())
    for _ in range(3):
        if total >= target:
            break
        need = target - total
        added = 0
        for etype, items in gen_fn(types_used, need).items():
            pool = result.setdefault(etype, [])
            if etype not in seen:
                seen[etype] = set()
            for it in items:
                qtext = it.get("question", "")
                if qtext and qtext in seen[etype]:
                    continue
                if qtext:
                    seen[etype].add(qtext)
                pool.append(it)
                added += 1
                if added >= need:
                    break
            if added >= need:
                break
        if added == 0:
            break
        total += added

    # 总数超出：从尾部裁剪（每题型至少保留 1 题）
    total = sum(len(v) for v in result.values())
    if total > target:
        overflow = total - target
        for t in reversed(list(result.keys())):
            if overflow <= 0:
                break
            lst = result[t]
            while len(lst) > 1 and overflow > 0:
                lst.pop()
                overflow -= 1

    return {k: v for k, v in result.items() if v}


def _paper_type_quotas(req: ExamCreateRequest, db: Session, all_types: List[str],
                       hard_types: List[str]) -> Dict[str, int]:
    """试卷题型配额：30% 题量按未掌握错题题型，70% 随机（按难度档微调权重）"""
    count = req.english_count
    wq: Dict[str, int] = {}
    if req.user_id and count >= 3:
        wrong_counts = _wrong_type_counts(db, req.user_id, req.subject)
        wq = _wrong_type_quotas(round(count * 0.3), wrong_counts, all_types)
    n_rand = count - sum(wq.values())
    merged = dict(wq)
    for t, n in _random_type_quotas(n_rand, all_types, req.difficulty, hard_types).items():
        merged[t] = merged.get(t, 0) + n
    return merged


def _generate_english_exam(req: ExamCreateRequest, db: Optional[Session] = None) -> tuple:
    """生成英语试卷，返回 (文件路径, 题目数据列表)

    连接策略：db 为 None 时自行开短会话（生成完即关，不泄漏到落库阶段）；
    db 由调用方提供时沿用（仍应在调用方作用域内）。
    """
    if db is None:
        with SessionLocal() as s:
            return _generate_english_exam(req, s)
    from app.services.english_generator import generate_english_exam, TYPE_NAMES, ALL_EXERCISE_TYPES
    from app.services.docx_service import build_english_docx

    # 题型由系统按成绩自动分配（忽略客户端题型筛选）
    types_used = ALL_EXERCISE_TYPES[:]

    def _gen(types, count):
        return generate_english_exam(
            grade=req.grade,
            book_ids=req.english_book_ids,
            count_per_type=count,
            exercise_types=types,
            db=db,
        )

    hard_types = ["cloze", "unscramble_sentence", "grammar_choice"]
    quotas = _paper_type_quotas(req, db, types_used, hard_types)
    exercises = _build_typed_paper(req.english_count, types_used, _gen, quotas=quotas)
    filepath = build_english_docx(exercises, req.grade, title=req.title)

    questions_data = []
    seq = 0
    for etype, items in exercises.items():
        type_name = TYPE_NAMES.get(etype, etype)
        for item in items:
            seq += 1
            questions_data.append({
                "seq": seq,
                "category": "英语",
                "type_code": etype,
                "type_name": type_name,
                "question": item["question"],
                "answer": item["answer"],
                "options": item.get("options"),
                "difficulty": 1,
                "audio_path": item.get("audio_path", ""),
            })
    return filepath, questions_data


def _generate_chinese_exam(req: ExamCreateRequest, db: Optional[Session] = None) -> tuple:
    """生成语文试卷，返回 (文件路径, 题目数据列表)"""
    if db is None:
        with SessionLocal() as s:
            return _generate_chinese_exam(req, s)
    from app.services.chinese_generator import generate_chinese_exam, TYPE_NAMES, ALL_EXERCISE_TYPES
    from app.services.docx_service import build_english_docx

    types_used = ALL_EXERCISE_TYPES[:]

    def _gen(types, count):
        return generate_chinese_exam(
            grade=req.grade,
            count_per_type=count,
            exercise_types=types,
            db=db,
        )

    hard_types = ["sentence_rewrite", "reading_comp", "poetry_translate"]
    quotas = _paper_type_quotas(req, db, types_used, hard_types)
    exercises = _build_typed_paper(req.english_count, types_used, _gen, quotas=quotas)
    filepath = build_english_docx(
        exercises, req.grade, title=req.title,
        type_names=TYPE_NAMES, filename_prefix="语文",
    )

    questions_data = []
    seq = 0
    for etype, items in exercises.items():
        type_name = TYPE_NAMES.get(etype, etype)
        for item in items:
            seq += 1
            questions_data.append({
                "seq": seq,
                "category": "语文",
                "type_code": etype,
                "type_name": type_name,
                "question": item["question"],
                "answer": item["answer"],
                "options": item.get("options"),
                "difficulty": 1,
            })
    return filepath, questions_data


def _generate_middle_exam(req: ExamCreateRequest, db: Optional[Session] = None) -> tuple:
    """生成初中六科（物理/化学/生物/道德与法治/历史/地理）试卷，返回 (文件路径, 题目数据列表)"""
    if db is None:
        with SessionLocal() as s:
            return _generate_middle_exam(req, s)
    from app.services.middle_generator import generate_middle_exam, TYPE_NAMES, MIDDLE_SUBJECTS
    from app.services.docx_service import build_english_docx
    from app.services.semester import stage_label

    exercises = generate_middle_exam(
        subject=req.subject,
        grade=req.grade,
        count=req.english_count,
        db=db,
    )
    default_title = f"{stage_label(req.grade)}{req.grade}年级{req.subject}练习"
    filepath = build_english_docx(
        exercises, req.grade, title=req.title or default_title,
        type_names={"choice": f"{req.subject}选择题"}, filename_prefix=req.subject,
    )

    questions_data = []
    seq = 0
    for etype, items in exercises.items():
        type_name = TYPE_NAMES.get(etype, etype)
        for item in items:
            seq += 1
            questions_data.append({
                "seq": seq,
                "category": req.subject,
                "type_code": etype,
                "type_name": type_name,
                "question": item["question"],
                "answer": item["answer"],
                "options": item.get("options"),
                "difficulty": 1,
            })
    return filepath, questions_data


__all__ = [
    "_auto_difficulty", "_wrong_type_counts", "_random_type_quotas",
    "_wrong_type_quotas", "generate_exam", "_generate_math_exam",
    "_build_typed_paper", "_paper_type_quotas", "_generate_english_exam",
    "_generate_chinese_exam", "_generate_middle_exam",
]
