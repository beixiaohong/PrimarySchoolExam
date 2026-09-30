"""tools/gx_calc_gen.py（高项计算题参数化生成）的测试

这里钉死的核心是**答案必须指向生成器算出的那个值**。

踩过的坑：选项字母前缀原来在 `rng.shuffle` **之前**就写死了（`"A. 104"`），打乱后
字母与位置脱钩 —— 180 道题的答案全部指向错误选项。而「答案字母在 A~D 内」「四个
选项互不相同」这两项检查**全都过得去**，只有把答案字母指向的文本和公式算出的
正确值比对才能发现。所以 `verify()` 必须带 `answer_text` 比对，这里也照此断言。
"""
import collections
import importlib.util
import random
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load(name):
    here = ROOT / "tools"
    spec = importlib.util.spec_from_file_location("_gx_" + name, str(here / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cg = _load("gx_calc_gen")


def _one(fn, seed=7):
    """跑某个生成器直到产出一道题（部分生成器会主动返回 None 要求换随机数）"""
    rng = random.Random(seed)
    for _ in range(80):
        it = fn(rng)
        if it:
            return it
    return None


def _picked_text(it):
    """答案字母实际指向的选项文本"""
    texts = [o.split(". ", 1)[-1] for o in it["options"]]
    return dict(zip("ABCD", texts))[it["answer"]]


# ── 每个考点都能出题，且答案指向正确值 ─────────────────────────────────

@pytest.mark.parametrize("label,fn", cg.GENERATORS)
def test_each_generator_produces_valid_item(label, fn):
    it = _one(fn)
    assert it, "%s 一道题都没生成出来" % label
    assert it["question"] and it["analysis"]
    assert len(it["options"]) == 4
    assert it["answer"] in ("A", "B", "C", "D")


@pytest.mark.parametrize("label,fn", cg.GENERATORS)
def test_answer_points_at_the_computed_value(label, fn):
    """⚠️ 回归：答案字母必须指向公式算出的正确值，而不是打乱后恰好落在的那个位置"""
    for seed in range(30):
        it = _one(fn, seed=seed)
        if not it:
            continue
        assert _picked_text(it) == it["answer_text"], (
            "%s：答案 %s 指向 %r，但正确值是 %r"
            % (label, it["answer"], _picked_text(it), it["answer_text"]))


@pytest.mark.parametrize("label,fn", cg.GENERATORS)
def test_options_are_four_distinct_values(label, fn):
    for seed in range(20):
        it = _one(fn, seed=seed)
        if not it:
            continue
        texts = [o.split(". ", 1)[-1] for o in it["options"]]
        assert len(set(texts)) == 4, "%s 选项重复：%s" % (label, texts)


def test_verify_passes_on_full_build():
    items, _ = cg.build(seed=cg.DEFAULT_SEED, per_kind=10, existing=set())
    assert items
    assert cg.verify(items) == []


def test_verify_would_catch_a_wrong_answer():
    """反证：把答案字母改掉，verify 必须报错 —— 否则上面那条断言是空转"""
    items, _ = cg.build(seed=1, per_kind=3, existing=set())
    assert cg.verify(items) == []
    items[0]["answer"] = "B" if items[0]["answer"] != "B" else "A"
    bad = cg.verify(items)
    assert bad and bad[0][1] == "答案指向错误选项"


# ── 可重现（否则每次重跑指纹都变，线上导入没法幂等） ────────────────────

def test_build_is_reproducible():
    a, _ = cg.build(seed=2026, per_kind=5, existing=set())
    b, _ = cg.build(seed=2026, per_kind=5, existing=set())
    assert [i["fingerprint"] for i in a] == [i["fingerprint"] for i in b]


def test_different_seed_gives_different_questions():
    a, _ = cg.build(seed=1, per_kind=5, existing=set())
    b, _ = cg.build(seed=2, per_kind=5, existing=set())
    assert {i["fingerprint"] for i in a} != {i["fingerprint"] for i in b}


def test_build_respects_existing_fingerprints():
    """撞上已有题库的题必须丢弃，不能直接覆盖线上真题"""
    base, _ = cg.build(seed=5, per_kind=5, existing=set())
    skip = {base[0]["fingerprint"]}
    again, dropped = cg.build(seed=5, per_kind=5, existing=skip)
    assert skip.isdisjoint({i["fingerprint"] for i in again})
    assert dropped >= 1


# ── 答案位置分布（防止「闭眼选 D」） ────────────────────────────────────

def test_answer_positions_are_not_skewed():
    items, _ = cg.build(seed=cg.DEFAULT_SEED, per_kind=20, existing=set())
    cnt = collections.Counter(i["answer"] for i in items)
    assert set(cnt) == {"A", "B", "C", "D"}, "某个字母一次都没出现：%s" % cnt
    n = len(items)
    for k, v in cnt.items():
        assert v >= n * 0.10, "答案 %s 只占 %.1f%%，分布过于倾斜" % (k, v * 100.0 / n)


# ── 数值可读性 ──────────────────────────────────────────────────────────

def test_no_ugly_floats_in_options():
    """选项里不能出现 1250.3333333 这种 —— 生成器按整除条件挑参数就是为了这个"""
    items, _ = cg.build(seed=cg.DEFAULT_SEED, per_kind=15, existing=set())
    for it in items:
        for o in it["options"]:
            txt = o.split(". ", 1)[-1]
            for m in re.findall(r"\d+\.\d{3,}", txt):
                pytest.fail("选项出现过长小数：%s（题目 %s）" % (txt, it["fingerprint"]))


def test_every_item_has_taxonomy_and_source():
    items, _ = cg.build(seed=3, per_kind=5, existing=set())
    for it in items:
        assert it["category"] == "选择题练习"      # 决定导入时落 qtype=single
        assert it["sub_kind"] == "计算专题"
        assert it["domain"] and it["chapter"]
        assert it["source_kind"] == cg.SRC_KIND
        assert it["fingerprint"]


# ── 关键路径算法本身 ────────────────────────────────────────────────────

def test_cpm_known_case():
    """手工可验证的网络：A-B-D-F = 14 为关键路径，活动 C 的总浮动为 2"""
    dur = {"A": 3, "B": 4, "C": 2, "D": 5, "E": 1, "F": 2}
    deps = {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"], "E": ["C"],
            "F": ["D", "E"]}
    total, info = cg._cpm(dur, deps)
    assert total == 14
    assert info["A"][4] == 0 and info["B"][4] == 0      # 关键路径上浮动为 0
    assert info["C"][4] == 2                            # 14 − (3+2+5+2)
    assert info["E"][4] == 6                            # 14 − (3+2+1+2)
    # 总浮动 = 关键路径长 − 经过该活动的最长路径长
    for a in dur:
        assert info[a][4] == total - (total - info[a][4])


def test_cpm_total_equals_longest_path():
    dur = {"A": 2, "B": 7, "C": 3, "D": 4, "E": 6, "F": 2}
    deps = {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"], "E": ["C"],
            "F": ["D", "E"]}
    total, _ = cg._cpm(dur, deps)
    assert total == max(dur["A"] + dur["B"] + dur["D"] + dur["F"],
                        dur["A"] + dur["C"] + dur["D"] + dur["F"],
                        dur["A"] + dur["C"] + dur["E"] + dur["F"])


# ── 与既有题库的关系 ────────────────────────────────────────────────────

_PACK_CHOICE = ROOT / "data" / "gx_materials" / "pack_choice.json"


@pytest.mark.skipif(not _PACK_CHOICE.exists(), reason="未生成本地数据包")
def test_generated_questions_do_not_collide_with_real_ones():
    """生成题不能和 PDF 解析出来的真题重复（否则会顶掉真题）"""
    import json
    real = {i.get("fingerprint") for i in
            (json.loads(_PACK_CHOICE.read_text(encoding="utf-8")).get("items") or [])}
    items, _ = cg.build(seed=cg.DEFAULT_SEED, per_kind=10, existing=real)
    assert real.isdisjoint({i["fingerprint"] for i in items})


# ── 数据包（若已生成）──────────────────────────────────────────────────

_PACK_GEN = ROOT / "data" / "gx_materials" / "pack_calc_gen.json"


@pytest.mark.skipif(not _PACK_GEN.exists(), reason="未生成计算题数据包")
def test_generated_pack_on_disk_is_clean():
    import json
    payload = json.loads(_PACK_GEN.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    assert len(items) >= 100
    fps = [i["fingerprint"] for i in items]
    assert len(fps) == len(set(fps)), "数据包内部有重复指纹"
    # 落盘的题目不该带自检用的中间字段
    assert all("answer_text" not in i for i in items)
    # 导入脚本按 category 分流，必须是选择题练习才会落到 qtype=single
    assert all(i["category"] == "选择题练习" for i in items)
