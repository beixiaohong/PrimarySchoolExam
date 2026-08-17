# -*- coding: utf-8 -*-
"""AI 判题复核：开放问答题本地语义预判回归测试

背景：数学开放问答/概念题（如等边三角形角度与对称轴、平行四边形与梯形区别）
本地填空题判分无法识别语义，本应靠 AI 复核改判。但 AI 降级/偏严时会漏判。
新增 _local_semantic_correct 本地语义预判，对确定性概念题做容错判对
（中文数字等价、错别字归一、度/° 统一、去标点虚字），不依赖 AI。

运行：python -m pytest tests/test_judge_semantic.py -q
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.judge import _local_semantic_correct, _fuzzy_match  # noqa: E402

# 应判对的确定性概念题（孩子表述含错别字/中文数字，但知识点正确）
SHOULD_CORRECT = [
    # 等边三角形：孩子"三条" vs 参考"3条"（中文数字等价）
    ("每个角60度，三条对称轴", "60°，3条"),
    # 平行四边形/梯形：孩子"对轴相直线"错别字 vs 参考"对边平行"
    ("平行四边形有两组对轴相直线，而梯形只有一组",
     "平行四边形两组对边平行，梯形只有一组"),
]

# 不应误判（知识点错误或结论相反）
SHOULD_NOT_WRONGLY_CORRECT = [
    ("每个角90度", "60°，3条"),                       # 角度错
    ("梯形有两组对边平行", "平行四边形两组对边平行，梯形只有一组"),  # 概念相反
    ("3条", "60°，3条"),                              # 参考过长，孩子过短且无核心
]


def test_semantic_correct_detected():
    for user_ans, ref in SHOULD_CORRECT:
        assert _local_semantic_correct(user_ans, ref) is True, (
            f"应判对却未判：{user_ans!r} vs {ref!r}"
        )


def test_semantic_no_false_positive():
    for user_ans, ref in SHOULD_NOT_WRONGLY_CORRECT:
        assert _local_semantic_correct(user_ans, ref) is not True, (
            f"不应误判为对：{user_ans!r} vs {ref!r}"
        )


def test_semantic_skip_arithmetic():
    # 含等号/运算的算式题应交由 AI，本地返回 None（不插手，防误判）
    assert _local_semantic_correct("25×125+5×125", "25×125+4×125") is None
    assert _local_semantic_correct("星期天", "星期四+59天，59÷7=8余3，星期日") is None


def test_fuzzy_match_chinese_num():
    # Step2 二次确认：中文数字与阿拉伯数字应等价
    assert _fuzzy_match("每个角60度，三条对称轴", "60°，3条") is True
