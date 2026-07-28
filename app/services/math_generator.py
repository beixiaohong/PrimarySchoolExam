"""
数学题生成器 - 优化版
支持难度梯度（基础/提高/拔高）+ 核心知识点覆盖
题型注册表模式：每个题型code对应一个生成函数
"""
import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from ..models.problem_type import ProblemType, ProblemCategory
from ..schemas.problem import ProblemItem

# ─── 题型生成器注册表 ─────────────────────────────────────────
# key = ProblemType.code, value = generator function
# 每个生成器签名: (difficulty: int, grade: int) -> (question: str, answer: str)
GENERATORS: Dict[str, Callable] = {}


def register(code: str):
    """装饰器：注册题型生成器"""
    def decorator(func):
        GENERATORS[code] = func
        return func
    return decorator


# ═══════════════════════════════════════════════════════════
# 一、计算题类
# ═══════════════════════════════════════════════════════════

@register("calc_int_basic")
def calc_int_basic(difficulty: int, grade: int):
    """整数四则运算"""
    if difficulty <= 2:
        a, b = random.randint(10, 99), random.randint(10, 99)
        op = random.choice(["+", "-", "×"])
        if op == "+":
            ans = a + b
        elif op == "-":
            a, b = max(a, b), min(a, b)
            ans = a - b
        else:
            a, b = random.randint(11, 99), random.randint(2, 9)
            ans = a * b
        return f"{a} {op} {b} = ", str(ans)
    elif difficulty <= 4:
        a = random.randint(100, 999)
        b = random.randint(100, 999)
        c = random.randint(2, 9)
        ops = random.choice([
            (f"{a} + {b} × {c}", a + b * c),
            (f"{a} × {c} - {b}", a * c - b),
            (f"({a} + {b}) × {c}", (a + b) * c),
            (f"{a} × {b // 100 + 1} + {b}", a * (b // 100 + 1) + b),
        ])
        return f"{ops[0]} = ", str(ops[1])
    else:
        a = random.randint(100, 999)
        b = random.randint(10, 99)
        c = random.randint(10, 99)
        d = random.randint(2, 9)
        expr = f"{a} × {d} + {b} × {c} - {a - b}"
        ans = a * d + b * c - (a - b)
        return f"{expr} = ", str(ans)


@register("calc_decimal")
def calc_decimal(difficulty: int, grade: int):
    """小数运算"""
    if difficulty <= 2:
        a = round(random.uniform(1, 20), 1)
        b = round(random.uniform(1, 20), 1)
        op = random.choice(["+", "-"])
        if op == "-":
            a, b = max(a, b), min(a, b)
        ans = round(a + b if op == "+" else a - b, 2)
        return f"{a} {op} {b} = ", str(ans)
    elif difficulty <= 4:
        a = round(random.uniform(1, 50), 2)
        b = round(random.uniform(0.1, 9.9), 1)
        ans = round(a * b, 3)
        return f"{a} × {b} = ", str(ans)
    else:
        a = round(random.uniform(10, 100), 2)
        b = round(random.uniform(0.1, 9.9), 2)
        c = round(random.uniform(0.1, 9.9), 1)
        ans = round(a * b + c, 3)
        return f"{a} × {b} + {c} = ", str(ans)


@register("calc_fraction")
def calc_fraction(difficulty: int, grade: int):
    """分数四则运算"""
    if difficulty <= 2:
        d = random.choice([2, 3, 4, 5, 6, 8])
        n1 = random.randint(1, d - 1)
        n2 = random.randint(1, d - n1)
        ans = Fraction(n1 + n2, d)
        return f"{n1}/{d} + {n2}/{d} = ", f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
    elif difficulty <= 4:
        d1, d2 = random.choice([(2, 3), (3, 4), (2, 5), (3, 5), (4, 6)])
        n1 = random.randint(1, d1 - 1)
        n2 = random.randint(1, d2 - 1)
        op = random.choice(["+", "-"])
        f1, f2 = Fraction(n1, d1), Fraction(n2, d2)
        if op == "-" and f1 < f2:
            f1, f2 = f2, f1
        ans = f1 + f2 if op == "+" else f1 - f2
        ans_str = f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
        return f"{n1}/{d1} {op} {n2}/{d2} = ", ans_str
    else:
        d1, d2 = random.choice([(3, 4), (5, 6), (7, 8), (3, 7)])
        n1 = random.randint(1, d1 - 1)
        n2 = random.randint(1, d2 - 1)
        f1, f2 = Fraction(n1, d1), Fraction(n2, d2)
        op = random.choice(["×", "÷"])
        if op == "×":
            ans = f1 * f2
            expr = f"{n1}/{d1} × {n2}/{d2}"
        else:
            ans = f1 / f2
            expr = f"{n1}/{d1} ÷ {n2}/{d2}"
        ans_str = f"{ans.numerator}/{ans.denominator}" if ans.denominator != 1 else str(ans.numerator)
        return f"{expr} = ", ans_str


@register("calc_mixed")
def calc_mixed(difficulty: int, grade: int):
    """混合运算与简便计算"""
    if difficulty <= 2:
        a = random.randint(20, 100)
        b = random.randint(20, 100)
        c = random.randint(2, 9)
        ans = (a + b) * c
        return f"({a} + {b}) × {c} = ", str(ans)
    elif difficulty <= 4:
        # 简便运算：凑整
        a = random.choice([25, 125, 50, 75])
        b = random.choice([4, 8, 2, 4])
        c = random.randint(10, 99)
        ans = a * b + c
        return f"{a} × {b} + {c} = （用简便方法计算）", str(ans)
    else:
        # 分配律逆用
        a = random.randint(11, 99)
        b = random.randint(11, 99)
        c = random.choice([3, 7, 9, 11])
        ans = (a + b) * c
        return f"{a} × {c} + {b} × {c} = （用简便方法计算）", str(ans)


@register("calc_equation")
def calc_equation(difficulty: int, grade: int):
    """解方程"""
    if difficulty <= 2:
        x = random.randint(2, 20)
        a = random.randint(2, 9)
        b = a * x
        return f"解方程：{a}x = {b}", f"x = {x}"
    elif difficulty <= 4:
        x = random.randint(2, 15)
        a = random.randint(2, 9)
        b = random.randint(1, 20)
        c = a * x + b
        return f"解方程：{a}x + {b} = {c}", f"x = {x}"
    else:
        x = random.randint(2, 12)
        a = random.randint(2, 6)
        b = random.randint(2, 6)
        c = random.randint(1, 10)
        # ax + b = cx + d 形式
        d = (a - b) * x + c if a != b else c + x
        if a == b:
            a += 1
            d = (a - b) * x + c
        return f"解方程：{a}x + {c} = {b}x + {d}", f"x = {x}"


# ═══════════════════════════════════════════════════════════
# 二、图形与几何（重点加强）
# ═══════════════════════════════════════════════════════════

@register("geo_area_plane")
def geo_area_plane(difficulty: int, grade: int):
    """平面图形面积（三角形/平行四边形/梯形/组合图形）"""
    if difficulty <= 2:
        # 基础：单一图形
        shape = random.choice(["三角形", "平行四边形"])
        if shape == "三角形":
            b = random.randint(4, 20)
            h = random.randint(3, 15)
            area = b * h / 2
            ans = f"{area:.1f}" if area != int(area) else str(int(area))
            return f"一个三角形的底是{b}cm，高是{h}cm，求面积。", f"{ans} cm²"
        else:
            b = random.randint(4, 20)
            h = random.randint(3, 15)
            area = b * h
            return f"一个平行四边形的底是{b}cm，高是{h}cm，求面积。", f"{area} cm²"
    elif difficulty <= 4:
        # 梯形 + 圆
        shape = random.choice(["梯形", "圆"])
        if shape == "梯形":
            a = random.randint(4, 12)
            b = random.randint(6, 16)
            h = random.randint(3, 10)
            area = (a + b) * h / 2
            ans = f"{area:.1f}" if area != int(area) else str(int(area))
            return f"一个梯形的上底是{a}cm，下底是{b}cm，高是{h}cm，求面积。", f"{ans} cm²"
        else:
            r = random.randint(2, 10)
            area = round(math.pi * r * r, 2)
            return f"一个圆的半径是{r}cm，求面积。（π取3.14）", f"{area} cm²"
    else:
        # 组合图形
        r = random.randint(3, 8)
        a = 2 * r  # 正方形边长=直径
        square_area = a * a
        circle_area = round(math.pi * r * r, 2)
        shadow = round(square_area - circle_area, 2)
        return (
            f"一个正方形的边长是{a}cm，以正方形中心为圆心、边长的一半为半径画一个圆，"
            f"求正方形内圆外（阴影部分）的面积。（π取3.14）",
            f"{shadow} cm²"
        )


@register("geo_volume")
def geo_volume(difficulty: int, grade: int):
    """立体图形体积（长方体/正方体/圆柱/圆锥）"""
    if difficulty <= 2:
        a = random.randint(3, 12)
        b = random.randint(3, 12)
        c = random.randint(3, 12)
        v = a * b * c
        return f"一个长方体的长是{a}cm，宽是{b}cm，高是{c}cm，求体积。", f"{v} cm³"
    elif difficulty <= 4:
        shape = random.choice(["圆柱", "正方体"])
        if shape == "圆柱":
            r = random.randint(2, 8)
            h = random.randint(5, 20)
            v = round(math.pi * r * r * h, 2)
            return f"一个圆柱的底面半径是{r}cm，高是{h}cm，求体积。（π取3.14）", f"{v} cm³"
        else:
            a = random.randint(3, 12)
            v = a ** 3
            return f"一个正方体的棱长是{a}cm，求体积和表面积。", f"体积{v} cm³，表面积{6*a*a} cm²"
    else:
        # 圆锥 + 等底等高关系
        r = random.randint(3, 8)
        h = random.randint(6, 18)
        v_cone = round(math.pi * r * r * h / 3, 2)
        v_cyl = round(math.pi * r * r * h, 2)
        return (
            f"一个圆锥和一个圆柱等底等高，圆锥的底面半径是{r}cm，高是{h}cm。"
            f"（1）求圆锥体积；（2）求圆柱体积；（3）圆柱体积是圆锥的几倍？（π取3.14）",
            f"（1）{v_cone} cm³（2）{v_cyl} cm³（3）3倍"
        )


@register("geo_perimeter")
def geo_perimeter(difficulty: int, grade: int):
    """周长与面积综合"""
    if difficulty <= 2:
        a = random.randint(5, 20)
        b = random.randint(3, 15)
        return f"一个长方形的长是{a}cm，宽是{b}cm，求周长和面积。", f"周长{2*(a+b)} cm，面积{a*b} cm²"
    elif difficulty <= 4:
        # 已知周长求面积
        c = random.randint(20, 60)
        ratio = random.choice([(2, 1), (3, 2), (3, 1), (5, 3)])
        half = c // 2
        total_parts = ratio[0] + ratio[1]
        if half % total_parts != 0:
            half = total_parts * random.randint(3, 8)
            c = half * 2
        a = half * ratio[0] // total_parts
        b = half - a
        return f"一个长方形的周长是{c}cm，长与宽的比是{ratio[0]}:{ratio[1]}，求面积。", f"{a*b} cm²"
    else:
        # 圆的周长与面积综合
        r = random.randint(3, 10)
        c = round(2 * math.pi * r, 2)
        area = round(math.pi * r * r, 2)
        return (
            f"用一根铁丝围成一个圆，圆的半径是{r}cm。"
            f"（1）这根铁丝至少多长？（2）圆的面积是多少？"
            f"（3）如果用这根铁丝围成一个正方形，正方形面积是多少？（π取3.14）",
            f"（1）{c} cm（2）{area} cm²（3）{round((c/4)**2, 2)} cm²"
        )


@register("geo_transform")
def geo_transform(difficulty: int, grade: int):
    """图形变换（平移/旋转/对称/放大缩小）"""
    if difficulty <= 2:
        a = random.randint(3, 10)
        return (
            f"一个正方形边长{a}cm，按2:1放大后，新正方形的边长是多少？面积是原来的几倍？",
            f"边长{a*2} cm，面积是原来的4倍"
        )
    elif difficulty <= 4:
        r = random.randint(2, 6)
        return (
            f"一个圆的半径是{r}cm，按1:2缩小后，新圆的周长和面积分别是多少？（π取3.14）",
            f"周长{round(2*math.pi*r/2, 2)} cm，面积{round(math.pi*(r/2)**2, 2)} cm²"
        )
    else:
        a = random.randint(4, 10)
        b = random.randint(3, 8)
        return (
            f"一个长方形长{a}cm、宽{b}cm，先按3:1放大，再按1:2缩小，"
            f"最终图形的面积是多少？与原来面积之比是多少？",
            f"最终面积{round(a*b*3/2*3/2, 2)} cm²，面积比9:4"
        )


# ═══════════════════════════════════════════════════════════
# 三、比例与比（重点加强）
# ═══════════════════════════════════════════════════════════

@register("ratio_basic")
def ratio_basic(difficulty: int, grade: int):
    """比的认识与化简"""
    if difficulty <= 2:
        a = random.randint(2, 12)
        b = random.randint(2, 12)
        g = math.gcd(a, b)
        return f"化简比：{a}:{b}", f"{a//g}:{b//g}"
    elif difficulty <= 4:
        a = random.randint(10, 50)
        b = random.randint(10, 50)
        c = random.randint(10, 50)
        g = math.gcd(math.gcd(a, b), c)
        return f"化简比：{a}:{b}:{c}", f"{a//g}:{b//g}:{c//g}"
    else:
        # 比的转换
        a = random.randint(2, 8)
        b = random.randint(3, 9)
        total = random.randint(50, 200)
        while total % (a + b) != 0:
            total += 1
        part_a = total * a // (a + b)
        part_b = total - part_a
        return f"甲乙两数的比是{a}:{b}，两数之和是{total}，求甲乙两数。", f"甲={part_a}，乙={part_b}"


@register("ratio_proportion")
def ratio_proportion(difficulty: int, grade: int):
    """比例应用（正比例/反比例/比例尺）"""
    if difficulty <= 2:
        # 正比例
        unit = random.randint(3, 15)
        n1 = random.randint(2, 8)
        n2 = random.randint(9, 20)
        return f"{n1}本同样的书重{unit*n1}克，{n2}本这样的书重多少克？（用比例解）", f"{unit*n2} 克"
    elif difficulty <= 4:
        # 比例尺
        scale = random.choice([100000, 200000, 500000, 50000])
        map_cm = random.randint(2, 15)
        real_km = map_cm * scale / 100000
        return f"在比例尺1:{scale}的地图上，量得两地距离{map_cm}cm，实际距离是多少千米？", f"{real_km:.1f} 千米" if real_km != int(real_km) else f"{int(real_km)} 千米"
    else:
        # 反比例
        workers1 = random.randint(4, 10)
        days1 = random.randint(10, 30)
        workers2 = random.randint(workers1 + 2, workers1 + 10)
        total_work = workers1 * days1
        if total_work % workers2 != 0:
            workers2 = workers1 + random.choice([2, 4, 5, 6])
            while total_work % workers2 != 0:
                workers2 += 1
        days2 = total_work // workers2
        return (
            f"一项工程，{workers1}人做需要{days1}天完成。如果增加{workers2-workers1}人，"
            f"几天可以完成？（用反比例知识解答）",
            f"{days2} 天"
        )


@register("ratio_percent")
def ratio_percent(difficulty: int, grade: int):
    """百分数应用（折扣/税率/利率/浓度）"""
    if difficulty <= 2:
        price = random.randint(50, 500)
        discount = random.choice([80, 85, 90, 75, 70])
        final = price * discount / 100
        return f"一件商品原价{price}元，打{'八' if discount==80 else '八五' if discount==85 else '九' if discount==90 else '七五' if discount==75 else '七'}折出售，现价多少元？", f"{final:.0f} 元" if final == int(final) else f"{final:.2f} 元"
    elif difficulty <= 4:
        principal = random.randint(1000, 10000)
        rate = random.choice([2.25, 2.75, 3.0, 3.25, 3.5])
        years = random.randint(1, 3)
        interest = principal * rate / 100 * years
        return f"小明把{principal}元存入银行，年利率{rate}%，存期{years}年，到期可得到利息多少元？", f"{interest:.2f} 元"
    else:
        # 连续涨跌
        price = random.randint(100, 500)
        up = random.randint(10, 30)
        down = random.randint(10, 30)
        final = price * (1 + up/100) * (1 - down/100)
        change = (final - price) / price * 100
        return (
            f"某商品原价{price}元，先涨价{up}%，再降价{down}%，"
            f"（1）现价多少元？（2）与原价相比涨了还是跌了？变化了百分之几？",
            f"（1）{final:.2f}元（2）{'涨' if change > 0 else '跌'}了{abs(change):.2f}%"
        )


# ═══════════════════════════════════════════════════════════
# 四、应用题类（经典 + 拔高）
# ═══════════════════════════════════════════════════════════

@register("app_travel")
def app_travel(difficulty: int, grade: int):
    """行程问题"""
    if difficulty <= 2:
        speed = random.randint(30, 80)
        time = random.randint(2, 8)
        dist = speed * time
        return f"一辆汽车每小时行{speed}千米，行了{time}小时，一共行了多少千米？", f"{dist} 千米"
    elif difficulty <= 4:
        # 相遇问题
        v1 = random.randint(40, 80)
        v2 = random.randint(40, 80)
        t = random.randint(2, 6)
        dist = (v1 + v2) * t
        return (
            f"甲乙两车同时从相距{dist}千米的A、B两地相向而行，"
            f"甲车每小时行{v1}千米，乙车每小时行{v2}千米，几小时后两车相遇？",
            f"{t} 小时"
        )
    else:
        # 追及 + 往返
        v1 = random.randint(50, 80)
        v2 = random.randint(30, v1 - 10)
        head_start = random.randint(1, 3)
        gap = v2 * head_start
        catch_time = gap / (v1 - v2)
        if catch_time != int(catch_time):
            v1 = v2 + random.choice([10, 20, 30])
            catch_time = gap / (v1 - v2)
        return (
            f"甲乙两人同向而行，乙先出发{head_start}小时，速度为每小时{v2}千米，"
            f"甲的速度为每小时{v1}千米。甲出发后几小时追上乙？",
            f"{catch_time:.1f} 小时" if catch_time != int(catch_time) else f"{int(catch_time)} 小时"
        )


@register("app_work")
def app_work(difficulty: int, grade: int):
    """工程问题"""
    if difficulty <= 2:
        days_a = random.randint(6, 20)
        days_b = random.randint(6, 20)
        fa, fb = Fraction(1, days_a), Fraction(1, days_b)
        together = fa + fb
        result = 1 / together
        ans = f"{result.numerator}/{result.denominator}" if result.denominator != 1 else str(result.numerator)
        return f"一项工程，甲独做{days_a}天完成，乙独做{days_b}天完成，两人合作几天完成？", f"{ans} 天"
    elif difficulty <= 4:
        days_a = random.randint(10, 20)
        days_b = random.randint(10, 20)
        work_days = random.randint(2, 5)
        fa, fb = Fraction(1, days_a), Fraction(1, days_b)
        done = fb * work_days
        remain = 1 - done
        together = fa + fb
        need = remain / together
        ans = f"{need.numerator}/{need.denominator}" if need.denominator != 1 else str(need.numerator)
        return (
            f"一项工程，甲独做{days_a}天完成，乙独做{days_b}天完成。"
            f"乙先做{work_days}天后，甲乙合作完成剩余工程，还需几天？",
            f"{ans} 天"
        )
    else:
        # 三人轮流
        days_a = random.choice([12, 15, 18, 20, 24])
        days_b = random.choice([12, 15, 18, 20, 24])
        days_c = random.choice([12, 15, 18, 20, 24])
        fa, fb, fc = Fraction(1, days_a), Fraction(1, days_b), Fraction(1, days_c)
        cycle = fa + fb + fc
        # 简化答案
        total_days = 1 / cycle * 3
        ans_approx = round(float(total_days), 1)
        return (
            f"一项工程，甲独做{days_a}天，乙独做{days_b}天，丙独做{days_c}天。"
            f"三人按甲、乙、丙的顺序轮流各做一天，完成这项工程共需约多少天？",
            f"约{ans_approx}天"
        )


@register("app_concentration")
def app_concentration(difficulty: int, grade: int):
    """浓度问题"""
    if difficulty <= 2:
        solution = random.randint(100, 500)
        rate = random.randint(5, 30)
        solute = solution * rate // 100
        return f"{solution}克盐水中含盐{rate}%，含盐多少克？", f"{solute} 克"
    elif difficulty <= 4:
        s1 = random.randint(100, 300)
        r1 = random.randint(10, 20)
        s2 = random.randint(100, 300)
        r2 = random.randint(25, 40)
        total_solute = s1 * r1 / 100 + s2 * r2 / 100
        total_solution = s1 + s2
        new_rate = round(total_solute / total_solution * 100, 1)
        return (
            f"将{s1}克浓度为{r1}%的盐水与{s2}克浓度为{r2}%的盐水混合，"
            f"混合后浓度是多少？",
            f"{new_rate}%"
        )
    else:
        # 蒸发/加盐
        solution = random.randint(200, 500)
        rate = random.randint(10, 20)
        target_rate = rate + random.randint(5, 15)
        solute = solution * rate / 100
        new_solution = solute / (target_rate / 100)
        evaporate = solution - new_solution
        return (
            f"有{solution}克浓度为{rate}%的盐水，要使浓度变为{target_rate}%，"
            f"需要蒸发掉多少克水？",
            f"{evaporate:.1f} 克" if evaporate != int(evaporate) else f"{int(evaporate)} 克"
        )


@register("app_profit")
def app_profit(difficulty: int, grade: int):
    """利润与折扣"""
    if difficulty <= 2:
        cost = random.randint(50, 200)
        profit_rate = random.randint(20, 50)
        sell = cost * (100 + profit_rate) // 100
        return f"一件商品进价{cost}元，按{profit_rate}%的利润率定价，售价多少元？", f"{sell} 元"
    elif difficulty <= 4:
        cost = random.randint(100, 500)
        markup = random.randint(30, 60)
        discount = random.choice([80, 85, 90])
        marked = cost * (100 + markup) // 100
        sell = marked * discount // 100
        profit = sell - cost
        real_rate = round(profit / cost * 100, 1)
        return (
            f"商品进价{cost}元，加价{markup}%标价，再打{'八' if discount==80 else '八五' if discount==85 else '九'}折出售，"
            f"实际利润率是多少？",
            f"{real_rate}%"
        )
    else:
        cost = random.randint(100, 300)
        total = random.randint(50, 200)
        profit_rate1 = random.randint(30, 50)
        sell1 = int(total * 0.6)
        sell2 = total - sell1
        discount = random.choice([70, 75, 80])
        price1 = cost * (100 + profit_rate1) // 100
        price2 = price1 * discount // 100
        total_revenue = sell1 * price1 + sell2 * price2
        total_cost = total * cost
        total_profit = total_revenue - total_cost
        return (
            f"商店购进{total}件商品，每件进价{cost}元。先按{profit_rate1}%利润率定价售出{sell1}件，"
            f"剩余按{'七' if discount==70 else '七五' if discount==75 else '八'}折售出。总利润是多少元？",
            f"{total_profit} 元"
        )


@register("app_fraction")
def app_fraction(difficulty: int, grade: int):
    """分数应用题"""
    if difficulty <= 2:
        total = random.randint(60, 300)
        while total % 5 == 0 and total % 3 == 0:
            total += 1
        frac = random.choice([(1, 3), (1, 4), (2, 5), (3, 8)])
        while total % frac[1] != 0:
            total += 1
        part = total * frac[0] // frac[1]
        return f"一袋米重{total}千克，吃了{frac[0]}/{frac[1]}，吃了多少千克？还剩多少千克？", f"吃了{part}千克，还剩{total-part}千克"
    elif difficulty <= 4:
        total = random.choice([120, 150, 180, 200, 240, 300])
        f1 = random.choice([(1, 4), (1, 5), (1, 6)])
        f2 = random.choice([(1, 3), (2, 5), (3, 8)])
        p1 = total * f1[0] // f1[1]
        p2 = total * f2[0] // f2[1]
        remain = total - p1 - p2
        return (
            f"一本书共{total}页，第一天看了{f1[0]}/{f1[1]}，第二天看了{f2[0]}/{f2[1]}，"
            f"还剩多少页没看？",
            f"{remain} 页"
        )
    else:
        # 比多比少
        a = random.randint(60, 150)
        frac_more = random.choice([(1, 4), (1, 5), (2, 5), (1, 3)])
        b = a * (1 + Fraction(frac_more[0], frac_more[1]))
        b_val = int(b) if b == int(b) else float(b)
        return (
            f"甲有{a}元，乙比甲多{frac_more[0]}/{frac_more[1]}，乙有多少元？"
            f"甲乙共有多少元？",
            f"乙有{b_val}元，共有{a + b_val}元"
        )


# ═══════════════════════════════════════════════════════════
# 五、统计与概率（新增）
# ═══════════════════════════════════════════════════════════

@register("stat_average")
def stat_average(difficulty: int, grade: int):
    """平均数与统计"""
    if difficulty <= 2:
        nums = [random.randint(60, 100) for _ in range(5)]
        avg = sum(nums) / 5
        ans = f"{avg:.1f}" if avg != int(avg) else str(int(avg))
        return f"5次测验成绩分别为{'、'.join(map(str, nums))}分，求平均分。", f"{ans} 分"
    elif difficulty <= 4:
        # 加权平均
        n1 = random.randint(5, 15)
        avg1 = random.randint(70, 90)
        n2 = random.randint(5, 15)
        avg2 = random.randint(70, 90)
        total_avg = (n1 * avg1 + n2 * avg2) / (n1 + n2)
        return (
            f"甲组{n1}人平均分{avg1}分，乙组{n2}人平均分{avg2}分，"
            f"两组合在一起的平均分是多少？",
            f"{total_avg:.1f} 分"
        )
    else:
        # 去掉最高最低
        nums = sorted([random.randint(70, 100) for _ in range(7)])
        trimmed = nums[1:-1]
        avg_all = sum(nums) / 7
        avg_trim = sum(trimmed) / 5
        return (
            f"7位评委打分：{'、'.join(map(str, nums))}。"
            f"（1）求平均分；（2）去掉一个最高分和一个最低分后求平均分。",
            f"（1）{avg_all:.1f}分（2）{avg_trim:.1f}分"
        )


@register("stat_probability")
def stat_probability(difficulty: int, grade: int):
    """可能性与概率"""
    if difficulty <= 2:
        red = random.randint(2, 6)
        blue = random.randint(2, 6)
        total = red + blue
        return (
            f"袋中有{red}个红球和{blue}个蓝球，任意摸一个，"
            f"摸到红球的可能性是多少？",
            f"{red}/{total}"
        )
    elif difficulty <= 4:
        red = random.randint(2, 5)
        blue = random.randint(2, 5)
        green = random.randint(1, 3)
        total = red + blue + green
        return (
            f"袋中有{red}个红球、{blue}个蓝球、{green}个绿球。"
            f"（1）摸到红球的可能性是多少？（2）摸到不是绿球的可能性是多少？",
            f"（1）{red}/{total}（2）{red+blue}/{total}"
        )
    else:
        # 至少/至多
        total_balls = random.randint(8, 15)
        colors = 3
        return (
            f"袋中有红、黄、蓝三种颜色的球共{total_balls}个（每种至少1个），"
            f"至少摸出几个球，才能保证有2个同色的？",
            f"4个（抽屉原理：3种颜色+1=4）"
        )


# ═══════════════════════════════════════════════════════════
# 六、逻辑推理与奥数思维（新增拔高）
# ═══════════════════════════════════════════════════════════

@register("logic_reasoning")
def logic_reasoning(difficulty: int, grade: int):
    """逻辑推理"""
    if difficulty <= 2:
        names = ["小明", "小红", "小刚"]
        items = ["语文", "数学", "英语"]
        random.shuffle(items)
        hints = [
            f"{names[0]}不学{items[1]}",
            f"{names[1]}不学{items[0]}也不学{items[2]}",
        ]
        return (
            f"{names[0]}、{names[1]}、{names[2]}分别参加{items[0]}、{items[1]}、{items[2]}兴趣小组。"
            f"已知：①{hints[0]}；②{hints[1]}。"
            f"请判断每人参加什么小组。",
            f"{names[0]}参加{items[0]}，{names[1]}参加{items[1]}，{names[2]}参加{items[2]}"
        )
    elif difficulty <= 4:
        # 鸡兔同笼变式
        heads = random.randint(15, 40)
        legs = random.randint(heads * 2 + 4, heads * 4 - 4)
        while (legs - 2 * heads) % 2 != 0:
            legs += 1
        rabbits = (legs - 2 * heads) // 2
        chickens = heads - rabbits
        if chickens <= 0 or rabbits <= 0:
            chickens, rabbits = 10, 8
            heads, legs = 18, 52
        return (
            f"鸡兔同笼，共有{heads}个头，{legs}条腿，鸡和兔各有多少只？",
            f"鸡{chickens}只，兔{rabbits}只"
        )
    else:
        # 最值问题
        n = random.randint(5, 12)
        total = random.randint(50, 150)
        return (
            f"把{total}分成{n}个不同的自然数之和，要使其中最大的数尽可能小，"
            f"这个最大的数最小是多少？",
            f"{_min_max_partition(total, n)}"
        )


def _min_max_partition(total: int, n: int) -> int:
    """将total分成n个不同自然数，使最大值最小"""
    # 最小和 = 1+2+...+n = n(n+1)/2
    min_sum = n * (n + 1) // 2
    extra = total - min_sum
    if extra < 0:
        return total  # 无法分成n个不同自然数
    # 均分extra
    base = list(range(1, n + 1))
    add_each = extra // n
    remainder = extra % n
    for i in range(n):
        base[i] += add_each
    for i in range(n - remainder, n):
        base[i] += 1
    return base[-1]


@register("logic_pattern")
def logic_pattern(difficulty: int, grade: int):
    """找规律与数列"""
    if difficulty <= 2:
        start = random.randint(1, 5)
        diff = random.randint(2, 7)
        seq = [start + diff * i for i in range(5)]
        return f"找规律填数：{'、'.join(map(str, seq))}、___、___", f"{seq[-1]+diff}、{seq[-1]+2*diff}"
    elif difficulty <= 4:
        # 等比或斐波那契变式
        a, b = random.randint(1, 3), random.randint(2, 4)
        seq = [a, b]
        for _ in range(5):
            seq.append(seq[-1] + seq[-2])
        return f"找规律：{'、'.join(map(str, seq[:5]))}、___、___", f"{seq[5]}、{seq[6]}"
    else:
        # 平方数列
        offset = random.randint(0, 2)
        seq = [(i + offset) ** 2 for i in range(1, 7)]
        return f"找规律：{'、'.join(map(str, seq[:5]))}、___", f"{seq[5]}"


@register("logic_combinatorics")
def logic_combinatorics(difficulty: int, grade: int):
    """排列组合与计数"""
    if difficulty <= 2:
        n = random.randint(3, 5)
        return f"{n}个人互相握手，一共要握多少次手？", f"{n*(n-1)//2} 次"
    elif difficulty <= 4:
        n = random.randint(4, 6)
        k = random.randint(2, 3)
        # C(n,k)
        result = math.factorial(n) // (math.factorial(k) * math.factorial(n - k))
        return f"从{n}个人中选{k}个人参加比赛，有多少种选法？", f"{result} 种"
    else:
        # 路径计数
        m = random.randint(3, 5)
        n = random.randint(3, 5)
        # C(m+n-2, m-1)
        result = math.factorial(m + n - 2) // (math.factorial(m - 1) * math.factorial(n - 1))
        return (
            f"从A到B要经过{m}×{n}的方格（只能向右或向下走），"
            f"共有多少种不同走法？",
            f"{result} 种"
        )


# ═══════════════════════════════════════════════════════════
# 七、数与代数（补充核心知识点）
# ═══════════════════════════════════════════════════════════

@register("number_gcd_lcm")
def number_gcd_lcm(difficulty: int, grade: int):
    """最大公因数与最小公倍数"""
    if difficulty <= 2:
        a = random.randint(6, 30)
        b = random.randint(6, 30)
        g = math.gcd(a, b)
        l = a * b // g
        return f"求{a}和{b}的最大公因数和最小公倍数。", f"最大公因数{g}，最小公倍数{l}"
    elif difficulty <= 4:
        a = random.randint(12, 48)
        b = random.randint(12, 48)
        c = random.randint(12, 48)
        g = math.gcd(math.gcd(a, b), c)
        l = a * b // math.gcd(a, b)
        l = l * c // math.gcd(l, c)
        return f"求{a}、{b}、{c}的最大公因数和最小公倍数。", f"最大公因数{g}，最小公倍数{l}"
    else:
        # 应用：铺地砖/裁纸
        a = random.choice([24, 36, 48, 60, 72])
        b = random.choice([18, 30, 42, 54, 66])
        g = math.gcd(a, b)
        count = (a // g) * (b // g)
        return (
            f"一张长{a}cm、宽{b}cm的长方形纸，要裁成同样大小的正方形且没有剩余，"
            f"正方形的边长最大是多少？可以裁多少块？",
            f"边长最大{g} cm，可以裁{count}块"
        )


@register("number_negative")
def number_negative(difficulty: int, grade: int):
    """负数与数轴"""
    if difficulty <= 2:
        a = random.randint(-20, -1)
        b = random.randint(1, 20)
        return f"计算：({a}) + {b} = ", str(a + b)
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
        return f"计算：{expr} = ", str(ans)
    else:
        a = random.randint(-10, -2)
        b = random.randint(2, 10)
        c = random.randint(-10, -2)
        ans = a * b + c
        return f"计算：({a}) × {b} + ({c}) = ", str(ans)


# ═══════════════════════════════════════════════════════════
# 八、单位换算
# ═══════════════════════════════════════════════════════════

@register("unit_conversion")
def unit_conversion(difficulty: int, grade: int):
    """单位换算（长度/面积/体积/重量/时间）"""
    if difficulty <= 2:
        conversions = [
            ("千米", "米", 1000, random.randint(2, 9)),
            ("米", "厘米", 100, random.randint(2, 9)),
            ("吨", "千克", 1000, random.randint(2, 8)),
            ("千克", "克", 1000, random.randint(2, 9)),
            ("时", "分", 60, random.randint(2, 5)),
            ("分", "秒", 60, random.randint(2, 9)),
        ]
        big, small, rate, val = random.choice(conversions)
        return f"{val}{big} = ___{small}", f"{val * rate} {small}"
    elif difficulty <= 4:
        conversions = [
            ("平方米", "平方分米", 100, random.randint(3, 20)),
            ("平方分米", "平方厘米", 100, random.randint(3, 20)),
            ("立方米", "立方分米", 1000, random.randint(2, 9)),
            ("立方分米", "立方厘米", 1000, random.randint(2, 9)),
            ("升", "毫升", 1000, random.randint(2, 8)),
            ("公顷", "平方米", 10000, random.randint(2, 5)),
        ]
        big, small, rate, val = random.choice(conversions)
        return f"{val}{big} = ___{small}", f"{val * rate} {small}"
    else:
        # 混合单位 / 复名数
        cases = [
            lambda: (
                f"3千米500米 = ___米",
                "3500 米"
            ),
            lambda: (
                f"2时45分 = ___分",
                "165 分"
            ),
            lambda: (
                f"4.05吨 = ___吨___千克",
                "4吨50千克"
            ),
            lambda: (
                f"2平方米30平方分米 = ___平方分米",
                "230 平方分米"
            ),
            lambda: (
                f"3.6立方米 = ___立方米___立方分米",
                "3立方米600立方分米"
            ),
        ]
        q, a = random.choice(cases)()
        return q, a


# ═══════════════════════════════════════════════════════════
# 九、数的整除与互化
# ═══════════════════════════════════════════════════════════

@register("number_divisibility")
def number_divisibility(difficulty: int, grade: int):
    """整除特征、质数合数、分解质因数"""
    if difficulty <= 2:
        n = random.randint(10, 200)
        div_by_2 = n % 2 == 0
        div_by_5 = n % 5 == 0
        div_by_3 = sum(int(d) for d in str(n)) % 3 == 0
        divisors = []
        if div_by_2:
            divisors.append("2")
        if div_by_3:
            divisors.append("3")
        if div_by_5:
            divisors.append("5")
        ans = "、".join(divisors) if divisors else "2、3、5都不能整除"
        return f"{n}能被2、3、5中的哪些数整除？", ans
    elif difficulty <= 4:
        # 分解质因数
        composites = [12, 18, 24, 30, 36, 42, 48, 56, 60, 72, 84, 90]
        n = random.choice(composites)
        factors = _prime_factorize(n)
        factor_str = "×".join(map(str, factors))
        return f"把{n}分解质因数。", f"{n} = {factor_str}"
    else:
        # 综合：求满足条件的数
        # 同时被2、3、5整除 → 是30的倍数
        low = random.randint(1, 5) * 30
        high = low + random.randint(3, 8) * 30
        multiples = list(range(low, high + 1, 30))
        if len(multiples) < 2:
            multiples = [30, 60, 90]
        return (
            f"在{multiples[0]-20}到{multiples[-1]+20}之间，"
            f"同时是2、3、5的倍数的数有哪些？共有几个？",
            f"{'、'.join(map(str, multiples))}，共{len(multiples)}个"
        )


def _prime_factorize(n: int) -> list:
    """分解质因数"""
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
    """分数、小数、百分数互化与大小比较"""
    if difficulty <= 2:
        # 分数→小数
        pairs = [(1, 2), (1, 4), (3, 4), (1, 5), (2, 5), (1, 8), (3, 8), (1, 20)]
        n, d = random.choice(pairs)
        decimal = n / d
        return f"把 {n}/{d} 化成小数。", f"{decimal}"
    elif difficulty <= 4:
        # 小数→百分数 或 分数→百分数
        cases = [
            lambda: (f"把 0.{random.randint(1,9)}{random.randint(0,9)} 化成百分数。", None),
            lambda: (
                f"把 {random.randint(1,7)}/{random.choice([8,10,20,25])} 化成百分数。",
                None
            ),
        ]
        # 用确定性计算
        dec_choices = [0.35, 0.75, 0.125, 0.6, 0.875, 0.04, 1.2]
        dec = random.choice(dec_choices)
        pct = dec * 100
        pct_str = f"{pct:.1f}%" if pct != int(pct) else f"{int(pct)}%"
        return f"把 {dec} 化成百分数。", pct_str
    else:
        # 大小比较：排列
        nums_raw = [
            ("2/3", 2/3), ("0.6", 0.6), ("65%", 0.65),
            ("3/5", 3/5), ("0.58", 0.58), ("7/10", 0.7),
            ("3/4", 0.75), ("0.8", 0.8), ("75%", 0.75),
            ("5/8", 0.625), ("0.67", 0.67), ("2/5", 0.4),
        ]
        selected = random.sample(nums_raw, 4)
        sorted_sel = sorted(selected, key=lambda x: x[1])
        display = "、".join(s[0] for s in selected)
        answer = " < ".join(s[0] for s in sorted_sel)
        return f"把 {display} 按从小到大的顺序排列。", answer


# ═══════════════════════════════════════════════════════════
# 十、图形认识与位置
# ═══════════════════════════════════════════════════════════

@register("geo_recognition")
def geo_recognition(difficulty: int, grade: int):
    """图形认识与分类（角、三角形、四边形、对称轴）"""
    if difficulty <= 2:
        angle = random.choice([30, 45, 60, 90, 120, 135, 150, 180])
        if angle < 90:
            kind = "锐角"
        elif angle == 90:
            kind = "直角"
        elif angle < 180:
            kind = "钝角"
        else:
            kind = "平角"
        return f"一个角是{angle}°，它是什么角？", kind
    elif difficulty <= 4:
        questions = [
            ("等边三角形有几个对称轴？", "3条"),
            ("正方形有几条对称轴？", "4条"),
            ("等腰梯形有几条对称轴？", "1条"),
            ("圆有几条对称轴？", "无数条"),
            ("平行四边形是轴对称图形吗？", "不是（一般平行四边形没有对称轴）"),
            ("三角形按角分类有哪三种？", "锐角三角形、直角三角形、钝角三角形"),
            ("一个三角形中最多有几个钝角？", "最多1个"),
        ]
        q, a = random.choice(questions)
        return q, a
    else:
        # 综合判断
        cases = [
            (
                "一个三角形的三个内角度数比是1:2:3，这个三角形是什么三角形？",
                "直角三角形（30°+60°+90°）"
            ),
            (
                "一个等腰三角形的顶角是80°，底角是多少度？",
                "50°"
            ),
            (
                "一个等腰三角形的一个底角是45°，顶角是多少度？它又是什么三角形？",
                "顶角90°，是等腰直角三角形"
            ),
            (
                "用一根36cm的铁丝围成一个等腰三角形，腰长是底边的2倍，各边长多少？",
                "底边6cm，腰长12cm（设底x，则2x+2x+x=36不对...设底x腰2x：x+2x+2x=36，x=7.2）底7.2cm，腰14.4cm"
            ),
        ]
        q, a = random.choice(cases)
        return q, a


@register("geo_position")
def geo_position(difficulty: int, grade: int):
    """位置与方向（数对、方向距离）"""
    if difficulty <= 2:
        col = random.randint(1, 8)
        row = random.randint(1, 8)
        return (
            f"小明坐在教室第{col}列第{row}行，用数对表示他的位置。",
            f"({col}, {row})"
        )
    elif difficulty <= 4:
        dist = random.randint(200, 1000)
        dist_round = dist // 100 * 100
        direction = random.choice(["东", "南", "西", "北", "东北", "东南", "西北", "西南"])
        return (
            f"学校在邮局的{direction}方向{dist_round}米处。"
            f"如果比例尺是1:10000，在图上应画多长？",
            f"{dist_round/10000*100:.1f} cm" if dist_round % 1000 != 0 else f"{dist_round//1000} cm"
        )
    else:
        # 路线描述
        return (
            "以学校为观测点：图书馆在学校北偏东30°方向600米处，"
            "医院在学校南偏西45°方向400米处。"
            "请描述从图书馆经学校到医院的路线和总距离。",
            "从图书馆向南偏西30°走600米到学校，再向南偏西45°走400米到医院，总距离1000米"
        )


# ═══════════════════════════════════════════════════════════
# 十一、经典应用题补充
# ═══════════════════════════════════════════════════════════

@register("app_chicken_rabbit")
def app_chicken_rabbit(difficulty: int, grade: int):
    """鸡兔同笼及变式"""
    if difficulty <= 2:
        chickens = random.randint(5, 20)
        rabbits = random.randint(3, 15)
        heads = chickens + rabbits
        legs = chickens * 2 + rabbits * 4
        return (
            f"鸡兔同笼，共有{heads}个头，{legs}条腿。鸡和兔各有多少只？",
            f"鸡{chickens}只，兔{rabbits}只"
        )
    elif difficulty <= 4:
        # 变式：轮子问题（自行车+三轮车）
        bikes = random.randint(5, 15)
        trikes = random.randint(3, 10)
        total = bikes + trikes
        wheels = bikes * 2 + trikes * 3
        return (
            f"停车场有自行车和三轮车共{total}辆，共有{wheels}个轮子。"
            f"自行车和三轮车各有多少辆？",
            f"自行车{bikes}辆，三轮车{trikes}辆"
        )
    else:
        # 百僧百馍 / 得分问题
        total_q = random.randint(15, 25)
        score_right = random.randint(4, 5)
        score_wrong = random.randint(1, 2)
        total_score = random.randint(50, 90)
        # 设答对x题: score_right*x - score_wrong*(total_q-x) = total_score
        x = (total_score + score_wrong * total_q) / (score_right + score_wrong)
        if x != int(x) or x < 0 or x > total_q:
            total_q, score_right, score_wrong, total_score = 20, 5, 2, 72
            x = (72 + 2 * 20) / (5 + 2)  # = 112/7 = 16
        x = int(x)
        wrong = total_q - x
        return (
            f"数学竞赛共{total_q}题，答对一题得{score_right}分，答错一题扣{score_wrong}分。"
            f"小明得了{total_score}分，他答对了几题？",
            f"答对{x}题，答错{wrong}题"
        )


@register("app_tree_planting")
def app_tree_planting(difficulty: int, grade: int):
    """植树问题（两端/一端/环形/锯木/爬楼）"""
    if difficulty <= 2:
        # 两端都种
        interval = random.randint(3, 8)
        length = interval * random.randint(5, 20)
        trees = length // interval + 1
        return (
            f"一条路长{length}米，每隔{interval}米种一棵树（两端都种），共需多少棵树？",
            f"{trees} 棵"
        )
    elif difficulty <= 4:
        # 环形 / 只种一端
        mode = random.choice(["ring", "one_end"])
        interval = random.randint(3, 6)
        count = random.randint(8, 20)
        length = interval * count
        if mode == "ring":
            return (
                f"一个圆形花坛周长{length}米，每隔{interval}米种一棵月季，共需多少棵？",
                f"{count} 棵（环形：棵数=间隔数）"
            )
        else:
            return (
                f"一条路长{length}米，从一端开始每隔{interval}米种一棵树（另一端不种），共需多少棵？",
                f"{count} 棵"
            )
    else:
        # 锯木头 / 爬楼梯
        cases = [
            lambda: (
                f"把一根木头锯成{random.randint(5,9)}段，每锯一次要3分钟，一共需要多少分钟？",
                None
            ),
            lambda: (
                f"小明从1楼走到5楼，每层楼梯有{random.randint(12,20)}级台阶，他一共要走多少级台阶？",
                None
            ),
        ]
        idx = random.randint(0, 1)
        if idx == 0:
            pieces = random.randint(5, 9)
            time_per = 3
            total_time = (pieces - 1) * time_per
            return f"把一根木头锯成{pieces}段，每锯一次要{time_per}分钟，一共需要多少分钟？", f"{total_time} 分钟"
        else:
            floors = random.randint(4, 8)
            steps = random.randint(12, 20)
            total_steps = (floors - 1) * steps
            return f"小明从1楼走到{floors}楼，每层楼梯有{steps}级台阶，他一共要走多少级台阶？", f"{total_steps} 级"


@register("app_sum_difference")
def app_sum_difference(difficulty: int, grade: int):
    """和差问题、和倍问题、差倍问题"""
    if difficulty <= 2:
        # 和差问题
        big = random.randint(20, 80)
        small = random.randint(10, big - 1)
        total = big + small
        diff = big - small
        return (
            f"两个数的和是{total}，差是{diff}，求这两个数。",
            f"大数{big}，小数{small}"
        )
    elif difficulty <= 4:
        # 和倍问题
        small = random.randint(10, 40)
        multiple = random.randint(2, 5)
        big = small * multiple
        total = big + small
        return (
            f"甲乙两数的和是{total}，甲是乙的{multiple}倍，甲乙各是多少？",
            f"乙={small}，甲={big}"
        )
    else:
        # 差倍问题
        small = random.randint(10, 30)
        multiple = random.randint(2, 4)
        big = small * multiple
        diff = big - small
        return (
            f"甲数是乙数的{multiple}倍，甲比乙多{diff}，甲乙各是多少？",
            f"乙={small}，甲={big}"
        )


@register("app_proportional_dist")
def app_proportional_dist(difficulty: int, grade: int):
    """按比例分配"""
    if difficulty <= 2:
        a_ratio = random.randint(2, 5)
        b_ratio = random.randint(2, 5)
        unit = random.randint(10, 50)
        total = (a_ratio + b_ratio) * unit
        part_a = a_ratio * unit
        part_b = b_ratio * unit
        return (
            f"把{total}按{a_ratio}:{b_ratio}分配给甲乙两人，各得多少？",
            f"甲{part_a}，乙{part_b}"
        )
    elif difficulty <= 4:
        # 三方分配
        r1, r2, r3 = random.randint(2, 4), random.randint(2, 4), random.randint(2, 4)
        unit = random.randint(10, 30)
        total = (r1 + r2 + r3) * unit
        return (
            f"学校把{total}本图书按{r1}:{r2}:{r3}分给四、五、六年级，各年级分到多少本？",
            f"四年级{r1*unit}本，五年级{r2*unit}本，六年级{r3*unit}本"
        )
    else:
        # 面积分配 / 带条件
        total_area = random.choice([120, 180, 240, 360, 480])
        r1, r2, r3 = 3, 2, 1
        while total_area % (r1 + r2 + r3) != 0:
            total_area += 10
        unit = total_area // (r1 + r2 + r3)
        return (
            f"一块{total_area}平方米的地，按3:2:1种水稻、小麦和蔬菜。"
            f"（1）各种多少平方米？（2）水稻面积比蔬菜多多少平方米？",
            f"（1）水稻{3*unit}m²，小麦{2*unit}m²，蔬菜{unit}m²（2）多{2*unit}m²"
        )


# ═══════════════════════════════════════════════════════════
# 十二、统计图与优化策略
# ═══════════════════════════════════════════════════════════

@register("stat_chart")
def stat_chart(difficulty: int, grade: int):
    """统计图读图分析（条形/折线/扇形）"""
    if difficulty <= 2:
        # 条形图读数
        items = ["周一", "周二", "周三", "周四", "周五"]
        values = [random.randint(20, 100) for _ in range(5)]
        max_idx = values.index(max(values))
        return (
            f"某商店一周前5天营业额（万元）：{'、'.join(f'{items[i]}{values[i]}' for i in range(5))}。"
            f"哪天营业额最高？5天平均营业额是多少万元？",
            f"{items[max_idx]}最高；平均{sum(values)/5:.1f}万元"
        )
    elif difficulty <= 4:
        # 扇形图百分比
        total_people = random.choice([200, 300, 400, 500])
        pct_a = random.randint(30, 50)
        pct_b = random.randint(20, 35)
        pct_c = 100 - pct_a - pct_b
        num_a = total_people * pct_a // 100
        num_b = total_people * pct_b // 100
        num_c = total_people - num_a - num_b
        if num_b >= num_c:
            q2 = "参加音乐的比美术的多多少人？"
            a2 = f"多{num_b - num_c}人"
        else:
            q2 = "参加美术的比音乐的多多少人？"
            a2 = f"多{num_c - num_b}人"
        return (
            f"某校{total_people}名学生参加课外活动：体育{pct_a}%、音乐{pct_b}%、美术{pct_c}%。"
            f"（1）参加体育的有多少人？（2）{q2}",
            f"（1）{num_a}人（2）{a2}"
        )
    else:
        # 折线图趋势 + 计算
        months = ["1月", "2月", "3月", "4月", "5月", "6月"]
        base = random.randint(100, 300)
        values = [base + random.randint(-30, 50) for _ in range(6)]
        max_v = max(values)
        min_v = min(values)
        max_month = months[values.index(max_v)]
        min_month = months[values.index(min_v)]
        return (
            f"某地上半年月降水量(mm)：{'、'.join(f'{months[i]}:{values[i]}' for i in range(6))}。"
            f"（1）哪月降水最多？哪月最少？（2）上半年月平均降水量是多少？",
            f"（1）{max_month}最多({max_v}mm)，{min_month}最少({min_v}mm)（2）平均{sum(values)/6:.1f}mm"
        )


@register("logic_optimization")
def logic_optimization(difficulty: int, grade: int):
    """找次品与优化策略（烙饼/沏茶/称量）"""
    if difficulty <= 2:
        # 找次品基础
        n = random.choice([3, 9])
        times = 1 if n == 3 else 2
        return (
            f"{n}个零件中有1个次品（轻一些），用天平至少称几次一定能找到？",
            f"至少{times}次"
        )
    elif difficulty <= 4:
        # 烙饼问题
        cakes = random.choice([3, 5, 7])
        # 每次烙2个，每面2分钟
        total_sides = cakes * 2
        batches = (total_sides + 1) // 2
        total_time = batches * 2
        return (
            f"烙{cakes}个饼，每次只能烙2个，每面需要2分钟。"
            f"烙完所有饼至少需要多少分钟？",
            f"至少{total_time}分钟"
        )
    else:
        # 沏茶问题 / 找次品进阶
        cases = [
            (
                "沏茶需要：洗水壶1分钟、烧水8分钟、洗茶杯2分钟、拿茶叶1分钟、沏茶1分钟。"
                "怎样安排最省时间？最少几分钟？",
                "先洗水壶(1分)→烧水(8分，同时洗茶杯+拿茶叶)→沏茶(1分)，共10分钟"
            ),
            (
                "27个球中有1个次品（重一些），用天平至少称几次一定能找到？请说明方法。",
                "至少3次。每次分3组(9,9,9)→(3,3,3)→(1,1,1)"
            ),
            (
                "小明要骑牛过河，有甲乙丙丁4头牛，过河时间分别为1、2、5、8分钟。"
                "每次只能骑1头赶1头，回来也要骑1头。全部过河最少多少分钟？",
                "15分钟（甲乙过2→甲回1→丙丁过8→乙回2→甲乙过2）"
            ),
        ]
        q, a = random.choice(cases)
        return q, a


# ═══════════════════════════════════════════════════════════
# 主生成函数
# ═══════════════════════════════════════════════════════════

DIFFICULTY_MAP = {
    "基础": (1, 2),
    "提高": (3, 4),
    "拔高": (4, 5),
    "综合": (1, 5),
}


def generate_math_problems(
    grade: int = 6,
    difficulty: str = "综合",
    categories: Optional[List[str]] = None,
    problem_types: Optional[List[str]] = None,
    count: int = 20,
    include_answer: bool = True,
    db: Optional[Session] = None,
) -> List[ProblemItem]:
    """
    主入口：生成数学题
    1. 从DB读取可用题型（或fallback到注册表）
    2. 按权重分配各题型数量
    3. 调用对应生成器
    """
    diff_range = DIFFICULTY_MAP.get(difficulty, (1, 5))

    # 获取可用题型
    available_types = _get_available_types(db, grade, categories, problem_types)

    if not available_types:
        # fallback: 使用所有注册生成器
        available_types = [
            {"code": code, "name": code, "category": "综合", "weight": 10}
            for code in GENERATORS.keys()
        ]

    # 按权重分配题数
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
                question, answer = gen_func(diff, grade)
                problems.append(ProblemItem(
                    id=pid,
                    category=type_info.get("category", "综合"),
                    type_name=type_info.get("name", code),
                    difficulty=diff,
                    question=question,
                    answer=answer if include_answer else "",
                ))
                pid += 1
            except Exception:
                continue

    random.shuffle(problems)
    # 重新编号
    for i, p in enumerate(problems, 1):
        p.id = i
    return problems[:count]


def _get_available_types(db, grade, categories, problem_types):
    """从数据库获取可用题型"""
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
            cat_name = t.category.name if t.category else "综合"
            result.append({
                "code": t.code,
                "name": t.name,
                "category": cat_name,
                "weight": t.weight,
            })
        return result
    except Exception:
        return None


def _allocate_counts(types: List[dict], total: int) -> List[Tuple[dict, int]]:
    """
    全覆盖优先分配策略：
    - total >= 题型数：每种题型先保底1题，剩余按权重分配
    - total < 题型数：按大类均匀抽取，确保每个大类都有代表
    """
    if not types:
        return []

    n_types = len(types)

    if total >= n_types:
        # 全覆盖模式：每种题型至少1题
        allocation_map = {t["code"]: 1 for t in types}
        remaining = total - n_types

        if remaining > 0:
            total_weight = sum(t["weight"] for t in types)
            if total_weight == 0:
                total_weight = n_types
            # 按权重分配剩余
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
        # 题数不够覆盖所有题型：按大类均匀抽取
        # 先按大类分组
        cat_groups: Dict[str, List[dict]] = {}
        for t in types:
            cat_groups.setdefault(t["category"], []).append(t)

        n_cats = len(cat_groups)
        # 每个大类至少分配1题
        per_cat = max(1, total // n_cats)
        remainder = total - per_cat * n_cats

        selected = []
        for i, (cat_name, cat_types) in enumerate(cat_groups.items()):
            cat_quota = per_cat + (1 if i < remainder else 0)
            if cat_quota <= 0:
                continue
            # 大类内按权重选取
            cat_weight = sum(t["weight"] for t in cat_types)
            if cat_quota >= len(cat_types):
                # 大类内全覆盖
                for t in cat_types:
                    selected.append((t, 1))
                extra = cat_quota - len(cat_types)
                if extra > 0 and cat_weight > 0:
                    for t in cat_types:
                        e = round(extra * t["weight"] / cat_weight)
                        if e > 0:
                            selected.append((t, e))
            else:
                # 大类内按权重抽取部分题型
                sorted_types = sorted(cat_types, key=lambda x: x["weight"], reverse=True)
                for t in sorted_types[:cat_quota]:
                    selected.append((t, 1))

        # 合并同一题型的多条记录
        merged: Dict[str, Tuple[dict, int]] = {}
        for t, n in selected:
            if t["code"] in merged:
                merged[t["code"]] = (t, merged[t["code"]][1] + n)
            else:
                merged[t["code"]] = (t, n)

        result = list(merged.values())
        # 截断到total
        actual_total = sum(n for _, n in result)
        if actual_total > total:
            result = result[:total]
            result = [(t, 1) for t, _ in result[:total]]
        return result
