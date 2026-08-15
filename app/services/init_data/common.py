"""init_data 子包公共工具：常量与共享导入

定义 GRADE_CN 年级中文映射等公共常量，供各种子数据模块复用。
"""
import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

GRADE_CN = {7: "七", 8: "八", 9: "九"}

__all__ = [
    "GRADE_CN",
]
