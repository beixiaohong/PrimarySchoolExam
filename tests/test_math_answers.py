# -*- coding: utf-8 -*-
"""数学题生成器答案回归测试（需求2：修复 Bug1/2/3/4/5/6/7/10 后补充）

覆盖：
- 每个修复点的固定用例（锁定回归，杜绝旧 bug 复发）；
- 修复生成器的随机重跑（无 HANG / 无 EXCEPTION / 无 None / 无畸形代数式）。

运行：
    python -m pytest tests/test_math_answers.py -q

说明：本测试不依赖数据库，也不触发 geo 配图（matplotlib）渲染，保证快速稳定。
检测口径与 tools/verify_math_answers.py 保持一致。
"""
import os
import re
import sys
import threading
from unittest import mock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.domains.assessment.services.math_generator.common import GENERATORS  # noqa: E402
import app.domains.assessment.services.math_generator.calc as calc_mod  # noqa: E402
import app.domains.assessment.services.math_generator.number as number_mod  # noqa: E402
import app.domains.assessment.services.math_generator.middle as middle_mod  # noqa: E402
import app.domains.assessment.services.math_generator.app as app_mod  # noqa: E402
import app.domains.assessment.services.math_generator.logic as logic_mod  # noqa: E402
import app.domains.assessment.services.math_generator.stat as stat_mod  # noqa: E402
import ast  # noqa: E402
from fractions import Fraction  # noqa: E402
from decimal import Decimal, ROUND_HALF_UP  # noqa: E402

# 与 verify_math_answers.py 一致的畸形代数式判定
MALFORMED_RE = [
    re.compile(r"x²\+?0x"),
    re.compile(r"x0="),
    re.compile(r"y=[+-]?\d+x0\b"),
    re.compile(r"\+0="),
]


def call_with_timeout(fn, diff, grade, timeout=3.0):
    """守护线程包裹单题生成，超时判定为 HANG（疑似死循环）。"""
    box = {}

    def runner():
        try:
            box["res"] = ("OK", fn(diff, grade))
        except BaseException as e:  # noqa: BLE001
            box["res"] = ("EXC", repr(e))

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return ("HANG", None)
    return box.get("res", ("HANG", None))


def cow_consistent(pairs):
    """牛吃草题设自洽性：所有 (牛数 c, 天数 d) 可由同一 (G, r) 解释（c*d = G + r*d）。"""
    if len(pairs) < 2:
        return True
    (c1, d1), (c2, d2) = pairs[0], pairs[1]
    if d1 == d2:
        if c1 != c2:
            return False
        r = 1
        G = c1 * d1 - r * d1
        if G <= 0:
            return False
    else:
        num = c2 * d2 - c1 * d1
        den = d2 - d1
        if den == 0 or num % den != 0:
            return False
        r = num // den
        if r < 1:
            return False
        G = c1 * d1 - r * d1
        if G <= 0:
            return False
    for c, d in pairs[2:]:
        if c * d != G + r * d:
            return False
    return True


# ---------------------------------------------------------------------------
# Bug1：calc_equation._eq_word_hard 答案恒为 None
# ---------------------------------------------------------------------------
def test_bug1_eq_word_hard_has_answer():
    # _eq_word_hard 为无参内部函数（不依赖 difficulty/grade）
    for _ in range(60):
        q, a = calc_mod._eq_word_hard()
        assert a is not None, "Bug1 回归：_eq_word_hard 答案不应为 None"
        m = re.search(r"去时每小时(\d+)千米，用了(\d+)小时。回来时每小时快(\d+)千米", q)
        assert m, "Bug1 回归：题面格式异常 -> %r" % q
        speed, time_, extra = int(m.group(1)), int(m.group(2)), int(m.group(3))
        dist = speed * time_
        back_speed = speed + extra
        back_time = dist / back_speed
        expected = ("%.1f小时" % back_time) if back_time != int(back_time) else ("%d小时" % int(back_time))
        assert expected in a, "Bug1 回归：返回时间应为 %s -> %r" % (expected, a)


# ---------------------------------------------------------------------------
# Bug2：number_large 四舍五入用银行家舍入（应为 round-half-up）
# ---------------------------------------------------------------------------
def test_bug2_number_large_round_half_up():
    # 强制 n=25000，并固定选择「四舍五入到万位」变体（variants[0]）
    with mock.patch.object(number_mod.random, "randint", return_value=25000), \
         mock.patch.object(number_mod.random, "choice", side_effect=lambda x: x[0]):
        q, a = number_mod.number_large(3, 5)
    assert "25000" in q
    # 银行家舍入会得 2万；学校「四舍五入」应为 3万
    assert a == "≈3万", "Bug2 回归：25000 四舍五入到万位应为 3万，得到 %r" % a


# ---------------------------------------------------------------------------
# Bug3：mid_quadratic_eq 畸形方程式（x²0x / x²+bx0）
# ---------------------------------------------------------------------------
def test_bug3_mid_quadratic_eq_no_malformed():
    # 该生成器含多个变体；只有「解方程: x²...」变体曾出现畸形，全量扫描 + 仅对该变体校验形态
    for _ in range(600):
        q, a = middle_mod.mid_quadratic_eq(4, 8)
        assert not any(rx.search(q) for rx in MALFORMED_RE), "Bug3 回归：畸形方程式 -> %r" % q
        if q.startswith("解方程: x²"):
            assert re.match(r"^解方程: x²([+-]?\d+x)?([+-]?\d+)?=0$", q), \
                "Bug3 回归：方程形态异常 -> %r" % q


# ---------------------------------------------------------------------------
# Bug4：mid_linear_func 畸形解析式（y=kx0）
# ---------------------------------------------------------------------------
def test_bug4_mid_linear_func_no_malformed():
    # 该生成器含多个变体；只有「y=...」解析式变体曾出现畸形，全量扫描 + 仅对该变体校验形态
    for _ in range(600):
        q, a = middle_mod.mid_linear_func(4, 8)
        assert not any(rx.search(a) for rx in MALFORMED_RE), "Bug4 回归：畸形解析式 -> %r" % a
        if isinstance(a, str) and a.startswith("y="):
            assert re.match(r"^y=[+-]?\d+x([+-]\d+)?$", a), "Bug4 回归：解析式形态异常 -> %r" % a


# ---------------------------------------------------------------------------
# Bug5：app_cow_grazing 题设不自洽
# ---------------------------------------------------------------------------
def test_bug5_cow_grazing_consistent():
    for _ in range(300):
        q, a = app_mod.app_cow_grazing(4, 8)
        pairs = None
        mm = re.search(r"(\d+)头牛(\d+)天可以吃完，(\d+)头牛几天可以吃完", q)
        if mm:
            c1, d1, c2 = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
            am = re.search(r"(\d+)天$", a)
            assert am, "Bug5 回归：答案格式异常 -> %r" % a
            pairs = [(c1, d1), (c2, int(am.group(1)))]
        hm = re.search(r"(\d+)头牛(\d+)天吃完，(\d+)头牛(\d+)天吃完。如果放(\d+)头牛", q)
        if hm:
            c1, d1, c2, d2, c3 = (int(x) for x in hm.groups())
            am = re.search(r"(\d+)天$", a)
            assert am, "Bug5 回归：答案格式异常 -> %r" % a
            pairs = [(c1, d1), (c2, d2), (c3, int(am.group(1)))]
        assert pairs is not None, "Bug5 回归：题面未被解析 -> %r" % q
        assert cow_consistent(pairs), "Bug5 回归：题设不自洽 -> %r | %s" % (q, pairs)


# ---------------------------------------------------------------------------
# Bug6 + Bug7：app_travel 除零崩溃 + 环形跑道死循环
# ---------------------------------------------------------------------------
def test_bug6_bug7_app_travel_no_crash():
    for diff in (3, 4, 5):  # 3-4 覆盖追及（v1 接近 v2），5 覆盖环形跑道
        for _ in range(120):
            status, payload = call_with_timeout(app_mod.app_travel, diff, 8, timeout=3.0)
            assert status != "HANG", "Bug7 回归：app_travel 疑似死循环 (diff=%d)" % diff
            assert status != "EXC", "Bug6 回归：app_travel 抛异常 -> %r" % payload
            q, a = payload
            assert a is not None, "Bug6 回归：app_travel 答案不应为 None (diff=%d)" % diff


# ---------------------------------------------------------------------------
# Bug10：logic_reasoning 鸡兔同笼死循环
# ---------------------------------------------------------------------------
def test_bug10_logic_reasoning_no_deadloop():
    for _ in range(200):
        status, payload = call_with_timeout(logic_mod.logic_reasoning, 4, 9, timeout=3.0)
        assert status != "HANG", "Bug10 回归：logic_reasoning 鸡兔同笼疑似死循环"
        assert status != "EXC", "Bug10 回归：logic_reasoning 抛异常 -> %r" % payload
        q, a = payload
        m = re.search(r"鸡兔同笼(\d+)头(\d+)腿", q)
        if not m:
            continue  # 该分支的其它变体（如硬币），跳过
        heads, legs = int(m.group(1)), int(m.group(2))
        rm = re.search(r"鸡(\d+)只，兔(\d+)只", a)
        assert rm, "Bug10 回归：答案格式异常 -> %r" % a
        chickens, rabbits = int(rm.group(1)), int(rm.group(2))
        assert chickens + rabbits == heads, "Bug10 回归：头数不符"
        assert 2 * chickens + 4 * rabbits == legs, "Bug10 回归：腿数不符"


# ---------------------------------------------------------------------------
# number_operation_law 分配律展开题：题干与答案系数必须一致
# （回归 number.py:211 两次独立 random 导致答案系数与题千不一致的 bug）
# ---------------------------------------------------------------------------
def test_number_distributive_coeff_consistent():
    hit = 0
    for _ in range(3000):
        q, a = number_mod.number_operation_law(4, 6)
        m = re.search(r"\((\d+)\+(\d+)\)×(\d+)怎样用分配律展开\？", q)
        if not m:
            continue
        hit += 1
        x_q = int(m.group(2))  # 题千括号内的加数
        ma = re.search(r"(\d+)×(\d+)\+(\d+)×(\d+)", a)
        assert ma, "分配律展开答案格式异常 -> %r" % a
        assert int(ma.group(3)) == x_q, (
            "题干系数(%d)与答案系数(%d)不一致 -> q=%r a=%r"
            % (x_q, int(ma.group(3)), q, a)
        )
    assert hit > 0, "未命中分配律展开题型，测试无效"


# ---------------------------------------------------------------------------
# stat_measure 中位数：奇数个数必须取正中间那个，偶数取中间两数平均
# （回归 stat.py:141：7 个数误按偶数算成 (s[3]+s[4])/2，如 [..,81,85,..] 错答 83.0）
# ---------------------------------------------------------------------------
def test_stat_measure_median_correct():
    for diff in (2, 3, 4):  # diff<=2 为 5 个数分支，diff 3-4 为 7 个数分支
        hit = 0
        for _ in range(1500):
            q, a = stat_mod.stat_measure(diff, 6)
            m = re.search(r"数据(\[.*?\])的中位数是多少", q)
            if not m:
                continue
            hit += 1
            data = ast.literal_eval(m.group(1))
            s = sorted(data)
            n = len(s)
            if n % 2 == 1:
                expected = s[n // 2]
            else:
                expected = (s[n // 2 - 1] + s[n // 2]) / 2
            assert float(a) == float(expected), (
                "中位数回归失败(diff=%d): data=%r n=%d 参考答案=%r 应为=%s"
                % (diff, data, n, a, expected))
        assert hit > 0, "diff=%d 未命中中位数变体，测试无效" % diff


# ---------------------------------------------------------------------------
# app_profit 实际利润率：参考答案精确到 2 位小数，不被浮点误差舍小
# （回归 app.py:199：33.4500...% 浮点偏小成 33.4499...，round(...,1) 错给 33.4，
#   孩子答精确值 33.45% 被误判）
# ---------------------------------------------------------------------------
def test_app_profit_real_rate_precision():
    # 固定：进价389 加价57% 打八五折 → 利润率精确值 33.45%
    def _fake_choice(seq):
        if len(seq) == 3 and seq[0] == 80:      # discount 候选项 [80,85,90] → 取 85（八五折）
            return 85
        return seq[0]                            # variants → 取利润率变体

    with mock.patch.object(app_mod.random, "randint", side_effect=[389, 57]), \
         mock.patch.object(app_mod.random, "choice", side_effect=_fake_choice):
        q, a = app_mod.app_profit(3, 6)
    assert "389" in q and "57" in q and "实际利润率" in q
    assert a == "33.45%", "实际利润率参考答案应为 33.45% -> %r" % a


def test_app_profit_real_rate_sweep():
    hit = 0
    for _ in range(800):
        q, a = app_mod.app_profit(3, 6)
        m = re.search(r"进价(\d+)元加价(\d+)%标价，打(.+?)折卖，实际利润率？", q)
        if not m:
            continue
        hit += 1
        cost, markup = int(m.group(1)), int(m.group(2))
        disc_map = {"八": 80, "八五": 85, "九": 90}
        discount = disc_map[m.group(3)]
        exact = (Fraction(cost) * Fraction(100 + markup) / 100 * Fraction(discount) / 100
                 - Fraction(cost)) / Fraction(cost) * 100
        exp = (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert a == f"{exp}%", "利润率参考答案 %r 应为 %s%% (q=%r)" % (a, exp, q)
    assert hit > 0, "未命中实际利润率变体，测试无效"


# ---------------------------------------------------------------------------
# 修复生成器随机扫描：无 HANG / 无 EXCEPTION / 无 None / 无畸形
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", [
    "calc_equation", "number_large", "mid_quadratic_eq", "mid_linear_func",
    "app_cow_grazing", "app_travel", "logic_reasoning",
])
def test_fixed_generators_sweep(code):
    fn = GENERATORS[code]
    for diff in range(1, 6):
        for grade in range(1, 10):
            status, payload = call_with_timeout(fn, diff, grade, timeout=3.0)
            assert status == "OK", "回归扫描 %s 在 d%d/g%d 异常: %s" % (code, diff, grade, status)
            q, a = payload
            assert a is not None, "回归扫描 %s 答案为 None (d%d/g%d)" % (code, diff, grade)
            text = "%s || %s" % (q, a)
            assert not any(rx.search(text) for rx in MALFORMED_RE), \
                "回归扫描 %s 畸形 -> %r" % (code, text)
