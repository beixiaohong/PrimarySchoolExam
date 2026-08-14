import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register

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

__all__ = [
    "_unit_area",
    "_unit_compare",
    "_unit_compound",
    "_unit_context",
    "_unit_length",
    "_unit_mixed",
    "_unit_multi_step",
    "_unit_real",
    "_unit_reverse",
    "_unit_time",
    "_unit_volume",
    "_unit_weight",
    "unit_conversion",
]
