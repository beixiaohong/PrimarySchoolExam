# -*- coding: utf-8 -*-
"""判分容差回归测试（app/services/answer_check.py）

覆盖：
- 中文数字容差（五=5、二十五=25、一百零五=105、两万=20000）
- 既有容差行为不回归（算式过程=结果、数字 token 兜底、无数字严格比对）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.answer_check import fill_answer_correct, _cn_num_value  # noqa: E402


def test_cn_num_value():
    assert _cn_num_value("五") == 5
    assert _cn_num_value("十") == 10
    assert _cn_num_value("二十五") == 25
    assert _cn_num_value("一百零五") == 105
    assert _cn_num_value("三百二十") == 320
    assert _cn_num_value("五千零三") == 5003
    assert _cn_num_value("两万") == 20000
    assert _cn_num_value("5") is None          # 阿拉伯数字不转
    assert _cn_num_value("答案是五") is None    # 含非数字字符不转
    assert _cn_num_value("") is None


def test_cn_num_match():
    # 用户写中文数字、参考答案阿拉伯数字 → 判对
    assert fill_answer_correct("五", "5") is True
    assert fill_answer_correct("二十五", "25") is True
    assert fill_answer_correct("一百零五", "105") is True
    assert fill_answer_correct("两万", "20000") is True
    # 写错的中文数字 → 判错
    assert fill_answer_correct("六", "5") is False


def test_existing_behavior_kept():
    # 普通相等
    assert fill_answer_correct("5", "5") is True
    # 算式过程 = 结果
    assert fill_answer_correct("2*(999+1)=2*1000=2000", "2000") is True
    # 带单位
    assert fill_answer_correct("2000元", "2000") is True
    # 无数字严格（单词/诗句）
    assert fill_answer_correct("apple", "apple") is True
    assert fill_answer_correct("apple", "banana") is False
    # 诗句逐字相等不受中文数字转换影响
    assert fill_answer_correct("一去二三里", "一去二三里") is True
    # 参考答案无数字时，中文数字不参与数值比对
    assert fill_answer_correct("五", "一去二三里") is False
    # 错误数字
    assert fill_answer_correct("6", "5") is False
