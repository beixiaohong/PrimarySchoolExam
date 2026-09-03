"""初中六科出题器：物理/化学/生物/道德与法治/历史/地理

从 middle_questions 题库表抽取选择题组卷（种子版数据，需人工扩充）。
返回结构与英语/语文出题器一致：{"choice": [{id, question, options, answer, analysis}]}
"""
import json
import random
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.middle import MiddleQuestion

# 初中新增六科（数学/英语/语文沿用既有出题器）
MIDDLE_SUBJECTS = ["物理", "化学", "生物", "道德与法治", "历史", "地理"]

TYPE_NAMES = {"choice": "选择题"}
ALL_EXERCISE_TYPES = ["choice"]


def generate_middle_exam(
    subject: str,
    grade: int = 7,
    count: int = 20,
    db: Session = None,
) -> Dict[str, list]:
    """生成初中六科试卷题目。

    抽题规则：年级范围 7 <= 题年级 <= 用户年级（低年级已学内容可考），随机抽取。
    题库不足 count 时有多少出多少。
    """
    if subject not in MIDDLE_SUBJECTS:
        return {}
    if db is None:
        return {}

    rows: List[MiddleQuestion] = (
        db.query(MiddleQuestion)
        .filter(MiddleQuestion.subject == subject)
        .filter(MiddleQuestion.grade >= 7, MiddleQuestion.grade <= grade)
        .all()
    )
    random.shuffle(rows)
    rows = rows[: max(1, count)]

    items = []
    for i, r in enumerate(rows, 1):
        try:
            options = json.loads(r.options_json or "[]")
        except (json.JSONDecodeError, TypeError):
            options = []
        items.append({
            "id": i,
            "question": r.question,
            "options": options,
            "answer": r.answer,
            "analysis": r.analysis or "",
        })
    return {"choice": items}
