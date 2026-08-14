import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

from .grammar import _migrate_middle_grammar, _seed_grammar
from .phrases import _seed_phrases
from .problem_types import _migrate_new_problem_types, _seed_problem_types
from .sentences import _seed_sentences
from .users import _seed_admin
from .words import _seed_middle_word_bank, _seed_word_bank

def ensure_initial_data():
    """确保数据库有初始题型和词库数据"""
    db = SessionLocal()
    try:
        _seed_problem_types(db)
        _migrate_new_problem_types(db)
        _seed_word_bank(db)
        _seed_middle_word_bank(db)
        _seed_phrases(db)
        _seed_sentences(db)
        _seed_grammar(db)
        _migrate_middle_grammar(db)
        _seed_admin(db)
    finally:
        db.close()

__all__ = [
    "ensure_initial_data",
]
