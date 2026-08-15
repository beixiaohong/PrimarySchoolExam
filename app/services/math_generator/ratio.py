import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register
from .util import fmt_num

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
            (f"原价{price}元，打{d_name}折，现价多少？", f"{fmt_num(price*discount/100)} 元"),
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
            (f"营业额{income}元，税率{tax_rate}%，缴税多少？", f"{fmt_num(income*tax_rate/100)} 元"),
            (f"去年产量{last}吨，今年增产{growth}%，今年多少？", f"{fmt_num(last*(100+growth)/100)} 吨"),
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
        final2 = orig * (100 - rate2) / 100
        a_val = random.randint(50, 150)
        b_val = random.randint(50, 150)
        pct_more = round(abs(a_val-b_val) / min(a_val,b_val) * 100, 1)
        variants = [
            (f"原价{price}元，先涨{up}%再降{down}%，现价多少？涨了还是跌了？", f"现价{final:.2f}元，{'涨' if change>0 else '跌'}了{abs(change):.2f}%"),
            (f"降价{rate2}%后是{fmt_num(final2)}元，原价多少？", f"{orig} 元"),
            (f"甲{a_val}乙{b_val}，多的比少的多百分之几？", f"{pct_more}%"),
        ]
        return random.choice(variants)

__all__ = [
    "ratio_basic",
    "ratio_percent",
    "ratio_proportion",
]
