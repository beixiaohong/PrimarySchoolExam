# -*- coding: utf-8 -*-
"""
数学题答案验证脚本（需求2：先出验证报告再修）

用法：
  python tools/verify_math_answers.py reset            # 首批：清空报告并从头跑
  python tools/verify_math_answers.py                  # 续跑：追加到现有报告
  python tools/verify_math_answers.py reset calc_equation,number_large   # 只跑指定生成器

环境变量：
  VMA_ITERS   每 (difficulty,grade) 组合迭代次数（默认 15）
  VMA_TIMEOUT 单道题目生成超时秒数，超时判定为「疑似死循环」（默认 2.0）

特点：
- 每个生成器处理完立即把「缺陷小结」写入报告文件（实时落盘），进程被杀也不丢已完成结果。
- 跨 difficulty ∈ {1..5}、grade ∈ {1..9}，每组合 ITERS 次。
- 单题生成用守护线程包裹并设超时：超时即记为 HANG（疑似死循环），不阻塞后续。
- 检测：答案为 None/空/字面None；畸形代数式（x²0x、x²+bx0、y=kx0）；
        number_large 四舍五入与银行家舍入不一致；app_cow_grazing 题设不自洽。
"""
import io
import os
import re
import sys
import threading
import traceback
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

REPORT_PATH = os.path.join(ROOT, "tools", "verify_math_report.txt")

ARGS = sys.argv[1:]
RESET = "reset" in ARGS
FILTER = [a for a in ARGS if a != "reset" and "," not in a]
if not FILTER and any("," in a for a in ARGS):
    FILTER = ARGS[[i for i, a in enumerate(ARGS) if "," in a][0]].split(",")
FILTER = [f for f in FILTER if f]

# 实时落盘
_mode = "w" if RESET else "a"
_f_report = open(REPORT_PATH, _mode, encoding="utf-8")
out = io.StringIO()


def log(*a):
    s = " ".join(str(x) for x in a)
    out.write(s + "\n")
    _f_report.write(s + "\n")
    _f_report.flush()


# ---------------------------------------------------------------------------
# 导入
# ---------------------------------------------------------------------------
try:
    import app  # noqa
    from app.domains.assessment.services.math_generator.common import GENERATORS  # noqa
    import app.domains.assessment.services.math_generator  # noqa
    from app.domains.assessment.services.math_generator.common import GENERATORS
except Exception:
    log("!!! 导入 math_generator 失败 !!!")
    log(traceback.format_exc())
    _f_report.close()
    raise

if RESET:
    log("生成器数量: %d" % len(GENERATORS))
    log("")


# ---------------------------------------------------------------------------
# 检测
# ---------------------------------------------------------------------------
MALFORMED_RE = [
    re.compile(r"x²\+?0x"),
    re.compile(r"x0="),
    re.compile(r"y=[+-]?\d+x0\b"),
    re.compile(r"\+0="),
]

COW_SEV = "牛吃草题设不自洽"


def cow_consistent(pairs):
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


def check_item(code, q, a):
    reasons = []
    if a is None:
        reasons.append("答案为None")
        return reasons
    if isinstance(a, str):
        if a.strip() == "":
            reasons.append("答案为空串")
        elif "None" in a:
            reasons.append("答案含字面None")
    text = (str(q) + " || " + str(a))
    for rx in MALFORMED_RE:
        if rx.search(text):
            reasons.append("畸形代数式:%s" % rx.pattern)
            break

    if code == "number_large":
        m = re.search(r"把(\d+)四舍五入到(万|亿)位", str(q))
        if m:
            n = int(m.group(1))
            unit = 10000 if m.group(2) == "万" else 100000000
            stated = re.search(r"≈(\d+)万", str(a)) or re.search(r"≈(\d+)亿", str(a))
            if stated:
                stated_val = int(stated.group(1))
                expected = (n + unit // 2) // unit
                if stated_val != expected:
                    reasons.append("四舍五入不符:题%d→答案%d,正确%d" % (n, stated_val, expected))

    if code == "app_cow_grazing":
        mm = re.search(r"(\d+)头牛(\d+)天可以吃完，(\d+)头牛几天可以吃完", str(q))
        pairs = None
        if mm:
            c1, d1, c2 = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
            am = re.search(r"(\d+)天$", str(a))
            if am:
                pairs = [(c1, d1), (c2, int(am.group(1)))]
        hm = re.search(r"(\d+)头牛(\d+)天吃完，(\d+)头牛(\d+)天吃完。如果放(\d+)头牛", str(q))
        if hm:
            c1, d1, c2, d2, c3 = (int(x) for x in hm.groups())
            am = re.search(r"(\d+)天$", str(a))
            if am:
                pairs = [(c1, d1), (c2, d2), (c3, int(am.group(1)))]
        if pairs and not cow_consistent(pairs):
            reasons.append(COW_SEV + ":%s" % pairs)
    return reasons


# ---------------------------------------------------------------------------
# 单题生成（守护线程超时包裹，防止死循环拖垮整轮）
# ---------------------------------------------------------------------------
def call_with_timeout(fn, diff, grade, timeout):
    box = {}

    def runner():
        try:
            box["res"] = ("OK", fn(diff, grade))
        except BaseException as e:
            box["res"] = ("EXC", e)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return ("HANG", None)
    return box.get("res", ("HANG", None))


# ---------------------------------------------------------------------------
# 主验证（每个生成器实时输出小结）
# ---------------------------------------------------------------------------
def main():
    DIFFS = [1, 2, 3, 4, 5]
    GRADES = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    ITERS = int(os.environ.get("VMA_ITERS", "15"))
    HANG_TIMEOUT = float(os.environ.get("VMA_TIMEOUT", "2.0"))

    codes = sorted(GENERATORS.keys())
    if FILTER:
        codes = [c for c in codes if c in FILTER]
        log("（筛选模式）仅跑: " + ", ".join(codes))

    for code in codes:
        fn = GENERATORS[code]
        st = {"runs": 0, "defects": 0, "samples": [], "types": defaultdict(int)}
        hang_break = False
        for diff in DIFFS:
            if hang_break:
                break
            for grade in GRADES:
                if hang_break:
                    break
                for _ in range(ITERS):
                    if hang_break:
                        break
                    st["runs"] += 1
                    status, payload = call_with_timeout(fn, diff, grade, HANG_TIMEOUT)
                    if status == "HANG":
                        st["defects"] += 1
                        st["types"]["HANG(疑似死循环)"] += 1
                        if len(st["samples"]) < 5:
                            st["samples"].append(("HANG(疑似死循环)", "d%d g%d" % (diff, grade), ""))
                        hang_break = True
                        break
                    if status == "EXC":
                        st["defects"] += 1
                        st["types"]["EXCEPTION"] += 1
                        if len(st["samples"]) < 5:
                            st["samples"].append(("EXCEPTION", repr(payload)[:120], ""))
                        continue
                    res = payload
                    if isinstance(res, tuple):
                        q = res[0]
                        a = res[1] if len(res) > 1 else None
                    else:
                        q, a = res, None
                    try:
                        reasons = check_item(code, q, a)
                    except Exception as e:
                        st["defects"] += 1
                        st["types"]["CHECK_ERROR"] += 1
                        if len(st["samples"]) < 5:
                            st["samples"].append(("CHECK_ERROR", repr(e)[:120], ""))
                        continue
                    if reasons:
                        st["defects"] += 1
                        for r in reasons:
                            st["types"][r] += 1
                        if len(st["samples"]) < 6:
                            st["samples"].append(("; ".join(reasons), str(q)[:140], str(a)[:140]))
        # ---- 实时输出该生成器小结 ----
        pct = 100.0 * st["defects"] / st["runs"] if st["runs"] else 0
        if st["defects"] > 0:
            log("\n[%s] 运行 %d 次, 缺陷 %d 次 (%.1f%%)" % (code, st["runs"], st["defects"], pct))
            log("  缺陷类型: " + ", ".join("%s×%d" % (k, v) for k, v in sorted(st["types"].items(), key=lambda x: -x[1])))
            for reason, q, a in st["samples"]:
                log("  样例[%s]" % reason)
                log("    Q: " + q)
                log("    A: " + a)
        else:
            log("[%s] 运行 %d 次, 无缺陷" % (code, st["runs"]))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!!! 主流程崩溃 !!!")
        log(traceback.format_exc())
    _f_report.close()
    log("\n（本批结束）")
