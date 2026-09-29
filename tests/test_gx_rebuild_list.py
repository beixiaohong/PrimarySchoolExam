"""tools/gx_rebuild_list.py 的解析与对齐逻辑测试

对齐是整条回填链路里唯一「错了不会报错、只会把正文换错」的环节：卡片与页不是一一
对应，靠相似度配对。所以这里把对齐的性质钉死 —— 单调、不重叠、顺序不乱、缺页能容忍。
"""
import importlib.util
import os
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


rb = _load("gx_rebuild_list")


# ── 归一化 ──────────────────────────────────────────────────────────────

def test_norm_chars_drops_dashes_and_bullets():
    """新旧正文的差异（----、缩进、•）必须在归一化后消失，否则相似度没法比"""
    a = rb.norm_chars("网络存储3种技术----直接附加存储DAS")
    b = rb.norm_chars("网络存储3种技术\n  • 直接附加存储DAS")
    assert a == b


def test_norm_chars_keeps_cjk_and_alnum():
    assert rb.norm_chars("DAS（1998）") == list("DAS1998")
    assert rb.norm_chars("，。；") == []


# ── 相似度 ──────────────────────────────────────────────────────────────

def test_overlap_score_identical_is_one():
    c = rb.char_counter("信息安全层次包括设备安全数据安全")
    assert rb.overlap_score(c, c) == pytest.approx(1.0)


def test_overlap_score_disjoint_is_zero():
    assert rb.overlap_score(rb.char_counter("甲乙丙丁"), rb.char_counter("戊己庚辛")) == 0.0


def test_overlap_score_uses_multiset_not_set():
    """多重集而非集合：重复字的次数不同也要扣分，否则长段落能靠字表重合骗分"""
    a = rb.char_counter("安全安全安全安全")
    b = rb.char_counter("安全")
    # 集合 Jaccard 会是 1.0，多重集只有 0.25
    assert rb.overlap_score(a, b) == pytest.approx(0.25)


# ── 单调 DP 对齐 ────────────────────────────────────────────────────────

def _mk(parts):
    return [rb.char_counter(p) for p in parts]


def test_align_one_to_one():
    cards = _mk(["AAA主题", "BBB主题", "CCC主题"])
    pages = _mk(["AAA主题展开", "BBB主题展开", "CCC主题展开"])
    spans, scores = rb.align(cards, pages)
    assert spans == [(0, 1), (1, 2), (2, 3)]
    assert all(s > 0.5 for s in scores)


def test_align_one_card_takes_many_pages():
    """整份只切出一张卡时，它必须能一次吃掉多页（span 按页数动态放宽）"""
    cards = _mk(["整章内容"])
    pages = _mk(["整章内容第一页", "整章内容第二页", "整章内容第三页"])
    spans, _ = rb.align(cards, pages, max_span=rb.span_for(3, 1))
    assert spans == [(0, 3)]


def test_align_spans_are_monotonic_and_disjoint():
    cards = _mk(["甲" * 20, "乙" * 20, "丙" * 20])
    pages = _mk(["甲" * 18, "乙" * 15, "乙" * 5, "丙" * 19, "丙" * 3])
    spans, _ = rb.align(cards, pages, max_span=rb.span_for(5, 3))
    prev_hi = 0
    for lo, hi in spans:
        assert lo >= prev_hi          # 不回退、不重叠
        assert hi >= lo               # 允许空段
        prev_hi = hi
    assert spans[1] == (1, 3)         # 两张页都属于「乙」


def test_align_tolerates_empty_page():
    """非正文页（封面/目录）被置空后不能把对齐带偏"""
    cards = _mk(["开头内容", "结尾内容"])
    pages = _mk(["", "开头内容展开", "", "结尾内容展开"])
    spans, scores = rb.align(cards, pages, max_span=rb.span_for(4, 2))
    assert spans[0][1] <= spans[1][0]
    assert scores[0] > 0.5 and scores[1] > 0.5


def test_align_never_exceeds_max_span():
    cards = _mk(["甲" * 10, "乙" * 10])
    pages = _mk(["甲" * 10] * 6)
    spans, _ = rb.align(cards, pages, max_span=2)
    for lo, hi in spans:
        assert hi - lo <= 2


# ── span 计算 ───────────────────────────────────────────────────────────

def test_span_for_grows_when_few_cards():
    """10 页 1 卡必须放宽到 >10，否则那张卡吃不下整份、整份资料被跳过"""
    assert rb.span_for(10, 1) > 10
    assert rb.span_for(130, 102) >= rb.MAX_SPAN
    assert rb.span_for(0, 0) == rb.MAX_SPAN


# ── 指纹去重与碰撞消解 ──────────────────────────────────────────────────

def _entry(old, new, src="a.pdf", title="章节", content="正文"):
    return {"old_fingerprint": old, "new_fingerprint": new, "source_file": src,
            "title": title, "content": content, "pages": [1, 2]}


def test_resolve_drops_entries_pointing_at_same_row():
    """分课 PDF 与汇总 PDF 会产出同一张卡片（old 相同）：补丁里只留一条"""
    ents = [_entry("OLD1", "NEW1", src="a.pdf"), _entry("OLD1", "NEW1", src="b.pdf")]
    out, stats = rb.resolve_fingerprints(ents)
    assert len(out) == 1
    assert stats["dup_old"] == 1
    assert stats["salted"] == 0


def test_resolve_salts_fingerprints_that_would_collide():
    """⚠️ 回归：old 不同但 new 相同的两条会撞唯一索引 1062，且干跑逐条查不出来"""
    ents = [_entry("OLD1", "NEW", src="a.pdf"), _entry("OLD2", "NEW", src="b.pdf")]
    out, stats = rb.resolve_fingerprints(ents)
    fps = [e["new_fingerprint"] for e in out]
    assert len(set(fps)) == 2, "两条必须拿到不同的新指纹，否则写库撞唯一索引"
    assert stats["salted"] == 2
    assert all(e.get("fp_salted") for e in out)


def test_resolve_leaves_unique_fingerprints_alone():
    ents = [_entry("OLD1", "NEW1"), _entry("OLD2", "NEW2")]
    out, stats = rb.resolve_fingerprints(ents)
    assert [e["new_fingerprint"] for e in out] == ["NEW1", "NEW2"]
    assert stats["salted"] == 0
    assert not any(e.get("fp_salted") for e in out)


def test_resolve_is_deterministic_regardless_of_order():
    """加盐不能依赖遍历顺序：换个顺序结果要完全一致"""
    a = rb.resolve_fingerprints([_entry("OLD1", "NEW", src="a.pdf"),
                                 _entry("OLD2", "NEW", src="b.pdf")])[0]
    b = rb.resolve_fingerprints([_entry("OLD2", "NEW", src="b.pdf"),
                                 _entry("OLD1", "NEW", src="a.pdf")])[0]
    key = lambda es: sorted((e["old_fingerprint"], e["new_fingerprint"]) for e in es)
    assert key(a) == key(b)


def test_resolve_output_has_no_duplicate_new_fingerprint():
    """最终产物的新指纹必须两两不同 —— 这是不撞唯一索引的充分条件"""
    ents = ([_entry("OLD%d" % i, "NEW%d" % (i // 2)) for i in range(6)]
            + [_entry("OLDX", "NEW0", src="x.pdf")])
    out, _ = rb.resolve_fingerprints(ents)
    fps = [e["new_fingerprint"] for e in out]
    assert len(fps) == len(set(fps))


# ── 端到端（需要本地资料 PDF） ───────────────────────────────────────────

_SAMPLE = (ROOT / "temp" / "软考【高项】2026年5月班备考资料"
           / "02. 课程主要知识点清单+思维导图+填空辅助记忆清单"
           / "第2章 信息技术发展"
           / "软考高项--第11课知识点清单--第2章 信息技术发展.pdf")


@pytest.mark.skipif(not _SAMPLE.exists(), reason="本地备考资料 PDF 不存在")
def test_rebuild_pdf_on_real_sample():
    # rel 必须是完整相对路径：gx_parse 的 classify 既看文件名也看父目录名，
    # 只传文件名会落到「其他」分支、一条卡片都解析不出来。
    rel = _SAMPLE.relative_to(ROOT / "temp" / "软考【高项】2026年5月班备考资料").as_posix()
    entries, skipped, info = rb.rebuild_pdf(str(_SAMPLE), rel)
    assert info["pages"] == 9
    assert entries, "至少应有卡片被成功重解析"
    # 层级必须真的展开出来了（否则等于白跑）
    joined = "\n".join(e["content"] for e in entries)
    assert "•" in joined
    # 封面/目录水印不能进正文
    assert "luckeeinc" not in joined
    # 每条都要带线上行的身份（old_fingerprint），否则无法回填
    assert all(e["old_fingerprint"] and e["new_fingerprint"] for e in entries)
    # 对齐分数不能低于阈值
    assert all(e["score"] >= rb.MIN_SCORE for e in entries)
