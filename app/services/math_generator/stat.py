import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register
from .util import fmt_num

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
        num_a = round(total_p * pct_a / 100)
        num_b = round(total_p * pct_b / 100)
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
        # 7 个数（奇数）：中位数 = 排序后第 4 个（index 3）。
        # 原实现取 (s_data[3]+s_data[4])/2 是按偶数个数算的，7 个数时答案偏大
        # （如 [.., 81, 85, ..] 会错答 83.0，实际应为 81）。
        mid = s_data[3]
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

__all__ = [
    "stat_average",
    "stat_chart",
    "stat_measure",
    "stat_probability",
]
