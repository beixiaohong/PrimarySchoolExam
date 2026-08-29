"""试卷生成路由包：共享工具函数（内部使用，无路由）"""
import json


def _check_answer(user_ans: str, correct_ans: str, options_json: str,
                  exact_answer: str = "") -> bool:
    """判断答案是否正确（填空题为容错判题：规范化 + 数学式求值，见 answer_check）

    exact_answer: 题目精确答案（高精度真值），有则优先按精确值判分（根因修复路径）。
    """
    if not user_ans:
        return False
    ua = user_ans.strip().lower()
    ca = correct_ans.strip().lower()

    # 选择题：用户可能只输入了字母 A/B/C/D
    if options_json:
        # 正确答案可能是 "A" 或 "B" 等
        if len(ca) == 1 and ca in "abcd":
            return ua == ca or ua == ca.upper()
        # 选项里匹配
        if ua == ca:
            return True

    # 精确匹配
    if ua == ca:
        return True

    # 填空题：容错判题（算式过程/单位/全角符号/顺序差异均可识别）
    from app.services.answer_check import fill_answer_correct
    return fill_answer_correct(ua, ca, exact_answer)


__all__ = ["_check_answer"]
