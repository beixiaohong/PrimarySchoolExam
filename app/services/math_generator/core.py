import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import DIFFICULTY_MAP, GENERATORS

import logging
logger = logging.getLogger(__name__)

# 题型默认适用年级范围（与 init_data/problem_types.py 种子一致）。
# 用途：① DB 不可用/题型表为空时的「年级安全 fallback」；② 对 DB 返回结果做年级二次校正。
# 即使题型表年级配置异常，也保证不把五六年级/中学题型下放到低年级
# （修复用户反馈「三年级出现五六年级题」的根因：旧逻辑 fallback 回退到全部生成器，含中学代数）。
# 中学题型(grade>=7)必须显式列出；未在此映射中的题型不参与 fallback，避免越级泄露。
_TYPE_GRADE_RANGE: Dict[str, Tuple[int, int]] = {
    # 计算题
    "calc_int_basic": (1, 6),
    "calc_decimal": (3, 6),
    "calc_fraction": (5, 6),
    "calc_mixed": (3, 6),
    "calc_equation": (4, 6),
    "unit_conversion": (2, 6),
    "number_operation_law": (3, 6),
    # 图形与几何
    "geo_area_plane": (3, 6),
    "geo_volume": (5, 6),
    "geo_perimeter": (3, 6),
    "geo_transform": (4, 6),
    "geo_recognition": (2, 6),
    "geo_position": (3, 6),
    "geo_motion": (2, 6),
    # 比与比例
    "ratio_basic": (5, 6),
    "ratio_proportion": (5, 6),
    "ratio_percent": (5, 6),
    # 应用题
    "app_travel": (3, 6),
    "app_work": (5, 6),
    "app_concentration": (5, 6),
    "app_profit": (5, 6),
    "app_fraction": (4, 6),
    "app_chicken_rabbit": (3, 6),
    "app_tree_planting": (3, 6),
    "app_sum_difference": (2, 6),
    "app_proportional_dist": (4, 6),
    "app_surplus_deficit": (4, 6),
    # 统计与概率
    "stat_average": (3, 6),
    "stat_probability": (4, 6),
    "stat_chart": (3, 6),
    "stat_measure": (4, 6),
    # 逻辑与思维
    "logic_reasoning": (3, 6),
    "logic_pattern": (2, 6),
    "logic_combinatorics": (4, 6),
    "logic_optimization": (3, 6),
    "logic_pigeonhole": (4, 6),
    "logic_period": (3, 6),
    "logic_clock": (4, 6),
    # 数与代数
    "number_gcd_lcm": (4, 6),
    "number_negative": (6, 6),
    "number_divisibility": (4, 6),
    "number_conversion": (4, 6),
    "number_large": (3, 6),
    # 新增应用题（migrate）
    "app_unit_rate": (3, 6),
    "app_total_rate": (3, 6),
    "app_ratio_compare": (3, 6),
    "app_boat_stream": (4, 6),
    "app_cow_grazing": (4, 6),
    # 中学（必须显式列出，fallback 不会越级包含）
    "mid_quadratic_eq": (8, 9),
    "mid_linear_func": (8, 9),
    "mid_pythagorean": (8, 9),
    "mid_inequality": (7, 9),
    "mid_probability": (9, 9),
}


def _fallback_types_by_grade(grade: int) -> List[dict]:
    """DB 查询不可用时的年级安全 fallback：按内置年级范围过滤注册生成器。

    未在内置映射中的题型（如后台新增）不参与 fallback，避免误放高年级/中学题。
    """
    out = []
    for code in GENERATORS:
        rng = _TYPE_GRADE_RANGE.get(code)
        if rng is None:
            continue
        lo, hi = rng
        if lo <= grade <= hi:
            out.append({"code": code, "name": code, "category": "综合", "weight": 10})
    return out


def _filter_by_grade(types: List[dict], grade: int) -> List[dict]:
    """对 DB 返回的题型做年级二次防御：剔除内置映射中年级不匹配的题型；
    内置映射未覆盖的题型（后台新增）予以保留，不误伤。"""
    out = []
    for t in types:
        rng = _TYPE_GRADE_RANGE.get(t.get("code"))
        if rng is None:
            out.append(t)
            continue
        lo, hi = rng
        if lo <= grade <= hi:
            out.append(t)
    return out

def generate_math_problems(
    grade: int = 6,
    difficulty: str = "\u7efc\u5408",
    categories: Optional[List[str]] = None,
    problem_types: Optional[List[str]] = None,
    count: int = 20,
    include_answer: bool = True,
    db: Optional[Session] = None,
) -> List[ProblemItem]:
    """数学题生成主入口：按年级/难度/题型分类从注册表取生成器，按比例出题并打乱。

    参数：grade 年级；difficulty 难度档（综合/简单/中等/较难，映射到 DIFFICULTY_MAP 的难度区间）；
    categories/problem_types 可限定范围（None 表示不限）；count 总题数；include_answer 是否带答案；
    db 用于读取题库中启用的题型与权重（None 时退化为全部注册生成器）。
    返回：ProblemItem 列表（已随机打乱并重新编号）。每个生成器返回 (题干, 答案) 或 (题干, 答案, 配图路径)。
    """
    diff_range = DIFFICULTY_MAP.get(difficulty, (1, 5))
    available_types = _get_available_types(db, grade, categories, problem_types)
    if available_types:
        # 二次防御：即使 DB 题型表年级范围配置有误，也按内置年级范围校正，
        # 防止高年级/中学题型下放到低年级（用户反馈「三年级出现五六年级题」的根因之一）。
        available_types = _filter_by_grade(available_types, grade)
    if not available_types:
        # DB 不可用/题型为空时的年级安全兜底：只取该年级适配的题型，
        # 绝不再回退到「全部生成器」（旧逻辑会让三年级抽到中学代数等越级题）。
        logger.warning("数学题年级适配降级：未取到可用题型（DB 题型为空或未传入题型），按内置年级映射兜底 grade=%s", grade)
        available_types = _fallback_types_by_grade(grade)
    allocation = _allocate_counts(available_types, count)
    problems = []
    pid = 1
    for type_info, num in allocation:
        code = type_info["code"]
        gen_func = GENERATORS.get(code)
        if not gen_func:
            continue
        for _ in range(num):
            diff = random.randint(diff_range[0], diff_range[1])
            try:
                result = gen_func(diff, grade)
                if len(result) == 3:
                    question, answer, image_path = result
                else:
                    question, answer = result
                    image_path = ""
                problems.append(ProblemItem(
                    id=pid,
                    category=type_info.get("category", "\u7efc\u5408"),
                    type_code=code,
                    type_name=type_info.get("name", code),
                    difficulty=diff,
                    question=question,
                    answer=answer if include_answer else "",
                    image_path=image_path,
                ))
                pid += 1
            except Exception:
                continue
    random.shuffle(problems)
    for i, p in enumerate(problems, 1):
        p.id = i
    return problems[:count]

def _get_available_types(db, grade, categories, problem_types):
    """从题库读取「当前年级可用且启用」的题型清单（code/name/分类/权重）。

    按 grade_min<=grade<=grade_max 与 is_active 过滤；可再用 problem_types/categories 进一步收窄。
    任意 DB 异常或无匹配都返回 None，让主入口回退到全部注册生成器，保证总能出题。
    """
    if db is None:
        # 生成阶段刻意不持连接（db=None）：若调用方已在短会话中算好 problem_types，
        # 用 GENERATORS 注册表还原为题型字典，避免误走年级兜底，也避免把「未持连接」
        # 误报成「DB 不可用」（DB 实际可达，本环境 ProblemType 共 53 条且全部启用）。
        if problem_types:
            out = []
            for code in problem_types:
                if code in GENERATORS:
                    out.append({"code": code, "name": code, "category": "综合", "weight": 10})
            return out or None
        return None
    try:
        q = db.query(ProblemType).filter(
            ProblemType.is_active == True,
            ProblemType.grade_min <= grade,
            ProblemType.grade_max >= grade,
        )
        if problem_types:
            q = q.filter(ProblemType.code.in_(problem_types))
        if categories:
            q = q.join(ProblemCategory).filter(ProblemCategory.name.in_(categories))
        types = q.all()
        if not types:
            return None
        result = []
        for t in types:
            cat_name = t.category.name if t.category else "\u7efc\u5408"
            result.append({"code": t.code, "name": t.name, "category": cat_name, "weight": t.weight})
        return result
    except Exception:
        logger.warning("查询可用数学题型失败，将按年级安全映射兜底", exc_info=True)
        return None

def _allocate_counts(types: List[dict], total: int) -> List[Tuple[dict, int]]:
    """题量分配：先保证每种题型至少 1 题（全覆盖），剩余量按题型权重分摊。

    total >= 题型数：每种先分 1 题，余数按 weight 比例分配（末项吃凑整残差，避免超总额）。
    total < 题型数：无法全覆盖，改为先按分类均分名额，每类内取权重最高的题型，尽量多覆盖不同类别。
    """
    if not types:
        return []
    n_types = len(types)
    if total >= n_types:
        allocation_map = {t["code"]: 1 for t in types}
        remaining = total - n_types
        if remaining > 0:
            total_weight = sum(t["weight"] for t in types) or n_types
            distributed = 0
            for i, t in enumerate(types):
                if i == n_types - 1:
                    extra = remaining - distributed
                else:
                    extra = round(remaining * t["weight"] / total_weight)
                    extra = min(extra, remaining - distributed)
                allocation_map[t["code"]] += max(0, extra)
                distributed += max(0, extra)
                if distributed >= remaining:
                    break
        return [(t, allocation_map[t["code"]]) for t in types]
    else:
        cat_groups: Dict[str, List[dict]] = {}
        for t in types:
            cat_groups.setdefault(t["category"], []).append(t)
        n_cats = len(cat_groups)
        per_cat = max(1, total // n_cats)
        remainder = total - per_cat * n_cats
        selected = []
        for i, (cat_name, cat_types) in enumerate(cat_groups.items()):
            cat_quota = per_cat + (1 if i < remainder else 0)
            if cat_quota <= 0:
                continue
            if cat_quota >= len(cat_types):
                for t in cat_types:
                    selected.append((t, 1))
                extra = cat_quota - len(cat_types)
                if extra > 0:
                    cat_weight = sum(t["weight"] for t in cat_types) or 1
                    for t in cat_types:
                        e = round(extra * t["weight"] / cat_weight)
                        if e > 0:
                            selected.append((t, e))
            else:
                sorted_types = sorted(cat_types, key=lambda x: x["weight"], reverse=True)
                for t in sorted_types[:cat_quota]:
                    selected.append((t, 1))
        merged: Dict[str, Tuple[dict, int]] = {}
        for t, n in selected:
            if t["code"] in merged:
                merged[t["code"]] = (t, merged[t["code"]][1] + n)
            else:
                merged[t["code"]] = (t, n)
        result = list(merged.values())
        actual_total = sum(n for _, n in result)
        if actual_total > total:
            result = [(t, 1) for t, _ in result[:total]]
        return result

__all__ = [
    "_allocate_counts",
    "_get_available_types",
    "generate_math_problems",
]
