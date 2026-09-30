#!/usr/bin/env python
"""高项（软考）计算题参数化生成器 —— 零成本、可重现、答案自洽

为什么需要它
------------
线上高项题库里「计算专题」只有 53 道（来自 4 份「计算题综合」PDF），案例题 17 道，
用户刷题很快就会重复。而再去解析 PDF 已经榨干了：本地 452 份资料里题目类的 PDF
基本都解析过，剩下的是图解/作图题（单代号图、双代号箭线图），文本抽出来只是
「A 1 2 3 4 5」这种图的标注碎片，做不成题目。

但**软考高项的计算题考点是收敛的**：三点估算、挣值分析、关键路径、决策树 EMV、
NPV/投资回收期、沟通渠道数、后悔值决策、指派问题、盈亏平衡……每个考点都有固定
公式，历年真题只是换数字。所以可以**参数化生成**——不调 AI、不花钱、答案必然
正确（由公式算出，不是猜的）。

设计约束
--------
1. **可重现**：固定随机种子，同一份参数跑两次产出完全一致的题目。否则每次重跑
   指纹都变，线上导入就没法幂等。
2. **答案必然在选项里且唯一**：所有题目先算出正确值，再用「典型错误」造干扰项
   （比如把 β 分布写成三角分布、CPI 分子分母颠倒、忘记除以 2），最后打乱成 A/B/C/D。
   干扰项与正确值重复时自动微调，保证四个选项互不相同。
3. **数值干净**：参数先按整除条件挑选（如 `d2-d1 ≡ 0 (mod 6)` 让三点估算的两个
   分布值都是整数），选项保留位数固定 —— 不出现 `1250.3333333` 这种。
4. **落进既有 taxonomy**：`domain` / `chapter` 只取数据包里已有的取值，否则归类会空。

用法
----
    .venv/Scripts/python.exe tools/gx_calc_gen.py                 # 生成并写数据包
    .venv/Scripts/python.exe tools/gx_calc_gen.py --per-kind 60   # 每个考点多生成些
    .venv/Scripts/python.exe tools/gx_calc_gen.py --dry-run       # 只看统计不写文件
    .venv/Scripts/python.exe tools/gx_calc_gen.py --verify        # 自检（重算校验答案）

产出 `data/gx_materials/pack_calc_gen.json`，格式与 `pack_choice.json` 一致，
由 `tools/import_gx_materials.py` 一并导入（按 fingerprint 幂等）。
"""
import argparse
import importlib.util
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_OUT = os.path.join("data", "gx_materials", "pack_calc_gen.json")
DEFAULT_SEED = 20260930
SRC_KIND = "生成计算"
SOURCE_FILE = "tools/gx_calc_gen.py"


def _load_sibling(name):
    """tools/ 不是 package，按路径加载 gx_parse（与 gx_pack.py 同一手法）"""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("_gx_" + name,
                                                  os.path.join(here, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


gx = _load_sibling("gx_parse")


# ── 数值与选项 ──────────────────────────────────────────────────────────

def _num(v, nd=0):
    """按位数格式化：整数不带小数点，小数补到 nd 位"""
    if nd <= 0:
        return str(int(round(v)))
    s = ("%.*f" % (nd, v))
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _nudge(v, tries, nd=0):
    """干扰项去重用：给数值一个小偏移，偏移量随位数缩放（不要偏移到 0）"""
    step = (10.0 ** -nd) * tries if nd else tries
    for k in range(1, 10):
        nv = v + step * k
        if abs(nv) > 1e-9:
            return nv
    return v + step


def _make_choice(question, correct, distractors, unit, analysis, rng,
                 nd=0, domain="", chapter=""):
    """把「正确值 + 干扰值」组装成四选一。

    返回题目字典（options 已打乱，answer 是打乱后的字母）。
    """
    vals, seen = [correct], {_num(correct, nd)}
    for d in distractors:
        v, tries = d, 0
        while _num(v, nd) in seen and tries < 8:
            tries += 1
            v = _nudge(d, tries, nd)
        key = _num(v, nd)
        if key in seen:
            continue
        seen.add(key)
        vals.append(v)
        if len(vals) == 4:
            break
    # 干扰项不够（撞车太多）→ 用正确值的偏移补齐，保证仍有四个选项
    i = 1
    while len(vals) < 4:
        v = _nudge(correct, i, nd)
        i += 1
        key = _num(v, nd)
        if key not in seen:
            seen.add(key)
            vals.append(v)

    labels = ["A", "B", "C", "D"]
    # ⚠️ 必须先打乱**数值**，再按新位置生成字母前缀。反过来（先写好 "A. " 前缀再打乱）
    # 会让字母与位置脱钩 —— 解析里算出的正确答案对应到别的选项上，整批题答案全错。
    order = vals[:]
    rng.shuffle(order)
    options = ["%s. %s%s" % (labels[i], _num(v, nd), unit)
               for i, v in enumerate(order)]
    answer = labels[order.index(correct)]
    return {
        "domain": domain,
        "chapter": chapter,
        "question": question,
        "options": options,
        "answer": answer,
        "analysis": analysis,
        # 正确答案的**文本**，供 verify() 比对（写文件前会被剔除，不进数据包）
        "answer_text": "%s%s" % (_num(correct, nd), unit),
    }


# ── 考点 1：三点估算 / PERT ────────────────────────────────────────────

def gen_pert(rng):
    """三角分布 (O+M+P)/3、β分布 (O+4M+P)/6、标准差 (P-O)/6、以及反推最悲观值"""
    M = rng.randint(20, 150)
    d1 = rng.randint(2, 15)              # M - O
    # 让 (d2 - d1) 同时被 3 和 6 整除 → 三角与 β 的估算值都是整数
    d2 = d1 + rng.choice([-6, 0, 6, 12])
    if d2 <= 0:
        d2 = d1 + 6
    O, P = M - d1, M + d2
    tri = M + (d2 - d1) / 3.0
    beta = M + (d2 - d1) / 6.0
    sigma = (P - O) / 6.0
    dom, chap = "成本管理", "第11章 成本管理"
    kind = rng.choice(["beta", "tri", "sigma", "reverse"])
    head = ("某项目一项活动的成本估算：最乐观 %d 万元，最可能 %d 万元，最悲观 %d 万元。"
            % (O, M, P))

    if kind == "beta":
        q = head + "按 β 分布（PERT）计算，该项活动的期望成本是（）万元？"
        return _make_choice(
            q, beta, [tri, (O + M + P) / 2.0, (O + 4 * M + P) / 3.0], "",
            "β 分布（PERT）公式：E = (O + 4M + P) / 6 = (%d + 4×%d + %d) / 6 = %s（万元）。\n"
            "注意别和三角分布 (O+M+P)/3 混淆。" % (O, M, P, _num(beta, 1)),
            rng, nd=1, domain=dom, chapter=chap)
    if kind == "tri":
        q = head + "按三角分布计算，该项活动的期望成本是（）万元？"
        return _make_choice(
            q, tri, [beta, (O + M + P) / 2.0, (O + 4 * M + P) / 3.0], "",
            "三角分布公式：E = (O + M + P) / 3 = (%d + %d + %d) / 3 = %s（万元）。"
            % (O, M, P, _num(tri, 1)),
            rng, nd=1, domain=dom, chapter=chap)
    if kind == "sigma":
        q = head + "该项活动成本估算的标准差是（）万元（保留两位小数）？"
        return _make_choice(
            q, sigma, [(P - O) / 3.0, (P - O) / 2.0, (P + O) / 6.0], "",
            "标准差 σ = (P − O) / 6 = (%d − %d) / 6 = %s（万元）。\n"
            "方差则是 σ²。" % (P, O, _num(sigma, 2)),
            rng, nd=2, domain=dom, chapter=chap)
    # reverse：已知两个分布的结果，反推最悲观值（真题常见套路）
    q = ("某项目估算，最乐观成本 %d 万元，利用三点估算法，按三角分布计算出的值为 %s 万元，"
         "按 β 分布计算出的值为 %s 万元，则最悲观成本为（）万元？"
         % (O, _num(tri, 1), _num(beta, 1)))
    return _make_choice(
        q, P, [P - d1, P + d1, M], "",
        "设最悲观为 X，最可能为 Y：\n"
        "三角分布：(%d + X + Y) / 3 = %s\nβ 分布：(%d + X + 4Y) / 6 = %s\n"
        "联立解得 X = %d、Y = %d，所以最悲观成本为 %d 万元。"
        % (O, _num(tri, 1), O, _num(beta, 1), P, M, P),
        rng, nd=0, domain=dom, chapter=chap)


# ── 考点 2：挣值分析 EVM ───────────────────────────────────────────────

def gen_evm(rng):
    """CV/SV/CPI/SPI/EAC/ETC/VAC/TCPI —— 软考计算题第一大考点"""
    BAC = rng.choice([1000, 1200, 1500, 2000, 2400, 3000, 5000])
    AC = int(BAC * rng.choice([0.4, 0.45, 0.5, 0.55, 0.6, 0.75, 0.8]))
    EV = int(BAC * rng.choice([0.35, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.9]))
    PV = int(BAC * rng.choice([0.4, 0.5, 0.6, 0.7, 0.8]))
    cv, sv = EV - AC, EV - PV
    cpi, spi = EV / AC, EV / PV
    eac_typ = BAC * AC / EV          # 典型偏差：按当前 CPI 外推
    eac_atyp = AC + (BAC - EV)       # 非典型：剩余工作按原预算
    dom, chap = "成本管理", "第11章 成本管理"
    head = ("某项目总预算 BAC = %d 万元，当前时点：计划价值 PV = %d 万元，"
            "挣值 EV = %d 万元，实际成本 AC = %d 万元。" % (BAC, PV, EV, AC))
    kind = rng.choice(["cv", "sv", "cpi", "spi", "eac_typ", "eac_atyp",
                       "etc", "vac", "tcpi"])

    if kind == "cv":
        q = head + "此时的成本偏差 CV 为（）万元？"
        return _make_choice(
            q, cv, [AC - EV, EV + AC, PV - AC], "",
            "CV = EV − AC = %d − %d = %d（万元）。\nCV > 0 表示成本节约，< 0 表示成本超支。"
            % (EV, AC, cv), rng, domain=dom, chapter=chap)
    if kind == "sv":
        q = head + "此时的进度偏差 SV 为（）万元？"
        return _make_choice(
            q, sv, [PV - EV, EV + PV, EV - AC], "",
            "SV = EV − PV = %d − %d = %d（万元）。\nSV > 0 表示进度提前，< 0 表示进度滞后。"
            % (EV, PV, sv), rng, domain=dom, chapter=chap)
    if kind == "cpi":
        q = head + "成本绩效指数 CPI 为（）（保留两位小数）？"
        return _make_choice(
            q, cpi, [AC / EV, EV / PV, AC / PV], "",
            "CPI = EV / AC = %d / %d = %s。\nCPI > 1 成本节约，< 1 成本超支。"
            % (EV, AC, _num(cpi, 2)), rng, nd=2, domain=dom, chapter=chap)
    if kind == "spi":
        q = head + "进度绩效指数 SPI 为（）（保留两位小数）？"
        return _make_choice(
            q, spi, [PV / EV, EV / AC, PV / AC], "",
            "SPI = EV / PV = %d / %d = %s。\nSPI > 1 进度提前，< 1 进度滞后。"
            % (EV, PV, _num(spi, 2)), rng, nd=2, domain=dom, chapter=chap)
    if kind == "eac_typ":
        q = (head + "若认为当前偏差具有典型性（会持续到项目结束），"
             "则完工估算 EAC 为（）万元（保留两位小数）？")
        return _make_choice(
            q, eac_typ, [eac_atyp, BAC - cv, BAC * EV / AC], "",
            "典型偏差：EAC = BAC / CPI = BAC × AC / EV = %d × %d / %d = %s（万元）。"
            % (BAC, AC, EV, _num(eac_typ, 2)), rng, nd=2, domain=dom, chapter=chap)
    if kind == "eac_atyp":
        q = (head + "若认为当前偏差是非典型的（剩余工作按原预算完成），"
             "则完工估算 EAC 为（）万元？")
        return _make_choice(
            q, eac_atyp, [eac_typ, BAC + cv, BAC - EV], "",
            "非典型偏差：EAC = AC + (BAC − EV) = %d + (%d − %d) = %d（万元）。"
            % (AC, BAC, EV, eac_atyp), rng, domain=dom, chapter=chap)
    if kind == "etc":
        eac = eac_typ
        q = (head + "按典型偏差估算，完工尚需绩效估算 ETC 为（）万元（保留两位小数）？")
        return _make_choice(
            q, eac - AC, [eac, BAC - EV, eac_atyp - AC], "",
            "ETC = EAC − AC；典型偏差下 EAC = BAC × AC / EV = %s，"
            "故 ETC = %s − %d = %s（万元）。"
            % (_num(eac, 2), _num(eac, 2), AC, _num(eac - AC, 2)),
            rng, nd=2, domain=dom, chapter=chap)
    if kind == "vac":
        eac = eac_typ
        q = head + "按典型偏差估算，完工偏差 VAC 为（）万元（保留两位小数）？"
        return _make_choice(
            q, BAC - eac, [eac - BAC, BAC - eac_atyp, cv], "",
            "VAC = BAC − EAC = %d − %s = %s（万元）。\nVAC < 0 表示预计完工将超支。"
            % (BAC, _num(eac, 2), _num(BAC - eac, 2)),
            rng, nd=2, domain=dom, chapter=chap)
    # tcpi
    denom = BAC - AC
    tcpi = (BAC - EV) / denom if denom else 0
    q = head + "按预算完工所需的完工尚需绩效指数 TCPI 为（）（保留两位小数）？"
    return _make_choice(
        q, tcpi, [EV / AC, (BAC - AC) / (BAC - EV), BAC / EV], "",
        "TCPI = (BAC − EV) / (BAC − AC) = (%d − %d) / (%d − %d) = %s。\n"
        "TCPI > 1 说明剩余工作必须比过去更高效才能按预算完工。"
        % (BAC, EV, BAC, AC, _num(tcpi, 2)), rng, nd=2, domain=dom, chapter=chap)


# ── 考点 3：沟通渠道数 ─────────────────────────────────────────────────

def gen_channels(rng):
    """n(n-1)/2 —— 送分题，但真题必考"""
    dom, chap = "沟通管理", "第14章 沟通管理"
    n = rng.randint(5, 15)
    total = n * (n - 1) // 2
    if rng.random() < 0.5:
        q = "某项目团队共有 %d 名成员，则该团队内部的沟通渠道数为（）条？" % n
        return _make_choice(
            q, total, [n * (n - 1), n * (n + 1) // 2, (n - 1) * (n - 2) // 2], "",
            "沟通渠道数 = n(n − 1) / 2 = %d × %d / 2 = %d（条）。\n"
            "注意是除以 2（每条渠道被两个人共享），不是 n(n−1)。" % (n, n - 1, total),
            rng, domain=dom, chapter=chap)
    m = rng.randint(2, 8)
    after = (n + m) * (n + m - 1) // 2
    q = ("某项目团队原有 %d 人，沟通渠道数为 %d 条；现新增 %d 名成员，"
         "则沟通渠道数增加了（）条？" % (n, total, m))
    return _make_choice(
        q, after - total, [after, m * (m - 1) // 2, (n + m) * (n + m - 1)], "",
        "原渠道数 = %d × %d / 2 = %d；新增后 = %d × %d / 2 = %d；"
        "增加了 %d − %d = %d（条）。"
        % (n, n - 1, total, n + m, n + m - 1, after, after, total, after - total),
        rng, domain=dom, chapter=chap)


# ── 考点 4：关键路径 CPM ───────────────────────────────────────────────

def _cpm(dur, deps):
    """前向/后向计算：返回 (总工期, 各活动 ES/EF/LS/LF, 总浮动)"""
    # deps: {活动: [前置]}
    es, ef = {}, {}
    for a in _topo(dur, deps):
        pre = deps.get(a) or []
        es[a] = max((ef[p] for p in pre), default=0)
        ef[a] = es[a] + dur[a]
    total = max(ef.values())
    ls, lf = {}, {}
    for a in reversed(_topo(dur, deps)):
        nxt = [b for b in dur if a in (deps.get(b) or [])]
        lf[a] = min((ls[b] for b in nxt), default=total)
        ls[a] = lf[a] - dur[a]
    return total, {a: (es[a], ef[a], ls[a], lf[a], ls[a] - es[a]) for a in dur}


def _topo(dur, deps):
    """按依赖关系做拓扑排序（活动数很少，直接 Kahn）"""
    order, done = [], set()
    while len(order) < len(dur):
        for a in dur:
            if a in done:
                continue
            if all(p in done for p in (deps.get(a) or [])):
                order.append(a)
                done.add(a)
    return order


def gen_cpm(rng):
    """关键路径总工期 + 某活动的总浮动时间"""
    dom, chap = "进度管理", "第10章 进度管理"
    dur = {"A": rng.randint(2, 8), "B": rng.randint(2, 9), "C": rng.randint(2, 9),
           "D": rng.randint(2, 8), "E": rng.randint(2, 7), "F": rng.randint(2, 8)}
    deps = {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"], "E": ["C"], "F": ["D", "E"]}
    total, info = _cpm(dur, deps)
    txt = "、".join("%s %d 天" % (a, dur[a]) for a in "ABCDEF")
    rel = ("活动 B、C 必须在 A 完成后开始；活动 D 必须在 B 和 C 完成后开始；"
           "活动 E 必须在 C 完成后开始；活动 F 必须在 D 和 E 完成后开始。")
    if rng.random() < 0.5:
        q = ("某项目包含 A~F 六个活动，各活动工期分别为：%s。依赖关系：%s"
             "该项目的关键路径长度为（）天？" % (txt, rel))
        return _make_choice(
            q, total, [total - min(dur.values()), total + max(dur.values()),
                       sum(dur.values()) // len(dur) * 3], "",
            "三条路径：A-B-D-F = %d；A-C-D-F = %d；A-C-E-F = %d。\n"
            "最长的一条即关键路径，长度为 %d 天。"
            % (dur["A"] + dur["B"] + dur["D"] + dur["F"],
               dur["A"] + dur["C"] + dur["D"] + dur["F"],
               dur["A"] + dur["C"] + dur["E"] + dur["F"], total),
            rng, domain=dom, chapter=chap)
    act = rng.choice("BCE")
    tf = info[act][4]
    via_act = total - tf          # 经过该活动的最长路径长度
    q = ("某项目包含 A~F 六个活动，各活动工期分别为：%s。依赖关系：%s"
         "活动 %s 的总浮动时间为（）天？" % (txt, rel, act))
    return _make_choice(
        q, tf, [tf + 1, max(0, tf - 1), 0], "",
        "关键路径长 %d 天；经过活动 %s 的最长路径为 %d 天，\n"
        "总浮动 = 关键路径长度 − 该路径长度 = %d − %d = %d（天）。"
        % (total, act, via_act, total, via_act, tf),
        rng, domain=dom, chapter=chap)


# ── 考点 5：决策树 EMV ─────────────────────────────────────────────────

def gen_emv(rng):
    """期望货币价值：两方案各两个概率分支，选 EMV 最优"""
    dom, chap = "风险管理", "第15章 风险管理"
    p = rng.choice([0.3, 0.4, 0.5, 0.6, 0.7])
    # 方案甲：成功 p 收益 a1，失败 (1-p) 亏损 b1
    a1 = rng.randint(60, 200)
    b1 = rng.randint(10, 60)
    emv1 = p * a1 - (1 - p) * b1
    # 方案乙：让 EMV 与之接近但不是同一个数
    a2 = rng.randint(60, 200)
    b2 = rng.randint(10, 60)
    emv2 = p * a2 - (1 - p) * b2
    if abs(emv1 - emv2) < 3:
        # 两方案太接近会失去区分度：反解出方案乙的收益，再按公式重算 EMV
        target = emv1 + rng.choice([-12, -8, 8, 12])
        a2 = int(round((target + (1 - p) * b2) / p))
        emv2 = p * a2 - (1 - p) * b2
    best = max(emv1, emv2)
    q = ("某公司需在两个方案中选择：方案甲有 %d%% 的概率获利 %d 万元，"
         "%d%% 的概率亏损 %d 万元；方案乙有 %d%% 的概率获利 %d 万元，"
         "%d%% 的概率亏损 %d 万元。按期望货币价值（EMV）决策，"
         "最优方案的 EMV 为（）万元（保留一位小数）？"
         % (int(p * 100), a1, int((1 - p) * 100), b1,
            int(p * 100), a2, int((1 - p) * 100), b2))
    return _make_choice(
        q, best, [min(emv1, emv2), (emv1 + emv2) / 2, max(a1, a2) * p], "",
        "EMV(甲) = %d%% × %d − %d%% × %d = %s；\n"
        "EMV(乙) = %d%% × %d − %d%% × %d = %s；\n"
        "取较大者，最优 EMV = %s（万元）。"
        % (int(p * 100), a1, int((1 - p) * 100), b1, _num(emv1, 1),
           int(p * 100), a2, int((1 - p) * 100), b2, _num(emv2, 1), _num(best, 1)),
        rng, nd=1, domain=dom, chapter=chap)


# ── 考点 6：NPV 与投资回收期 ──────────────────────────────────────────

def gen_npv(rng):
    """净现值 NPV / 静态投资回收期"""
    dom, chap = "项目立项管理", "第7章 项目立项管理"
    inv = rng.choice([100, 150, 200, 300, 500])
    years = rng.randint(3, 4)
    rate = rng.choice([0.05, 0.1, 0.12])
    # 必须保证累计现金流能覆盖投资，否则「投资回收期」无解（题目会自相矛盾）
    cfs = []
    for _ in range(40):
        cfs = [rng.randint(30, 120) for _ in range(years)]
        if sum(cfs) > inv * 1.1:
            break
    else:
        return None
    npv = -inv + sum(cf / ((1 + rate) ** (i + 1)) for i, cf in enumerate(cfs))
    flows = "，第".join("%d 年现金流 %d 万元" % (i + 1, cf) for i, cf in enumerate(cfs))
    head = "某项目初期投资 %d 万元，第%s，折现率为 %d%%。" % (inv, flows, int(rate * 100))
    if rng.random() < 0.5:
        q = head + "该项目的净现值 NPV 为（）万元（保留两位小数）？"
        return _make_choice(
            q, npv, [npv + inv, -npv, sum(cfs) - inv], "",
            "NPV = −%d + " % inv + " + ".join(
                "%d/%.2f^%d" % (cf, 1 + rate, i + 1) for i, cf in enumerate(cfs))
            + " = %s（万元）。\nNPV > 0 项目可行。" % _num(npv, 2),
            rng, nd=2, domain=dom, chapter=chap)
    # 静态投资回收期（含小数年）
    acc, payback = 0, None
    for i, cf in enumerate(cfs):
        if acc + cf >= inv:
            payback = i + (inv - acc) / cf
            break
        acc += cf
    if payback is None:
        return None
    year = max(1, int(payback) + (0 if payback == int(payback) else 1))
    q = head + "该项目的静态投资回收期约为（）年（保留两位小数）？"
    return _make_choice(
        q, payback, [payback + 1, max(0.5, payback - 1), float(years)], "",
        "累计现金流：%s。\n在第 %d 年累计达到投资额 %d 万元，"
        "故静态投资回收期 ≈ %s 年。"
        % ("、".join(str(sum(cfs[:i + 1])) for i in range(len(cfs))),
           year, inv, _num(payback, 2)),
        rng, nd=2, domain=dom, chapter=chap)


# ── 考点 7：投资收益率与盈亏平衡 ──────────────────────────────────────

def gen_roi(rng):
    """投资收益率 ROI / 盈亏平衡点产量"""
    dom, chap = "项目立项管理", "第7章 项目立项管理"
    if rng.random() < 0.5:
        cost = rng.choice([100, 200, 250, 400, 500])
        gain = int(cost * rng.choice([1.15, 1.2, 1.25, 1.3, 1.4, 1.5]))
        roi = (gain - cost) / cost * 100
        q = ("某项目投资 %d 万元，项目完成后预计总收益 %d 万元，"
             "则该项目的投资收益率 ROI 为（）%%？" % (cost, gain))
        return _make_choice(
            q, roi, [roi / 2, (gain - cost) / gain * 100, roi + 10], "",
            "ROI = (收益 − 投资) / 投资 × 100%% = (%d − %d) / %d × 100%% = %s%%。"
            % (gain, cost, cost, _num(roi, 1)), rng, nd=1, domain=dom, chapter=chap)
    fc = rng.choice([20000, 30000, 50000, 60000, 80000])     # 固定成本
    vc = rng.randint(20, 60)                                  # 单位变动成本
    price = vc + rng.randint(15, 60)                          # 单价
    bep = fc / (price - vc)
    q = ("某产品固定成本 %d 元，单位变动成本 %d 元/件，售价 %d 元/件。"
         "该产品的盈亏平衡点产量为（）件？" % (fc, vc, price))
    return _make_choice(
        q, bep, [fc / price, fc / (price + vc), bep * 1.2], "",
        "盈亏平衡点产量 = 固定成本 / (单价 − 单位变动成本) = %d / (%d − %d) = %s（件）。"
        % (fc, price, vc, _num(bep, 0)), rng, domain=dom, chapter=chap)


# ── 考点 8：后悔值决策 ────────────────────────────────────────────────

def gen_regret(rng):
    """最小最大后悔值：收益矩阵 → 后悔矩阵 → 选最大后悔值最小的方案"""
    dom, chap = "风险管理", "第15章 风险管理"
    names = ["甲", "乙", "丙"]
    states = ["好", "中", "差"]
    # 收益矩阵 3×3
    mat = [[rng.randint(20, 200) for _ in states] for _ in names]
    # 每个状态下的最优收益
    best_of_state = [max(mat[i][j] for i in range(len(names))) for j in range(len(states))]
    regret = [[best_of_state[j] - mat[i][j] for j in range(len(states))]
              for i in range(len(names))]
    max_regret = [max(r) for r in regret]
    if max_regret.count(min(max_regret)) > 1:
        return None                      # 并列会让答案有歧义，换一组随机数重来
    pick = max_regret.index(min(max_regret))
    correct = names[pick]
    rows = "；".join(
        "%s 方案在%s、%s、%s 三种市场状态下的收益分别为 %d、%d、%d 万元"
        % (names[i], states[0], states[1], states[2], *mat[i]) for i in range(len(names)))
    q = ("某公司有甲、乙、丙三种方案，%s。若采用最小最大后悔值准则决策，"
         "应选择（）方案？" % rows)
    # 命名型选项（不是数值），单独走 _shuffle_named —— 只打乱一次，
    # 否则选项与答案字母会对不上（打乱两次必然错位）。
    options = _shuffle_named(correct, [n for n in names if n != correct], rng)
    return {
        "domain": dom,
        "chapter": chap,
        "question": q,
        "options": options,
        "answer": _letter_of(options, correct),
        "answer_text": correct,
        "analysis": "各状态下的最优收益：%s。\n后悔矩阵：%s。\n"
                    "各方案最大后悔值：%s，取最小者 → 选%s方案。"
                    % ("、".join(str(b) for b in best_of_state),
                       "；".join("（%s：%s）" % (names[i],
                                              "、".join(str(x) for x in regret[i]))
                                 for i in range(len(names))),
                       "、".join("%s=%d" % (names[i], max_regret[i])
                                 for i in range(len(names))),
                       correct),
    }


def _shuffle_named(correct, others, rng):
    """四个命名选项（甲/乙/丙 + 一个干扰）打乱成 A/B/C/D"""
    pool = [correct] + list(others)
    while len(pool) < 4:
        pool.append("无法确定")
    rng.shuffle(pool)
    return ["%s. %s" % (l, o) for l, o in zip("ABCD", pool)]


def _letter_of(options, correct):
    for o in options:
        if o.split(". ", 1)[-1] == correct:
            return o.split(".")[0]
    return "A"


# ── 考点 9：指派问题（匈牙利法，4×4 规模直接枚举） ────────────────────

def _perms(n):
    if n <= 1:
        yield (0,)
        return
    for p in _perms(n - 1):
        for i in range(n):
            yield p[:i] + (n - 1,) + p[i:]


def gen_assignment(rng):
    """4 人 4 任务，每人一项，求最短总工时"""
    dom, chap = "资源管理", "第13章 资源管理"
    names = ["甲", "乙", "丙", "丁"]
    tasks = ["A", "B", "C", "D"]
    mat = [[rng.randint(3, 20) for _ in tasks] for _ in names]
    best = min(sum(mat[i][p[i]] for i in range(4)) for p in _perms(4))
    table = "；".join("%s 完成 %s 分别需 %s 天" % (names[i], "、".join(tasks),
                                                "、".join(str(x) for x in mat[i]))
                      for i in range(4))
    q = ("有甲、乙、丙、丁四人分别去完成 A、B、C、D 四项任务，每人完成一项。"
         "各人完成各项任务所需时间：%s。为使总时间最短，"
         "最短总时间为（）天？" % table)
    return _make_choice(
        q, best, [best + rng.randint(2, 6), max(min(r) for r in mat) * 4,
                  sum(min(r) for r in mat)], "",
        "四人四项任务共 4! = 24 种分配方案，枚举取最小总时间 = %d（天）。\n"
        "也可用匈牙利法求解。" % best, rng, domain=dom, chapter=chap)


GENERATORS = [
    ("三点估算", gen_pert),
    ("挣值分析", gen_evm),
    ("沟通渠道", gen_channels),
    ("关键路径", gen_cpm),
    ("决策树EMV", gen_emv),
    ("NPV与回收期", gen_npv),
    ("投资与盈亏平衡", gen_roi),
    ("后悔值决策", gen_regret),
    ("指派问题", gen_assignment),
]


# ── 组装 ────────────────────────────────────────────────────────────────

def build(seed=DEFAULT_SEED, per_kind=40, existing=()):
    """生成全部题目。

    `existing` 是已存在的 fingerprint 集合 —— 撞车的题直接丢弃，保证导入时
    不会和线上已有题目重复，也不会和本批内部重复。
    """
    items, seen, dropped = [], set(existing), 0
    for ki, (label, fn) in enumerate(GENERATORS):
        rng = random.Random(seed + ki * 7919)
        got = 0
        for _ in range(per_kind * 12):        # 撞车就换一组随机数再试
            if got >= per_kind:
                break
            try:
                it = fn(rng)
            except Exception:
                continue
            if not it or not it.get("question"):
                continue
            fp = gx.fingerprint(it["question"], "".join(it["options"]))
            if fp in seen:
                dropped += 1
                continue
            seen.add(fp)
            it.update({
                "fingerprint": fp,
                "source_kind": SRC_KIND,
                "source_file": SOURCE_FILE,
                "deck": label[:20],
                "category": "选择题练习",
                "sub_kind": "计算专题",
                "seq": len(items) + 1,
                "sources": [SOURCE_FILE],
            })
            items.append(it)
            got += 1
    return items, dropped


def verify(items):
    """自检：答案字母指向的选项必须**就是**生成器算出的正确值

    光检查「答案在 A~D 里」是不够的 —— 曾经踩过一次：字母前缀在打乱选项**之前**
    就写死了，打乱后字母与位置脱钩，180 道题的答案全部指向错误选项，而「答案字母
    合法、四个选项互不相同」这两项检查全都过得去。所以这里必须拿 `answer_text`
    （生成器算出的正确值）和「答案字母实际指向的选项文本」做比对。
    """
    bad = []
    for it in items:
        opts = it.get("options") or []
        ans = (it.get("answer") or "").strip()
        want = it.get("answer_text")
        if len(opts) != 4 or ans not in ("A", "B", "C", "D"):
            bad.append((it.get("fingerprint"), "选项数或答案字母异常", ans))
            continue
        texts = [o.split(". ", 1)[-1] for o in opts]
        if len(set(texts)) != 4:
            bad.append((it.get("fingerprint"), "选项重复", texts))
        picked = dict(zip("ABCD", texts)).get(ans, "")
        if want is not None and picked != want:
            bad.append((it.get("fingerprint"), "答案指向错误选项",
                        "应为 %r，实际指向 %r" % (want, picked)))
    return bad


def main():
    ap = argparse.ArgumentParser(description="高项计算题参数化生成器")
    ap.add_argument("--out", default=DEFAULT_OUT, help="产出路径")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子")
    ap.add_argument("--per-kind", type=int, default=40, help="每个考点生成条数")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--verify", action="store_true", help="生成后做答案自检")
    args = ap.parse_args()

    # 已有的选择题指纹：避免和线上/数据包里的真题重复
    existing = set()
    choice_path = Path("data/gx_materials/pack_choice.json")
    if choice_path.exists():
        try:
            payload = json.loads(choice_path.read_text(encoding="utf-8"))
            for it in payload.get("items") or []:
                fp = it.get("fingerprint")
                if fp:
                    existing.add(fp)
        except Exception as exc:
            print("读取已有选择题数据包失败（忽略去重）：%s" % exc)

    items, dropped = build(seed=args.seed, per_kind=args.per_kind, existing=existing)

    print("-" * 68)
    print("高项计算题生成：种子 %d，每考点 %d 条" % (args.seed, args.per_kind))
    print("  考点 %d 个 → 产出 %d 条（与已有题库撞车丢弃 %d 条）"
          % (len(GENERATORS), len(items), dropped))
    import collections
    by_deck = collections.Counter(i["deck"] for i in items)
    for label, _ in GENERATORS:
        print("    %-14s %3d 条" % (label, by_deck.get(label[:20], 0)))

    if args.verify:
        bad = verify(items)
        print("\n答案自检：%s" % ("全部通过（%d 条）" % len(items) if not bad
                               else "发现 %d 条异常" % len(bad)))
        for fp, why, extra in bad[:10]:
            print("   %s → %s：%s" % (fp, why, str(extra)[:80]))
        if bad:
            return 1

    if not args.dry_run:
        # answer_text 只是自检用的中间量，不进数据包（导入脚本不认这个字段）
        for it in items:
            it.pop("answer_text", None)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"generated_by": "tools/gx_calc_gen.py", "seed": args.seed,
             "kinds": [k for k, _ in GENERATORS], "items": items},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n已写入：%s（%d 条）" % (out, len(items)))
    else:
        print("\n（--dry-run，未写文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
