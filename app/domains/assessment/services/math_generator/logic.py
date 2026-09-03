"""逻辑与规律类题型生成器：推理 / 找规律 / 组合 / 方案优化 / 抽屉原理 / 周期 / 时钟

注册题型 7 个：logic_reasoning、logic_pattern、logic_combinatorics、logic_optimization、
logic_pigeonhole、logic_period、logic_clock。

约定同 calc.py：`@register` 注册 → core 按 code 分发。
"""
import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register

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
        # 鸡兔同笼：腿数落在 [2*heads+2, 4*heads-2] 的偶数内，
        # 保证至少1鸡1兔且方程可解，避免原 while 在 legs>4*heads 时死循环
        extra_max = (4 * heads - 2) - (2 * heads)  # = 2*heads-2 ≥ 28
        legs = 2 * heads + random.randrange(2, extra_max + 1, 2)
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

__all__ = [
    "logic_clock",
    "logic_combinatorics",
    "logic_optimization",
    "logic_pattern",
    "logic_period",
    "logic_pigeonhole",
    "logic_reasoning",
]
