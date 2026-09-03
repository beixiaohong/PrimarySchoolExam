"""每日任务 · 各科进度计算（读真实学习数据，无路由）

从原 common.py 拆分而来：根据刷题/错题/背诵/单词等模块的真实记录，
计算某任务今天的完成进度。所有函数只依赖传入的 Session，不直接写库。
"""
from datetime import date, datetime, time as dtime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from app.models.vocab import VocabDailyLog
from app.models.classical import ClassicalDailyLog

from .constants import TASK_PASS_SCORE


def _today_start() -> datetime:
    return datetime.combine(date.today(), dtime.min)


def _today_new_attempts(db: Session, user_id: str, subject: str) -> int:
    """今日达标、且以往从未做过的卷子数（防反复刷同一张卷子凑每日任务）

    判定标准：今日分数达标的卷子中，exam_id 在「今天之前」不存在该用户的任何做题记录。
    即同一份卷子只有第一次做才算数，之后每天重做都不再计入进度——必须做新卷子才能完成。
    """
    today_start = _today_start()
    # 今日达标 attempt 涉及的卷子（去重）
    todays = db.query(func.distinct(ExamAttempt.exam_id)).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id, ExamRecord.subject == subject,
        ExamAttempt.score >= TASK_PASS_SCORE, ExamAttempt.created_at >= today_start,
    ).all()
    new_ids = {r[0] for r in todays}
    if not new_ids:
        return 0
    # 这些卷子中，今天之前该用户是否已做过（任何 attempt，不限分数 → 接触过即不算新）
    prev = db.query(func.distinct(ExamAttempt.exam_id)).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id, ExamRecord.subject == subject,
        ExamAttempt.created_at < today_start,
        ExamAttempt.exam_id.in_(new_ids),
    ).all()
    prev_ids = {r[0] for r in prev}
    return len(new_ids - prev_ids)


def _today_mastered(db: Session, user_id: str, subject: str) -> int:
    """今日通过重做答对而掌握的错题数（防刷：手动标记已掌握不计入，需正确答对 correct_streak>0）"""
    return db.query(WrongRecord).join(Question, WrongRecord.question_id == Question.id).filter(
        WrongRecord.user_id == user_id, Question.subject == subject,
        WrongRecord.mastered_at != None, WrongRecord.mastered_at >= _today_start(),
        WrongRecord.correct_streak > 0,
    ).count()


def _today_challenge_count(db: Session, user_id: str, kind: str) -> int:
    """今天某类挑战赛中「通过（正确率 ≥ 80%）」的次数。

    需求：60 秒挑战赛需通过率 80% 以上才算完成。故只统计
    total>0 且 correct/total ≥ 0.8 的记录，低分挑战不计入每日任务进度。
    """
    from app.models.sprint4 import ChallengeRecord
    rows = db.query(ChallengeRecord).filter(
        ChallengeRecord.user_id == user_id,
        ChallengeRecord.kind == kind,
        ChallengeRecord.created_at >= _today_start(),
    ).all()
    return sum(
        1 for r in rows
        # 通过判定：正确率 ≥ 80%（correct/total >= 0.8 等价于 correct*5 >= total*4）
        if r.total and r.total > 0 and r.correct * 5 >= r.total * 4
    )


def _today_dictation_words(db: Session, user_id: str) -> int:
    """今天听写的单词数（从 VocabDailyLog 的 words_reviewed 字段近似）"""
    log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id, VocabDailyLog.learn_date == date.today()
    ).first()
    return (log.words_reviewed or 0) if log else 0


def _today_dictation_texts(db: Session, user_id: str) -> int:
    """今天默写的古诗文数（从 ClassicalDailyLog 近似）"""
    log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id, ClassicalDailyLog.learn_date == date.today()
    ).first()
    return (log.texts_reviewed or 0) if log else 0


def _user_grade(db: Session, user_id: str) -> int:
    """取用户年级（背诵任务按年级圈定词库/篇目）"""
    from app.models.user import User
    u = db.query(User).filter_by(user_id=user_id).first()
    return (u.grade if u and u.grade else 6)


def _vocab_all_done(db: Session, user_id: str) -> tuple:
    """英语单词「全量完成」判定：今日新学全部完成 且 当日复习达标（或清空积压）。

    返回 (done, new_done, review_done, learned_today, reviewed_today)。
    - 新学完成：新学额度用完（今日新学数达标或词库已无可学新词）
    - 复习完成：当天已复习数达到每日复习额度，或已无剩余到期复习词（积压清空）。
      用「每日复习额度」替代「清空全部积压」，避免初期积压单词导致任务永远无法完成。
    """
    from app.models.word import Word, WordBook
    from app.models.vocab import VocabProgress
    # 延迟导入，避免与 service 循环依赖
    from .service import get_daily_quota
    today = date.today()
    grade = _user_grade(db, user_id)
    book_ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
    if not book_ids:
        return True, True, True, 0, 0  # 无词库视为完成，不阻塞全勤
    word_q = db.query(Word.id).filter(Word.book_id.in_(book_ids))

    # 到期复习剩余数（复习后 next_review_date 均 > 今日）
    review_left = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "learning",
        VocabProgress.next_review_date <= today,
        VocabProgress.word_id.in_(word_q),
    ).count()

    log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id, VocabDailyLog.learn_date == today).first()
    learned_today = (log.new_words_learned or 0) if log else 0
    reviewed_today = (log.words_reviewed or 0) if log else 0

    if learned_today >= get_daily_quota(db, user_id, "daily_new_words"):
        new_done = True
    else:
        # 词库中是否还有未学新词（无新词可学也视为完成）
        learned_ids = db.query(VocabProgress.word_id).filter(
            VocabProgress.user_id == user_id).subquery()
        unlearned = db.query(Word.id).filter(
            Word.book_id.in_(book_ids), ~Word.id.in_(db.query(learned_ids))).count()
        new_done = unlearned == 0

    review_quota = get_daily_quota(db, user_id, "daily_review_words")
    # 复习完成：无固定门槛（清空积压）或当天已复习达到每日额度
    review_done = (review_left == 0) or (reviewed_today >= review_quota)
    return (new_done and review_done), new_done, review_done, learned_today, reviewed_today


def _classical_all_done(db: Session, user_id: str) -> tuple:
    """古诗文「全量完成」判定：今日新背全部完成 且 当日复习达标（或清空积压）。

    返回 (done, new_done, review_done, learned_today, reviewed_today)。
    复习完成用「每日复习额度」替代「清空全部积压」，避免初期积压篇目导致任务永远无法完成。
    """
    from app.models.classical import ClassicalText, ClassicalProgress
    # 延迟导入，避免与 service 循环依赖
    from .service import get_daily_quota
    today = date.today()
    grade = _user_grade(db, user_id)

    review_left = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "learning",
        ClassicalProgress.next_review_date <= today,
    ).count()

    log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id, ClassicalDailyLog.learn_date == today).first()
    learned_today = (log.texts_learned or 0) if log else 0
    reviewed_today = (log.texts_reviewed or 0) if log else 0

    if learned_today >= get_daily_quota(db, user_id, "daily_new_texts"):
        new_done = True
    else:
        learned_ids = db.query(ClassicalProgress.text_id).filter(
            ClassicalProgress.user_id == user_id).subquery()
        unlearned = db.query(ClassicalText.id).filter(
            ClassicalText.grade <= grade,
            ~ClassicalText.id.in_(db.query(learned_ids))).count()
        new_done = unlearned == 0

    review_quota = get_daily_quota(db, user_id, "daily_review_texts")
    # 复习完成：无固定门槛（清空积压）或当天已复习达到每日额度
    review_done = (review_left == 0) or (reviewed_today >= review_quota)
    return (new_done and review_done), new_done, review_done, learned_today, reviewed_today


def _task_progress(db: Session, user_id: str, subj: str, code: str, target: int) -> int:
    """根据真实学习数据计算任务进度（封顶为目标值）"""
    # 强制任务
    if code == "math_exam":
        return min(target, _today_new_attempts(db, user_id, "数学"))
    if code == "chi_classical":
        done, _, _, learned, reviewed = _classical_all_done(db, user_id)
        if done:
            return target
        # 未全部完成：展示进度但永不达标（新背+复习必须全部完成）
        return min(target - 1, learned + reviewed)
    if code == "eng_vocab":
        done, _, _, learned, reviewed = _vocab_all_done(db, user_id)
        if done:
            return target
        return min(target - 1, learned + reviewed)
    # 可选任务
    if code == "math_fix":
        return min(target, _today_mastered(db, user_id, "数学"))
    if code == "chi_exam":
        return min(target, _today_new_attempts(db, user_id, "语文"))
    if code == "eng_exam":
        return min(target, _today_new_attempts(db, user_id, "英语"))
    if code == "math_challenge":
        return min(target, _today_challenge_count(db, user_id, "math"))
    if code == "eng_challenge":
        return min(target, _today_challenge_count(db, user_id, "word"))
    if code == "eng_dictation":
        return min(target, _today_dictation_words(db, user_id))
    if code == "chi_dictation":
        return min(target, _today_dictation_texts(db, user_id))
    return 0


def _available_new_exams(db: Session, user_id: str, subject: str) -> int:
    """今天仍可「首次达标」的该科试卷数 = 该科总卷数 − 今天之前已做过的卷数。

    用于判定「刷题类任务」是否因题库内容不足而铁定无法达到 target。
    """
    total_ids = [r[0] for r in db.query(ExamRecord.id).filter(
        ExamRecord.subject == subject).all()]
    if not total_ids:
        return 0
    done_before = db.query(func.distinct(ExamAttempt.exam_id)).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id, ExamRecord.subject == subject,
        ExamAttempt.created_at < _today_start(),
        ExamAttempt.exam_id.in_(total_ids),
    ).all()
    return len(total_ids) - len({r[0] for r in done_before})


def _daily_task_feasible(db: Session, user_id: str, code: str, subject: str, target: int) -> bool:
    """判定某非手动每日任务今天是否「内容可达」（铁定达不到则判 impossible）。

    仅刷题类任务(math_exam/chi_exam/eng_exam)受题库容量约束：
      若「今天仍可首次达标的卷数」< target，则无论怎么刷都完不成 → 不可达。
    其余任务（听写/挑战/订正/背诵/单词 等）无内容稀缺，默认可达。
    """
    if code in ("math_exam", "chi_exam", "eng_exam"):
        subj = {"math_exam": "数学", "chi_exam": "语文", "eng_exam": "英语"}[code]
        return _available_new_exams(db, user_id, subj) >= target
    return True
