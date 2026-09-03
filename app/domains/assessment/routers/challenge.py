"""限时挑战赛：60 秒口算 / 单词快答 + 成绩纪录

- 口算题内置生成（加/减/乘/除，按年级调难度），单词题从词库取词 + 干扰项
- 成绩 POST /record 持久化，GET /records 取个人最佳
"""
import random

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter()


class RecordReq(BaseModel):
    user_id: str
    kind: str
    correct: int = 0
    total: int = 0


def _math_quick(grade: int, n: int) -> list:
    """按年级生成口算题：三年级以内加减/乘法，高年级加除法与多位数"""
    ops = ["+", "-", "*"]
    if grade >= 4:
        ops.append("/")
    items = []
    while len(items) < n:
        op = random.choice(ops)
        if op == "+":
            a = random.randint(10, 90 if grade >= 4 else 50)
            b = random.randint(1, 50 if grade >= 4 else 30)
            q, ans = f"{a} + {b} = ?", a + b
        elif op == "-":
            a = random.randint(20, 100 if grade >= 5 else 60)
            b = random.randint(1, a - 1)
            q, ans = f"{a} − {b} = ?", a - b
        elif op == "*":
            a = random.randint(2, 9)
            b = random.randint(2, 9 if grade <= 4 else 12)
            q, ans = f"{a} × {b} = ?", a * b
        else:  # /
            b = random.randint(2, 9)
            ans = random.randint(2, 9)
            a = b * ans
            q, ans = f"{a} ÷ {b} = ?", ans
        items.append({"q": q, "answer": str(ans), "options": None})
    return items


def _word_quick(db: Session, grade: int, n: int) -> list:
    """单词快答：给英文选中文，4 选 1"""
    from app.models.word import Word, WordBook
    books = db.query(WordBook).filter(WordBook.grade == grade).all()
    if not books:
        books = db.query(WordBook).all()
    if not books:
        return []
    book_ids = [b.id for b in books]
    words = db.query(Word).filter(Word.book_id.in_(book_ids)).all()
    if not words:
        return []
    pool = random.sample(words, min(n, len(words)))
    items = []
    for w in pool:
        others = random.sample([x for x in words if x.id != w.id], min(3, len(words) - 1))
        options = [w.meaning] + [o.meaning for o in others]
        random.shuffle(options)
        items.append({"q": w.word, "answer": w.meaning, "options": options})
    return items


@router.get("/questions", summary="取一批挑战题（口算/单词）")
def get_questions(user_id: str = Query(...), kind: str = "math",
                  grade: int = 6, count: int = 20, db: Session = Depends(get_db)):
    """取一批挑战题（口算/单词）。

    查询参数：user_id, kind=math/word, grade, count(夹取到 5~50)；无需家长密码。
    返回：{kind, questions:[{q, answer, options}]}（math 题 options=None）。
    副作用：只读，无写库。口算按年级调难度（4 年级起加除法/多位数），单词从对应年级词书取词 + 3 个干扰项。
    """
    if kind not in ("math", "word"):
        raise HTTPException(400, "kind 只能是 math/word")
    count = max(5, min(50, count))
    if kind == "math":
        return {"kind": kind, "questions": _math_quick(grade, count)}
    return {"kind": kind, "questions": _word_quick(db, grade, count)}


@router.post("/record", summary="保存挑战成绩，返回最佳纪录")
def save_record(req: RecordReq, db: Session = Depends(get_db)):
    """保存挑战成绩，返回最佳纪录。

    请求：{user_id, kind=math/word, correct, total}；无需家长密码。
    返回：{best, today_best, times}（个人最佳/今日最佳/参与次数）。
    副作用：写 challenge_records；correct/total 各夹取到 0~200 防异常值；无金币发放（成绩仅记录）。
    """
    from app.models.sprint4 import ChallengeRecord
    if req.kind not in ("math", "word"):
        raise HTTPException(400, "kind 只能是 math/word")
    if req.correct < 0 or req.total < 0:
        raise HTTPException(400, "成绩不能为负数")
    if req.correct > req.total:
        raise HTTPException(400, "答对数不能超过总题数")
    # 成绩夹取 0~200，防止异常/超大数值污染最佳纪录
    correct = max(0, min(200, req.correct))
    total = max(0, min(200, req.total))
    rec = ChallengeRecord(user_id=req.user_id, kind=req.kind,
                          correct=correct, total=total)
    db.add(rec)
    db.commit()
    return _records(db, req.user_id, req.kind)


def _records(db: Session, user_id: str, kind: str) -> dict:
    from app.models.sprint4 import ChallengeRecord
    from datetime import date
    rows = db.query(ChallengeRecord).filter(
        ChallengeRecord.user_id == user_id, ChallengeRecord.kind == kind).all()
    today = date.today()
    return {
        "best": max((r.correct for r in rows), default=0),
        "today_best": max((r.correct for r in rows if r.created_at.date() == today), default=0),
        "times": len(rows),
    }


@router.get("/records", summary="挑战纪录汇总")
def get_records(user_id: str = Query(...), db: Session = Depends(get_db)):
    """挑战纪录汇总（口算 + 单词分别统计最佳）。无需家长密码，只读。"""
    return {"math": _records(db, user_id, "math"), "word": _records(db, user_id, "word")}
