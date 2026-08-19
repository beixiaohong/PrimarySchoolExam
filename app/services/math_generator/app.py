import random
import math
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register
from .util import fmt_num

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
        v1 = random.randint(45, 80)
        v2 = random.randint(40, v1 - 1)  # 保证 v1>v2，追及场景甲更快，且不会除零
        t = random.randint(2, 6)
        dist = (v1 + v2) * t
        variants = [
            (f"甲乙相向而行，甲速{v1}乙速{v2}，{t}小时相遇，两地相距多少？", f"{dist} 千米"),
            (f"相距{dist}千米，甲速{v1}乙速{v2}相向而行，几小时相遇？", f"{t} 小时"),
            (None, None),  # 占位：追及题下方专门构造，避免 v1==v2 除零
        ]
        q, a = random.choice(variants)
        if q is None:
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
    """环形跑道反向相遇：周长取速度和的整数倍，保证整除且整数分钟，避免死循环"""
    s = v1 + v2
    n = random.randint(3, 8)  # 相遇所需分钟数（整数），周长 = n * 速度和
    circumference = n * s
    t = circumference // s
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
            (f"{sol}克盐水浓度{rate}%，含盐多少？", f"{fmt_num(sol*rate/100)} 克"),
            (f"盐{fmt_num(sol*rate/100)}克配成{rate}%盐水，盐水多少克？", f"{sol} 克"),
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
            (f"进价{cost}元，利润率{rate}%，售价多少？", f"{fmt_num(cost*(100+rate)/100)} 元"),
            (f"售价{fmt_num(cost*(100+rate)/100)}元，进价{cost}元，利润率多少？", f"{rate}%"),
        ]
        return random.choice(variants)
    elif difficulty <= 4:
        cost = random.randint(100, 500)
        markup = random.randint(30, 60)
        discount = random.choice([80, 85, 90])
        marked = cost * (100 + markup) / 100
        sell = marked * discount / 100
        # 利润率用分数精确计算：真实值（如 33.4500...%）在浮点中会偏小成
        # 33.4499...，round(...,1) 会错舍成 33.4（孩子答 33.45% 被误判）。
        # 改为精确分数 + Decimal 四舍五入到 2 位小数（33.45%）。
        real_rate_f = (Fraction(cost) * Fraction(100 + markup) / 100
                       * Fraction(discount) / 100 - Fraction(cost)) / Fraction(cost) * 100
        real_rate = (Decimal(real_rate_f.numerator) / Decimal(real_rate_f.denominator)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        d_name = {80:"八",85:"八五",90:"九"}[discount]
        variants = [
            (f"进价{cost}元加价{markup}%标价，打{d_name}折卖，实际利润率？", f"{real_rate}%"),
            (f"打{d_name}折后卖{fmt_num(sell)}元，标价是多少？", f"{fmt_num(marked)} 元"),
        ]
        return random.choice(variants)
    else:
        cost = random.randint(100, 300)
        total = random.randint(50, 150)
        pr = random.randint(30, 50)
        sell1 = int(total * 0.6)
        sell2 = total - sell1
        discount = random.choice([70, 75, 80])
        price1 = cost * (100 + pr) / 100
        price2 = price1 * discount / 100
        revenue = sell1 * price1 + sell2 * price2
        profit = revenue - total * cost
        d_name = {70:"七",75:"七五",80:"八"}[discount]
        variants = [
            (f"进{total}件每件{cost}元，{pr}%利润率定价售{sell1}件，余下{d_name}折售完，总利润？", f"{fmt_num(profit)} 元"),
            (f"两种方案：A全部{pr}%利润出售；B先售60%再{d_name}折清仓。哪种利润高？", None),
        ]
        q, a = random.choice(variants)
        if a is None:
            plan_a = total * cost * pr / 100
            return f"进{total}件每件{cost}元。方案A全部加{pr}%出售；方案B售60%后{d_name}折清仓。哪种利润高？", f"A利润{fmt_num(plan_a)}元，B利润{fmt_num(profit)}元，{'A' if plan_a > profit else 'B'}高"
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

def _cow_grazing_build(min_pairs):
    """构造自洽的牛吃草题参数。

    模型：c 头牛吃 d 天 → c*d = G + r*d（G 为初始草量，r 为每日生长量），
    等价于 d*(c - r) = G。给定 G、r，枚举天数 d∈[4,15] 使其整除 G，
    得到净日耗 k=G//d 与牛数 c=k+r。挑选 min_pairs 组互异 (d, c)，
    保证所有场景可由同一 (G, r) 解释，且天数为整数、牛数在合理范围。
    """
    for _ in range(300):
        G = random.randint(150, 360)
        r = random.randint(1, 4)
        pairs = []
        for d in range(4, 16):
            if G % d != 0:
                continue
            cows = G // d + r
            if 8 <= cows <= 30:
                pairs.append((d, cows))
        if len(pairs) >= min_pairs:
            random.shuffle(pairs)
            return G, r, pairs[:min_pairs]
    # 兜底（极少触发）：确定性自洽参数
    G, r = 240, 2
    return G, r, [(10, 26), (12, 22), (15, 18)]


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
        # 经典牛吃草：由统一 (G, r) 反解两组 (牛数, 天数)，题设自洽、天数为整数
        _, r, pairs = _cow_grazing_build(min_pairs=2)
        d1, c1 = pairs[0]
        d2, c2 = pairs[1]
        return (f"牧场上有一片草地，草每天匀速生长。{c1}头牛{d1}天可以吃完，{c2}头牛几天可以吃完？",
                f"{d2}天")
    else:
        # 三组条件，均由同一 (G, r) 解释，求第三组天数
        _, r, pairs = _cow_grazing_build(min_pairs=3)
        d1, c1 = pairs[0]
        d2, c2 = pairs[1]
        d3, c3 = pairs[2]
        return (f"牧场草地草每天匀速生长。{c1}头牛{d1}天吃完，{c2}头牛{d2}天吃完。如果放{c3}头牛，几天可以吃完？",
                f"{d3}天")

__all__ = [
    "_travel_avg_speed",
    "_travel_bridge",
    "_travel_circular",
    "_travel_round_trip",
    "app_boat_stream",
    "app_chicken_rabbit",
    "app_concentration",
    "app_cow_grazing",
    "app_fraction",
    "app_profit",
    "app_proportional_dist",
    "app_ratio_compare",
    "app_sum_difference",
    "app_surplus_deficit",
    "app_total_rate",
    "app_travel",
    "app_tree_planting",
    "app_unit_rate",
    "app_work",
]
