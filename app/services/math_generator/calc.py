import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register

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

__all__ = [
    "_dec_add_sub",
    "_dec_approx",
    "_dec_compare",
    "_dec_context_measure",
    "_dec_context_money",
    "_dec_divide",
    "_dec_missing",
    "_dec_mixed",
    "_dec_multi_step",
    "_dec_multiply",
    "_dec_multiply_simple",
    "_dec_reverse",
    "_eq_add_form",
    "_eq_both_sides",
    "_eq_bracket",
    "_eq_fraction_coeff",
    "_eq_proportion",
    "_eq_simple",
    "_eq_system_hint",
    "_eq_two_step",
    "_eq_word_hard",
    "_eq_word_mid",
    "_eq_word_simple",
    "_frac_chain",
    "_frac_compare",
    "_frac_complex",
    "_frac_context",
    "_frac_diff_denom",
    "_frac_divide",
    "_frac_mixed_op",
    "_frac_multiply",
    "_frac_of_number",
    "_frac_reverse",
    "_frac_same_denom",
    "_frac_to_mixed",
    "_mix_advanced_trick",
    "_mix_bracket",
    "_mix_combine",
    "_mix_context",
    "_mix_distribute",
    "_mix_fraction_dec",
    "_mix_multi_law",
    "_mix_order",
    "_mix_reverse_law",
    "_mix_simple_distribute",
    "_mix_subtract_prop",
    "_solve_int_variant",
    "calc_decimal",
    "calc_equation",
    "calc_fraction",
    "calc_int_basic",
    "calc_mixed",
]
