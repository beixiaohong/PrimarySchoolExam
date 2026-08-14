import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

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
                ("运算律与简便计算", "number_operation_law", 1, 5, 3, 6, 10),
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
                ("图形运动(对称/平移/旋转)", "geo_motion", 1, 5, 2, 6, 8),
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
                ("盈亏问题", "app_surplus_deficit", 2, 5, 4, 6, 8),
            ],
        },
        {
            "name": "统计与概率",
            "description": "平均数、统计图、可能性",
            "types": [
                ("平均数与统计", "stat_average", 1, 4, 3, 6, 10),
                ("可能性与概率", "stat_probability", 1, 4, 4, 6, 8),
                ("统计图读图分析", "stat_chart", 1, 5, 3, 6, 10),
                ("统计量选择(中位数/众数)", "stat_measure", 1, 5, 4, 6, 8),
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
                ("抽屉原理", "logic_pigeonhole", 2, 5, 4, 6, 6),
                ("周期问题", "logic_period", 1, 5, 3, 6, 8),
                ("时钟问题", "logic_clock", 2, 5, 4, 6, 6),
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
                ("大数认识与近似数", "number_large", 1, 4, 3, 6, 6),
            ],
        },
        {
            "name": "中学代数",
            "description": "一元二次方程、一次函数、不等式",
            "types": [
                ("一元二次方程", "mid_quadratic_eq", 1, 5, 8, 9, 15),
                ("一次函数", "mid_linear_func", 1, 5, 8, 9, 15),
                ("一元一次不等式", "mid_inequality", 1, 5, 7, 9, 12),
            ],
        },
        {
            "name": "中学几何与概率",
            "description": "勾股定理、概率统计",
            "types": [
                ("勾股定理", "mid_pythagorean", 1, 5, 8, 9, 12),
                ("概率", "mid_probability", 1, 5, 9, 9, 10),
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

def _migrate_new_problem_types(db):
    """为已有数据库补充新增的题型"""
    new_types = [
        # (name, code, d_min, d_max, g_min, g_max, weight, category_name)
        ("归一问题", "app_unit_rate", 1, 5, 3, 6, 10, "应用题"),
        ("归总问题", "app_total_rate", 1, 5, 3, 6, 10, "应用题"),
        ("倍比问题", "app_ratio_compare", 1, 5, 3, 6, 10, "应用题"),
        ("流水行船", "app_boat_stream", 1, 5, 4, 6, 10, "应用题"),
        ("牛吃草问题", "app_cow_grazing", 1, 5, 4, 6, 8, "应用题"),
    ]
    added = 0
    for name, code, d_min, d_max, g_min, g_max, weight, cat_name in new_types:
        existing = db.query(ProblemType).filter(ProblemType.code == code).first()
        if existing:
            continue
        cat = db.query(ProblemCategory).filter(ProblemCategory.name == cat_name).first()
        if not cat:
            continue
        db.add(ProblemType(
            category_id=cat.id, name=name, code=code,
            difficulty_min=d_min, difficulty_max=d_max,
            grade_min=g_min, grade_max=g_max, weight=weight,
        ))
        added += 1
    if added:
        db.commit()

__all__ = [
    "_migrate_new_problem_types",
    "_seed_problem_types",
]
