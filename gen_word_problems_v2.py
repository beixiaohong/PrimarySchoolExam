"""
小升初数学应用题200道生成器 — 高质量版
12个大类，每个大类多个子类型，所有答案经过参数校验确保正确
"""
import random
import math

random.seed(2026)
ri = random.randint
rc = random.choice


# ==================== 1. 行程问题 ====================

def xingcheng_basic_distance():
    v, t = ri(30, 80), ri(2, 6)
    return f"一辆汽车每小时行{v}千米，行了{t}小时，一共行了多少千米？", f"路程 = {v} × {t} = {v*t}（千米）"

def xingcheng_find_time():
    v = rc([30, 40, 45, 50, 60, 70, 80])
    t = ri(2, 6)
    d = v * t
    return f"甲乙两地相距{d}千米，汽车每小时行{v}千米，需要几小时到达？", f"时间 = {d} ÷ {v} = {t}（小时）"

def xingcheng_find_speed():
    v = ri(30, 70)
    t = ri(3, 6)
    d = v * t
    return f"一辆汽车{t}小时行了{d}千米，平均每小时行多少千米？", f"速度 = {d} ÷ {t} = {v}（千米/小时）"

def xingcheng_round_trip():
    v1 = rc([40, 50, 60])
    t1 = ri(2, 4)
    d = v1 * t1
    v2 = rc([30, 40, 50, 60, 80])
    while d % v2 != 0 or v2 == v1:
        v2 = rc([30, 40, 50, 60, 80])
    t2 = d // v2
    return (f"从A城到B城，去时每小时行{v1}千米，用了{t1}小时。返回时每小时行{v2}千米，返回用了几小时？",
            f"距离 = {v1}×{t1} = {d}千米，返回时间 = {d}÷{v2} = {t2}小时")

def xingcheng_meeting():
    v1, v2 = ri(40, 60), ri(30, 50)
    t = ri(2, 5)
    d = (v1 + v2) * t
    return (f"甲乙两人同时从两地相向而行，甲每小时行{v1}千米，乙每小时行{v2}千米，{t}小时后相遇。两地相距多少千米？",
            f"距离 = ({v1}+{v2}) × {t} = {d}（千米）")

def xingcheng_pursuit():
    v1 = rc([60, 70, 80])
    v2 = rc([30, 40, 50])
    head_start = ri(1, 3)
    diff = v1 - v2
    dist = v2 * head_start
    while dist % diff != 0:
        head_start = ri(1, 3)
        dist = v2 * head_start
    catch_time = dist // diff
    return (f"甲每小时行{v1}千米，乙每小时行{v2}千米。乙先走{head_start}小时，甲几小时后追上乙？",
            f"追及距离 = {v2}×{head_start} = {dist}千米，速度差 = {diff}千米/时，追及时间 = {dist}÷{diff} = {catch_time}小时")

def xingcheng_boat():
    v_boat = rc([20, 25, 30, 35, 40])
    v_water = rc([3, 4, 5, 6])
    return (f"船在静水中的速度是每小时{v_boat}千米，水流速度是每小时{v_water}千米。顺水速度是多少？逆水速度是多少？",
            f"顺水速度 = {v_boat}+{v_water} = {v_boat+v_water}千米/时，逆水速度 = {v_boat}-{v_water} = {v_boat-v_water}千米/时")

def xingcheng_avg_speed():
    d = rc([60, 80, 90, 100, 120])
    v1 = rc([30, 40, 60])
    v2 = rc([40, 50, 60])
    while d % v1 != 0 or d % v2 != 0:
        d = rc([60, 80, 90, 100, 120])
        v1 = rc([30, 40, 60])
        v2 = rc([40, 50, 60])
    t1, t2 = d // v1, d // v2
    total_d, total_t = 2 * d, t1 + t2
    while total_d % total_t != 0:
        d = rc([60, 80, 90, 100, 120])
        v1 = rc([30, 40, 60])
        v2 = rc([40, 50, 60])
        if d % v1 != 0 or d % v2 != 0:
            continue
        t1, t2 = d // v1, d // v2
        total_d, total_t = 2 * d, t1 + t2
    avg = total_d // total_t
    return (f"上山{d}千米速度{v1}千米/时，下山原路返回速度{v2}千米/时。上下山平均速度是多少？",
            f"总路程 = {d}+{d} = {total_d}千米，总时间 = {t1}+{t2} = {total_t}小时，平均速度 = {total_d}÷{total_t} = {avg}千米/时")

XINGCHENG = [xingcheng_basic_distance, xingcheng_find_time, xingcheng_find_speed,
             xingcheng_round_trip, xingcheng_meeting, xingcheng_pursuit,
             xingcheng_boat, xingcheng_avg_speed]


# ==================== 2. 工程问题 ====================

def gongcheng_coop():
    pairs = [(6, 12), (8, 24), (10, 15), (12, 6), (4, 12), (5, 20), (6, 3), (10, 10), (8, 8)]
    a, b = rc(pairs)
    lcm_val = (a * b) // math.gcd(a, b)
    eff_a, eff_b = lcm_val // a, lcm_val // b
    total_eff = eff_a + eff_b
    while lcm_val % total_eff != 0:
        a, b = rc(pairs)
        lcm_val = (a * b) // math.gcd(a, b)
        eff_a, eff_b = lcm_val // a, lcm_val // b
        total_eff = eff_a + eff_b
    days = lcm_val // total_eff
    return (f"一项工程，甲独做{a}天完成，乙独做{b}天完成。两人合做几天完成？",
            f"甲效率=1/{a}，乙效率=1/{b}，合做效率=1/{a}+1/{b}={total_eff}/{lcm_val}，天数={lcm_val}÷{total_eff}={days}天")

def gongcheng_partial():
    pairs = [(10, 15), (12, 8), (8, 12), (6, 12)]
    a, b = rc(pairs)
    lcm_val = (a * b) // math.gcd(a, b)
    eff_a, eff_b = lcm_val // a, lcm_val // b
    total_eff = eff_a + eff_b
    pre_days = ri(1, max(a // 2, 2))
    done = pre_days * eff_a
    remain = lcm_val - done
    while remain <= 0 or remain % total_eff != 0:
        pre_days = ri(1, max(a // 2, 2))
        done = pre_days * eff_a
        remain = lcm_val - done
    coop_days = remain // total_eff
    return (f"一项工程，甲独做{a}天完成，乙独做{b}天完成。甲先做{pre_days}天，剩下的甲乙合做几天完成？",
            f"甲效率=1/{a}，{pre_days}天完成{pre_days}/{a}，剩{remain}/{lcm_val}，合做效率={total_eff}/{lcm_val}，还需{remain}÷{total_eff}={coop_days}天")

def gongcheng_three():
    triples = [(6, 12, 4), (10, 15, 6), (8, 24, 12), (4, 6, 12)]
    a, b, c = rc(triples)
    lcm_val = a
    for x in [b, c]:
        lcm_val = lcm_val * x // math.gcd(lcm_val, x)
    eff_a, eff_b, eff_c = lcm_val // a, lcm_val // b, lcm_val // c
    total_eff = eff_a + eff_b + eff_c
    while lcm_val % total_eff != 0:
        a, b, c = rc(triples)
        lcm_val = a
        for x in [b, c]:
            lcm_val = lcm_val * x // math.gcd(lcm_val, x)
        eff_a, eff_b, eff_c = lcm_val // a, lcm_val // b, lcm_val // c
        total_eff = eff_a + eff_b + eff_c
    days = lcm_val // total_eff
    return (f"一项工程，甲独做{a}天完成，乙独做{b}天完成，丙独做{c}天完成。三人合做几天完成？",
            f"合做效率=1/{a}+1/{b}+1/{c}={total_eff}/{lcm_val}，天数={lcm_val}÷{total_eff}={days}天")

GONGCHENG = [gongcheng_coop, gongcheng_partial, gongcheng_three]


# ==================== 3. 浓度问题 ====================

def nongdu_find_concentration():
    salt = rc([10, 15, 20, 25, 30, 40, 50])
    water = rc([50, 100, 150, 200, 250])
    total = salt + water
    while salt * 100 % total != 0:
        salt = rc([10, 15, 20, 25, 30, 40, 50])
        water = rc([50, 100, 150, 200, 250])
        total = salt + water
    pct = salt * 100 // total
    return f"{salt}克盐溶解在{water}克水中，盐水的浓度是多少？", f"浓度 = {salt}÷{total}×100% = {pct}%"

def nongdu_find_salt():
    pct = rc([10, 15, 20, 25, 30])
    total = rc([100, 200, 300, 400, 500])
    salt = total * pct // 100
    return f"{total}克盐水浓度为{pct}%，含盐多少克？", f"含盐 = {total} × {pct}% = {salt}克"

def nongdu_add_water():
    pct1 = rc([20, 30, 40])
    total1 = rc([100, 200, 300])
    salt = total1 * pct1 // 100
    pct2 = rc([10, 15])
    while pct2 >= pct1 or salt * 100 % pct2 != 0:
        pct2 = rc([10, 15])
    total2 = salt * 100 // pct2
    add_water = total2 - total1
    return (f"{total1}克{pct1}%盐水，加入多少克水后浓度变为{pct2}%？",
            f"盐 = {total1}×{pct1}% = {salt}克不变，新溶液 = {salt}÷{pct2}% = {total2}克，加水 = {total2}-{total1} = {add_water}克")

def nongdu_add_salt():
    pct1 = rc([10, 20])
    total1 = rc([100, 200, 300])
    salt1 = total1 * pct1 // 100
    add_salt = rc([20, 25, 40, 50])
    new_salt = salt1 + add_salt
    new_total = total1 + add_salt
    while new_salt * 100 % new_total != 0:
        add_salt = rc([20, 25, 40, 50])
        new_salt = salt1 + add_salt
        new_total = total1 + add_salt
    pct2 = new_salt * 100 // new_total
    return (f"{total1}克{pct1}%盐水中加入{add_salt}克盐，浓度变为多少？",
            f"原盐 = {salt1}克，新盐 = {new_salt}克，新溶液 = {new_total}克，浓度 = {new_salt}÷{new_total}×100% = {pct2}%")

def nongdu_mix():
    p1 = rc([20, 30, 40])
    p2 = rc([10, 20])
    # 用相同质量保证整除
    t = rc([100, 200, 300])
    s1 = t * p1 // 100
    s2 = t * p2 // 100
    salt = s1 + s2
    total = 2 * t
    p_mix = salt * 100 // total
    while salt * 100 % total != 0:
        p1 = rc([20, 30, 40])
        p2 = rc([10, 20])
        s1 = t * p1 // 100
        s2 = t * p2 // 100
        salt = s1 + s2
        p_mix = salt * 100 // total
    return (f"{p1}%盐水{t}克和{p2}%盐水{t}克混合，浓度是多少？",
            f"盐 = {s1}+{s2} = {salt}克，溶液 = {total}克，浓度 = {salt}÷{total}×100% = {p_mix}%")

def nongdu_evaporate():
    pct1 = rc([10, 15, 20])
    total1 = rc([200, 300, 400, 500])
    salt = total1 * pct1 // 100
    evap = rc([50, 100, 150])
    new_total = total1 - evap
    while new_total <= 0 or salt * 100 % new_total != 0:
        evap = rc([50, 100, 150])
        new_total = total1 - evap
    pct2 = salt * 100 // new_total
    return (f"{total1}克{pct1}%盐水蒸发{evap}克水后，浓度变为多少？",
            f"盐 = {salt}克不变，新溶液 = {new_total}克，浓度 = {salt}÷{new_total}×100% = {pct2}%")

NONGDU = [nongdu_find_concentration, nongdu_find_salt, nongdu_add_water,
          nongdu_add_salt, nongdu_mix, nongdu_evaporate]


# ==================== 4. 利润折扣 ====================

def lirun_basic():
    cost = rc([50, 80, 100, 120, 150, 200])
    markup = rc([20, 30, 40, 50, 60])
    price = cost + markup
    return f"商品进价{cost}元，售价{price}元，利润是多少？", f"利润 = {price} - {cost} = {markup}元"

def lirun_profit_rate():
    cost = rc([50, 80, 100, 120, 150, 200])
    markup_pct = rc([10, 20, 25, 30, 40, 50])
    while cost * markup_pct % 100 != 0:
        cost = rc([50, 80, 100, 120, 150, 200])
    profit = cost * markup_pct // 100
    return (f"商品进价{cost}元，加价{markup_pct}%出售，利润是多少？",
            f"利润 = {cost}×{markup_pct}% = {profit}元")

def lirun_discount():
    price = rc([100, 150, 200, 250, 300])
    discount = rc([7, 8, 9])
    while price * discount % 10 != 0:
        price = rc([100, 150, 200, 250, 300])
    actual = price * discount // 10
    return (f"商品原价{price}元，打{discount}折出售，现价多少？",
            f"现价 = {price}×{discount}0% = {actual}元")

def lirun_discount_profit():
    cost = rc([80, 100, 120, 150, 200])
    markup = rc([40, 50, 60, 80, 100])
    price = cost + markup
    discount = rc([8, 9])
    while price * discount % 10 != 0:
        markup = rc([40, 50, 60, 80, 100])
        price = cost + markup
    actual = price * discount // 10
    profit = actual - cost
    while profit <= 0 or profit * 100 % cost != 0:
        cost = rc([80, 100, 120, 150, 200])
        markup = rc([40, 50, 60, 80, 100])
        price = cost + markup
        while price * discount % 10 != 0:
            markup = rc([40, 50, 60, 80, 100])
            price = cost + markup
        actual = price * discount // 10
        profit = actual - cost
    pct = profit * 100 // cost
    return (f"商品进价{cost}元，加价{markup}元后打{discount}折出售，利润和利润率各是多少？",
            f"标价 = {price}元，实际售价 = {actual}元，利润 = {profit}元，利润率 = {profit}÷{cost}×100% = {pct}%")

def lirun_bulk():
    cost = rc([30, 50, 80, 100])
    unit_profit = rc([10, 15, 20, 25, 30])
    price = cost + unit_profit
    qty = rc([10, 20, 30, 50])
    total = unit_profit * qty
    return (f"商品进价{cost}元，售价{price}元，卖出{qty}件，总利润多少？",
            f"每件利润 = {unit_profit}元，总利润 = {unit_profit}×{qty} = {total}元")

LIRUN = [lirun_basic, lirun_profit_rate, lirun_discount, lirun_discount_profit, lirun_bulk]


# ==================== 5. 比例问题 ====================

def bili_ratio_sum():
    sa, sb = rc([(2, 3), (3, 4), (3, 5), (2, 5), (1, 4)])
    total_parts = sa + sb
    total = total_parts * rc([10, 20, 25, 30, 50])
    unit = total // total_parts
    return (f"甲乙之比{sa}:{sb}，两数之和为{total}，甲乙各是多少？",
            f"总份数 = {total_parts}，每份 = {unit}，甲 = {unit*sa}，乙 = {unit*sb}")

def bili_ratio_diff():
    sa, sb = rc([(2, 5), (3, 7), (1, 3), (2, 7), (3, 8)])
    diff_parts = sb - sa
    diff = diff_parts * rc([5, 8, 10, 12, 15, 20])
    unit = diff // diff_parts
    return (f"甲乙之比{sa}:{sb}，乙比甲多{diff}，甲乙各是多少？",
            f"差的份数 = {diff_parts}，每份 = {unit}，甲 = {unit*sa}，乙 = {unit*sb}")

def bili_find_other():
    ratio = rc([(2, 3), (3, 4), (4, 5), (3, 5)])
    known = ratio[0] * rc([10, 15, 20, 25, 30])
    other = known * ratio[1] // ratio[0]
    return (f"甲乙之比{ratio[0]}:{ratio[1]}，甲是{known}，乙是多少？",
            f"乙 = {known}×{ratio[1]}÷{ratio[0]} = {other}")

def bili_scale():
    scale = rc([500, 1000, 2000, 5000])
    map_dist = ri(2, 10)
    real_cm = map_dist * scale
    real_m = real_cm // 100
    return (f"比例尺1:{scale}，图上{map_dist}厘米，实际多少米？",
            f"实际 = {map_dist}×{scale} = {real_cm}厘米 = {real_m}米")

def bili_three():
    a, b, c = rc([(2, 3, 5), (1, 2, 3), (2, 3, 4), (3, 4, 5)])
    total_parts = a + b + c
    total = total_parts * rc([10, 20, 30, 50])
    unit = total // total_parts
    return (f"甲乙丙之比{a}:{b}:{c}，总和{total}，各是多少？",
            f"总份数 = {total_parts}，每份 = {unit}，甲 = {unit*a}，乙 = {unit*b}，丙 = {unit*c}")

BILI = [bili_ratio_sum, bili_ratio_diff, bili_find_other, bili_scale, bili_three]


# ==================== 6. 年龄问题 ====================

def age_future():
    child = ri(8, 15)
    diff = ri(22, 30)
    years = ri(3, 10)
    return (f"小明{child}岁，爸爸比他大{diff}岁，{years}年后爸爸几岁？",
            f"爸爸现在{child+diff}岁，{years}年后{child+diff+years}岁")

def age_sum():
    diff = ri(2, 8)
    big = ri(25, 45)
    small = big - diff
    total = big + small
    return (f"兄弟两人年龄和{total}岁，哥哥比弟弟大{diff}岁，各几岁？",
            f"哥哥 = ({total}+{diff})÷2 = {big}岁，弟弟 = ({total}-{diff})÷2 = {small}岁")

def age_multiple():
    child = ri(5, 12)
    times = rc([3, 4, 5])
    parent = child * times
    return (f"爸爸今年{parent}岁，是儿子年龄的{times}倍，儿子今年几岁？父子相差几岁？",
            f"儿子 = {parent}÷{times} = {child}岁，相差{parent-child}岁")

def age_diff_constant():
    a = ri(30, 45)
    b = ri(5, 12)
    diff = a - b
    years = ri(5, 20)
    return (f"爸爸{a}岁，儿子{b}岁，{years}年后两人相差几岁？",
            f"年龄差永远不变 = {a}-{b} = {diff}岁")

def age_past():
    # 直接构造：years_ago年前儿子child_past岁，爸爸是times倍
    child_past = rc([6, 8, 10, 12])
    times = rc([3, 4, 5])
    parent_past = child_past * times
    years_ago = rc([2, 3, 4])
    child_now = child_past + years_ago
    parent_now = parent_past + years_ago
    return (f"{years_ago}年前爸爸年龄是儿子的{times}倍。儿子现在{child_now}岁，爸爸现在几岁？",
            f"{years_ago}年前儿子{child_past}岁，爸爸{child_past*times}岁，现在爸爸{parent_now}岁")

AGE = [age_future, age_sum, age_multiple, age_diff_constant, age_past]


# ==================== 7. 鸡兔同笼 ====================

def jitu_basic():
    rabbits = ri(5, 18)
    chickens = ri(5, 18)
    heads = rabbits + chickens
    legs = 4 * rabbits + 2 * chickens
    return (f"鸡兔同笼，共{heads}个头{legs}条腿，鸡和兔各几只？",
            f"假设全是鸡：{heads*2}条腿，多出{legs-heads*2}条，每只兔多2条，兔 = {legs-heads*2}÷2 = {rabbits}只，鸡 = {chickens}只")

def jitu_find_chicken():
    rabbits = ri(3, 15)
    chickens = ri(8, 25)
    heads = rabbits + chickens
    legs = 4 * rabbits + 2 * chickens
    return (f"笼中有鸡和兔共{heads}只，数腿有{legs}条，鸡有几只？",
            f"假设全是兔：{heads*4}条，多{heads*4-legs}条，每只鸡少2条，鸡 = {heads*4-legs}÷2 = {chickens}只")

def jitu_coin():
    a_count = ri(5, 15)
    b_count = ri(10, 25)
    total_count = a_count + b_count
    total_value = a_count * 10 + b_count * 5
    return (f"有1元和5角硬币共{total_count}枚，合计{total_value}角，各几枚？",
            f"假设全是5角：{total_count*5}角，多{total_value-total_count*5}角，每换1元多5角，1元 = {total_value-total_count*5}÷5 = {a_count}枚，5角 = {b_count}枚")

def jitu_vehicle():
    cars = ri(5, 12)
    bikes = ri(5, 18)
    total = cars + bikes
    wheels = 4 * cars + 2 * bikes
    return (f"停车场有汽车和自行车共{total}辆，数轮子共{wheels}个，各几辆？",
            f"假设全是自行车：{total*2}个轮，多{wheels-total*2}个，每辆汽车多2轮，汽车 = {wheels-total*2}÷2 = {cars}辆，自行车 = {bikes}辆")

def jitu_score():
    correct = ri(12, 18)
    wrong = ri(2, 6)
    total_q = correct + wrong
    score = correct * 5 - wrong * 2
    return (f"考试共{total_q}题，答对得5分答错扣2分，得{score}分，答对几题？",
            f"假设全对：{total_q*5}分，少{total_q*5-score}分，每错1题差7分，错 = {total_q*5-score}÷7 = {wrong}题，对 = {correct}题")

JITU = [jitu_basic, jitu_find_chicken, jitu_coin, jitu_vehicle, jitu_score]


# ==================== 8. 植树问题 ====================

def zhishu_line_both():
    length = rc([100, 200, 300, 500, 600])
    gap = rc([5, 10, 20, 25, 50])
    while length % gap != 0:
        length = rc([100, 200, 300, 500, 600])
        gap = rc([5, 10, 20, 25, 50])
    intervals = length // gap
    return (f"路长{length}米，每隔{gap}米植一棵树，两端都植，需要几棵？",
            f"间隔数 = {length}÷{gap} = {intervals}，棵数 = {intervals}+1 = {intervals+1}棵")

def zhishu_line_one():
    length = rc([100, 200, 300, 500])
    gap = rc([5, 10, 20, 25])
    while length % gap != 0:
        length = rc([100, 200, 300, 500])
        gap = rc([5, 10, 20, 25])
    intervals = length // gap
    return (f"路长{length}米，每隔{gap}米植一棵树，只植一端，需要几棵？",
            f"间隔数 = {intervals}，只植一端棵数 = {intervals}棵")

def zhishu_circle():
    perimeter = rc([200, 300, 400, 500, 600])
    gap = rc([5, 10, 20, 25])
    while perimeter % gap != 0:
        perimeter = rc([200, 300, 400, 500, 600])
        gap = rc([5, 10, 20, 25])
    trees = perimeter // gap
    return (f"圆形池塘周长{perimeter}米，每隔{gap}米植一棵，需要几棵？",
            f"环形植树：棵数 = {perimeter}÷{gap} = {trees}棵")

def zhishu_find_gap():
    intervals = rc([10, 15, 20, 25])
    gap = rc([5, 10, 15, 20])
    length = intervals * gap
    trees = intervals + 1
    return (f"路长{length}米，两端都植，共植{trees}棵树，每两棵之间相距多少米？",
            f"间隔数 = {trees}-1 = {intervals}，间距 = {length}÷{intervals} = {gap}米")

def zhishu_both_sides():
    length = rc([200, 300, 500, 600])
    gap = rc([5, 10, 20, 25])
    while length % gap != 0:
        length = rc([200, 300, 500, 600])
        gap = rc([5, 10, 20, 25])
    one_side = length // gap + 1
    return (f"路长{length}米，每隔{gap}米植一棵，两端都植，路两旁共需几棵？",
            f"一旁{one_side}棵，两旁共{one_side*2}棵")

ZHISHU = [zhishu_line_both, zhishu_line_one, zhishu_circle, zhishu_find_gap, zhishu_both_sides]


# ==================== 9. 分数百分数 ====================

def fenshu_basic_pct():
    pct = rc([20, 25, 40, 50, 60, 75, 80])
    frac_map = {20: "1/5", 25: "1/4", 40: "2/5", 50: "1/2", 60: "3/5", 75: "3/4", 80: "4/5"}
    return f"{pct}%化成分数和小数各是多少？", f"分数 = {frac_map[pct]}，小数 = {pct/100}"

def fenshu_increase():
    base = rc([100, 200, 300, 400, 500])
    pct = rc([10, 20, 25, 30, 50])
    increase = base * pct // 100
    return (f"某数从{base}增加{pct}%，变为多少？",
            f"增加 = {increase}，新值 = {base+increase}")

def fenshu_decrease():
    base = rc([200, 300, 400, 500])
    pct = rc([10, 20, 25, 30])
    decrease = base * pct // 100
    return (f"某数从{base}减少{pct}%，变为多少？",
            f"减少 = {decrease}，新值 = {base-decrease}")

def fenshu_find_pct():
    old = rc([100, 200, 250, 400, 500])
    diff = rc([20, 40, 50, 100, 150, 200])
    while diff * 100 % old != 0:
        old = rc([100, 200, 250, 400, 500])
        diff = rc([20, 40, 50, 100, 150, 200])
    pct = diff * 100 // old
    new_val = old + diff
    return (f"从{old}增加到{new_val}，增幅百分之几？",
            f"增加{diff}，增幅 = {diff}÷{old}×100% = {pct}%")

def fenshu_of_total():
    n, d = rc([(1, 3), (1, 4), (2, 5), (3, 4), (1, 6)])
    total = (d // math.gcd(n, d)) * rc([10, 15, 20, 25, 30])
    while total * n % d != 0:
        total = d * rc([10, 15, 20, 25, 30])
    part = total * n // d
    return (f"一共有{total}个苹果，吃了{n}/{d}，吃了多少个？",
            f"吃了 = {total}×{n}/{d} = {part}个")

def fenshu_find_total():
    n, d = rc([(1, 3), (1, 4), (2, 5), (3, 4)])
    unit = rc([10, 15, 20, 25, 30])
    part = n * unit
    total = d * unit
    return (f"看了一本书的{n}/{d}，看了{part}页，这本书共多少页？",
            f"总页数 = {part}÷{n}/{d} = {part}×{d}/{n} = {total}页")

def fenshu_compare():
    a = rc([100, 200, 250, 300])
    pct = rc([10, 20, 25, 30])
    while a * (100 + pct) % 100 != 0:
        a = rc([100, 200, 250, 300])
    b = a * (100 + pct) // 100
    return (f"甲是{a}，乙比甲多{pct}%，乙是多少？",
            f"乙 = {a}×(1+{pct}%) = {b}")

FENSHU = [fenshu_basic_pct, fenshu_increase, fenshu_decrease, fenshu_find_pct,
          fenshu_of_total, fenshu_find_total, fenshu_compare]


# ==================== 10. 几何应用 ====================

def geo_rectangle():
    l, w = ri(5, 30), ri(3, 20)
    return (f"长方形长{l}cm，宽{w}cm，周长和面积各是多少？",
            f"周长 = ({l}+{w})×2 = {(l+w)*2}cm，面积 = {l}×{w} = {l*w}cm²")

def geo_square():
    a = ri(3, 25)
    return f"正方形边长{a}cm，周长和面积各是多少？", f"周长 = {a*4}cm，面积 = {a*a}cm²"

def geo_triangle():
    base = rc([6, 8, 10, 12, 14, 16, 20])
    height = rc([4, 6, 8, 10, 12])
    while base * height % 2 != 0:
        base = rc([6, 8, 10, 12, 14, 16, 20])
        height = rc([4, 6, 8, 10, 12])
    area = base * height // 2
    return f"三角形底{base}cm，高{height}cm，面积是多少？", f"面积 = {base}×{height}÷2 = {area}cm²"

def geo_circle():
    r = rc([3, 5, 7, 10])
    perimeter = round(2 * 3.14 * r, 2)
    area = round(3.14 * r * r, 2)
    return (f"圆的半径{r}cm，周长和面积各是多少？（π取3.14）",
            f"周长 = 2×3.14×{r} = {perimeter}cm，面积 = 3.14×{r}² = {area}cm²")

def geo_trapezoid():
    a, b = rc([6, 8, 10, 12]), rc([4, 6, 8, 10])
    h = rc([4, 6, 8, 10])
    while (a + b) * h % 2 != 0:
        a, b = rc([6, 8, 10, 12]), rc([4, 6, 8, 10])
        h = rc([4, 6, 8, 10])
    area = (a + b) * h // 2
    return f"梯形上底{a}cm，下底{b}cm，高{h}cm，面积是多少？", f"面积 = ({a}+{b})×{h}÷2 = {area}cm²"

def geo_cube():
    a = rc([3, 4, 5, 6, 8, 10])
    return (f"正方体棱长{a}cm，表面积和体积各是多少？",
            f"表面积 = 6×{a}² = {6*a*a}cm²，体积 = {a}³ = {a**3}cm³")

def geo_cylinder():
    r = rc([3, 5, 10])
    h = rc([5, 8, 10, 12])
    volume = round(3.14 * r * r * h, 2)
    return (f"圆柱底面半径{r}cm，高{h}cm，体积是多少？（π取3.14）",
            f"体积 = 3.14×{r}²×{h} = {volume}cm³")

GEO = [geo_rectangle, geo_square, geo_triangle, geo_circle,
       geo_trapezoid, geo_cube, geo_cylinder]


# ==================== 11. 平均数 ====================

def avg_basic():
    n = rc([4, 5, 6])
    base = ri(70, 90)
    nums = [base + ri(-8, 12) for _ in range(n)]
    total = sum(nums)
    while total % n != 0:
        nums[-1] += (n - total % n) % n
        total = sum(nums)
    avg = total // n
    return f"{n}个数分别是{'、'.join(map(str, nums))}，平均数是多少？", f"总和 = {total}，平均数 = {total}÷{n} = {avg}"

def avg_find_total():
    n = ri(5, 8)
    avg = ri(70, 95)
    return f"{n}个数的平均数是{avg}，总和是多少？", f"总和 = {n}×{avg} = {n*avg}"

def avg_find_missing():
    n = rc([4, 5, 6])
    avg = ri(70, 90)
    total = n * avg
    nums = [ri(65, 90) for _ in range(n - 1)]
    missing = total - sum(nums)
    while missing <= 0 or missing > 100:
        nums = [ri(65, 90) for _ in range(n - 1)]
        missing = total - sum(nums)
    return (f"{n}个数平均{avg}，已知{n-1}个数分别是{'、'.join(map(str, nums))}，第{n}个数是多少？",
            f"总和 = {total}，已知和 = {sum(nums)}，第{n}个数 = {total}-{sum(nums)} = {missing}")

def avg_weighted():
    n1, n2 = ri(20, 30), ri(20, 30)
    avg1, avg2 = ri(70, 85), ri(80, 95)
    while avg1 == avg2:
        avg2 = ri(80, 95)
    total = n1 * avg1 + n2 * avg2
    total_n = n1 + n2
    while total % total_n != 0:
        n1, n2 = ri(20, 30), ri(20, 30)
        total = n1 * avg1 + n2 * avg2
        total_n = n1 + n2
    overall = total // total_n
    return (f"甲班{n1}人平均{avg1}分，乙班{n2}人平均{avg2}分，两班总平均多少分？",
            f"总分 = {total}，总人数 = {total_n}，平均 = {total}÷{total_n} = {overall}分")

def avg_add_one():
    new_n = rc([5, 6, 7])
    new_avg = ri(70, 90)
    new_total = new_n * new_avg
    n = new_n - 1
    avg = ri(65, 85)
    total = n * avg
    new_val = new_total - total
    while new_val <= 0:
        avg = ri(65, 85)
        total = n * avg
        new_val = new_total - total
    return (f"{n}个数平均{avg}，加入一个{new_val}后，新平均数是多少？",
            f"原总和 = {total}，新总和 = {new_total}，新平均 = {new_total}÷{new_n} = {new_avg}")

AVG = [avg_basic, avg_find_total, avg_find_missing, avg_weighted, avg_add_one]


# ==================== 12. 还原问题 ====================

def huanyuan_basic():
    original = ri(20, 80)
    add = ri(5, 20)
    sub = ri(5, 15)
    result = original + add - sub
    return (f"某数加{add}再减{sub}得{result}，原数是多少？",
            f"原数 = {result}+{sub}-{add} = {original}")

def huanyuan_mul_div():
    original = ri(5, 25)
    mul = ri(2, 5)
    div = ri(2, 4)
    while original * mul % div != 0:
        original = ri(5, 25)
    result = original * mul // div
    return (f"某数乘{mul}再除以{div}得{result}，原数是多少？",
            f"原数 = {result}×{div}÷{mul} = {original}")

def huanyuan_half():
    original = ri(20, 60) * 2
    half = original // 2
    extra = ri(3, 10)
    sold = half + extra
    remain = original - sold
    return (f"一筐苹果，卖出一半多{extra}个，还剩{remain}个，原来有几个？",
            f"原有 = ({remain}+{extra})×2 = {original}个")

def huanyuan_reverse():
    original = ri(10, 40)
    add_val = ri(5, 20)
    result = (original + add_val) * 2
    return (f"某数加{add_val}后乘2得{result}，原数是多少？",
            f"逆运算：{result}÷2 = {original+add_val}，{original+add_val}-{add_val} = {original}")

def huanyuan_multi_step():
    original = ri(15, 50)
    add1 = ri(10, 25)
    mul2 = ri(2, 4)
    step1 = original + add1
    step2 = step1 * mul2
    return (f"某数加{add1}后乘{mul2}得{step2}，原数是多少？",
            f"逆运算：{step2}÷{mul2} = {step1}，{step1}-{add1} = {original}")

HUANYUAN = [huanyuan_basic, huanyuan_mul_div, huanyuan_half, huanyuan_reverse, huanyuan_multi_step]


# ==================== 生成主逻辑 ====================

ALL_CATEGORIES = [
    ("行程问题", XINGCHENG),
    ("工程问题", GONGCHENG),
    ("浓度问题", NONGDU),
    ("利润折扣", LIRUN),
    ("比例问题", BILI),
    ("年龄问题", AGE),
    ("鸡兔同笼", JITU),
    ("植树问题", ZHISHU),
    ("分数百分数", FENSHU),
    ("几何应用", GEO),
    ("平均数", AVG),
    ("还原问题", HUANYUAN),
]


def generate_all(total=200):
    per_cat = total // len(ALL_CATEGORIES)
    extra = total - per_cat * len(ALL_CATEGORIES)
    all_problems = []
    global_seen = set()

    for i, (cat_name, funcs) in enumerate(ALL_CATEGORIES):
        n = per_cat + (1 if i < extra else 0)
        cat_problems = []
        per_func = max(n // len(funcs), 1)

        for func in funcs:
            for _ in range(per_func + 2):  # 多生成几个备用
                try:
                    q, a = func()
                    fp = q[:30]
                    if fp not in global_seen:
                        global_seen.add(fp)
                        cat_problems.append((q, a))
                except Exception:
                    pass

        # 补充不足的部分
        attempts = 0
        while len(cat_problems) < n and attempts < n * 20:
            func = random.choice(funcs)
            try:
                q, a = func()
                fp = q[:30]
                if fp not in global_seen:
                    global_seen.add(fp)
                    cat_problems.append((q, a))
            except Exception:
                pass
            attempts += 1

        all_problems.extend([(cat_name, q, a) for q, a in cat_problems[:n]])

    random.shuffle(all_problems)
    return all_problems


def to_markdown(problems):
    lines = []
    lines.append("# 小升初数学应用题 200 道（含答案）")
    lines.append("")
    lines.append("> 涵盖行程问题、工程问题、浓度问题、利润折扣、比例问题、年龄问题、鸡兔同笼、植树问题、分数百分数、几何应用、平均数、还原问题共 12 大类。")
    lines.append("")
    lines.append("---")
    lines.append("")

    cat_count = {}
    for cat, q, a in problems:
        cat_count[cat] = cat_count.get(cat, 0) + 1

    idx = 1
    started_cats = set()
    for cat, q, a in problems:
        if cat not in started_cats:
            started_cats.add(cat)
            lines.append(f"## {cat}（{cat_count[cat]} 道）")
            lines.append("")

        lines.append(f"**第 {idx} 题**")
        lines.append("")
        lines.append(q)
        lines.append("")
        lines.append(f"> **答案：** {a}")
        lines.append("")
        idx += 1

    return "\n".join(lines)


if __name__ == "__main__":
    problems = generate_all(200)
    md = to_markdown(problems)
    print(md)
