import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

from .common import GRADE_CN

def _seed_word_bank(db):
    """初始化英语词库（从CSV导入）"""
    if db.query(WordBook).count() > 0:
        return

    csv_path = Path(WORD_CSV_PATH)
    if not csv_path.exists():
        return

    # 按年级+学期创建词库并导入
    books_cache = {}
    seen_words = {}  # {book_name: set of words} 用于去重

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            grade = int(row.get("grade", 3))
            semester = row.get("semester", "上")
            book_name = f"人教版PEP{grade}年级{semester}"

            if book_name not in books_cache:
                book = WordBook(
                    name=book_name,
                    grade=grade,
                    semester=semester,
                    publisher="人教版PEP",
                )
                db.add(book)
                db.flush()
                books_cache[book_name] = book
                seen_words[book_name] = set()

            word_text = row.get("word", "").strip()
            if not word_text:
                continue
            # 跳过同一词库内的重复单词
            word_lower = word_text.lower()
            if word_lower in seen_words[book_name]:
                continue
            seen_words[book_name].add(word_lower)

            book = books_cache[book_name]
            word = Word(
                book_id=book.id,
                word=word_text,
                phonetic=row.get("phonetic", "").strip(),
                pos=row.get("pos", "").strip(),
                meaning=row.get("meaning", "").strip(),
                unit=row.get("unit", "").strip(),
                difficulty=int(row.get("difficulty", 1) or 1),
                tags=row.get("tags", "").strip(),
            )
            db.add(word)

    # 更新词库计数（直接用去重集合长度，避免flush时序问题）
    for book_name, book in books_cache.items():
        book.word_count = len(seen_words[book_name])

    db.commit()

def _seed_middle_word_bank(db):
    """增量导入初中英语词库（grade>=7，册名：人教版七/八/九年级上/下）"""
    if db.query(WordBook).filter(WordBook.grade >= 7).count() > 0:
        return

    csv_path = Path(MIDDLE_WORD_CSV_PATH)
    if not csv_path.exists():
        return

    books_cache = {}
    seen_words = {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            grade = int(row.get("grade", 7))
            if grade < 7:
                continue
            semester = row.get("semester", "上")
            book_name = f"人教版{GRADE_CN[grade]}年级{semester}"

            if book_name not in books_cache:
                book = WordBook(
                    name=book_name,
                    grade=grade,
                    semester=semester,
                    publisher="人教版",
                )
                db.add(book)
                db.flush()
                books_cache[book_name] = book
                seen_words[book_name] = set()

            word_text = row.get("word", "").strip()
            if not word_text:
                continue
            word_lower = word_text.lower()
            if word_lower in seen_words[book_name]:
                continue
            seen_words[book_name].add(word_lower)

            book = books_cache[book_name]
            db.add(Word(
                book_id=book.id,
                word=word_text,
                phonetic=row.get("phonetic", "").strip(),
                pos=row.get("pos", "").strip(),
                meaning=row.get("meaning", "").strip(),
                unit=row.get("unit", "").strip(),
                difficulty=int(row.get("difficulty", 2) or 2),
                tags=row.get("tags", "").strip(),
            ))

    for book_name, book in books_cache.items():
        book.word_count = len(seen_words[book_name])

    db.commit()

__all__ = [
    "_seed_middle_word_bank",
    "_seed_word_bank",
]
