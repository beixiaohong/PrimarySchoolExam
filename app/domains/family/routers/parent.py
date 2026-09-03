"""家长功能独立：密码解锁 + 留言 + 学习数据 + 试卷题数下限 + 提醒汇总

背景（011 迁移）：
- parent_passwords：家长密码 + 密保（忘记密码时重置），按孩子 user_id 存一份
- exam_min_counts：每科试卷最少题数（数学/语文/英语分别设置）
- parent_messages：家长发给孩子的留言

安全设计：
- 密码 pbkdf2-sha256 加盐哈希存储（200k 迭代），校验用恒定时间比较
- 解锁限频 10 次/10 分钟/用户，防止孩子暴力试密码
- 忘记密码需答对家长预设的密保问题才能重置
"""
import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.platform.contracts import rate_limit
from app.domains.identity.contracts import ensure_parent_pwd

router = APIRouter()

PBKDF2_ITER = 200_000
PWD_MIN, PWD_MAX = 4, 32
HINT_MAX = 100
UNLOCK_LIMIT = 10  # 10 次 / 10 分钟

# 试卷难度档位（防刷：家长可设下限，孩子选低于下限时强制提升）
DIFFICULTY_LEVELS = ["基础", "提高", "拔高"]


def _hash_pwd(pwd: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), PBKDF2_ITER)
    return f"pbkdf2${PBKDF2_ITER}${salt}${dk.hex()}"


def _verify_pwd(pwd: str, stored: str) -> bool:
    try:
        _, iters, salt, hex_digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), hex_digest)
    except Exception:
        return False


def _get_password(db, user_id):
    from app.models.parent import ParentPassword
    return db.query(ParentPassword).filter_by(user_id=user_id).first()


class SetupReq(BaseModel):
    user_id: str
    password: str
    hint_question: str = "孩子最爱吃的零食是？"
    hint_answer: str


class UnlockReq(BaseModel):
    user_id: str
    password: str


class ChangePwdReq(BaseModel):
    user_id: str
    old_password: str
    new_password: str
    hint_question: str = ""
    hint_answer: str = ""


class ResetPwdReq(BaseModel):
    user_id: str
    hint_answer: str
    new_password: str
    hint_question: str = ""
    hint_answer_new: str = ""


class MessageReq(BaseModel):
    user_id: str
    content: str


class UserReq(BaseModel):
    user_id: str


class ExamSettingsReq(BaseModel):
    user_id: str
    math_min: int = 5
    chi_min: int = 5
    eng_min: int = 5
    difficulty_min: str = "基础"  # 试卷难度下限：基础/提高/拔高


def _validate_pwd(pwd: str):
    if len(pwd) < PWD_MIN or len(pwd) > PWD_MAX:
        raise HTTPException(400, f"密码长度需 {PWD_MIN}-{PWD_MAX} 位")


# ═══════════════════ 家长密码 ═══════════════════

@router.get("/status", summary="家长密码是否已设置（含密保问题，忘记密码页展示用）")
def parent_status(user_id: str, db: Session = Depends(get_db)):
    """查询家长密码是否已设置，并返回密保问题（忘记密码页展示用）。

    参数（Query）：user_id。
    返回：{has_password, hint_question}。
    副作用：无（只读）。无需家长密码。
    """
    p = _get_password(db, user_id)
    return {"has_password": p is not None,
            "hint_question": p.hint_question if p else ""}


@router.post("/setup", summary="首次设置家长密码（含密保，忘记密码时重置用）")
def setup_password(req: SetupReq, db: Session = Depends(get_db)):
    """首次设置家长密码（含密保问题与答案，用于忘记密码时重置）。

    参数（Body）：user_id、password（4-32 位）、hint_question、hint_answer。
    返回：{ok: True}；已设置过返回 400，密保未填返回 400。
    副作用：写入 parent_passwords（密码与密保均 pbkdf2 哈希）。无需家长密码。
    """
    _validate_pwd(req.password)
    if _get_password(db, req.user_id):
        raise HTTPException(400, "已设置过家长密码，可在家长管理里修改或重置")
    q = (req.hint_question or "").strip()[:HINT_MAX]
    a = (req.hint_answer or "").strip()
    if not q or not a:
        raise HTTPException(400, "请填写密保问题和答案（忘记密码时用于重置）")
    from app.models.parent import ParentPassword
    p = ParentPassword(
        user_id=req.user_id,
        password_hash=_hash_pwd(req.password),
        hint_question=q,
        hint_answer_hash=_hash_pwd(a),
    )
    db.add(p)
    db.commit()
    return {"ok": True}


@router.post("/unlock", summary="家长密码解锁家长管理")
def unlock(req: UnlockReq, db: Session = Depends(get_db)):
    """家长密码解锁家长管理。

    参数（Body）：user_id、password。
    返回：{ok: True}；未设置密码返回 400，密码错返回 403。
    副作用：无写库；受限频保护（UNLOCK_LIMIT=10 次/10 分钟/用户，防暴力试密码）。
    无需家长密码（本接口即解锁动作）。
    """
    if not rate_limit(f"pwd:{req.user_id}", UNLOCK_LIMIT, 600):
        raise HTTPException(429, "尝试太多次啦，休息 10 分钟再试")
    p = _get_password(db, req.user_id)
    if not p:
        raise HTTPException(400, "还没设置家长密码，先设置才能进入家长管理")
    if not _verify_pwd(req.password, p.password_hash):
        raise HTTPException(403, "密码不对哦")
    return {"ok": True}


@router.post("/change-password", summary="验证旧密码后修改家长密码（密保可一并修改）")
def change_password(req: ChangePwdReq, db: Session = Depends(get_db)):
    """验证旧密码后修改家长密码；密保问题/答案可一并修改。

    参数（Body）：user_id、old_password、new_password（4-32 位）、可选 hint_question/hint_answer。
    返回：{ok: True}；未设置密码返回 400，旧密码错返回 403。
    副作用：更新 parent_passwords。无需家长密码（用旧密码自验）。
    """
    p = _get_password(db, req.user_id)
    if not p:
        raise HTTPException(400, "还没设置家长密码")
    if not _verify_pwd(req.old_password, p.password_hash):
        raise HTTPException(403, "旧密码不对哦")
    _validate_pwd(req.new_password)
    p.password_hash = _hash_pwd(req.new_password)
    if (req.hint_question or "").strip() and (req.hint_answer or "").strip():
        p.hint_question = req.hint_question.strip()[:HINT_MAX]
        p.hint_answer_hash = _hash_pwd(req.hint_answer.strip())
    db.commit()
    return {"ok": True}


@router.post("/reset-password", summary="忘记密码：答对密保问题后重置（可同时换密保）")
def reset_password(req: ResetPwdReq, db: Session = Depends(get_db)):
    """忘记密码：答对密保问题后重置密码（可同时换密保问题/答案）。

    参数（Body）：user_id、hint_answer（密保答案）、new_password、可选 hint_question/hint_answer_new。
    返回：{ok: True}；未设置密码返回 400，密保答案错返回 403。
    副作用：更新 parent_passwords。无需家长密码（凭密保重置）。
    """
    p = _get_password(db, req.user_id)
    if not p:
        raise HTTPException(400, "还没设置家长密码")
    if not _verify_pwd(req.hint_answer, p.hint_answer_hash):
        raise HTTPException(403, "密保答案不对哦")
    _validate_pwd(req.new_password)
    p.password_hash = _hash_pwd(req.new_password)
    if (req.hint_question or "").strip() and (req.hint_answer_new or "").strip():
        p.hint_question = req.hint_question.strip()[:HINT_MAX]
        p.hint_answer_hash = _hash_pwd(req.hint_answer_new.strip())
    db.commit()
    return {"ok": True}


# ═══════════════════ 家长留言 ═══════════════════

@router.post("/message", summary="家长给孩子发留言")
def send_message(req: MessageReq, db: Session = Depends(get_db)):
    """家长给孩子发留言。

    参数（Body）：user_id、content（1-300 字）。
    返回：{id, created_at}；空内容/超长返回 400；限频 10 条/分钟/用户。
    副作用：写入 parent_messages。无需家长密码。
    """
    content = (req.content or "").strip()
    if not content:
        raise HTTPException(400, "留言内容不能为空")
    if len(content) > 300:
        raise HTTPException(400, "留言最多 300 字")
    if not rate_limit(f"msg:{req.user_id}", 10, 60):
        raise HTTPException(429, "留言发太快啦，歇一歇")
    from app.models.parent import ParentMessage
    m = ParentMessage(user_id=req.user_id, content=content)
    db.add(m)
    db.commit()
    return {"id": m.id, "created_at": str(m.created_at)[:16]}


@router.get("/messages", summary="孩子查看家长留言（含未读数）")
def list_messages(user_id: str, db: Session = Depends(get_db)):
    """孩子查看家长留言列表（含未读数）。

    参数（Query）：user_id。
    返回：{unread, messages[{id, content, created_at, read}]}（最多 100 条，倒序）。
    副作用：无（只读）。无需家长密码。
    """
    from app.models.parent import ParentMessage
    rows = db.query(ParentMessage).filter_by(user_id=user_id).order_by(
        ParentMessage.id.desc()).limit(100).all()
    unread = db.query(ParentMessage).filter_by(
        user_id=user_id, read_at=None).count()
    return {
        "unread": unread,
        "messages": [{
            "id": m.id, "content": m.content,
            "created_at": str(m.created_at)[:16] if m.created_at else "",
            "read": m.read_at is not None,
        } for m in rows],
    }


@router.post("/messages/read", summary="孩子标记全部留言已读")
def mark_read(req: UserReq, db: Session = Depends(get_db)):
    """孩子标记该用户全部未读留言为已读。

    参数（Body）：user_id。
    返回：{ok: True}。
    副作用：将 read_at=None 的留言置为当前时间。无需家长密码。
    """
    from app.models.parent import ParentMessage
    db.query(ParentMessage).filter_by(user_id=req.user_id, read_at=None).update(
        {"read_at": datetime.now()})
    db.commit()
    return {"ok": True}


# ═══════════════════ 学习数据看板 ═══════════════════

@router.get("/child-stats", summary="家长查看孩子学习数据（本周做题/错题/连续天数/任务）")
def child_stats(user_id: str, db: Session = Depends(get_db)):
    """家长查看孩子本周学习数据看板。

    参数（Query）：user_id。
    返回：{week_attempts（本周做题份数）, week_avg_score（平均分）, unmastered_wrong（未掌握错题数）,
           streak_days（连续学习天数）, week_tasks_done（本周完成任务数）}。
    统计窗口：本周一至今天。副作用：无（只读）。无需家长密码。
    """
    from app.models.exam import ExamAttempt, WrongRecord
    from app.models.daily_task import DailyTask
    from app.domains.identity.contracts import _streak

    monday = date.today() - timedelta(days=date.today().weekday())
    week_start = datetime.combine(monday, datetime.min.time())

    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.user_id == user_id,
        ExamAttempt.created_at >= week_start,
    ).all()
    total = len(attempts)
    avg = round(sum(a.score or 0 for a in attempts) / total, 1) if total else 0

    wrong = db.query(WrongRecord).filter_by(
        user_id=user_id, is_mastered=False).count()

    tasks_done = db.query(DailyTask).filter(
        DailyTask.user_id == user_id,
        DailyTask.status == "done",
        DailyTask.task_date >= monday,
    ).count()

    return {
        "week_attempts": total,
        "week_avg_score": avg,
        "unmastered_wrong": wrong,
        "streak_days": _streak(db, user_id),
        "week_tasks_done": tasks_done,
    }


# ═══════════════════ 试卷最少题数 ═══════════════════

@router.get("/exam-settings", summary="获取每科试卷最少题数与难度下限")
def get_exam_settings(user_id: str, db: Session = Depends(get_db)):
    """获取每科试卷最少题数与难度下限（缺省返回默认值）。

    参数（Query）：user_id。
    返回：{math_min, chi_min, eng_min, difficulty_min, difficulty_levels}。
    副作用：无（只读）。无需家长密码。
    """
    from app.models.parent import ExamMinCount
    row = db.query(ExamMinCount).filter_by(user_id=user_id).first()
    if not row:
        return {"math_min": 5, "chi_min": 5, "eng_min": 5,
                "difficulty_min": "基础", "difficulty_levels": DIFFICULTY_LEVELS}
    return {"math_min": row.math_min, "chi_min": row.chi_min, "eng_min": row.eng_min,
            "difficulty_min": row.difficulty_min or "基础",
            "difficulty_levels": DIFFICULTY_LEVELS}


@router.post("/exam-settings", summary="保存试卷最少题数与难度下限（需家长密码）")
def save_exam_settings(req: ExamSettingsReq, request: Request, db: Session = Depends(get_db)):
    """保存每科试卷最少题数与难度下限。

    参数（Body）：user_id、math_min/chi_min/eng_min（默认 5）、difficulty_min（基础/提高/拔高）。
    请求头：必须携带 X-Parent-Pwd（家长密码），由 ensure_parent_pwd 校验，否则 403。
    返回：{math_min, chi_min, eng_min, difficulty_min}（题数被夹到 1-50）。
    副作用：upsert exam_min_counts；题数越界时按 _bounded 收敛。需要家长密码。
    """
    from app.models.parent import ExamMinCount
    ensure_parent_pwd(db, req.user_id, request)

    def _bounded(v):
        return max(1, min(50, int(v)))

    dmin = (req.difficulty_min or "基础").strip()
    if dmin not in DIFFICULTY_LEVELS:
        raise HTTPException(400, f"难度下限只能是 {DIFFICULTY_LEVELS}")

    row = db.query(ExamMinCount).filter_by(user_id=req.user_id).first()
    if not row:
        row = ExamMinCount(user_id=req.user_id)
        db.add(row)
    row.math_min = _bounded(req.math_min)
    row.chi_min = _bounded(req.chi_min)
    row.eng_min = _bounded(req.eng_min)
    row.difficulty_min = dmin
    row.updated_at = datetime.now()
    db.commit()
    return {"math_min": row.math_min, "chi_min": row.chi_min, "eng_min": row.eng_min,
            "difficulty_min": row.difficulty_min}


# ═══════════════════ 提醒汇总（孩子端首页提醒条 / 家长端待办） ═══════════════════

@router.get("/notices", summary="提醒汇总：未读留言 + 待确认/待兑现心愿 + 家长密码状态")
def notices(user_id: str, db: Session = Depends(get_db)):
    """提醒汇总：未读留言数 + 待确认/待兑现心愿数 + 是否已设家长密码。

    参数（Query）：user_id。
    返回：{unread_messages, pending_wishes（待确认）, pending_redeem（待兑现）, has_password}。
    副作用：无（只读）。无需家长密码。
    """
    from app.models.parent import ParentMessage, ParentPassword
    from app.models.reward import WishItem
    unread = db.query(ParentMessage).filter_by(user_id=user_id, read_at=None).count()
    pending = db.query(WishItem).filter_by(
        user_id=user_id, status="pending").count()
    to_redeem = db.query(WishItem).filter_by(
        user_id=user_id, status="pending_redeem").count()
    has_password = db.query(ParentPassword).filter_by(user_id=user_id).first() is not None
    return {
        "unread_messages": unread,
        "pending_wishes": pending,
        "pending_redeem": to_redeem,
        "has_password": has_password,
    }
