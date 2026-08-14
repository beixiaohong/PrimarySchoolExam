import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import DIFFICULTY_MAP, GENERATORS

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
    if not available_types:
        available_types = [
            {"code": code, "name": code, "category": "\u7efc\u5408", "weight": 10}
            for code in GENERATORS.keys()
        ]
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
