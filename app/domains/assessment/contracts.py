"""D3 练习与测评域对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口（`.importlinter` 域独立契约强制）。

对外能力
- 判分：`fill_answer_correct`（填空题容错判题，与前端 `_matchAnswer` 同口径，支持
  `exact_answer` 高精度真值优先）、`normalize_answer`（答案规范化：小写/去空白/全角转半角/
  数学符号统一）、`_check_answer`（试卷作答判定入口，客观题即时判 + 容错判题）。
  判分口径由本域独占，禁止其它域自行实现比对逻辑（历史上 8 次判分准确性修复均出自口径分叉）。
- AI 复核：`judge_wrong_items(user_id, items, force=False)` —— 批量复核本地判错的作答，
  两步独立判题并落 `judge_review_issues`。
- 出题：`generate_math_problems(grade, difficulty, categories, problem_types, ...)`
  数学结构变体生成器（注册表模式）。

再导出为延迟解析（PEP 562）：判分/复核实现在函数体内反向引用平台域 AI 网关与商业域计费，
契约层若在 import 期拉起会与之成环，延迟解析后调用方时序与改造前一致。

文档 02 所列 `ExamService.generate(filters)`、`GradingService.grade(answers)`、
`QuestionGenService.generate(subject, grade, type, n)` 为 M0 目标接口：现分别由
`routers/exam/generate.py`、`routers/grading.py`、各学科 generator 承担，尚无统一服务层，
本期不新建包装；建立回归评测集后在此登记。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    "fill_answer_correct": ("app.domains.assessment.services.answer_check", "fill_answer_correct"),
    "normalize_answer": ("app.domains.assessment.services.answer_check", "normalize_answer"),
    "judge_wrong_items": ("app.domains.assessment.services.judge", "judge_wrong_items"),
    "generate_math_problems": ("app.domains.assessment.services.math_generator", "generate_math_problems"),
    "_check_answer": ("app.domains.assessment.routers.exam", "_check_answer"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)
