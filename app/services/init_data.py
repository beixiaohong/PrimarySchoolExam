"""
初始化种子数据：题型分类 + 默认词库
首次启动时自动执行，已有数据则跳过
"""
import csv
import os
from pathlib import Path

from ..database import SessionLocal
from ..models.word import Word, WordBook
from ..models.problem_type import ProblemType, ProblemCategory
from ..config import WORD_CSV_PATH


def ensure_initial_data():
    """确保数据库有初始题型和词库数据"""
    db = SessionLocal()
    try:
        _seed_problem_types(db)
        _seed_word_bank(db)
    finally:
        db.close()


def _seed_problem_types(db):
    """初始化数学题型分类"""
    if db.query(ProblemCategory).count() > 0:
        return

    categories_data = [
        {
            "name": "计算题",
            "description": "整数、小数、分数、混合运算、方程、单位换算",
            "types": [
                ("整数四则运算", "calc_int_basic", 1, 5, 1, 6, 15),
                ("小数运算", "calc_decimal", 1, 5, 3, 6, 12),
                ("分数四则运算", "calc_fraction", 1, 5, 5, 6, 12),
                ("混合运算与简便计算", "calc_mixed", 1, 5, 3, 6, 12),
                ("解方程", "calc_equation", 1, 5, 4, 6, 10),
                ("单位换算", "unit_conversion", 1, 5, 2, 6, 12),
            ],
        },
        {
            "name": "图形与几何",
            "description": "面积、体积、周长、图形变换、图形认识、位置方向",
            "types": [
                ("平面图形面积", "geo_area_plane", 1, 5, 3, 6, 15),
                ("立体图形体积", "geo_volume", 1, 5, 5, 6, 12),
                ("周长与面积综合", "geo_perimeter", 1, 5, 3, 6, 10),
                ("图形变换", "geo_transform", 2, 5, 4, 6, 8),
                ("图形认识与分类", "geo_recognition", 1, 5, 2, 6, 10),
                ("位置与方向", "geo_position", 1, 4, 3, 6, 8),
            ],
        },
        {
            "name": "比与比例",
            "description": "比的认识、正反比例、比例尺、百分数",
            "types": [
                ("比的认识与化简", "ratio_basic", 1, 4, 5, 6, 10),
                ("比例应用", "ratio_proportion", 2, 5, 5, 6, 12),
                ("百分数应用", "ratio_percent", 1, 5, 5, 6, 12),
            ],
        },
        {
            "name": "应用题",
            "description": "行程、工程、浓度、利润、分数、鸡兔同笼、植树、和差倍、按比例分配",
            "types": [
                ("行程问题", "app_travel", 1, 5, 3, 6, 15),
                ("工程问题", "app_work", 2, 5, 5, 6, 12),
                ("浓度问题", "app_concentration", 2, 5, 5, 6, 10),
                ("利润与折扣", "app_profit", 1, 5, 5, 6, 10),
                ("分数应用题", "app_fraction", 1, 5, 4, 6, 12),
                ("鸡兔同笼", "app_chicken_rabbit", 1, 5, 3, 6, 12),
                ("植树问题", "app_tree_planting", 1, 5, 3, 6, 10),
                ("和差与和倍差倍", "app_sum_difference", 1, 5, 2, 6, 10),
                ("按比例分配", "app_proportional_dist", 1, 5, 4, 6, 10),
            ],
        },
        {
            "name": "统计与概率",
            "description": "平均数、统计图、可能性",
            "types": [
                ("平均数与统计", "stat_average", 1, 4, 3, 6, 10),
                ("可能性与概率", "stat_probability", 1, 4, 4, 6, 8),
                ("统计图读图分析", "stat_chart", 1, 5, 3, 6, 10),
            ],
        },
        {
            "name": "逻辑与思维",
            "description": "逻辑推理、找规律、排列组合、优化策略",
            "types": [
                ("逻辑推理", "logic_reasoning", 2, 5, 3, 6, 8),
                ("找规律与数列", "logic_pattern", 1, 5, 2, 6, 8),
                ("排列组合与计数", "logic_combinatorics", 2, 5, 4, 6, 6),
                ("找次品与优化策略", "logic_optimization", 2, 5, 3, 6, 8),
            ],
        },
        {
            "name": "数与代数",
            "description": "因数倍数、整除、数的互化、负数",
            "types": [
                ("最大公因数与最小公倍数", "number_gcd_lcm", 1, 5, 4, 6, 10),
                ("负数与数轴", "number_negative", 1, 4, 6, 6, 6),
                ("整除与分解质因数", "number_divisibility", 1, 5, 4, 6, 10),
                ("数的互化与比较", "number_conversion", 1, 5, 4, 6, 10),
            ],
        },
    ]

    for cat_data in categories_data:
        cat = ProblemCategory(
            name=cat_data["name"],
            subject="数学",
            description=cat_data["description"],
        )
        db.add(cat)
        db.flush()

        for name, code, d_min, d_max, g_min, g_max, weight in cat_data["types"]:
            pt = ProblemType(
                category_id=cat.id,
                name=name,
                code=code,
                difficulty_min=d_min,
                difficulty_max=d_max,
                grade_min=g_min,
                grade_max=g_max,
                weight=weight,
            )
            db.add(pt)

    db.commit()


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
