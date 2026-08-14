import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register

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

__all__ = [
    "_place_name",
    "_prime_factorize",
    "_read_number",
    "number_conversion",
    "number_divisibility",
    "number_gcd_lcm",
    "number_large",
    "number_negative",
    "number_operation_law",
]
