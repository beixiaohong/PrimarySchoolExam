"""小学几何题生成器

提供平面图形面积(geo_area_plane)、立体图形体积(geo_volume)、周长(geo_perimeter)、
图形变换(geo_transform)、图形认识(geo_recognition)、位置方向(geo_position)、
图形运动(geo_motion) 等题型的随机生成，多数含配图渲染与反推凑整逻辑。
"""
import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


from .common import register

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
        from app.domains.assessment.services.figure_renderer import render_triangle
        img = render_triangle(b, h)
    except Exception:
        img = ""
    return f"三角形底{b}cm、高{h}cm，面积是多少？", f"{s} cm\u00b2", img

def _area_parallelogram():
    """平行四边形面积（底×高），附配图"""
    b, h = random.randint(4, 20), random.randint(3, 15)
    try:
        from app.domains.assessment.services.figure_renderer import render_parallelogram
        img = render_parallelogram(b, h)
    except Exception:
        img = ""
    return f"平行四边形底{b}cm、高{h}cm，面积是多少？", f"{b*h} cm\u00b2", img

def _area_rect_both():
    """长方形面积与周长（同时考两个公式），附配图"""
    l, w = random.randint(5, 25), random.randint(3, 15)
    try:
        from app.domains.assessment.services.figure_renderer import render_rectangle
        img = render_rectangle(l, w)
    except Exception:
        img = ""
    return f"长方形长{l}cm、宽{w}cm，面积和周长各是多少？", f"面积{l*w}cm\u00b2，周长{2*(l+w)}cm", img

def _area_reverse_base():
    """已知三角形面积与高反求底（底=面积×2÷高，凑整除保证底为整数）。"""
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
        from app.domains.assessment.services.figure_renderer import render_trapezoid
        img = render_trapezoid(a, b, h)
    except Exception:
        img = ""
    return f"梯形上底{a}cm、下底{b}cm、高{h}cm，面积？", f"{s} cm\u00b2", img

def _area_circle():
    """圆面积（πr²，π取3.14），附配图"""
    r = random.randint(2, 10)
    area = round(3.14 * r * r, 2)
    try:
        from app.domains.assessment.services.figure_renderer import render_circle
        img = render_circle(r)
    except Exception:
        img = ""
    return f"圆半径{r}cm，求面积。（\u03c0取3.14）", f"{area} cm\u00b2", img

def _area_composite_sub():
    """L形组合面积（大长方形 − 右上角小长方形），附配图"""
    L, W = random.randint(10, 20), random.randint(8, 15)
    l, w = random.randint(3, L-3), random.randint(3, W-3)
    try:
        from app.domains.assessment.services.figure_renderer import render_composite_L
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
        from app.domains.assessment.services.figure_renderer import render_composite_square_circle
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
        from app.domains.assessment.services.figure_renderer import render_composite_rect_triangle
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
        from app.domains.assessment.services.figure_renderer import render_composite_rect_semicircle
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
        from app.domains.assessment.services.figure_renderer import render_cuboid
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
        from app.domains.assessment.services.figure_renderer import render_cylinder
        img = render_cylinder(r, h)
    except Exception:
        img = ""
    return f"圆柱底面半径{r}cm高{h}cm，体积？（\u03c0取3.14）", f"{v} cm\u00b3", img

def _vol_cone():
    """圆锥体积（πr²h÷3，π取3.14），附配图"""
    r, h = random.randint(3, 8), random.randint(6, 18)
    v = round(3.14 * r * r * h / 3, 2)
    try:
        from app.domains.assessment.services.figure_renderer import render_cone
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
        from app.domains.assessment.services.figure_renderer import render_composite_cylinder_cone
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
        from app.domains.assessment.services.figure_renderer import render_composite_cuboid_hole
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

__all__ = [
    "_area_circle",
    "_area_composite_sub",
    "_area_equal_transform",
    "_area_house",
    "_area_inscribed",
    "_area_parallelogram",
    "_area_ratio_2d",
    "_area_rect_both",
    "_area_rect_semicircle",
    "_area_reverse_base",
    "_area_reverse_height",
    "_area_shaded",
    "_area_trapezoid",
    "_area_triangle",
    "_vol_capacity",
    "_vol_cone",
    "_vol_cube",
    "_vol_cuboid",
    "_vol_cuboid_hole",
    "_vol_cylinder",
    "_vol_cylinder_cone",
    "_vol_displacement",
    "_vol_equal_bh",
    "_vol_hollow",
    "_vol_melt",
    "_vol_ratio_3d",
    "_vol_reverse_h",
    "_vol_water_rise",
    "geo_area_plane",
    "geo_motion",
    "geo_perimeter",
    "geo_position",
    "geo_recognition",
    "geo_transform",
    "geo_volume",
]
