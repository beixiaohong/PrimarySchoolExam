"""
数学题生成器 - 结构变体版
每个题型包含多个结构变体（不同问法/条件组合/情境），非简单换数字。
注册表模式：@register(code) 注册生成器。
"""
import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from ..models.problem_type import ProblemType, ProblemCategory
from ..schemas.problem import ProblemItem

GENERATORS: Dict[str, Callable] = {}


def register(code: str):
    """生成器注册装饰器：把被装饰函数挂到全局 GENERATORS[code] 注册表。

    主入口 generate_math_problems 通过 code 查表调用，新增题型只需 @register("code") 即可接入。
    """
    def decorator(func):
        GENERATORS[code] = func
        return func
    return decorator


# ═══════════════════════════════════════════════════════════
# 一、计算题（6种）
# ═══════════════════════════════════════════════════════════

@register("calc_int_basic")
def calc_int_basic(difficulty: int, grade: int):
    """整数四则运算 - 6个结构变体"""
    variants_easy = [
        # 1. 基础运算
        lambda: (
            f"{random.randint(100,999)} + {random.randint(100,999)} = ",
            None, "+"
        ),
        # 2. 连续运算
        lambda: (
            f"{random.randint(20,80)} × {random.randint(3,9)} - {random.randint(10,50)} = ",
            None, "*-"
        ),
        # 3. 缺数填空
        lambda: (
            f"(  ) × {random.randint(3,9)} = {random.randint(3,9)*random.randint(20,99)}",
            None, "missing"
        ),
        # 4. 比较大小
        lambda: (
            f"比较大小：{random.randint(100,500)}×{random.randint(2,5)} ○ {random.randint(100,500)}×{random.randint(2,5)}",
            None, "compare"
        ),
    ]
    variants_mid = [
        # 1. 带括号混合
        lambda: (
            f"({random.randint(100,500)} + {random.randint(100,500)}) × {random.randint(2,9)} = ",
            None, "bracket"
        ),
        # 2. 多步运算
        lambda: (
            f"{random.randint(10,50)} × {random.randint(10,50)} + {random.randint(10,50)} × {random.randint(10,50)} = ",
            None, "multi"
        ),
        # 3. 缺数逆推
        lambda: (
            f"{random.randint(100,999)} - (  ) × {random.randint(2,9)} = {random.randint(10,200)}",
            None, "reverse"
        ),
        # 4. 估算判断
        lambda: (
            f"估算：{random.randint(198,899)} × {random.randint(3,8)} 的积大约是几千？精确值是多少？",
            None, "estimate"
        ),
    ]
    variants_hard = [
        # 1. 四则混合
        lambda: (
            f"{random.randint(100,999)} × {random.randint(2,9)} - {random.randint(100,999)} ÷ {random.randint(2,9)} = ",
            None, "mixed4"
        ),
        # 2. 多层括号
        lambda: (
            f"[{random.randint(10,50)} × ({random.randint(10,50)} + {random.randint(10,50)}) - {random.randint(10,100)}] × {random.randint(2,5)} = ",
            None, "nested"
        ),
        # 3. 数字谜
        lambda: (
            f"□□ × {random.randint(3,9)} = {random.randint(100,899)}，□□代表的两位数是？",
            None, "puzzle"
        ),
        # 4. 巧算
        lambda: (
            f"999 × {random.randint(2,9)} + {random.randint(2,9)} = （用简便方法）",
            None, "trick"
        ),
    ]

    if difficulty <= 2:
        return _solve_int_variant(random.choice(variants_easy)())
    elif difficulty <= 4:
        return _solve_int_variant(random.choice(variants_mid)())
    else:
        return _solve_int_variant(random.choice(variants_hard)())


def _solve_int_variant(item):
    """解析整数运算变体，返回(question, answer)"""
    q, _, vtype = item
    # 重新生成带确定答案的题目
    if vtype == "+":
        a, b = random.randint(100, 999), random.randint(100, 999)
        return f"{a} + {b} = ", str(a + b)
    elif vtype == "*-":
        a, b, c = random.randint(20, 80), random.randint(3, 9), random.randint(10, 50)
        return f"{a} × {b} - {c} = ", str(a * b - c)
    elif vtype == "missing":
        b = random.randint(3, 9)
        x = random.randint(20, 99)
        return f"(  ) × {b} = {b * x}，括号里填几？", str(x)
    elif vtype == "compare":
        a, b = random.randint(100, 500), random.randint(2, 5)
        c, d = random.randint(100, 500), random.randint(2, 5)
        left, right = a * b, c * d
        sym = ">" if left > right else "<" if left < right else "="
        return f"比较大小：{a}×{b} ○ {c}×{d}", f"{sym}（{left} ○ {right}）"
    elif vtype == "bracket":
        a, b, c = random.randint(100, 500), random.randint(100, 500), random.randint(2, 9)
        return f"({a} + {b}) × {c} = ", str((a + b) * c)
    elif vtype == "multi":
        a, b, c, d = random.randint(10, 50), random.randint(10, 50), random.randint(10, 50), random.randint(10, 50)
        return f"{a} × {b} + {c} × {d} = ", str(a * b + c * d)
    elif vtype == "reverse":
        a = random.randint(100, 999)
        b = random.randint(2, 9)
        x = random.randint(10, 99)
        result = a - b * x
        return f"{a} - (  ) × {b} = {result}，括号里填几？", str(x)
    elif vtype == "estimate":
        a = random.randint(198, 899)
        b = random.randint(3, 8)
        approx = round(a, -2) * b
        return f"估算：{a} × {b} 的积大约是几千？精确值是多少？", f"约{approx//1000}千多，精确值{a*b}"
    elif vtype == "mixed4":
        a, b = random.randint(100, 999), random.randint(2, 9)
        c, d = random.randint(100, 999), random.randint(2, 9)
        while c % d != 0:
            c = d * random.randint(20, 200)
        return f"{a} × {b} - {c} ÷ {d} = ", str(a * b - c // d)
    elif vtype == "nested":
        a, b, c, d, e = random.randint(10, 50), random.randint(10, 50), random.randint(10, 50), random.randint(10, 100), random.randint(2, 5)
        ans = (a * (b + c) - d) * e
        return f"[{a} × ({b} + {c}) - {d}] × {e} = ", str(ans)
    elif vtype == "puzzle":
        b = random.randint(3, 9)
        x = random.randint(11, 99)
        return f"□□ × {b} = {x * b}，□□代表的两位数是？", str(x)
    elif vtype == "trick":
        b = random.randint(2, 9)
        ans = 999 * b + b
        return f"999 × {b} + {b} = （用简便方法）", f"{ans}（原式=1000×{b}={1000*b}）"
    return q, "?"


@register("calc_decimal")
def calc_decimal(difficulty: int, grade: int):
    """小数运算 - 结构变体"""
    if difficulty <= 2:
        variants = [
            lambda: _dec_add_sub(),
            lambda: _dec_multiply_simple(),
            lambda: _dec_compare(),
            lambda: _dec_missing(),
        ]
    elif difficulty <= 4:
        variants = [
            lambda: _dec_multiply(),
            lambda: _dec_divide(),
            lambda: _dec_mixed(),
            lambda: _dec_context_money(),
        ]
    else:
        variants = [
            lambda: _dec_multi_step(),
            lambda: _dec_approx(),
            lambda: _dec_reverse(),
            lambda: _dec_context_measure(),
        ]
    return random.choice(variants)()


def _dec_add_sub():
    """小数加减：减法先取大减小避免负数，结果保留2位"""
    a = round(random.uniform(1, 30), random.choice([1, 2]))
    b = round(random.uniform(1, 30), random.choice([1, 2]))
    op = random.choice(["+", "-"])
    if op == "-":
        a, b = max(a, b), min(a, b)
    ans = round(a + b if op == "+" else a - b, 2)
    return f"{a} {op} {b} = ", str(ans)

def _dec_multiply_simple():
    """小数×整数（保留1位）"""
    a = round(random.uniform(1, 10), 1)
    b = random.randint(2, 9)
    return f"{a} × {b} = ", str(round(a * b, 1))

def _dec_compare():
    """小数大小比较"""
    a = round(random.uniform(0.1, 9.9), 2)
    b = round(random.uniform(0.1, 9.9), 2)
    sym = ">" if a > b else "<"
    return f"比较大小：{a} ○ {b}", sym

def _dec_missing():
    """小数缺数逆填（已知积求因数）"""
    b = round(random.uniform(1.1, 9.9), 1)
    x = round(random.uniform(1.1, 9.9), 1)
    product = round(b * x, 2)
    return f"(  ) × {b} = {product}，括号里填几？", str(x)

def _dec_multiply():
    """小数乘小数（保留3位）"""
    a = round(random.uniform(1, 50), 2)
    b = round(random.uniform(0.1, 9.9), 1)
    return f"{a} × {b} = ", str(round(a * b, 3))

def _dec_divide():
    """小数除法（先定被除数再求商，保证整除）"""
    b = round(random.uniform(0.2, 9.9), 1)
    x = round(random.uniform(1, 20), 1)
    a = round(b * x, 2)
    return f"{a} ÷ {b} = ", str(x)

def _dec_mixed():
    """小数带括号混合运算"""
    a = round(random.uniform(1, 20), 1)
    b = round(random.uniform(1, 20), 1)
    c = random.randint(2, 9)
    ans = round((a + b) * c, 2)
    return f"({a} + {b}) × {c} = ", str(ans)

def _dec_context_money():
    """购物找零情境题（付款向上取整到整十再加10，凑出整数找回）"""
    price = round(random.uniform(2.5, 15.9), 1)
    qty = random.randint(3, 8)
    paid = math.ceil(price * qty / 10) * 10 + 10
    change = round(paid - price * qty, 2)
    return f"小明买了{qty}本笔记本，每本{price}元，付了{paid}元，应找回多少元？", f"{change} 元"

def _dec_multi_step():
    """小数多步混合"""
    a = round(random.uniform(10, 100), 2)
    b = round(random.uniform(0.1, 9.9), 2)
    c = round(random.uniform(0.1, 9.9), 1)
    ans = round(a * b + c, 3)
    return f"{a} × {b} + {c} = ", str(ans)

def _dec_approx():
    """小数估算（保留2位+给出精确值）"""
    a = round(random.uniform(10, 99), 2)
    b = round(random.uniform(1.1, 9.9), 2)
    exact = round(a * b, 4)
    return f"{a} × {b} ≈ ?（保留两位小数）精确值是多少？", f"≈{round(exact,2)}，精确值{exact}"

def _dec_reverse():
    """小数缺数逆填：由积反推因数（保留2位）"""
    a = round(random.uniform(10, 99), 1)
    result = round(random.uniform(100, 999), 1)
    b = round(result / a, 2)
    return f"{a} × (  ) = {round(a * b, 2)}，括号里填几？", str(b)

def _dec_context_measure():
    """长方形面积情境题（长×宽，保留4位）"""
    length = round(random.uniform(1.5, 9.9), 2)
    width = round(random.uniform(1.5, 9.9), 2)
    area = round(length * width, 4)
    return f"一块长方形玻璃长{length}米、宽{width}米，面积是多少平方米？", f"{area} 平方米"


@register("calc_fraction")
def calc_fraction(difficulty: int, grade: int):
    """分数四则运算 - 结构变体"""
    if difficulty <= 2:
        variants = [_frac_same_denom, _frac_to_mixed, _frac_compare, _frac_of_number]
    elif difficulty <= 4:
        variants = [_frac_diff_denom, _frac_multiply, _frac_divide, _frac_mixed_op]
    else:
        variants = [_frac_complex, _frac_chain, _frac_reverse, _frac_context]
    return random.choice(variants)()


def _frac_same_denom():
    """同分母分数加减（用 Fraction 自动约分，整数结果省略分母）"""
    d = random.choice([3, 4, 5, 6, 7, 8])
    n1 = random.randint(1, d - 2)
    n2 = random.randint(1, d - n1)
    ans = Fraction(n1 + n2, d)
    s = f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
    return f"{n1}/{d} + {n2}/{d} = ", s

def _frac_to_mixed():
    """假分数化带分数"""
    d = random.choice([3, 4, 5, 6, 7])
    whole = random.randint(1, 4)
    n = random.randint(1, d - 1)
    improper = whole * d + n
    return f"把 {improper}/{d} 化成带分数。", f"{whole}又{n}/{d}"

def _frac_compare():
    """分数大小比较（用易混淆的固定对，制造干扰）"""
    pairs = [(2, 3, 3, 4), (3, 5, 2, 3), (5, 8, 3, 5), (4, 7, 3, 5)]
    n1, d1, n2, d2 = random.choice(pairs)
    f1, f2 = Fraction(n1, d1), Fraction(n2, d2)
    sym = ">" if f1 > f2 else "<"
    return f"比较大小：{n1}/{d1} ○ {n2}/{d2}", sym

def _frac_of_number():
    """求一个数的几分之几（总数凑到能被分母整除，保证结果为整数）"""
    total = random.choice([60, 80, 100, 120, 150, 200])
    n, d = random.choice([(1, 3), (2, 5), (3, 4), (1, 4), (3, 8)])
    while total % d != 0:
        total += 10  # 把总数凑到能被分母整除，保证「的几分之几」结果为整数
    ans = total * n // d
    return f"{total}的{n}/{d}是多少？", str(ans)

def _frac_diff_denom():
    """异分母分数加减（自动调序，保证大减小不出现负数）"""
    d1, d2 = random.choice([(2, 3), (3, 4), (2, 5), (3, 5), (4, 6), (5, 6)])
    n1 = random.randint(1, d1 - 1)
    n2 = random.randint(1, d2 - 1)
    f1, f2 = Fraction(n1, d1), Fraction(n2, d2)
    op = random.choice(["+", "-"])
    if op == "-" and f1 < f2:
        f1, f2 = f2, f1
        n1, d1, n2, d2 = f1.numerator, f1.denominator, f2.numerator, f2.denominator
    ans = f1 + f2 if op == "+" else f1 - f2
    s = f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
    return f"{n1}/{d1} {op} {n2}/{d2} = ", s

def _frac_multiply():
    """分数乘法（Fraction 自动约分）"""
    d1, d2 = random.choice([(3, 4), (5, 6), (2, 7), (3, 8)])
    n1 = random.randint(1, d1 - 1)
    n2 = random.randint(1, d2 - 1)
    ans = Fraction(n1, d1) * Fraction(n2, d2)
    s = f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
    return f"{n1}/{d1} × {n2}/{d2} = ", s

def _frac_divide():
    """分数除法（乘以倒数，Fraction 自动约分）"""
    d1, d2 = random.choice([(3, 4), (5, 6), (2, 5), (3, 7)])
    n1 = random.randint(1, d1 - 1)
    n2 = random.randint(1, d2 - 1)
    ans = Fraction(n1, d1) / Fraction(n2, d2)
    s = f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
    return f"{n1}/{d1} ÷ {n2}/{d2} = ", s

def _frac_mixed_op():
    """带分数加法（先转假分数运算，结果再化回带分数）"""
    # 带分数运算
    w1 = random.randint(1, 3)
    d1 = random.choice([3, 4, 5])
    n1 = random.randint(1, d1 - 1)
    w2 = random.randint(1, 2)
    n2 = random.randint(1, d1 - 1)
    f1 = Fraction(w1 * d1 + n1, d1)
    f2 = Fraction(w2 * d1 + n2, d1)
    ans = f1 + f2
    aw = ans.numerator // ans.denominator
    an = ans.numerator % ans.denominator
    s = f"{aw}又{an}/{ans.denominator}" if an else str(aw)
    return f"{w1}又{n1}/{d1} + {w2}又{n2}/{d1} = ", s

def _frac_complex():
    """分数乘加混合（固定分母组合，便于口算）"""
    # 分数混合：a/b × c/d + e/f
    d1, d2, d3 = 3, 4, 6
    n1, n2, n3 = random.randint(1, 2), random.randint(1, 3), random.randint(1, 5)
    ans = Fraction(n1, d1) * Fraction(n2, d2) + Fraction(n3, d3)
    s = f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
    return f"{n1}/{d1} × {n2}/{d2} + {n3}/{d3} = ", s

def _frac_chain():
    """连续求几分之几（分步写出两步结果）"""
    # 连续运算
    total = random.choice([120, 180, 240, 360])
    f1 = random.choice([(1, 3), (1, 4), (2, 5)])
    f2 = random.choice([(1, 2), (2, 3), (3, 4)])
    step1 = total * f1[0] // f1[1]
    step2 = step1 * f2[0] // f2[1]
    return (
        f"{total}的{f1[0]}/{f1[1]}是多少？再取结果的{f2[0]}/{f2[1]}是多少？",
        f"第一步{step1}，第二步{step2}"
    )

def _frac_reverse():
    """已知一个数的几分之几是多少，反求原数（凑整除）"""
    # 已知一个数的几分之几，求这个数
    n, d = random.choice([(2, 3), (3, 5), (4, 7), (5, 8)])
    x = random.randint(30, 200)
    while x % d != 0:
        x += 1
    part = x * n // d
    return f"一个数的{n}/{d}是{part}，这个数是多少？", str(x)

def _frac_context():
    """分数剩余情境题（两天分别吃总量/剩余的比例，求最后余量）"""
    # 情境：剩余问题
    total = random.choice([100, 120, 150, 200])
    f1 = random.choice([(1, 4), (1, 5), (2, 5)])
    f2 = random.choice([(1, 3), (1, 4), (2, 5)])
    used1 = total * f1[0] // f1[1]
    remain1 = total - used1
    used2 = remain1 * f2[0] // f2[1]
    final = remain1 - used2
    return (
        f"一袋米{total}千克，第一天吃了{f1[0]}/{f1[1]}，第二天吃了剩下的{f2[0]}/{f2[1]}，还剩多少千克？",
        f"{final} 千克"
    )


@register("calc_mixed")
def calc_mixed(difficulty: int, grade: int):
    """混合运算与简便计算 - 结构变体"""
    if difficulty <= 2:
        variants = [_mix_order, _mix_bracket, _mix_simple_distribute]
    elif difficulty <= 4:
        variants = [_mix_distribute, _mix_combine, _mix_subtract_prop, _mix_context]
    else:
        variants = [_mix_advanced_trick, _mix_multi_law, _mix_reverse_law, _mix_fraction_dec]
    return random.choice(variants)()


def _mix_order():
    """混合运算顺序（无括号，先乘后加）"""
    a, b, c = random.randint(20, 100), random.randint(2, 9), random.randint(10, 50)
    return f"{a} + {b} × {c} = （注意运算顺序）", str(a + b * c)

def _mix_bracket():
    """带括号混合运算"""
    a, b, c = random.randint(20, 100), random.randint(20, 100), random.randint(2, 9)
    return f"({a} + {b}) × {c} = ", str((a + b) * c)

def _mix_simple_distribute():
    """凑整简便（25×4/125×8 等）"""
    a = random.choice([25, 50, 125])
    b = random.choice([4, 2, 8])
    c = random.randint(10, 99)
    return f"{a} × {b} + {c} = （先凑整再算）", str(a * b + c)

def _mix_distribute():
    """乘法分配律正向运用（a×c+b×c）"""
    a = random.randint(11, 99)
    b = random.randint(11, 99)
    c = random.choice([3, 7, 9, 11, 13])
    return f"{a} × {c} + {b} × {c} = （用简便方法）", f"{(a+b)*c}（= ({a}+{b})×{c}）"

def _mix_combine():
    """连乘凑整 + 加减（如 125×8）"""
    a = random.choice([125, 25, 50])
    b = random.choice([8, 4, 2])
    c = random.randint(10, 99)
    d = random.randint(10, 99)
    return f"{a} × {b} + {c} - {d} = ", str(a * b + c - d)

def _mix_subtract_prop():
    """减法性质简算（a-b-c = a-(b+c)）"""
    a = random.randint(200, 999)
    b = random.randint(50, 200)
    c = random.randint(50, 200)
    return f"{a} - {b} - {c} = （用减法性质简算）", f"{a-b-c}（= {a}-({b}+{c})）"

def _mix_context():
    """购物简便情境（合并数量后用单价，隐含分配律）"""
    price = random.randint(15, 45)
    n1 = random.randint(3, 8)
    n2 = random.randint(3, 8)
    return f"买{n1}支钢笔和{n2}支钢笔，每支{price}元，一共多少元？（用简便方法）", f"{(n1+n2)*price} 元"

def _mix_advanced_trick():
    """接近整百的巧算（99/101 等，拆成 100±d 用分配律）"""
    a = random.choice([99, 101, 98, 102])
    b = random.randint(20, 99)
    base = 100
    diff = a - base
    ans = base * b + diff * b
    return f"{a} × {b} = （用简便方法）", f"{ans}（= {base}×{b}{'+'if diff>0 else '-'}{abs(diff)}×{b}）"

def _mix_multi_law():
    """乘法交换/结合律（25×4、125×8 凑整）"""
    a = random.choice([25, 125])
    b = random.choice([4, 8])
    c = random.randint(11, 99)
    return f"{a} × {c} × {b} = （用交换律和结合律）", f"{a*b*c}（= {a}×{b}×{c}）"

def _mix_reverse_law():
    """逆用乘法分配律（a×c-b×c = (a-b)×c）"""
    a = random.randint(11, 50)
    b = random.randint(11, 50)
    c = random.choice([5, 9, 11])
    total = a * c - b * c
    return f"{a} × {c} - {b} × {c} = （逆用分配律）", f"{total}（= ({a}-{b})×{c}）"

def _mix_fraction_dec():
    """分数小数混合简算（把小数化成分数凑整）"""
    # 分数小数混合
    a = random.choice([0.25, 0.5, 0.75, 1.25])
    b = random.randint(20, 80)
    c = random.choice([4, 2, 8])
    ans = a * b * c
    return f"{a} × {b} × {c} = （把小数化分数简算）", f"{ans:.0f}" if ans == int(ans) else str(ans)


@register("calc_equation")
def calc_equation(difficulty: int, grade: int):
    """解方程 - 结构变体"""
    if difficulty <= 2:
        variants = [_eq_simple, _eq_add_form, _eq_word_simple]
    elif difficulty <= 4:
        variants = [_eq_two_step, _eq_both_sides, _eq_bracket, _eq_word_mid]
    else:
        variants = [_eq_fraction_coeff, _eq_proportion, _eq_word_hard, _eq_system_hint]
    return random.choice(variants)()


def _eq_simple():
    """最简一元一次方程 ax = b（构造整数解）"""
    x = random.randint(2, 20)
    a = random.randint(2, 9)
    return f"解方程：{a}x = {a*x}", f"x = {x}"

def _eq_add_form():
    """ax + b = c 型（加法形式）"""
    x = random.randint(2, 15)
    a = random.randint(2, 9)
    b = random.randint(1, 20)
    return f"解方程：{a}x + {b} = {a*x+b}", f"x = {x}"

def _eq_word_simple():
    """和倍文字题（列方程解）"""
    x = random.randint(5, 30)
    a = random.randint(2, 5)
    total = a * x
    return f"一个数的{a}倍是{total}，这个数是多少？（列方程解）", f"设这个数为x，{a}x={total}，x={x}"

def _eq_two_step():
    """两步方程 ax + b = c"""
    x = random.randint(2, 15)
    a = random.randint(2, 9)
    b = random.randint(1, 30)
    c = a * x + b
    return f"解方程：{a}x + {b} = {c}", f"x = {x}"

def _eq_both_sides():
    """等式两边均含 x（移项合并）"""
    x = random.randint(2, 12)
    a = random.randint(3, 8)
    b = random.randint(2, a - 1)
    c = random.randint(1, 15)
    d = (a - b) * x + c
    return f"解方程：{a}x + {c} = {b}x + {d}", f"x = {x}"

def _eq_bracket():
    """带括号方程 c(ax+b) = 结果（构造整数解）"""
    x = random.randint(2, 10)
    a = random.randint(2, 5)
    b = random.randint(1, 10)
    c = random.randint(2, 4)
    result = c * (a * x + b)
    return f"解方程：{c}({a}x + {b}) = {result}", f"x = {x}"

def _eq_word_mid():
    """和差文字题（列方程，甲乙各多少）"""
    x = random.randint(10, 50)
    more = random.randint(5, 30)
    total = x + (x + more)
    return f"甲乙两数和是{total}，甲比乙多{more}，甲乙各是多少？（列方程）", f"乙x={x}，甲={x+more}"

def _eq_fraction_coeff():
    """分数系数方程（x/3+x/2，凑 x 被 6 整除便于去分母）"""
    x = random.randint(6, 30)
    while x % 3 != 0:
        x += 1
    # x/3 + x/2 = result
    result = x // 3 + x // 2
    return f"解方程：x/3 + x/2 = {result}", f"x = {x}"

def _eq_proportion():
    """解比例 a/b = c/x（调整 c 使 x 为整数）"""
    x = random.randint(4, 20)
    a, b = random.randint(2, 5), random.randint(2, 5)
    c = random.randint(2, 10)
    # a/b = c/x → x = bc/a
    x_val = b * c
    while x_val % a != 0:
        c += 1
        x_val = b * c
    x_val //= a
    return f"解比例：{a}/{b} = {c}/x", f"x = {x_val}"

def _eq_word_hard():
    """行程文字题（列方程求返回时间，返回速度=去时+增量）"""
    speed = random.randint(40, 80)
    time = random.randint(2, 5)
    dist = speed * time
    return (
        f"一辆车从A到B，去时每小时{speed}千米，用了{time}小时。"
        f"回来时每小时快{random.randint(10,20)}千米，回来用几小时？（列方程）",
        None
    )
    # 重新计算
    extra = random.randint(10, 20)
    back_speed = speed + extra
    back_time = dist / back_speed
    ans = f"{back_time:.1f}小时" if back_time != int(back_time) else f"{int(back_time)}小时"
    return (
        f"一辆车从A到B，去时每小时{speed}千米，用了{time}小时。"
        f"回来时每小时快{extra}千米，回来用几小时？（列方程）",
        f"设回来用x小时，{back_speed}x={dist}，x={ans}"
    )

def _eq_system_hint():
    """和差方程组（已知两数和与差，求大数/小数）"""
    x = random.randint(5, 15)
    y = random.randint(5, 15)
    s = x + y
    d = abs(x - y)
    big, small = max(x, y), min(x, y)
    return (
        f"两个数的和是{s}，差是{d}，求这两个数。（列方程组）",
        f"大数{big}，小数{small}"
    )


@register("unit_conversion")
def unit_conversion(difficulty: int, grade: int):
    """单位换算 - 结构变体"""
    if difficulty <= 2:
        variants = [_unit_length, _unit_weight, _unit_time, _unit_reverse]
    elif difficulty <= 4:
        variants = [_unit_area, _unit_volume, _unit_compound, _unit_context]
    else:
        variants = [_unit_mixed, _unit_compare, _unit_multi_step, _unit_real]
    return random.choice(variants)()


def _unit_length():
    """长度单位换算（大→小，乘进率）"""
    cases = [("千米", "米", 1000), ("米", "厘米", 100), ("米", "分米", 10)]
    big, small, rate = random.choice(cases)
    v = random.randint(2, 9)
    return f"{v}{big} = ___{small}", f"{v*rate} {small}"

def _unit_weight():
    """质量单位换算（大→小）"""
    cases = [("吨", "千克", 1000), ("千克", "克", 1000)]
    big, small, rate = random.choice(cases)
    v = random.randint(2, 8)
    return f"{v}{big} = ___{small}", f"{v*rate} {small}"

def _unit_time():
    """时间单位换算（大→小）"""
    cases = [("时", "分", 60), ("分", "秒", 60), ("日", "时", 24)]
    big, small, rate = random.choice(cases)
    v = random.randint(2, 5)
    return f"{v}{big} = ___{small}", f"{v*rate} {small}"

def _unit_reverse():
    """单位换算（小→大，除以进率；取值为进率整数倍保证整除）"""
    cases = [("米", "千米", 1000), ("厘米", "米", 100), ("千克", "吨", 1000)]
    small, big, rate = random.choice(cases)
    v = random.randint(2, 9) * rate
    return f"{v}{small} = ___{big}", f"{v//rate} {big}"

def _unit_area():
    """面积单位换算（大→小，面积进率为长度平方）"""
    cases = [("平方米", "平方分米", 100), ("平方分米", "平方厘米", 100), ("公顷", "平方米", 10000)]
    big, small, rate = random.choice(cases)
    v = random.randint(2, 15)
    return f"{v}{big} = ___{small}", f"{v*rate} {small}"

def _unit_volume():
    """体积/容积单位换算（大→小）"""
    cases = [("立方米", "立方分米", 1000), ("立方分米", "立方厘米", 1000), ("升", "毫升", 1000)]
    big, small, rate = random.choice(cases)
    v = random.randint(2, 9)
    return f"{v}{big} = ___{small}", f"{v*rate} {small}"

def _unit_compound():
    """复合单位换算（如 3千米500米 → 米），用固定示例减少歧义"""
    cases = [
        (f"3千米500米 = ___米", "3500 米"),
        (f"2时45分 = ___分", "165 分"),
        (f"4.05吨 = ___吨___千克", "4吨50千克"),
        (f"2平方米30平方分米 = ___平方分米", "230 平方分米"),
        (f"5.6升 = ___升___毫升", "5升600毫升"),
    ]
    return random.choice(cases)

def _unit_context():
    """米→千米情境题（除以1000）"""
    m = random.randint(1500, 9500)
    km = m / 1000
    return f"小明家到学校{m}米，合多少千米？", f"{km} 千米"

def _unit_mixed():
    """小数表示复合单位（如 3.6立方米 → 3立方米600立方分米）"""
    cases = [
        (f"3.6立方米 = ___立方米___立方分米", "3立方米600立方分米"),
        (f"2.05千米 = ___千米___米", "2千米50米"),
        (f"4时30分 = ___时（用小数）", "4.5时"),
    ]
    return random.choice(cases)

def _unit_compare():
    """不同单位比较大小（统一成米/千米再比）"""
    a_m = random.randint(1, 5) * 1000 + random.randint(1, 9) * 100
    b_m = random.randint(1, 5) * 1000 + random.randint(1, 9) * 100
    sym = ">" if a_m > b_m else "<"
    return f"比较：{a_m}米 ○ {b_m/1000:.1f}千米", f"{sym}"

def _unit_multi_step():
    """跨单位面积换算（cm² → m²，除以10000）"""
    l_cm = random.randint(100, 500)
    w_cm = random.randint(50, 200)
    area_cm2 = l_cm * w_cm
    area_m2 = area_cm2 / 10000
    return f"一块地长{l_cm}厘米、宽{w_cm}厘米（图纸上），实际面积是多少平方厘米？合多少平方米？", f"{area_cm2}平方厘米 = {area_m2}平方米"

def _unit_real():
    """速度×时间情境题（分钟→小时，求路程）"""
    speed_kmh = random.randint(60, 120)
    time_min = random.randint(30, 90)
    time_h = time_min / 60
    dist = speed_kmh * time_h
    return f"汽车时速{speed_kmh}千米，行驶{time_min}分钟，行了多少千米？", f"{dist:.1f} 千米" if dist != int(dist) else f"{int(dist)} 千米"


# ═══════════════════════════════════════════════════════════
# 二、图形与几何（6种）
# ═══════════════════════════════════════════════════════════

@register("geo_area_plane")
def geo_area_plane(difficulty: int, grade: int):
    """平面图形面积 - 结构变体"""
    if difficulty <= 2:
        variants = [_area_triangle, _area_parallelogram, _area_rect_both, _area_reverse_base]
    elif difficulty <= 4:
        variants = [_area_trapezoid, _area_circle, _area_composite_sub, _area_reverse_height, _area_house]
    else:
        variants = [_area_shaded, _area_equal_transform, _area_ratio_2d, _area_inscribed, _area_rect_semicircle]
    return random.choice(variants)()

def _area_triangle():
    """三角形面积（底×高÷2），调用配图渲染并附 img 路径"""
    b, h = random.randint(4, 20), random.randint(3, 15)
    area = b * h / 2
    s = f"{area:.1f}" if area != int(area) else str(int(area))
    try:
        from .figure_renderer import render_triangle
        img = render_triangle(b, h)
    except Exception:
        img = ""
    return f"三角形底{b}cm、高{h}cm，面积是多少？", f"{s} cm\u00b2", img

def _area_parallelogram():
    """平行四边形面积（底×高），附配图"""
    b, h = random.randint(4, 20), random.randint(3, 15)
    try:
        from .figure_renderer import render_parallelogram
        img = render_parallelogram(b, h)
    except Exception:
        img = ""
    return f"平行四边形底{b}cm、高{h}cm，面积是多少？", f"{b*h} cm\u00b2", img

def _area_rect_both():
    """长方形面积与周长（同时考两个公式），附配图"""
    l, w = random.randint(5, 25), random.randint(3, 15)
    try:
        from .figure_renderer import render_rectangle
        img = render_rectangle(l, w)
    except Exception:
        img = ""
    return f"长方形长{l}cm、宽{w}cm，面积和周长各是多少？", f"面积{l*w}cm\u00b2，周长{2*(l+w)}cm", img

def _area_reverse_base():
    h = random.randint(3, 12)
    area = random.randint(20, 120)
    while (2 * area) % h != 0:
        area += 1  # 已知面积和高反求底：底=面积×2÷高，凑整除保证底为整数
    b = 2 * area // h
    return f"三角形面积{area}cm\u00b2，高{h}cm，底是多少？", f"{b} cm（底=面积\u00d72\u00f7高）"

def _area_trapezoid():
    """梯形面积（(上底+下底)×高÷2），附配图"""
    a, b, h = random.randint(4, 12), random.randint(6, 16), random.randint(3, 10)
    area = (a + b) * h / 2
    s = f"{area:.1f}" if area != int(area) else str(int(area))
    try:
        from .figure_renderer import render_trapezoid
        img = render_trapezoid(a, b, h)
    except Exception:
        img = ""
    return f"梯形上底{a}cm、下底{b}cm、高{h}cm，面积？", f"{s} cm\u00b2", img

def _area_circle():
    """圆面积（πr²，π取3.14），附配图"""
    r = random.randint(2, 10)
    area = round(3.14 * r * r, 2)
    try:
        from .figure_renderer import render_circle
        img = render_circle(r)
    except Exception:
        img = ""
    return f"圆半径{r}cm，求面积。（\u03c0取3.14）", f"{area} cm\u00b2", img

def _area_composite_sub():
    """L形组合面积（大长方形 − 右上角小长方形），附配图"""
    L, W = random.randint(10, 20), random.randint(8, 15)
    l, w = random.randint(3, L-3), random.randint(3, W-3)
    try:
        from .figure_renderer import render_composite_L
        img = render_composite_L(L, W, l, w)
    except Exception:
        img = ""
    return f"L形：外框{L}\u00d7{W}cm，挖去右上角{l}\u00d7{w}cm小长方形，面积？", f"{L*W - l*w} cm\u00b2", img

def _area_reverse_height():
    """已知梯形面积与上下底，反求高（凑整除保整数）"""
    a, b = random.randint(5, 12), random.randint(8, 16)
    area = random.randint(30, 100)
    while (2 * area) % (a + b) != 0:
        area += 1
    h = 2 * area // (a + b)
    return f"梯形面积{area}cm\u00b2，上底{a}cm下底{b}cm，高是多少？", f"{h} cm"

def _area_shaded():
    """阴影面积（正方形 − 内切圆），π取3.14，附配图"""
    r = random.randint(3, 8)
    side = 2 * r
    shadow = round(side * side - 3.14 * r * r, 2)
    try:
        from .figure_renderer import render_composite_square_circle
        img = render_composite_square_circle(side, r)
    except Exception:
        img = ""
    return f"正方形边长{side}cm，内切圆半径{r}cm，阴影面积？（\u03c0取3.14）", f"{shadow} cm\u00b2", img

def _area_equal_transform():
    """等面积转换：已知平行四边形面积与三角形高，反求三角形底（凑整除）"""
    b, h = random.randint(6, 15), random.randint(4, 10)
    para_area = b * h
    tri_h = random.randint(4, 12)
    while (2 * para_area) % tri_h != 0:
        tri_h += 1
    tri_b = 2 * para_area // tri_h
    return f"平行四边形底{b}cm高{h}cm，与它等面积的三角形高{tri_h}cm，底是多少？", f"{tri_b} cm"

def _area_ratio_2d():
    """圆面积比 = 半径平方比（r1²:r2²）"""
    r1, r2 = random.randint(2, 5), random.randint(4, 8)
    return f"两圆半径比{r1}:{r2}，面积比是多少？", f"{r1**2}:{r2**2}"

def _area_inscribed():
    """圆内接正方形面积（对角线=直径，面积=对角线²÷2）"""
    r = random.randint(3, 7)
    d = 2 * r
    sq_area = d * d / 2
    return f"圆半径{r}cm，内接正方形面积是多少？", f"{sq_area:.1f} cm\u00b2（对角线=直径{d}cm）"

def _area_house():
    """长方形+三角形（房屋形组合面积）"""
    w = random.randint(6, 16)
    h_rect = random.randint(5, 12)
    h_tri = random.randint(3, 10)
    area = w * h_rect + w * h_tri / 2
    s = f"{area:.1f}" if area != int(area) else str(int(area))
    try:
        from .figure_renderer import render_composite_rect_triangle
        img = render_composite_rect_triangle(w, h_rect, h_tri)
    except Exception:
        img = ""
    return (f"组合图形：下方长方形宽{w}cm高{h_rect}cm，"
            f"上方三角形高{h_tri}cm（底与长方形同宽），总面积？",
            f"{s} cm\u00b2", img)

def _area_rect_semicircle():
    """长方形+半圆（组合面积）"""
    w = random.choice([6, 8, 10, 12, 14])
    h = random.randint(5, 15)
    r = w / 2
    area = round(w * h + 3.14 * r * r / 2, 2)
    try:
        from .figure_renderer import render_composite_rect_semicircle
        img = render_composite_rect_semicircle(w, h)
    except Exception:
        img = ""
    return (f"组合图形：长方形宽{w}cm高{h}cm，顶部接一个半圆（直径={w}cm），"
            f"总面积？（\u03c0取3.14）",
            f"{area} cm\u00b2", img)


@register("geo_volume")
def geo_volume(difficulty: int, grade: int):
    """立体图形体积 - 结构变体"""
    if difficulty <= 2:
        variants = [_vol_cuboid, _vol_cube, _vol_reverse_h, _vol_capacity]
    elif difficulty <= 4:
        variants = [_vol_cylinder, _vol_cone, _vol_equal_bh, _vol_displacement, _vol_cylinder_cone]
    else:
        variants = [_vol_hollow, _vol_melt, _vol_water_rise, _vol_ratio_3d, _vol_cuboid_hole]
    return random.choice(variants)()

def _vol_cuboid():
    """长方体体积（长×宽×高），附配图"""
    a, b, c = random.randint(3, 12), random.randint(3, 12), random.randint(3, 12)
    try:
        from .figure_renderer import render_cuboid
        img = render_cuboid(a, b, c)
    except Exception:
        img = ""
    return f"长方体长{a}cm宽{b}cm高{c}cm，体积？", f"{a*b*c} cm\u00b3", img

def _vol_cube():
    """正方体体积与表面积（棱长³、6×棱长²）"""
    a = random.randint(3, 12)
    return f"正方体棱长{a}cm，体积和表面积？", f"体积{a**3}cm\u00b3，表面积{6*a*a}cm\u00b2"

def _vol_reverse_h():
    """已知体积与长宽反求高（凑整除保整数）"""
    v = random.randint(60, 500)
    a, b = random.randint(3, 10), random.randint(3, 10)
    while v % (a * b) != 0:
        v += 1
    return f"长方体体积{v}cm\u00b3，长{a}cm宽{b}cm，高是多少？", f"{v//(a*b)} cm"

def _vol_capacity():
    """容器容积（cm³ → 毫升，1:1）"""
    l, w, h = random.randint(10, 40), random.randint(8, 30), random.randint(5, 20)
    ml = l * w * h
    return f"容器长{l}cm宽{w}cm高{h}cm，最多装多少毫升水？", f"{ml}毫升（={ml/1000:.1f}升）"

def _vol_cylinder():
    """圆柱体积（πr²h，π取3.14），附配图"""
    r, h = random.randint(2, 8), random.randint(5, 20)
    v = round(3.14 * r * r * h, 2)
    try:
        from .figure_renderer import render_cylinder
        img = render_cylinder(r, h)
    except Exception:
        img = ""
    return f"圆柱底面半径{r}cm高{h}cm，体积？（\u03c0取3.14）", f"{v} cm\u00b3", img

def _vol_cone():
    """圆锥体积（πr²h÷3，π取3.14），附配图"""
    r, h = random.randint(3, 8), random.randint(6, 18)
    v = round(3.14 * r * r * h / 3, 2)
    try:
        from .figure_renderer import render_cone
        img = render_cone(r, h)
    except Exception:
        img = ""
    return f"圆锥底面半径{r}cm高{h}cm，体积？（\u03c0取3.14）", f"{v} cm\u00b3", img

def _vol_equal_bh():
    """等底等高圆柱与圆锥体积（圆锥是圆柱的1/3）"""
    r, h = random.randint(3, 7), random.randint(6, 15)
    v_cyl = round(3.14 * r * r * h, 2)
    v_cone = round(v_cyl / 3, 2)
    return f"圆柱圆锥等底等高，半径{r}cm高{h}cm，各体积多少？什么关系？", f"圆柱{v_cyl}cm\u00b3，圆锥{v_cone}cm\u00b3，3倍关系"

def _vol_displacement():
    """排水法求不规则物体体积（底面积×水面升高）"""
    l, w, rise = random.randint(10, 25), random.randint(8, 20), random.randint(2, 8)
    return f"容器长{l}cm宽{w}cm，放石头后水面升{rise}cm，石头体积？", f"{l*w*rise} cm\u00b3"

def _vol_hollow():
    """空心铁皮箱（无盖）铁皮体积（外体积 − 内腔体积）"""
    L, W, H, t = random.randint(10, 20), random.randint(8, 15), random.randint(5, 12), 1
    inner = (L-2*t) * (W-2*t) * (H-t)
    v = L*W*H - inner
    return f"无盖铁皮箱外尺寸{L}\u00d7{W}\u00d7{H}cm，壁厚{t}cm，铁皮体积？", f"{v} cm\u00b3"

def _vol_melt():
    """熔铸问题（正方体体积不变，求长方体底面积，凑整除）"""
    a = random.randint(4, 10)
    v = a ** 3
    h = random.randint(3, 8)
    while v % h != 0:
        h += 1
    return f"棱长{a}cm正方体熔铸成高{h}cm长方体，底面积多少？", f"{v//h} cm\u00b2"

def _vol_water_rise():
    """放入物体水面升高（物体体积÷圆柱底面积）"""
    r = random.randint(5, 10)
    obj_v = random.randint(50, 200)
    rise = round(obj_v / (3.14 * r * r), 2)
    return f"圆柱容器底面半径{r}cm，放入{obj_v}cm\u00b3物体，水面升多少？", f"约{rise} cm"

def _vol_ratio_3d():
    """正方体体积比 = 棱长立方比（a1³:a2³）"""
    a1, a2 = random.randint(2, 4), random.randint(3, 6)
    return f"两正方体棱长比{a1}:{a2}，体积比是多少？", f"{a1**3}:{a2**3}"

def _vol_cylinder_cone():
    """圆柱+圆锥组合体（如铅笔、塔尖）"""
    r = random.randint(2, 6)
    h_cyl = random.randint(6, 15)
    h_cone = random.randint(3, 10)
    v_cyl = round(3.14 * r * r * h_cyl, 2)
    v_cone = round(3.14 * r * r * h_cone / 3, 2)
    v_total = round(v_cyl + v_cone, 2)
    try:
        from .figure_renderer import render_composite_cylinder_cone
        img = render_composite_cylinder_cone(r, h_cyl, h_cone)
    except Exception:
        img = ""
    return (f"组合体：下方圆柱半径{r}cm高{h_cyl}cm，"
            f"上方圆锥半径{r}cm高{h_cone}cm，总体积？（\u03c0取3.14）",
            f"{v_total} cm\u00b3（圆柱{v_cyl}+圆锥{v_cone}）", img)

def _vol_cuboid_hole():
    """长方体挖去圆柱孔"""
    a = random.randint(10, 20)
    b = random.randint(8, 15)
    c = random.randint(6, 12)
    r = random.randint(2, min(a, c) // 2 - 1)
    v_cuboid = a * b * c
    v_hole = round(3.14 * r * r * b, 2)
    v_remain = round(v_cuboid - v_hole, 2)
    try:
        from .figure_renderer import render_composite_cuboid_hole
        img = render_composite_cuboid_hole(a, b, c, r)
    except Exception:
        img = ""
    return (f"长方体长{a}cm宽{b}cm高{c}cm，沿宽的方向打一个半径{r}cm的圆柱孔（打穿），"
            f"剩余体积？（\u03c0取3.14）",
            f"{v_remain} cm\u00b3（{v_cuboid}-{v_hole}）", img)


@register("geo_perimeter")
def geo_perimeter(difficulty: int, grade: int):
    """周长综合 - 结构变体"""
    if difficulty <= 2:
        l, w = random.randint(5, 20), random.randint(3, 15)
        variants = [
            (f"长方形长{l}cm宽{w}cm，周长和面积？", f"周长{2*(l+w)}cm，面积{l*w}cm\u00b2"),
            (f"正方形边长{random.randint(4,15)}cm，周长和面积？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            s = random.randint(4, 15)
            return f"正方形边长{s}cm，周长和面积？", f"周长{4*s}cm，面积{s*s}cm\u00b2"
        return q, a
    elif difficulty <= 4:
        variants = [
            lambda: (lambda r: (f"圆半径{r}cm，周长？（\u03c0取3.14）", f"{round(2*3.14*r,2)} cm"))(random.randint(2,10)),
            lambda: (lambda r: (f"半圆半径{r}cm，周长？（含直径）", f"{round(3.14*r+2*r,2)} cm"))(random.randint(3,8)),
            lambda: (lambda c,rt: (f"长方形周长{c}cm，长宽比{rt[0]}:{rt[1]}，面积？", None))(random.choice([20,24,32,40]), random.choice([(2,1),(3,2)])),
            lambda: (lambda l,w: (f"靠墙围长{l}m宽{w}m菜园（一面靠墙），篱笆多长？", f"{l+2*w} m"))(random.randint(10,30), random.randint(5,15)),
        ]
        q, a = random.choice(variants)()
        if a is None:
            c = random.choice([20, 24, 32, 40])
            rt = random.choice([(2, 1), (3, 2)])
            half = c // 2
            tp = rt[0] + rt[1]
            while half % tp != 0:
                c += 2
                half = c // 2
            ll = half * rt[0] // tp
            ww = half - ll
            return f"长方形周长{c}cm，长宽比{rt[0]}:{rt[1]}，面积？", f"{ll*ww} cm\u00b2"
        return q, a
    else:
        variants = [
            lambda: (lambda r: (f"铁丝围半径{r}cm圆，改围正方形，边长？（\u03c0取3.14）", f"{round(2*3.14*r/4,2)} cm"))(random.randint(3,8)),
            lambda: (lambda c: (f"周长{c}cm的长方形，怎样围面积最大？最大多少？", f"正方形最大，边长{c//4}cm，面积{(c//4)**2}cm\u00b2"))(random.choice([20,24,32,40])),
            lambda: (lambda r,l: (f"跑道：两直道各{l}m，两半圆半径{r}m，一圈多长？", f"{round(2*3.14*r+2*l,2)} m"))(random.randint(20,40), random.randint(50,100)),
        ]
        return random.choice(variants)()


@register("geo_transform")
def geo_transform(difficulty: int, grade: int):
    """图形变换 - 结构变体"""
    if difficulty <= 2:
        a = random.randint(3, 8)
        variants = [
            (f"正方形边长{a}cm按2:1放大，新边长和新面积？", f"边长{a*2}cm，面积{a*a*4}cm\u00b2（4倍）"),
            (f"图形按1:2缩小，面积变为原来的几分之几？", "1/4"),
            (f"等边三角形有几条对称轴？长方形呢？", "等边3条，长方形2条"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        r = random.randint(2, 6)
        variants = [
            (f"圆半径{r}cm按3:1放大，周长扩大几倍？面积扩大几倍？", "周长3倍，面积9倍"),
            (f"三角形按2:1放大后面积是原来的几倍？", "4倍"),
            (f"长方形长8cm宽5cm，按1:2缩小后再按3:1放大，最终面积？", f"{round(8*5*3/2*3/2,1)} cm\u00b2（原来的9/4倍）"),
        ]
        return random.choice(variants)
    else:
        variants = [
            (f"两相似三角形边长比3:5，面积比是多少？", "9:25"),
            (f"正方形按2:1放大后，对角线变为原来的几倍？面积呢？", "对角线2倍，面积4倍"),
            (f"一个图形先按4:1放大再按1:2缩小，面积变为原来的几倍？", "4倍（4\u00b2\u00f72\u00b2=4）"),
        ]
        return random.choice(variants)


@register("geo_recognition")
def geo_recognition(difficulty: int, grade: int):
    """图形认识与分类 - 结构变体"""
    if difficulty <= 2:
        variants = [
            (f"一个角是{random.choice([35,60,89])}\u00b0，是什么角？", "锐角"),
            (f"一个角是{random.choice([91,120,150,179])}\u00b0，是什么角？", "钝角"),
            ("三角形按角分类有哪三种？", "锐角三角形、直角三角形、钝角三角形"),
            ("长方形有几条对称轴？正方形呢？", "长方形2条，正方形4条"),
        ]
    elif difficulty <= 4:
        variants = [
            ("等边三角形每个角多少度？几条对称轴？", "60\u00b0，3条"),
            ("三角形两角分别35\u00b0和55\u00b0，第三角多少？什么三角形？", "90\u00b0，直角三角形"),
            ("平行四边形和梯形的主要区别？", "平行四边形两组对边平行，梯形只有一组"),
            ("圆有几条对称轴？半圆呢？", "圆无数条，半圆1条"),
        ]
    else:
        variants = [
            ("三角形内角比1:2:3，各角多少度？什么三角形？", "30\u00b0+60\u00b0+90\u00b0，直角三角形"),
            ("等腰三角形顶角80\u00b0，底角多少度？", "50\u00b0"),
            ("等腰三角形一个底角45\u00b0，顶角多少？又是什么三角形？", "顶角90\u00b0，等腰直角三角形"),
            ("36cm铁丝围等腰三角形，腰是底的2倍，各边多长？", "底7.2cm，腰14.4cm"),
        ]
    return random.choice(variants)


@register("geo_position")
def geo_position(difficulty: int, grade: int):
    """位置与方向 - 结构变体"""
    if difficulty <= 2:
        col, row = random.randint(1, 8), random.randint(1, 8)
        variants = [
            (f"小明在第{col}列第{row}行，用数对表示。", f"({col}, {row})"),
            ("数对(3, 5)表示第几列第几行？", "第3列第5行"),
            ("(2,4)和(4,2)是同一位置吗？", "不是，第一个数是列，第二个是行"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        dist = random.choice([200, 300, 400, 500, 600, 800])
        direction = random.choice(["东", "南", "西", "北", "东北", "东南", "西北", "西南"])
        variants = [
            (f"学校在邮局{direction}方向{dist}m处，比例尺1:10000，图上多长？", f"{dist//100} cm"),
            ("A在B的北偏东30\u00b0方向500m处，B在A的什么方向？", "南偏西30\u00b0方向500m处"),
            ("从(1,1)向东走3格再向北走2格，到达哪里？", "(4, 3)"),
        ]
        return random.choice(variants)
    else:
        variants = [
            ("图书馆在学校北偏东30\u00b0方向600m，医院在南偏西45\u00b0方向400m。描述从图书馆经学校到医院的路线。", "向南偏西30\u00b0走600m到学校，再向南偏西45\u00b0走400m到医院，共1000m"),
            ("甲在乙东偏北40\u00b0方向800m，丙在乙正南600m。甲在丙的什么方向？", "甲在丙的东北方向（需画图分析）"),
        ]
        return random.choice(variants)


# ═══════════════════════════════════════════════════════════
# 三、比与比例（3种）
# ═══════════════════════════════════════════════════════════

@register("ratio_basic")
def ratio_basic(difficulty: int, grade: int):
    """比的认识与化简 - 结构变体"""
    if difficulty <= 2:
        a, b = random.randint(2, 15), random.randint(2, 15)
        g = math.gcd(a, b)
        variants = [
            (f"化简比：{a}:{b}", f"{a//g}:{b//g}"),
            (f"{a}:{b}的比值是多少？", f"{a/b:.2f}" if a % b != 0 else str(a//b)),
            (f"把{a}:{b}写成分数形式。", f"{a//g}/{b//g}"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        a, b, c = random.randint(6, 30), random.randint(6, 30), random.randint(6, 30)
        g = math.gcd(math.gcd(a, b), c)
        variants = [
            (f"化简比：{a}:{b}:{c}", f"{a//g}:{b//g}:{c//g}"),
            (f"0.5:0.75化简比是多少？", "2:3"),
            (f"1/4:1/6化简比是多少？", "3:2"),
        ]
        return random.choice(variants)
    else:
        a, b = random.randint(2, 7), random.randint(3, 9)
        total = random.randint(50, 200)
        while total % (a + b) != 0:
            total += 1
        pa, pb = total * a // (a + b), total * b // (a + b)
        variants = [
            (f"甲乙比{a}:{b}，和是{total}，各是多少？", f"甲{pa}，乙{pb}"),
            (f"甲乙比{a}:{b}，甲比乙多{abs(pa-pb)}，各是多少？", f"甲{pa}，乙{pb}"),
            ("A的2/3等于B的3/4，A:B是多少？", "9:8"),
        ]
        return random.choice(variants)


@register("ratio_proportion")
def ratio_proportion(difficulty: int, grade: int):
    """比例应用 - 结构变体"""
    if difficulty <= 2:
        unit = random.randint(3, 15)
        n1, n2 = random.randint(2, 6), random.randint(7, 15)
        dist3 = random.randint(30, 60) * 3
        variants = [
            (f"{n1}本书重{unit*n1}克，{n2}本重多少？（正比例）", f"{unit*n2} 克"),
            (f"3小时走{dist3}千米，5小时走多少？（正比例）", f"{dist3//3*5} 千米"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        scale = random.choice([50000, 100000, 200000, 500000])
        map_cm = random.randint(2, 12)
        real_km = map_cm * scale / 100000
        w1, d1 = random.randint(4, 8), random.randint(10, 20)
        w2 = w1 + random.randint(2, 4)
        tw = w1 * d1
        while tw % w2 != 0:
            w2 += 1
        d2 = tw // w2
        variants = [
            (f"比例尺1:{scale}，图上{map_cm}cm，实际多少千米？", f"{real_km:.0f}千米" if real_km == int(real_km) else f"{real_km:.1f}千米"),
            (f"{w1}人{d1}天完成，增加到{w2}人几天完成？（反比例）", f"{d2} 天"),
        ]
        return random.choice(variants)
    else:
        a_t, b_t = random.randint(20, 40), random.randint(10, 25)
        a_turns = random.randint(2, 5)
        b_turns = a_t * a_turns / b_t
        ratio_w = random.randint(50, 200)
        total = random.randint(200, 500)
        while total % (1 + ratio_w) != 0:
            total += 1
        drug = total // (1 + ratio_w)
        variants = [
            (f"齿轮A有{a_t}齿B有{b_t}齿，A转{a_turns}圈B转几圈？", f"{b_turns:.1f}圈" if b_turns != int(b_turns) else f"{int(b_turns)}圈"),
            (f"药和水质量比1:{ratio_w}，配{total}克药水需药多少？", f"{drug} 克"),
        ]
        return random.choice(variants)


@register("ratio_percent")
def ratio_percent(difficulty: int, grade: int):
    """百分数应用 - 结构变体"""
    if difficulty <= 2:
        price = random.randint(50, 500)
        discount = random.choice([70, 75, 80, 85, 90])
        d_name = {70:"七",75:"七五",80:"八",85:"八五",90:"九"}[discount]
        part = random.randint(20, 80)
        whole = random.randint(100, 400)
        variants = [
            (f"原价{price}元，打{d_name}折，现价多少？", f"{price*discount//100} 元"),
            (f"{part}是{whole}的百分之几？", f"{part/whole*100:.1f}%"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        p = random.randint(1000, 10000)
        r = random.choice([2.25, 2.75, 3.0, 3.25])
        y = random.randint(1, 3)
        income = random.randint(5000, 50000)
        tax_rate = random.choice([3, 5, 10])
        last = random.randint(100, 500)
        growth = random.randint(10, 30)
        variants = [
            (f"存{p}元，年利率{r}%，{y}年后利息多少？", f"{p*r/100*y:.2f} 元"),
            (f"营业额{income}元，税率{tax_rate}%，缴税多少？", f"{income*tax_rate//100} 元"),
            (f"去年产量{last}吨，今年增产{growth}%，今年多少？", f"{last*(100+growth)//100} 吨"),
        ]
        return random.choice(variants)
    else:
        price = random.randint(100, 500)
        up = random.randint(10, 30)
        down = random.randint(10, 30)
        final = price * (1 + up/100) * (1 - down/100)
        change = (final - price) / price * 100
        rate2 = random.choice([10, 20, 25, 50])
        orig = random.randint(100, 500)
        final2 = orig * (100 - rate2) // 100
        a_val = random.randint(50, 150)
        b_val = random.randint(50, 150)
        pct_more = round(abs(a_val-b_val) / min(a_val,b_val) * 100, 1)
        variants = [
            (f"原价{price}元，先涨{up}%再降{down}%，现价多少？涨了还是跌了？", f"现价{final:.2f}元，{'涨' if change>0 else '跌'}了{abs(change):.2f}%"),
            (f"降价{rate2}%后是{final2}元，原价多少？", f"{orig} 元"),
            (f"甲{a_val}乙{b_val}，多的比少的多百分之几？", f"{pct_more}%"),
        ]
        return random.choice(variants)


# ═══════════════════════════════════════════════════════════
# 四、应用题（9种）
# ═══════════════════════════════════════════════════════════

@register("app_travel")
def app_travel(difficulty: int, grade: int):
    """行程问题 - 结构变体"""
    if difficulty <= 2:
        v, t = random.randint(30, 80), random.randint(2, 8)
        variants = [
            (f"时速{v}千米，行{t}小时，路程多少？", f"{v*t} 千米"),
            (f"路程{v*t}千米，时速{v}千米，行几小时？", f"{t} 小时"),
            (f"路程{v*t}千米，{t}小时行完，时速多少？", f"{v} 千米/时"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        v1, v2 = random.randint(40, 80), random.randint(40, 80)
        t = random.randint(2, 6)
        dist = (v1 + v2) * t
        variants = [
            (f"甲乙相向而行，甲速{v1}乙速{v2}，{t}小时相遇，两地相距多少？", f"{dist} 千米"),
            (f"相距{dist}千米，甲速{v1}乙速{v2}相向而行，几小时相遇？", f"{t} 小时"),
            (f"甲速{v1}乙速{v2}同向而行，甲在乙后{dist//t*(v1-v2)//(v1-v2)}千米，几小时追上？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            gap = (v1 - v2) * random.randint(2, 5)
            catch = gap // (v1 - v2)
            return f"甲速{v1}乙速{v2}同向，甲在乙后{gap}千米，几小时追上？", f"{catch} 小时"
        return q, a
    else:
        v1 = random.randint(50, 80)
        v2 = random.randint(30, v1 - 10)
        variants = [
            lambda: _travel_round_trip(v1, v2),
            lambda: _travel_circular(v1, v2),
            lambda: _travel_bridge(v1),
            lambda: _travel_avg_speed(),
        ]
        return random.choice(variants)()

def _travel_round_trip(v1, v2):
    """往返平均速度：总路程÷总时间（提示学生不是速度算术平均）"""
    dist = random.randint(100, 300)
    t_go = dist / v1
    t_back = dist / v2
    avg = 2 * dist / (t_go + t_back)
    return f"去时时速{v1}千米，回时时速{v2}千米，往返平均速度是多少？", f"{avg:.1f} 千米/时（不是简单平均！）"

def _travel_circular(v1, v2):
    """环形跑道反向相遇：周长÷速度和（凑整除保整数分钟）"""
    circumference = random.randint(200, 600)
    while circumference % (v1 + v2) != 0:
        circumference += 10
    t = circumference // (v1 + v2)
    return f"环形跑道周长{circumference}米，甲速{v1}米/分乙速{v2}米/分同时同地反向跑，几分钟首次相遇？", f"{t} 分钟"

def _travel_bridge(v1):
    """火车过桥：总路程=车长+桥长，再换算时速→秒"""
    train_len = random.randint(100, 300)
    bridge_len = random.randint(500, 1500)
    speed_ms = v1 * 1000 / 3600
    time = (train_len + bridge_len) / speed_ms
    return f"火车长{train_len}米，桥长{bridge_len}米，时速{v1}千米，完全过桥需几秒？", f"约{time:.1f} 秒"

def _travel_avg_speed():
    """分段平均速度：总路程÷总时间"""
    d1 = random.randint(60, 120)
    d2 = random.randint(60, 120)
    v1 = random.randint(30, 60)
    v2 = random.randint(30, 60)
    total_d = d1 + d2
    total_t = d1/v1 + d2/v2
    avg = total_d / total_t
    return f"前{d1}千米时速{v1}，后{d2}千米时速{v2}，全程平均速度？", f"{avg:.1f} 千米/时"


@register("app_work")
def app_work(difficulty: int, grade: int):
    """工程问题 - 结构变体"""
    if difficulty <= 2:
        da = random.randint(6, 20)
        db = random.randint(6, 20)
        fa, fb = Fraction(1, da), Fraction(1, db)
        together = 1 / (fa + fb)
        s = f"{together.numerator}/{together.denominator}" if together.denominator != 1 else str(together.numerator)
        variants = [
            (f"甲独做{da}天，乙独做{db}天，合作几天？", f"{s} 天"),
            (f"甲独做{da}天，甲每天完成几分之几？", f"1/{da}"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        da = random.randint(10, 20)
        db = random.randint(10, 20)
        work_days = random.randint(2, 5)
        fb = Fraction(1, db)
        done = fb * work_days
        remain = 1 - done
        fa = Fraction(1, da)
        need = remain / (fa + fb)
        s = f"{need.numerator}/{need.denominator}" if need.denominator != 1 else str(need.numerator)
        variants = [
            (f"甲独做{da}天乙独做{db}天，乙先做{work_days}天后合作，还需几天？", f"{s} 天"),
            (f"甲独做{da}天乙独做{db}天，甲效率比乙高几分之几？", f"{str((fa-fb)/fb)}"),
        ]
        return random.choice(variants)
    else:
        da = random.choice([12, 15, 18, 20, 24])
        db = random.choice([12, 15, 18, 20, 24])
        dc = random.choice([12, 15, 18, 20, 24])
        fa, fb, fc = Fraction(1, da), Fraction(1, db), Fraction(1, dc)
        cycle = fa + fb + fc
        total_days = float(1 / cycle * 3)
        variants = [
            (f"甲{da}天乙{db}天丙{dc}天，按甲乙丙轮流各做一天，约几天完成？", f"约{total_days:.1f}天"),
            (f"甲{da}天乙{db}天，合作中途甲休息了2天，共用了几天？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            # 甲休息2天 = 乙独做2天 + 合作
            done_by_b = fb * 2
            remain = 1 - done_by_b
            coop_days = float(remain / (fa + fb))
            total = 2 + coop_days
            return f"甲{da}天乙{db}天合作，中途甲休息2天（乙继续），共几天完成？", f"约{total:.1f}天"
        return q, a


@register("app_concentration")
def app_concentration(difficulty: int, grade: int):
    """浓度问题 - 结构变体"""
    if difficulty <= 2:
        sol = random.randint(100, 500)
        rate = random.randint(5, 30)
        variants = [
            (f"{sol}克盐水浓度{rate}%，含盐多少？", f"{sol*rate//100} 克"),
            (f"盐{sol*rate//100}克配成{rate}%盐水，盐水多少克？", f"{sol} 克"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        s1, r1 = random.randint(100, 300), random.randint(10, 20)
        s2, r2 = random.randint(100, 300), random.randint(25, 40)
        new_rate = round((s1*r1/100 + s2*r2/100) / (s1+s2) * 100, 1)
        sol = random.randint(200, 500)
        rate = random.randint(10, 20)
        target = rate + random.randint(5, 15)
        solute = sol * rate / 100
        evaporate = sol - solute / (target / 100)
        variants = [
            (f"{s1}克{r1}%盐水与{s2}克{r2}%盐水混合，浓度多少？", f"{new_rate}%"),
            (f"{sol}克{rate}%盐水蒸发水使浓度变{target}%，蒸发多少克？", f"{evaporate:.1f}克" if evaporate != int(evaporate) else f"{int(evaporate)}克"),
        ]
        return random.choice(variants)
    else:
        sol = random.randint(200, 400)
        rate = random.randint(15, 25)
        add_salt = random.randint(20, 60)
        new_solute = sol * rate / 100 + add_salt
        new_rate = round(new_solute / (sol + add_salt) * 100, 1)
        variants = [
            (f"{sol}克{rate}%盐水加{add_salt}克盐，新浓度多少？", f"{new_rate}%"),
            (f"{sol}克{rate}%盐水要变成{rate+10}%，需加盐多少克？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            target = rate + 10
            solute = sol * rate / 100
            # solute + x = (sol + x) * target/100
            x = (target * sol / 100 - solute) / (1 - target / 100)
            return f"{sol}克{rate}%盐水要变成{target}%，需加盐多少克？", f"{x:.1f} 克"
        return q, a


@register("app_profit")
def app_profit(difficulty: int, grade: int):
    """利润与折扣 - 结构变体"""
    if difficulty <= 2:
        cost = random.randint(50, 200)
        rate = random.randint(20, 50)
        variants = [
            (f"进价{cost}元，利润率{rate}%，售价多少？", f"{cost*(100+rate)//100} 元"),
            (f"售价{cost*(100+rate)//100}元，进价{cost}元，利润率多少？", f"{rate}%"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        cost = random.randint(100, 500)
        markup = random.randint(30, 60)
        discount = random.choice([80, 85, 90])
        marked = cost * (100 + markup) // 100
        sell = marked * discount // 100
        real_rate = round((sell - cost) / cost * 100, 1)
        d_name = {80:"八",85:"八五",90:"九"}[discount]
        variants = [
            (f"进价{cost}元加价{markup}%标价，打{d_name}折卖，实际利润率？", f"{real_rate}%"),
            (f"打{d_name}折后卖{sell}元，标价是多少？", f"{marked} 元"),
        ]
        return random.choice(variants)
    else:
        cost = random.randint(100, 300)
        total = random.randint(50, 150)
        pr = random.randint(30, 50)
        sell1 = int(total * 0.6)
        sell2 = total - sell1
        discount = random.choice([70, 75, 80])
        price1 = cost * (100 + pr) // 100
        price2 = price1 * discount // 100
        revenue = sell1 * price1 + sell2 * price2
        profit = revenue - total * cost
        d_name = {70:"七",75:"七五",80:"八"}[discount]
        variants = [
            (f"进{total}件每件{cost}元，{pr}%利润率定价售{sell1}件，余下{d_name}折售完，总利润？", f"{profit} 元"),
            (f"两种方案：A全部{pr}%利润出售；B先售60%再{d_name}折清仓。哪种利润高？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            plan_a = total * cost * pr // 100
            return f"进{total}件每件{cost}元。方案A全部加{pr}%出售；方案B售60%后{d_name}折清仓。哪种利润高？", f"A利润{plan_a}元，B利润{profit}元，{'A' if plan_a > profit else 'B'}高"
        return q, a


@register("app_fraction")
def app_fraction(difficulty: int, grade: int):
    """分数应用题 - 结构变体"""
    if difficulty <= 2:
        total = random.choice([60, 80, 100, 120, 150, 200])
        n, d = random.choice([(1, 3), (1, 4), (2, 5), (3, 8)])
        while total % d != 0:
            total += 10
        part = total * n // d
        variants = [
            (f"一袋米{total}千克，吃了{n}/{d}，吃了多少？剩多少？", f"吃了{part}千克，剩{total-part}千克"),
            (f"{total}的{n}/{d}是多少？", str(part)),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        total = random.choice([120, 150, 180, 200, 240, 300])
        f1 = random.choice([(1, 4), (1, 5), (1, 6)])
        f2 = random.choice([(1, 3), (2, 5), (3, 8)])
        p1 = total * f1[0] // f1[1]
        p2 = total * f2[0] // f2[1]
        variants = [
            (f"书共{total}页，第一天看{f1[0]}/{f1[1]}，第二天看{f2[0]}/{f2[1]}，剩多少页？", f"{total-p1-p2} 页"),
            (f"一根绳用去{f1[0]}/{f1[1]}后又用去{f2[0]}/{f2[1]}米，共用去多少？（绳长{total}米）", f"{p1+f2[0]/f2[1]:.2f} 米"),
        ]
        return random.choice(variants)
    else:
        a = random.randint(60, 150)
        fn, fd = random.choice([(1, 4), (1, 5), (2, 5), (1, 3)])
        b = a + a * fn // fd
        variants = [
            (f"甲有{a}元，乙比甲多{fn}/{fd}，乙有多少？共多少？", f"乙{b}元，共{a+b}元"),
            (f"甲比乙少{fn}/{fd}，甲有{a}元，乙有多少？", None),
        ]
        q, a2 = random.choice(variants)
        if a2 is None:
            # 甲 = 乙 * (1 - fn/fd)
            b_val = a * fd // (fd - fn)
            return f"甲比乙少{fn}/{fd}，甲有{a}元，乙有多少？", f"{b_val} 元"
        return q, a2


@register("app_chicken_rabbit")
def app_chicken_rabbit(difficulty: int, grade: int):
    """鸡兔同笼 - 结构变体"""
    if difficulty <= 2:
        c = random.randint(5, 20)
        r = random.randint(3, 15)
        variants = [
            (f"鸡兔同笼，{c+r}个头{c*2+r*4}条腿，各几只？", f"鸡{c}只，兔{r}只"),
            (f"鸡兔同笼，兔比鸡多{r-c if r>c else 0}只，共{c*2+r*4}条腿，各几只？", f"鸡{c}只，兔{r}只") if r > c else (f"鸡兔同笼，{c+r}个头{c*2+r*4}条腿，各几只？", f"鸡{c}只，兔{r}只"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        bikes = random.randint(5, 15)
        trikes = random.randint(3, 10)
        total_q = 20
        score_r, score_w = 5, 2
        x = random.randint(12, 18)
        total_score = score_r * x - score_w * (total_q - x)
        variants = [
            (f"自行车三轮车共{bikes+trikes}辆，{bikes*2+trikes*3}个轮子，各几辆？", f"自行车{bikes}辆，三轮车{trikes}辆"),
            (f"竞赛{total_q}题，对得{score_r}分错扣{score_w}分，得{total_score}分，对几题？", f"对{x}题，错{total_q-x}题"),
        ]
        return random.choice(variants)
    else:
        # 三动物 / 假设法
        c = random.randint(5, 10)
        r = random.randint(3, 8)
        s = random.randint(2, 5)  # 蜘蛛8条腿
        legs = c*2 + r*4 + s*8
        heads = c + r + s
        variants = [
            (f"鸡兔蜘蛛共{heads}只，{legs}条腿，蜘蛛比兔少1只，各几只？", f"鸡{c}只，兔{r}只，蜘蛛{s}只" if r == s+1 else f"需列方程组求解"),
            (f"鸡兔同笼共{c+r}头{c*2+r*4}腿。用假设法：假设全是鸡，会怎样？", f"假设全鸡则{(c+r)*2}条腿，少了{c*2+r*4-(c+r)*2}条，每只兔多2条，所以兔={(c*2+r*4-(c+r)*2)//2}只"),
        ]
        # 简化：用标准变式
        gap = random.randint(2, 6)
        total_heads = random.randint(15, 35)
        # 兔比鸡多gap只
        r2 = (total_heads + gap) // 2
        c2 = total_heads - r2
        if r2 - c2 != gap or c2 <= 0:
            c2, r2 = 10, 10 + gap
            total_heads = c2 + r2
        legs2 = c2 * 2 + r2 * 4
        return f"鸡兔同笼共{total_heads}头{legs2}腿，兔比鸡多几只？", f"兔{r2}只鸡{c2}只，兔比鸡多{gap}只"


@register("app_tree_planting")
def app_tree_planting(difficulty: int, grade: int):
    """植树问题 - 结构变体"""
    if difficulty <= 2:
        interval = random.randint(3, 8)
        n = random.randint(5, 20)
        length = interval * n
        variants = [
            (f"路长{length}米，每隔{interval}米种一棵（两端都种），几棵？", f"{n+1} 棵"),
            (f"路长{length}米，每隔{interval}米种一棵（只种一端），几棵？", f"{n} 棵"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        interval = random.randint(3, 6)
        count = random.randint(8, 20)
        length = interval * count
        variants = [
            (f"圆形花坛周长{length}米，每隔{interval}米种一棵，几棵？", f"{count} 棵（环形=间隔数）"),
            (f"路两边都种树，路长{length}米每隔{interval}米一棵（两端种），共几棵？", f"{(count+1)*2} 棵"),
        ]
        return random.choice(variants)
    else:
        pieces = random.randint(5, 9)
        time_per = random.randint(2, 4)
        floors = random.randint(4, 8)
        steps = random.randint(12, 20)
        variants = [
            (f"锯木头成{pieces}段，每锯一次{time_per}分钟，共几分钟？", f"{(pieces-1)*time_per} 分钟"),
            (f"从1楼到{floors}楼，每层{steps}级台阶，共走几级？", f"{(floors-1)*steps} 级"),
            (f"时钟3点敲3下用2秒，6点敲6下用几秒？", "10秒（5个间隔）"),
        ]
        return random.choice(variants)


@register("app_sum_difference")
def app_sum_difference(difficulty: int, grade: int):
    """和差与和倍差倍 - 结构变体"""
    if difficulty <= 2:
        big = random.randint(20, 80)
        small = random.randint(10, big - 1)
        variants = [
            (f"两数和{big+small}，差{big-small}，各是多少？", f"大数{big}，小数{small}"),
            (f"甲乙共{big+small}，甲比乙多{big-small}，各多少？", f"甲{big}，乙{small}"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        small = random.randint(10, 40)
        m = random.randint(2, 5)
        variants = [
            (f"甲乙和{small*(m+1)}，甲是乙的{m}倍，各多少？", f"乙{small}，甲{small*m}"),
            (f"甲乙差{small*(m-1)}，甲是乙的{m}倍，各多少？", f"乙{small}，甲{small*m}"),
        ]
        return random.choice(variants)
    else:
        # 三人 / 年龄
        a = random.randint(5, 15)
        b = a + random.randint(2, 5)
        c = b + random.randint(2, 5)
        total = a + b + c
        variants = [
            (f"三人年龄和{total}，乙比甲大{b-a}岁，丙比乙大{c-b}岁，各几岁？", f"甲{a}，乙{b}，丙{c}"),
            (f"甲乙丙和{total}，甲是乙的2倍，丙比乙多{c-b}，各多少？", f"乙{a}，甲{a*2}，丙{a*2+c-b}" if a*2+a+a*2+c-b == total else f"甲{b*2}，乙{b}，丙{c}"),
        ]
        # 用确定性版本
        x = random.randint(8, 20)
        return f"甲乙丙和{x*6}，甲是乙的2倍，丙是乙的3倍，各多少？", f"乙{x}，甲{x*2}，丙{x*3}"


@register("app_proportional_dist")
def app_proportional_dist(difficulty: int, grade: int):
    """按比例分配 - 结构变体"""
    if difficulty <= 2:
        r1, r2 = random.randint(2, 5), random.randint(2, 5)
        unit = random.randint(10, 50)
        total = (r1 + r2) * unit
        variants = [
            (f"把{total}按{r1}:{r2}分给甲乙，各多少？", f"甲{r1*unit}，乙{r2*unit}"),
            (f"甲乙按{r1}:{r2}分，甲得{r1*unit}，总共多少？", f"{total}"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        r1, r2, r3 = random.randint(2, 4), random.randint(2, 4), random.randint(2, 4)
        unit = random.randint(10, 30)
        total = (r1 + r2 + r3) * unit
        variants = [
            (f"把{total}本图书按{r1}:{r2}:{r3}分给四五六年级，各多少？", f"四年级{r1*unit}，五年级{r2*unit}，六年级{r3*unit}"),
            (f"三角形三角度数比{r1}:{r2}:{r3}，各多少度？", f"{180*r1//(r1+r2+r3)}\u00b0、{180*r2//(r1+r2+r3)}\u00b0、{180*r3//(r1+r2+r3)}\u00b0"),
        ]
        return random.choice(variants)
    else:
        total_area = random.choice([120, 180, 240, 360])
        unit = total_area // 6
        variants = [
            (f"{total_area}m\u00b2地按3:2:1种水稻小麦蔬菜，各多少？水稻比蔬菜多多少？", f"水稻{3*unit}m\u00b2，小麦{2*unit}m\u00b2，蔬菜{unit}m\u00b2，多{2*unit}m\u00b2"),
            (f"甲乙丙投资比3:4:5，利润{total_area}万元按比例分，各得多少？", f"甲{3*unit}万，乙{4*unit}万，丙{5*unit}万"),
        ]
        return random.choice(variants)


# ═══════════════════════════════════════════════════════════
# 五、统计与概率（3种）
# ═══════════════════════════════════════════════════════════

@register("stat_average")
def stat_average(difficulty: int, grade: int):
    """平均数 - 结构变体"""
    if difficulty <= 2:
        nums = [random.randint(60, 100) for _ in range(5)]
        avg = sum(nums) / 5
        variants = [
            (f"5次成绩{'、'.join(map(str,nums))}分，平均分？", f"{avg:.1f}分" if avg != int(avg) else f"{int(avg)}分"),
            (f"4个数平均数{random.randint(70,90)}，加入一个数后平均数变为{random.randint(70,90)}，新加的数是多少？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            avg4 = random.randint(70, 90)
            avg5 = random.randint(70, 90)
            new_num = avg5 * 5 - avg4 * 4
            return f"4个数平均数{avg4}，加入一个数后平均数变{avg5}，新加的数是多少？", f"{new_num}"
        return q, a
    elif difficulty <= 4:
        n1, avg1 = random.randint(5, 15), random.randint(70, 90)
        n2, avg2 = random.randint(5, 15), random.randint(70, 90)
        total_avg = (n1*avg1 + n2*avg2) / (n1+n2)
        variants = [
            (f"甲组{n1}人均{avg1}分，乙组{n2}人均{avg2}分，合起来平均？", f"{total_avg:.1f}分"),
            (f"前3次平均{avg1}分，要使4次平均达到{avg2}分，第4次至少多少分？", f"{avg2*4-avg1*3}分"),
        ]
        return random.choice(variants)
    else:
        nums = sorted([random.randint(70, 100) for _ in range(7)])
        avg_all = sum(nums) / 7
        avg_trim = sum(nums[1:-1]) / 5
        variants = [
            (f"7位评委打分{'、'.join(map(str,nums))}，去掉最高最低后平均？", f"全部平均{avg_all:.1f}，去掉后{avg_trim:.1f}"),
            (f"5个数平均数{random.randint(60,80)}，去掉一个后平均数变大还是变小？一定吗？", "不一定，取决于去掉的数比平均数大还是小"),
        ]
        return random.choice(variants)


@register("stat_probability")
def stat_probability(difficulty: int, grade: int):
    """可能性与概率 - 结构变体"""
    if difficulty <= 2:
        red, blue = random.randint(2, 6), random.randint(2, 6)
        total = red + blue
        variants = [
            (f"袋中{red}红{blue}蓝，摸到红球的可能性？", f"{red}/{total}"),
            (f"掷骰子，掷到偶数的可能性？", "3/6 = 1/2"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        red, blue, green = random.randint(2, 5), random.randint(2, 5), random.randint(1, 3)
        total = red + blue + green
        variants = [
            (f"袋中{red}红{blue}蓝{green}绿，摸到不是绿球的可能性？", f"{red+blue}/{total}"),
            (f"同时掷两枚硬币，都是正面的可能性？", "1/4"),
        ]
        return random.choice(variants)
    else:
        variants = [
            (f"袋中红黄蓝各若干个共{random.randint(8,15)}个，至少摸几个保证有2个同色？", "4个（3种颜色+1）"),
            (f"掷两枚骰子，点数和为7的可能性是多少？", "6/36 = 1/6"),
            (f"从1-10中随机取一个，是质数的可能性？", "4/10 = 2/5（2,3,5,7）"),
        ]
        return random.choice(variants)


@register("stat_chart")
def stat_chart(difficulty: int, grade: int):
    """统计图读图 - 结构变体"""
    if difficulty <= 2:
        items = ["周一", "周二", "周三", "周四", "周五"]
        values = [random.randint(20, 100) for _ in range(5)]
        max_idx = values.index(max(values))
        variants = [
            (f"5天营业额{'、'.join(f'{items[i]}:{values[i]}万' for i in range(5))}，哪天最高？平均多少？", f"{items[max_idx]}最高；平均{sum(values)/5:.1f}万"),
            (f"5天营业额{'、'.join(f'{items[i]}:{values[i]}万' for i in range(5))}，中位数是多少？", f"{sorted(values)[2]}万"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        total_p = random.choice([200, 300, 400, 500])
        pct_a = random.randint(30, 50)
        pct_b = random.randint(20, 35)
        pct_c = 100 - pct_a - pct_b
        num_a = total_p * pct_a // 100
        num_b = total_p * pct_b // 100
        num_c = total_p - num_a - num_b
        if num_b >= num_c:
            q2 = f"音乐比美术多多少人？"
            a2 = f"多{num_b-num_c}人"
        else:
            q2 = f"美术比音乐多多少人？"
            a2 = f"多{num_c-num_b}人"
        variants = [
            (f"{total_p}人参加活动：体育{pct_a}%音乐{pct_b}%美术{pct_c}%。体育多少人？{q2}", f"体育{num_a}人；{a2}"),
            (f"扇形图中体育占{pct_a}%，对应{num_a}人，总人数多少？", f"{total_p}人"),
        ]
        return random.choice(variants)
    else:
        months = ["1月", "2月", "3月", "4月", "5月", "6月"]
        base = random.randint(100, 300)
        values = [base + random.randint(-30, 50) for _ in range(6)]
        max_v, min_v = max(values), min(values)
        max_m = months[values.index(max_v)]
        min_m = months[values.index(min_v)]
        variants = [
            (f"上半年降水{'、'.join(f'{months[i]}:{values[i]}mm' for i in range(6))}，最多最少各是哪月？月均多少？", f"{max_m}最多{max_v}mm，{min_m}最少{min_v}mm，月均{sum(values)/6:.1f}mm"),
            (f"折线图显示销量从{values[0]}逐月变化到{values[-1]}，总体趋势是什么？增长了多少？", f"{'上升' if values[-1]>values[0] else '下降'}趋势，变化了{abs(values[-1]-values[0])}"),
        ]
        return random.choice(variants)


# ═══════════════════════════════════════════════════════════
# 六、逻辑与思维（4种）
# ═══════════════════════════════════════════════════════════

@register("logic_reasoning")
def logic_reasoning(difficulty: int, grade: int):
    """逻辑推理 - 结构变体"""
    if difficulty <= 2:
        names = ["小明", "小红", "小刚"]
        items = ["语文", "数学", "英语"]
        random.shuffle(items)
        variants = [
            (f"{names[0]}、{names[1]}、{names[2]}分别参加{items[0]}、{items[1]}、{items[2]}组。已知{names[0]}不参加{items[1]}，{names[1]}不参加{items[0]}也不参加{items[2]}。各参加什么？", f"{names[1]}参加{items[1]}，{names[0]}参加{items[0]}，{names[2]}参加{items[2]}"),
            (f"3个人排成一排，{names[0]}不站第一，{names[1]}不站第二，有几种排法？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            return "3人排队，甲不站第一乙不站第二，有几种排法？", "3种（列举排除）"
        return q, a
    elif difficulty <= 4:
        heads = random.randint(15, 40)
        legs = heads * 2 + random.randint(4, 40)
        while (legs - 2 * heads) % 2 != 0 or legs > heads * 4:
            legs += 1
        rabbits = (legs - 2 * heads) // 2
        chickens = heads - rabbits
        if chickens <= 0:
            chickens, rabbits = 10, 8
            heads, legs = 18, 52
        variants = [
            (f"鸡兔同笼{heads}头{legs}腿，各几只？", f"鸡{chickens}只，兔{rabbits}只"),
            (f"桌上有1元和5角硬币共{random.randint(15,30)}枚，总值{random.randint(10,25)}元，各几枚？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            n5 = random.randint(5, 15)
            n10 = random.randint(5, 15)
            total_n = n5 + n10
            total_v = n5 * 5 + n10 * 10
            return f"5角和1元硬币共{total_n}枚，总值{total_v/10:.1f}元，各几枚？", f"5角{n5}枚，1元{n10}枚"
        return q, a
    else:
        variants = [
            ("甲说'乙在说谎'，乙说'丙在说谎'，丙说'甲乙都在说谎'。谁在说真话？", "乙说真话（假设法逐一验证）"),
            (f"把{random.randint(50,150)}分成{random.randint(5,10)}个不同自然数之和，最大的数最小是多少？", "用均分策略：先1+2+...+n，余量从大到小分配"),
            ("5个人考试，已知：甲不是第一，乙不是第二，丙不是第一也不是第五，丁不是第二，戊不是第三。谁可能是第一？", "丙或丁或戊（排除法）"),
        ]
        return random.choice(variants)


@register("logic_pattern")
def logic_pattern(difficulty: int, grade: int):
    """找规律 - 结构变体"""
    if difficulty <= 2:
        start = random.randint(1, 5)
        diff = random.randint(2, 7)
        seq = [start + diff * i for i in range(5)]
        variants = [
            (f"找规律：{'、'.join(map(str,seq))}、___、___", f"{seq[-1]+diff}、{seq[-1]+2*diff}"),
            (f"找规律：2、6、18、54、___", "162（公比3）"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        a, b = random.randint(1, 3), random.randint(2, 4)
        seq = [a, b]
        for _ in range(5):
            seq.append(seq[-1] + seq[-2])
        variants = [
            (f"找规律：{'、'.join(map(str,seq[:5]))}、___、___", f"{seq[5]}、{seq[6]}"),
            (f"找规律：1、4、9、16、25、___", "36（平方数列）"),
        ]
        return random.choice(variants)
    else:
        offset = random.randint(0, 2)
        seq = [(i + offset) ** 2 for i in range(1, 7)]
        variants = [
            (f"找规律：{'、'.join(map(str,seq[:5]))}、___", f"{seq[5]}"),
            (f"找规律：1、1、2、3、5、8、13、___、___", "21、34（斐波那契）"),
            (f"第100个三角形数（1+2+3+...+n）是多少？", "5050"),
        ]
        return random.choice(variants)


@register("logic_combinatorics")
def logic_combinatorics(difficulty: int, grade: int):
    """排列组合与计数 - 结构变体"""
    if difficulty <= 2:
        n = random.randint(3, 6)
        variants = [
            (f"{n}人互相握手，共握几次？", f"{n*(n-1)//2} 次"),
            (f"{n}支球队单循环赛，共几场？", f"{n*(n-1)//2} 场"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        n = random.randint(4, 6)
        k = random.randint(2, 3)
        result = math.factorial(n) // (math.factorial(k) * math.factorial(n-k))
        variants = [
            (f"从{n}人中选{k}人参赛，几种选法？", f"{result} 种"),
            (f"用0-9组成无重复数字的两位数，共几个？", "81个（十位9种\u00d7个位9种）"),
        ]
        return random.choice(variants)
    else:
        m, n = random.randint(3, 5), random.randint(3, 5)
        result = math.factorial(m+n-2) // (math.factorial(m-1) * math.factorial(n-1))
        variants = [
            (f"{m}\u00d7{n}方格从左上到右下（只向右或下），几种走法？", f"{result} 种"),
            (f"5本不同的书分给3人，每人至少1本，几种分法？", "150种"),
            (f"6人站一排，甲乙必须相邻，几种排法？", "240种（捆绑法：5!\u00d72）"),
        ]
        return random.choice(variants)


@register("logic_optimization")
def logic_optimization(difficulty: int, grade: int):
    """找次品与优化 - 结构变体"""
    if difficulty <= 2:
        n = random.choice([3, 9])
        times = 1 if n == 3 else 2
        variants = [
            (f"{n}个零件有1个次品（轻些），天平至少称几次？", f"至少{times}次"),
            (f"烙1个饼每面2分钟，烙3个饼至少几分钟？（每次烙2个）", "6分钟"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        cakes = random.choice([3, 5, 7])
        total_time = ((cakes * 2 + 1) // 2) * 2
        variants = [
            (f"烙{cakes}个饼，每次烙2个每面2分钟，至少几分钟？", f"至少{total_time}分钟"),
            (f"沏茶：洗壶1分、烧水8分、洗杯2分、拿茶叶1分、沏茶1分，最少几分钟？", "10分钟（烧水同时洗杯拿茶叶）"),
        ]
        return random.choice(variants)
    else:
        variants = [
            ("27个球有1个次品（重些），天平至少称几次？方法？", "3次，每次分3组(9,9,9)\u2192(3,3,3)\u2192(1,1,1)"),
            ("甲乙丙丁过河分别需1、2、5、8分钟，每次最多2人且需1人回来送船，全部过河最少几分钟？", "15分钟"),
            ("用平底锅烙饼，每锅2个每面3分钟，烙11个饼至少几分钟？", "33分钟（11\u00d72面\u00f72个/锅\u00d73分）"),
        ]
        return random.choice(variants)


# ═══════════════════════════════════════════════════════════
# 七、数与代数（4种）
# ═══════════════════════════════════════════════════════════

@register("number_gcd_lcm")
def number_gcd_lcm(difficulty: int, grade: int):
    """公因数公倍数 - 结构变体"""
    if difficulty <= 2:
        a, b = random.randint(6, 30), random.randint(6, 30)
        g = math.gcd(a, b)
        l = a * b // g
        variants = [
            (f"求{a}和{b}的最大公因数和最小公倍数。", f"最大公因数{g}，最小公倍数{l}"),
            (f"{a}和{b}是互质数吗？为什么？", f"{'是' if g==1 else '不是'}，最大公因数是{g}"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        a, b, c = random.randint(12, 48), random.randint(12, 48), random.randint(12, 48)
        g = math.gcd(math.gcd(a, b), c)
        l = a * b // math.gcd(a, b)
        l = l * c // math.gcd(l, c)
        variants = [
            (f"求{a}、{b}、{c}的最大公因数和最小公倍数。", f"最大公因数{g}，最小公倍数{l}"),
            (f"甲每{random.choice([3,4,5])}天去一次图书馆，乙每{random.choice([4,5,6])}天去一次，今天同时去了，至少几天后再同时去？", None),
        ]
        q, a2 = random.choice(variants)
        if a2 is None:
            da = random.choice([3, 4, 5])
            db2 = random.choice([4, 5, 6])
            lcm = da * db2 // math.gcd(da, db2)
            return f"甲每{da}天去图书馆，乙每{db2}天去，今天同时去了，至少几天后再同时去？", f"{lcm} 天后"
        return q, a2
    else:
        a = random.choice([24, 36, 48, 60, 72])
        b = random.choice([18, 30, 42, 54, 66])
        g = math.gcd(a, b)
        count = (a // g) * (b // g)
        variants = [
            (f"长{a}cm宽{b}cm的纸裁成最大正方形无剩余，边长多少？裁几块？", f"边长{g}cm，裁{count}块"),
            (f"一排路灯从起点到终点共{random.randint(20,50)}盏，间距相等。改为间距{random.choice([6,8,10])}米后不用移动几盏？", None),
        ]
        q, a2 = random.choice(variants)
        if a2 is None:
            old_gap = random.choice([4, 5, 6])
            new_gap = random.choice([6, 8, 10])
            n = random.randint(20, 40)
            total_len = old_gap * (n - 1)
            lcm_gap = old_gap * new_gap // math.gcd(old_gap, new_gap)
            stay = total_len // lcm_gap + 1
            return f"路灯{n}盏间距{old_gap}米，改为间距{new_gap}米，不用移动的有几盏？", f"{stay} 盏（在公倍数位置）"
        return q, a2


@register("number_negative")
def number_negative(difficulty: int, grade: int):
    """负数与数轴 - 结构变体"""
    if difficulty <= 2:
        a = random.randint(-20, -1)
        b = random.randint(1, 20)
        variants = [
            (f"计算：({a}) + {b} = ", str(a + b)),
            (f"-5的相反数是多少？绝对值呢？", "相反数5，绝对值5"),
            (f"数轴上-3和5之间的距离是多少？", "8"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        a = random.randint(-20, -5)
        b = random.randint(-15, -1)
        op = random.choice(["+", "-"])
        if op == "+":
            ans = a + b
            expr = f"({a}) + ({b})"
        else:
            ans = a - b
            expr = f"({a}) - ({b})"
        variants = [
            (f"计算：{expr} = ", str(ans)),
            (f"数轴上A在-7，B在3，AB中点表示几？", "-2"),
        ]
        return random.choice(variants)
    else:
        a = random.randint(-10, -2)
        b = random.randint(2, 10)
        c = random.randint(-10, -2)
        ans = a * b + c
        variants = [
            (f"计算：({a}) \u00d7 {b} + ({c}) = ", str(ans)),
            (f"|x-3| + |x+2| 的最小值是多少？x取什么范围时取到？", "最小值5，-2\u2264x\u22643时取到"),
        ]
        return random.choice(variants)


@register("number_divisibility")
def number_divisibility(difficulty: int, grade: int):
    """整除与质因数 - 结构变体"""
    if difficulty <= 2:
        n = random.randint(10, 200)
        divs = []
        if n % 2 == 0: divs.append("2")
        if sum(int(d) for d in str(n)) % 3 == 0: divs.append("3")
        if n % 5 == 0: divs.append("5")
        ans = "、".join(divs) if divs else "都不能整除"
        variants = [
            (f"{n}能被2、3、5中的哪些整除？", ans),
            (f"20以内质数有哪些？", "2、3、5、7、11、13、17、19"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        composites = [12, 18, 24, 30, 36, 42, 48, 56, 60, 72, 84, 90]
        n = random.choice(composites)
        factors = _prime_factorize(n)
        factor_str = "\u00d7".join(map(str, factors))
        variants = [
            (f"把{n}分解质因数。", f"{n} = {factor_str}"),
            (f"50以内既是3的倍数又是5的倍数的数有哪些？", "15、30、45"),
        ]
        return random.choice(variants)
    else:
        low = random.randint(1, 3) * 30
        multiples = list(range(low, low + random.randint(3, 6) * 30 + 1, 30))
        variants = [
            (f"在{multiples[0]-20}到{multiples[-1]+20}之间，同时是2、3、5倍数的数有哪些？", f"{'、'.join(map(str,multiples))}（共{len(multiples)}个）"),
            (f"一个三位数，百位是2，个位是5，且能被3整除，这样的数有哪些？", "225、255、285（十位使数字和为3的倍数）"),
        ]
        return random.choice(variants)


def _prime_factorize(n: int) -> list:
    """质因数分解（试除法，d 从 2 递增到 √n）。

    供 number_gcd_lcm 等题型求最大公约数/最小公倍数用；返回质因子列表（含重复）。
    """
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors


@register("number_conversion")
def number_conversion(difficulty: int, grade: int):
    """数的互化与比较 - 结构变体"""
    if difficulty <= 2:
        pairs = [(1, 2), (1, 4), (3, 4), (1, 5), (2, 5), (1, 8), (3, 8)]
        n, d = random.choice(pairs)
        variants = [
            (f"把{n}/{d}化成小数。", f"{n/d}"),
            (f"把0.{random.choice(['5','25','75','125','6'])}化成分数。", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            dec_map = {"5": "1/2", "25": "1/4", "75": "3/4", "125": "1/8", "6": "3/5"}
            dec = random.choice(["5", "25", "75", "125", "6"])
            return f"把0.{dec}化成分数。", dec_map[dec]
        return q, a
    elif difficulty <= 4:
        dec_choices = [0.35, 0.75, 0.125, 0.6, 0.875, 0.04]
        dec = random.choice(dec_choices)
        pct = dec * 100
        pct_str = f"{pct:.1f}%" if pct != int(pct) else f"{int(pct)}%"
        variants = [
            (f"把{dec}化成百分数。", pct_str),
            (f"把3/8化成小数和百分数。", "0.375 = 37.5%"),
        ]
        return random.choice(variants)
    else:
        nums_raw = [
            ("2/3", 2/3), ("0.6", 0.6), ("65%", 0.65),
            ("3/5", 3/5), ("0.58", 0.58), ("7/10", 0.7),
            ("3/4", 0.75), ("0.8", 0.8), ("5/8", 0.625),
        ]
        selected = random.sample(nums_raw, 4)
        sorted_sel = sorted(selected, key=lambda x: x[1])
        display = "、".join(s[0] for s in selected)
        answer = " < ".join(s[0] for s in sorted_sel)
        variants = [
            (f"把{display}从小到大排列。", answer),
            (f"在0.67、2/3、67%、0.6中，最大的是？最小的是？", "最大2/3\u22480.667（或67%=0.67最大），最小0.6"),
        ]
        return random.choice(variants)


# ═══════════════════════════════════════════════════════════
# 九、补充题型（8种）
# ═══════════════════════════════════════════════════════════

@register("number_operation_law")
def number_operation_law(difficulty: int, grade: int):
    """运算律辨认与填空"""
    if difficulty <= 2:
        a, b = random.randint(2, 50), random.randint(2, 50)
        c = random.randint(2, 30)
        variants = [
            (f"{a}+{b}={b}+{a}，运用了什么运算律？", "加法交换律"),
            (f"{a}×{b}={b}×{a}，运用了什么运算律？", "乘法交换律"),
            (f"({a}+{b})+{c}={a}+({b}+{c})，运用了什么运算律？", "加法结合律"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        a = random.choice([25, 125, 4, 8])
        b = random.choice([4, 8, 25, 125])
        c = random.randint(2, 20)
        variants = [
            (f"{a}×{b}×{c}怎样简便计算？运用了什么律？", f"{a}×{b}={a*b}，再×{c}={a*b*c}，乘法结合律"),
            (f"{a}×{c}+{b}×{c}怎样简便计算？", f"({a}+{b})×{c}={a+b}×{c}={ (a+b)*c }，乘法分配律"),
            (f"({a}+{random.randint(1,9)})×{b}怎样用分配律展开？", f"{a}×{b}+{random.randint(1,9)}×{b}"),
            (f"99×{random.randint(11,99)}怎样简便计算？", "99=100-1，用乘法分配律：100×n-n"),
        ]
        return random.choice(variants)
    else:
        n = random.randint(11, 99)
        variants = [
            (f"101×{n}怎样简便计算？结果是多少？", f"(100+1)×{n}=100×{n}+{n}={100*n+n}"),
            (f"{n}×99+{n}怎样简便计算？", f"{n}×(99+1)={n}×100={n*100}，乘法分配律逆用"),
            (f"25×32×125怎样简便计算？", "25×4×(8×125)=100×1000=100000，结合律拆分"),
            (f"56×101-56怎样简便计算？", f"56×(101-1)=56×100=5600，分配律逆用"),
        ]
        return random.choice(variants)


@register("geo_motion")
def geo_motion(difficulty: int, grade: int):
    """图形运动：对称、平移、旋转"""
    if difficulty <= 2:
        shapes = [
            ("长方形", 2), ("正方形", 4), ("等边三角形", 3),
            ("圆", "无数条"), ("等腰三角形", 1), ("平行四边形", 0),
        ]
        name, axes = random.choice(shapes)
        variants = [
            (f"{name}有几条对称轴？", f"{axes}条" if isinstance(axes, int) else axes),
            (f"下列图形中，是轴对称图形的是：平行四边形、等腰梯形、普通三角形？", "等腰梯形"),
            (f"字母\"H\"有几条对称轴？", "2条（水平1条+竖直1条）"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        dx = random.randint(2, 6)
        dy = random.randint(2, 6)
        deg = random.choice([90, 180, 270])
        direction = random.choice(["顺时针", "逆时针"])
        variants = [
            (f"将三角形向右平移{dx}格，再向下平移{dy}格，形状大小是否改变？", "不改变，平移不改变形状和大小"),
            (f"将图形绕点O{direction}旋转{deg}°，形状大小是否改变？", "不改变，旋转不改变形状和大小"),
            (f"钟面上分针从12转到3，旋转了多少度？方向？", "顺时针旋转90°"),
            (f"一个图形先向右平移3格，再向左平移3格，最终位置？", "回到原位"),
        ]
        return random.choice(variants)
    else:
        variants = [
            ("正方形绕中心旋转多少度后能与自身重合？共有几种？", "旋转90°即可重合，共4种位置(90°/180°/270°/360°)"),
            ("正六边形绕中心旋转，至少转多少度与自身重合？", "60°"),
            ("将△ABC绕点A顺时针旋转90°后，AB边与原来哪条边垂直？", "与原来的AC边垂直（旋转90°产生垂直关系）"),
            ("一个图案由基本图形经过平移得到，如何判断平移方向和距离？", "找对应点，连线方向即平移方向，格数即距离"),
        ]
        return random.choice(variants)


@register("stat_measure")
def stat_measure(difficulty: int, grade: int):
    """统计量选择：平均数/中位数/众数"""
    if difficulty <= 2:
        data = sorted([random.randint(60, 100) for _ in range(5)])
        avg = sum(data) / 5
        mid = data[2]
        variants = [
            (f"数据{data}的平均数是多少？", f"{avg:.1f}"),
            (f"数据{data}的中位数是多少？", f"{mid}"),
            (f"数据{data}的中位数是多少？（已排序）", f"{mid}"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        base = random.randint(70, 90)
        data = [base]*3 + [random.randint(60, 100) for _ in range(4)]
        random.shuffle(data)
        mode = base
        s_data = sorted(data)
        mid = (s_data[3] + s_data[4]) / 2
        avg = sum(data) / 7
        variants = [
            (f"数据{data}的众数是多少？", f"{mode}"),
            (f"数据{data}的中位数是多少？", f"{mid}"),
            (f"7个数据平均数{avg:.1f}，去掉最高最低后平均数会怎样变化？", "可能变大、变小或不变，取决于去掉的值"),
        ]
        return random.choice(variants)
    else:
        salary_low = [3000, 3000, 3500, 4000, 4000, 4500, 50000]
        avg_s = sum(salary_low) / 7
        mid_s = sorted(salary_low)[3]
        variants = [
            (f"7名员工月薪(元)：{salary_low}。用平均数还是中位数表示一般水平更合适？", f"中位数{mid_s}元更合适，平均数{avg_s:.0f}被极端值拉高"),
            ("演讲比赛7位评委打分，为什么要去掉最高分和最低分？", "减少极端值对平均数的影响，使结果更公平"),
            ("鞋店统计最畅销鞋号来决定进货，应关注平均数、中位数还是众数？", "众数（最畅销的鞋号）"),
        ]
        return random.choice(variants)


@register("number_large")
def number_large(difficulty: int, grade: int):
    """大数认识、读写、改写与近似数"""
    if difficulty <= 2:
        n = random.randint(10000, 99999999)
        variants = [
            (f"读出这个数：{n}", f"读作：{_read_number(n)}"),
            (f"{n}是几位数？最高位是什么位？", f"{len(str(n))}位数，最高位是{_place_name(len(str(n)))}"),
            (f"把{n}改写成用\"万\"作单位的数", f"{n/10000:.1f}万" if n % 10000 != 0 else f"{n//10000}万"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        n = random.randint(100000, 999999999)
        wan = round(n / 10000)
        yi = round(n / 100000000)
        variants = [
            (f"把{n}四舍五入到万位", f"≈{wan}万"),
            (f"把{n}改写成用\"万\"作单位的数", f"{n/10000:.1f}万" if n % 10000 != 0 else f"{n//10000}万"),
            (f"3050006000读作什么？", "三十亿五千万六千"),
            (f"由3个亿、5个万、6个千组成的数是多少？", "300056000"),
        ]
        return random.choice(variants)
    else:
        variants = [
            ("把399500000四舍五入到亿位", "≈4亿"),
            ("□里最大能填几？ 4□2000000≈4亿", "□最大填4（四舍五入后仍为4亿）"),
            ("□里最小能填几？ □85000000≈5亿", "□最小填5（五入后为5亿）"),
            ("一个数四舍五入到万位是30万，这个数最大是多少？最小是多少？", "最大304999，最小295000"),
        ]
        return random.choice(variants)


def _read_number(n: int) -> str:
    """简化读数"""
    s = str(n)
    if n >= 100000000:
        yi = n // 100000000
        rest = n % 100000000
        return f"{yi}亿{'零' if 0 < rest < 10000000 else ''}{rest if rest else ''}"
    elif n >= 10000:
        wan = n // 10000
        rest = n % 10000
        return f"{wan}万{'零' if 0 < rest < 1000 else ''}{rest if rest else ''}"
    return str(n)


def _place_name(digits: int) -> str:
    """整数位数 → 数位中文名（1→个、5→万、9→亿…），用于「最高位是什么位」类题目。"""
    names = {1:"个",2:"十",3:"百",4:"千",5:"万",6:"十万",7:"百万",8:"千万",9:"亿",10:"十亿"}
    return names.get(digits, f"第{digits}位")


@register("logic_pigeonhole")
def logic_pigeonhole(difficulty: int, grade: int):
    """抽屉原理（至少问题）"""
    if difficulty <= 2:
        n = random.randint(3, 6)
        variants = [
            (f"把{n+1}个苹果放进{n}个抽屉，至少有一个抽屉里有几个苹果？", "至少2个"),
            (f"{n}只鸽子飞进{n-1}个鸽笼，至少有一个鸽笼里有几只？", "至少2只"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        colors = random.randint(2, 4)
        n = random.randint(5, 15)
        at_least = n // colors + 1
        variants = [
            (f"袋中有红黄蓝{colors}种球各若干个，至少摸几个才能保证有2个同色？", f"{colors+1}个"),
            (f"把{n}本书放进{colors}个抽屉，至少有一个抽屉里有几本？", f"至少{at_least}本"),
            (f"全班{random.randint(30,45)}人，至少有几人生日在同一月份？", f"至少{random.randint(30,45)//12+1}人（抽屉原理：12个月）"),
        ]
        return random.choice(variants)
    else:
        variants = [
            ("从1~20中至少取几个数，才能保证其中必有两个数的差是5？", "11个（按差5配对：(1,6)(2,7)...(15,20)共10对+16~20无法配对的归入，取11个必有一对）"),
            ("一副扑克牌(54张)至少抽几张才能保证有4张同花色？", "15张（最坏：3×4花色+2王=14张，第15张必有4张同花色）"),
            ("任意5个整数中，必有3个数的和是3的倍数，为什么？", "按除以3余数分3类(抽屉)，5个数放入3类，必有一类≥2个或三类各≥1个，均可凑出3的倍数"),
        ]
        return random.choice(variants)


@register("logic_period")
def logic_period(difficulty: int, grade: int):
    """周期问题"""
    if difficulty <= 2:
        period = random.randint(3, 5)
        items = "○●△□★"[:period]
        n = random.randint(15, 40)
        pos = n % period
        ans_item = items[pos - 1] if pos != 0 else items[-1]
        variants = [
            (f"按\"{items}\"的规律重复排列，第{n}个是什么？", f"第{n}个是{ans_item}（周期{period}，{n}÷{period}={n//period}余{pos}）"),
            (f"一列数按2、0、2、6循环，第{n}个数是几？", f"周期4，{n}÷4余{n%4}，第{n}个是{'2026'[n%4-1] if n%4!=0 else '6'}"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        days = ["一","二","三","四","五","六","日"]
        start = random.randint(0, 6)
        offset = random.randint(20, 100)
        target = (start + offset) % 7
        variants = [
            (f"今天是星期{days[start]}，{offset}天后是星期几？", f"星期{days[target]}（{offset}÷7={offset//7}余{offset%7}）"),
            (f"2026年1月1日是星期四，2026年3月1日是星期几？", "星期四+59天，59÷7=8余3，星期日"),
            (f"按1、2、3、4、5、4、3、2循环，第{random.randint(30,80)}个数是几？", "周期8，用余数确定位置"),
        ]
        return random.choice(variants)
    else:
        n = random.randint(50, 200)
        variants = [
            (f"按1、1、2、3、5、8...（斐波那契）排列，第{n}个数除以3的余数有周期吗？", "余数序列周期为8（1,1,2,0,2,2,1,0循环）"),
            (f"一列数：1、3、5、7、9、1、3、5...周期为5，前{n}个数之和是多少？", f"每周期和=25，{n}÷5={n//5}余{n%5}，和={n//5*25}+前{n%5}项和"),
            ("2026年7月28日是星期二，2027年元旦是星期几？", "7月剩3天+8月31+9月30+10月31+11月30+12月31=156天，156÷7=22余2，星期四"),
        ]
        return random.choice(variants)


@register("app_surplus_deficit")
def app_surplus_deficit(difficulty: int, grade: int):
    """盈亏问题"""
    if difficulty <= 2:
        per1 = random.randint(3, 6)
        per2 = per1 + random.randint(1, 3)
        surplus = random.randint(5, 15)
        deficit = random.randint(5, 15)
        people = (surplus + deficit) // (per2 - per1)
        total = people * per1 + surplus
        variants = [
            (f"分糖果，每人{per1}颗多{surplus}颗，每人{per2}颗少{deficit}颗，几人几颗？",
             f"人数=({surplus}+{deficit})÷({per2}-{per1})={people}人，糖={total}颗"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        per1 = random.randint(4, 8)
        per2 = per1 + random.randint(2, 4)
        people = random.randint(8, 20)
        total = people * per1 + random.randint(5, 20)
        surplus = total - people * per1
        deficit = people * per2 - total
        variants = [
            (f"学生搬花盆，每人搬{per1}盆多{surplus}盆，每人搬{per2}盆少{deficit}盆，多少学生？",
             f"({surplus}+{deficit})÷({per2}-{per1})={people}人"),
            (f"租车出游，每车坐{per1}人多{surplus}人没座，每车坐{per2}人少{deficit}个空位，几辆车？",
             f"({surplus}+{deficit})÷({per2}-{per1})={people}辆"),
            (f"分铅笔，每人{per1}支多{surplus}支，每人{per2}支多{surplus - (per2-per1)*people}支，几人？",
             f"两次都多（盈盈），人数=({surplus}-{surplus-(per2-per1)*people})÷({per2}-{per1})={people}人"),
        ]
        return random.choice(variants)
    else:
        variants = [
            ("宿舍分房间，每间4人多20人，每间8人正好住满，几间房多少人？", "20÷(8-4)=5间，共40人"),
            ("用绳子量井深，折三折量多2米，折四折量差1米，绳长和井深？", "设井深x：(3x+6)/3绳=(4x-4)/4绳→绳长=3x+6=4x-4→x=10米，绳长36米"),
            ("工人运花瓶，运一个得5元，碎一个赔10元。运了100个得440元，碎了几个？", "设碎x个：5(100-x)-10x=440→500-15x=440→x=4个"),
        ]
        return random.choice(variants)


@register("logic_clock")
def logic_clock(difficulty: int, grade: int):
    """时钟问题（角度与追及）"""
    if difficulty <= 2:
        h = random.randint(1, 12)
        variants = [
            (f"{h}时整，时针和分针的夹角是多少度？", f"{min(abs(h-12), h)*30}°" if h != 3 and h != 9 else "90°"),
            (f"分针走一圈是多少度？时针走一大格是多少度？", "分针360°，时针30°"),
            (f"6时整，时针和分针成多少度角？", "180°（平角）"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        h = random.randint(1, 11)
        m = random.choice([0, 15, 30, 45])
        # 时针角度: h*30 + m*0.5, 分针角度: m*6
        h_angle = h * 30 + m * 0.5
        m_angle = m * 6
        angle = abs(h_angle - m_angle)
        if angle > 180:
            angle = 360 - angle
        variants = [
            (f"{h}时{m}分，时针和分针的夹角是多少度？", f"{angle}°"),
            (f"分针每分钟走几度？时针每分钟走几度？", "分针6°/分，时针0.5°/分"),
            (f"3时多少分时，时针和分针重合？", f"3时{180/5.5:.1f}分≈3时16.4分（分针追时针，差90°，速度差5.5°/分）"),
        ]
        return random.choice(variants)
    else:
        variants = [
            ("从12点开始，经过多少分钟时针和分针第一次重合？", f"360÷5.5≈65.5分钟（即1时5.5分）"),
            ("一昼夜(24小时)时针和分针重合几次？", "22次（每12小时重合11次）"),
            ("从3点整开始，经过多少分钟时针和分针第一次成直角？", "3点时差90°，分针追时针速度差5.5°/分，90÷5.5≈16.4分钟"),
            ("某钟慢5分钟/小时，早上8点对准，当钟显示12点时实际几点？", "钟走55分=实际60分，钟走4小时=实际4×60/55≈4.36小时，实际约12时22分"),
        ]
        return random.choice(variants)


# ═══════════════════════════════════════════════════════════
# 中学数学题型（7-9年级）
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# 四、应用题（补充）
# ═══════════════════════════════════════════════════════════

@register("app_unit_rate")
def app_unit_rate(difficulty: int, grade: int):
    """归一问题 — 先求单一量，再求总量"""
    if difficulty <= 2:
        n = random.randint(2, 5)
        total = n * random.randint(3, 12)
        unit = total // n
        ask_n = random.randint(1, 6)
        ans = unit * ask_n
        return (f"{n}台拖拉机{total}小时耕地完，照这样计算，{ask_n}台同样的拖拉机需要多少小时耕完同样的地？",
                f"{ans}小时")
    elif difficulty <= 4:
        n_items = random.randint(3, 8)
        cost = n_items * random.randint(5, 15)
        unit = cost // n_items
        ask_n = random.randint(2, 10)
        ans = unit * ask_n
        return (f"买{n_items}支铅笔花了{cost}元，照这样计算，买{ask_n}支同样的铅笔需要多少钱？",
                f"{ans}元")
    else:
        workers = random.randint(4, 8)
        days = random.randint(6, 15)
        total_work = workers * days
        ask_workers = random.randint(2, 10)
        ans_days = total_work // ask_workers if total_work % ask_workers == 0 else (total_work + ask_workers - 1) // ask_workers
        return (f"{workers}个人{days}天可以完成一项工程，照这样计算，如果增加到{ask_workers}个人，几天可以完成？",
                f"{ans_days}天")


@register("app_total_rate")
def app_total_rate(difficulty: int, grade: int):
    """归总问题 — 先求总量，再分配"""
    if difficulty <= 2:
        per_day = random.randint(3, 8)
        days = random.randint(3, 7)
        total = per_day * days
        new_per = random.randint(1, per_day - 1) if per_day > 1 else 1
        new_days = (total + new_per - 1) // new_per
        return (f"小明每天读{per_day}页书，{days}天读完一本书。如果每天只读{new_per}页，需要多少天读完？",
                f"{new_days}天")
    elif difficulty <= 4:
        trucks = random.randint(3, 6)
        loads = random.randint(4, 8)
        total = trucks * loads
        new_trucks = random.randint(2, trucks + 2)
        new_loads = (total + new_trucks - 1) // new_trucks
        return (f"{trucks}辆卡车每辆运{loads}吨货物，正好运完。如果改用{new_trucks}辆卡车，每辆要运多少吨？",
                f"{new_loads}吨")
    else:
        cows = random.randint(5, 10)
        days = random.randint(10, 20)
        total_grass = cows * days
        new_cows = random.randint(3, 15)
        new_days = total_grass // new_cows if total_grass % new_cows == 0 else (total_grass + new_cows - 1) // new_cows
        return (f"牧场有{cows}头牛，{days}天吃完一片草地的草。如果放{new_cows}头牛，几天可以吃完？",
                f"{new_days}天")


@register("app_ratio_compare")
def app_ratio_compare(difficulty: int, grade: int):
    """倍比问题 — 通过倍数关系求解"""
    if difficulty <= 2:
        a = random.randint(5, 20)
        m = random.randint(2, 5)
        b = a * m
        ask_m = random.randint(2, 6)
        ans = a * ask_m
        return (f"甲数是{a}，乙数是甲的{m}倍。如果丙数是甲的{ask_m}倍，丙数是多少？",
                f"{ans}")
    elif difficulty <= 4:
        a = random.randint(10, 30)
        b = random.randint(2, 5)
        total = a * (1 + b)
        va = a
        vb = a * b
        return (f"甲乙两数之和是{total}，乙是甲的{b}倍，甲和乙各是多少？",
                f"甲{va}，乙{vb}")
    else:
        a = random.randint(8, 20)
        m1 = random.randint(2, 4)
        m2 = random.randint(2, 4)
        while m2 == m1:
            m2 = random.randint(2, 4)
        b = a * m1
        c = a * m2
        return (f"甲是{a}，乙是甲的{m1}倍，丙是甲的{m2}倍。乙是丙的几分之几？",
                f"{m1}/{m2}" if m1 < m2 else f"{m1}/{m2}")


@register("app_boat_stream")
def app_boat_stream(difficulty: int, grade: int):
    """流水行船问题"""
    if difficulty <= 2:
        boat = random.randint(16, 30)
        stream = random.randint(2, 6)
        downstream = boat + stream
        upstream = boat - stream
        return (f"一艘船在静水中的速度是每小时{boat}千米，水流速度是每小时{stream}千米。这艘船顺水航行速度是多少？逆水航行速度是多少？",
                f"顺水{downstream}千米/时，逆水{upstream}千米/时")
    elif difficulty <= 4:
        downstream = random.randint(24, 40)
        upstream = random.randint(12, 22)
        boat = (downstream + upstream) // 2
        stream = (downstream - upstream) // 2
        return (f"一艘船顺水航行速度为每小时{downstream}千米，逆水航行速度为每小时{upstream}千米。求船在静水中的速度和水流速度。",
                f"船速{boat}千米/时，水速{stream}千米/时")
    else:
        boat = random.randint(20, 36)
        stream = random.randint(2, 6)
        dist = random.randint(60, 150)
        down_speed = boat + stream
        up_speed = boat - stream
        down_time = dist / down_speed
        up_time = dist / up_speed
        total_time = down_time + up_time
        total_str = f"{total_time:.1f}" if total_time != int(total_time) else str(int(total_time))
        return (f"一艘船在静水中速度为每小时{boat}千米，水流速度每小时{stream}千米。该船在相距{dist}千米的两个码头间往返一次，共需多少小时？",
                f"{total_str}小时")


@register("app_cow_grazing")
def app_cow_grazing(difficulty: int, grade: int):
    """牛吃草问题（牛顿问题）"""
    if difficulty <= 2:
        # 简化版：固定草量，不考虑生长
        grass = random.randint(100, 200)
        cows1 = random.randint(5, 10)
        days1 = grass // cows1
        cows2 = random.randint(cows1 + 1, cows1 + 5)
        days2 = grass // cows2
        return (f"一片草地有{grass}份草，{cows1}头牛{days1}天吃完。如果放{cows2}头牛，几天可以吃完？（假设草不生长）",
                f"{days2}天")
    elif difficulty <= 4:
        # 经典简化：已知两组条件求第三组
        # 设定：原有草量G，每天生长r
        r = random.randint(1, 3)
        G = random.randint(80, 150)
        cows1 = random.randint(10, 20)
        days1 = random.randint(5, 10)
        # 验证：cows1 * days1 = G + r * days1
        actual_G = cows1 * days1 - r * days1
        cows2 = random.randint(15, 25)
        # days2 = actual_G / (cows2 - r)
        denom = cows2 - r
        if denom <= 0:
            denom = 1
        days2 = actual_G // denom if actual_G % denom == 0 else actual_G // denom
        return (f"牧场上有一片草地，草每天匀速生长。{cows1}头牛{days1}天可以吃完，{cows2}头牛几天可以吃完？",
                f"{days2}天")
    else:
        r = random.randint(2, 5)
        G = random.randint(100, 200)
        cows1 = random.randint(20, 30)
        days1 = random.randint(8, 15)
        actual_G = cows1 * days1 - r * days1
        cows2 = random.randint(25, 40)
        denom = cows2 - r
        if denom <= 0:
            denom = 1
        days2 = actual_G // denom
        cows3 = random.randint(10, 20)
        denom3 = cows3 - r
        if denom3 <= 0:
            denom3 = 1
        days3 = actual_G // denom3
        return (f"牧场草地草每天匀速生长。{cows1}头牛{days1}天吃完，{cows2}头牛{days2}天吃完。如果放{cows3}头牛，几天可以吃完？",
                f"{days3}天")


# ═══════════════════════════════════════════════════════════
# 主生成函数
# ═══════════════════════════════════════════════════════════

DIFFICULTY_MAP = {
    "\u57fa\u7840": (1, 2),
    "\u63d0\u9ad8": (3, 4),
    "\u62d4\u9ad8": (4, 5),
    "\u7efc\u5408": (1, 5),
}


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
