import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

def _seed_sentences(db):
    """初始化英语句子（从CSV导入）"""
    if db.query(Sentence).count() > 0:
        return

    csv_path = Path(DATA_DIR) / "sentences_primary_school.csv"
    if not csv_path.exists():
        return

    seen = set()
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            en = row.get("sentence_en", "").strip()
            if not en or en.lower() in seen:
                continue
            seen.add(en.lower())
            db.add(Sentence(
                grade=int(row.get("grade", 3)),
                sentence_en=en,
                sentence_cn=row.get("sentence_cn", "").strip(),
                type=row.get("type", "").strip(),
                grammar_point=row.get("grammar_point", "").strip(),
            ))

    db.commit()

__all__ = [
    "_seed_sentences",
]
