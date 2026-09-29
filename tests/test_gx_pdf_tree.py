#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""gx_pdf_tree 的单测：层级重建是否还原了 PDF 的缩进排版。

不依赖真实 PDF —— 直接构造「(y, 行文本, 是否含分隔符, [(x0, 文本)], 字号)」，
这样断言的是建树规则本身，坐标取自真实 PDF 实测值（见模块注释）。
"""
import pytest

from tools.gx_pdf_tree import build_tree, render_lines, node_lines, _is_desc

# 真实坐标：网络存储3种技术(42.7) / DAS(164.0) / NAS(162.9) / SAN(162.9)
_ROWS_STORAGE = [
    (48.8, "网络存储3种技术----直接附加存储DAS----无需网络、直连、很难扩展、无存储操作系统；",
     True, [(42.7, "网络存储3种技术"), (164.0, "直接附加存储DAS"),
            (296.3, "无需网络、直连、很难扩展、无存储操作系统；")], 10.0),
    (75.3, "网络附加存储NAS----需要网络、网络连接、扩展性强、共享存取；",
     True, [(162.9, "网络附加存储NAS"), (291.8, "需要网络、网络连接、扩展性强、共享存取；")], 10.0),
    (101.9, "存储区域网络SAN----需要网络、存储区域网络连接、块级存储；",
     True, [(162.9, "存储区域网络SAN"), (291.8, "需要网络、存储区域网络连接、块级存储；")], 10.0),
]

# OSI 七层的真实坐标：「数据链路层」212.2 比同级的 235.4 偏左 23pt（PDF 排版噪声）
_ROWS_OSI = [
    (252.9, "开放系统互连参考模型OSI七层网络模型----（物链网传话表用）",
     True, [(41.5, "开放系统互连参考模型OSI七层网络模型"), (294.4, "（物链网传话表用）")], 10.0),
    (271.6, "物理层----物理连接、数模转换；",
     True, [(235.4, "物理层"), (296.9, "物理连接、数模转换；")], 10.0),
    (290.3, "数据链路层----逻辑连接、物理寻址；",
     True, [(212.2, "数据链路层"), (299.5, "逻辑连接、物理寻址；")], 10.0),
    (309.1, "网络层----路由选择、逻辑寻址；",
     True, [(235.4, "网络层"), (296.9, "路由选择、逻辑寻址；")], 10.0),
]


def _flat(rows, pno=1):
    """建树 → [(level, 文本, 是否描述)]"""
    root = build_tree(rows, pno=pno)
    out = []
    for top in root.children:
        node_lines(top, out)
    return out


def test_dash_siblings_share_parent():
    """DAS/NAS/SAN 是「网络存储3种技术」下的同级兄弟，描述挂在各自术语下。"""
    flat = _flat(_ROWS_STORAGE)
    levels = {t: lv for lv, t, _d in flat}
    assert levels["网络存储3种技术"] == 0
    assert levels["直接附加存储DAS"] == 1
    # 兄弟 x0 只差 1.1pt（164.0 vs 162.9），必须判为同级而不是 DAS 的子级
    assert levels["网络附加存储NAS"] == 1
    assert levels["存储区域网络SAN"] == 1

    # DAS 的描述挂在它自己下面（缩进比 DAS 再深一级），而不是糊在主题下
    desc_of = {}
    cur = None
    for lv, t, is_desc in flat:
        if is_desc:
            desc_of[cur] = t
        else:
            cur = t
    assert "无需网络" in desc_of["直接附加存储DAS"]
    assert "需要网络、网络连接" in desc_of["网络附加存储NAS"]


def test_noisy_sibling_indent_stays_same_level():
    """「数据链路层」缩进比同级偏左 23pt，不能让后续兄弟掉进它的下一级。"""
    flat = _flat(_ROWS_OSI)
    levels = {t: lv for lv, t, _d in flat}
    assert levels["数据链路层"] == 1
    assert levels["网络层"] == 1, "排版噪声不得把后续兄弟降级为上一项的子级"
    assert levels["物理层"] == 1


def test_continuation_line_appends_to_last_desc():
    """无分隔符且紧接上一行 → 续行，追加到上一个术语的描述，不新建节点。"""
    rows = [
        (48.8, "层次模型（树结构）----结点的双亲是唯一，只能直接处理一对多",
         True, [(264.4, "层次模型（树结构）"),
                (403.7, "结点的双亲是唯一，只能直接处理一对多")], 10.0),
        (75.3, "结构清晰、查询效率高；多对多不行、查子女必须通过双亲；",
         False, [(15.7, "结构清晰、查询效率高；多对多不行、查子女必须通过双亲；")], 10.0),
    ]
    flat = _flat(rows)
    assert len(flat) == 2, "续行不应产生新节点"
    desc = flat[1][1]
    assert "结点的双亲是唯一" in desc and "结构清晰" in desc


def test_far_apart_line_starts_new_node():
    """跨卡片/跨页的标题行（间距远大于行距）不能被吞成上一条的描述。"""
    rows = [
        (48.8, "应用层----与最终用户的接口；", True,
         [(42.7, "应用层"), (200.0, "与最终用户的接口；")], 10.0),
        (400.0, "OSI七层网络模型的协议：", False, [(41.5, "OSI七层网络模型的协议：")], 10.0),
    ]
    flat = _flat(rows)
    assert any(t == "OSI七层网络模型的协议：" for _lv, t, _d in flat)


def test_render_lines_indents_two_spaces_per_level():
    out = render_lines([(0, "主题", False), (1, "子项", False), (2, "孙项", False)])
    assert out.splitlines() == ["主题", "  • 子项", "    ◦ 孙项"]


@pytest.mark.parametrize("text,want", [
    ("高速度、低时延、大连接；", True),      # 句末标点
    ("面向移动互联网流量爆炸式增长，提供更加极致的应用体验；", True),  # 够长
    ("增强移动宽带（eMBB）", False),
    ("关系型数据库SQL", False),
])
def test_is_desc(text, want):
    assert _is_desc(text) is want
