import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register

@register("mid_quadratic_eq")
def mid_quadratic_eq(difficulty: int, grade: int):
    """一元二次方程"""
    def variant_solve():
        """由整数根反推 x²+bx+c=0，保证方程有整数根"""
        # x² + bx + c = 0 (有整数根)
        r1 = random.randint(-8, 8)
        r2 = random.randint(-8, 8)
        while r1 == 0 and r2 == 0:
            r1 = random.randint(-8, 8)
            r2 = random.randint(-8, 8)
        b = -(r1 + r2)
        c = r1 * r2
        b_str = f"+{b}" if b > 0 else str(b)
        c_str = f"+{c}" if c > 0 else str(c)
        q = f"解方程: x\u00b2{b_str}x{c_str}=0"
        roots = sorted([r1, r2])
        a = f"x\u2081={roots[0]}, x\u2082={roots[1]}"
        return q, a

    def variant_discriminant():
        """判断根的情况（Δ=b²-4ac 的正负零）"""
        a = random.choice([1, 2, 3])
        b = random.randint(-10, 10)
        c = random.randint(-10, 10)
        delta = b * b - 4 * a * c
        if delta > 0:
            result = "有两个不相等的实数根"
        elif delta == 0:
            result = "有两个相等的实数根"
        else:
            result = "没有实数根"
        q = f"判断方程 {a}x\u00b2+({b})x+({c})=0 的根的情况"
        return q, f"\u0394={delta}, {result}"

    def variant_vieta():
        """韦达定理：根与系数关系（x₁+x₂、x₁·x₂）"""
        r1 = random.randint(1, 6)
        r2 = random.randint(1, 6)
        b = -(r1 + r2)
        c = r1 * r2
        q = f"方程 x\u00b2+({b})x+{c}=0 的两根为x\u2081、x\u2082，求 x\u2081+x\u2082 和 x\u2081\u00b7x\u2082"
        return q, f"x\u2081+x\u2082={r1+r2}, x\u2081\u00b7x\u2082={c}"

    variants = [variant_solve, variant_discriminant, variant_vieta]
    return random.choice(variants)()

@register("mid_linear_func")
def mid_linear_func(difficulty: int, grade: int):
    """一次函数"""
    def variant_find_expr():
        """由两点坐标求一次函数解析式"""
        k = random.randint(-5, 5)
        while k == 0:
            k = random.randint(-5, 5)
        b = random.randint(-10, 10)
        x1 = random.randint(-3, 3)
        y1 = k * x1 + b
        x2 = x1 + random.randint(1, 4)
        y2 = k * x2 + b
        q = f"一次函数过点({x1},{y1})和({x2},{y2})，求解析式"
        k_str = f"+{k}" if k > 0 else str(k)
        b_str = f"+{b}" if b > 0 else str(b)
        return q, f"y={k}x{b_str}"

    def variant_quadrant():
        """判断图象经过的象限（按 k、b 符号组合）"""
        k = random.choice([-3, -2, -1, 1, 2, 3])
        b = random.choice([-5, -3, -1, 1, 3, 5])
        if k > 0 and b > 0:
            ans = "一、二、三象限"
        elif k > 0 and b < 0:
            ans = "一、三、四象限"
        elif k < 0 and b > 0:
            ans = "一、二、四象限"
        else:
            ans = "二、三、四象限"
        b_str = f"+{b}" if b > 0 else str(b)
        q = f"一次函数 y={k}x{b_str} 的图象经过哪些象限？"
        return q, ans

    def variant_intersect():
        """求两直线交点（k1≠k2，结果可能非整数则只求x）"""
        k1, b1 = random.randint(1, 4), random.randint(-5, 5)
        k2 = k1 + random.randint(1, 3)
        b2 = random.randint(-5, 5)
        while b1 == b2:
            b2 = random.randint(-5, 5)
        x = (b2 - b1) / (k1 - k2)
        y = k1 * x + b1
        if x == int(x):
            x = int(x)
            y = int(y)
            q = f"求 y={k1}x+({b1}) 与 y={k2}x+({b2}) 的交点坐标"
            return q, f"({x}, {y})"
        else:
            q = f"y={k1}x+({b1}) 与 y={k2}x+({b2}) 的交点x坐标是多少？"
            return q, f"x={x:.2f}"

    variants = [variant_find_expr, variant_quadrant, variant_intersect]
    return random.choice(variants)()

@register("mid_pythagorean")
def mid_pythagorean(difficulty: int, grade: int):
    """勾股定理"""
    triples = [(3,4,5), (5,12,13), (6,8,10), (7,24,25), (8,15,17), (9,12,15), (9,40,41)]
    def variant_find_hyp():
        """已知两直角边求斜边（用固定勾股数）"""
        a, b, c = random.choice(triples)
        q = f"直角三角形两直角边为{a}和{b}，求斜边长"
        return q, f"{c}"

    def variant_find_leg():
        """已知斜边与一直角边求另一直角边"""
        a, b, c = random.choice(triples)
        q = f"直角三角形斜边为{c}，一直角边为{a}，求另一直角边"
        return q, f"{b}"

    def variant_real_life():
        """勾股定理生活情境（梯子靠墙，按勾股数缩放）"""
        a, b, c = random.choice(triples)
        scale = random.choice([1, 2, 10])
        a, b, c = a*scale, b*scale, c*scale
        q = f"梯子长{c}m，底部距墙{a}m，梯子顶端距地面多高？"
        return q, f"{b} m"

    variants = [variant_find_hyp, variant_find_leg, variant_real_life]
    return random.choice(variants)()

@register("mid_inequality")
def mid_inequality(difficulty: int, grade: int):
    """一元一次不等式"""
    def variant_basic():
        a = random.randint(2, 8)
        b = random.randint(1, 20)
        c = random.randint(1, 30)
        # ax + b > c
        x_val = (c - b) / a
        if x_val == int(x_val):
            x_val = int(x_val)
            q = f"解不等式: {a}x+{b}>{c}"
            return q, f"x>{x_val}"
        else:
            q = f"解不等式: {a}x-{b}<{c}"
            x_val2 = (c + b) / a
            return q, f"x<{x_val2:.2f}"

    def variant_system():
        # x > a 且 x < b
        a = random.randint(-5, 3)
        b = a + random.randint(2, 8)
        q = f"解不等式组: x>{a} 且 x<{b}，求整数解的个数"
        count = b - a - 1
        return q, f"{count}个（{a+1}到{b-1}）"

    variants = [variant_basic, variant_system]
    return random.choice(variants)()

@register("mid_probability")
def mid_probability(difficulty: int, grade: int):
    """概率"""
    def variant_dice():
        target = random.randint(2, 12)
        count = sum(1 for i in range(1, 7) for j in range(1, 7) if i + j == target)
        from math import gcd
        g = gcd(count, 36)
        q = f"同时掷两枚骰子，点数之和为{target}的概率是多少？"
        return q, f"{count//g}/{36//g}"

    def variant_ball():
        red = random.randint(2, 5)
        white = random.randint(2, 5)
        total = red + white
        q = f"袋中有{red}个红球、{white}个白球，随机取一个是红球的概率？"
        from math import gcd
        g = gcd(red, total)
        return q, f"{red//g}/{total//g}"

    def variant_card():
        q = "从1-10的整数中随机取一个，取到偶数的概率是多少？"
        return q, "1/2"

    variants = [variant_dice, variant_ball, variant_card]
    return random.choice(variants)()

__all__ = [
    "mid_inequality",
    "mid_linear_func",
    "mid_probability",
    "mid_pythagorean",
    "mid_quadratic_eq",
]
