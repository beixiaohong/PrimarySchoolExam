import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

def _seed_phrases(db):
    """初始化英语词组（从CSV导入）"""
    if db.query(Phrase).count() > 0:
        return

    csv_path = Path(DATA_DIR) / "phrases_primary_school.csv"
    if not csv_path.exists():
        return

    seen = set()
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            phrase_text = row.get("phrase", "").strip()
            if not phrase_text or phrase_text.lower() in seen:
                continue
            seen.add(phrase_text.lower())
            db.add(Phrase(
                grade=int(row.get("grade", 3)),
                phrase=phrase_text,
                meaning=row.get("meaning", "").strip(),
                type=row.get("type", "动词词组").strip(),
            ))

    db.commit()

__all__ = [
    "_seed_phrases",
]
