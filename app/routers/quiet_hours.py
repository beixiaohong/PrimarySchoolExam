"""夜间静默时段依赖（需求1）：每晚 22:30–次日 07:00 禁止刷题/背诵等动作端点。

目的：防止学生熬夜，保护视力与睡眠。
- 仅拦截「做题/提交/背诵判分」等动作端点；只读查看（历史/统计）仍允许。
- 前端在静默时段点击动作会被后端 403 拦截并给出友好提示（文案含"夜间休息"便于前端识别）。
- 以 router 级依赖方式挂载在 main.py 的 9 个前缀上，单点生效、零漏拦、不动各端点文件。
"""
from datetime import datetime, time

from fastapi import HTTPException, Request, status

# 静默时段：22:30 至次日 07:00
QUIET_START = time(22, 30)
QUIET_END = time(7, 0)

# 静态动作端点前缀（直接匹配动作端点，前缀命中即拦截）。
# 仅含「做题/提交/背诵判分」动作，不含只读查看（list/stats/today/progress 等）。
STATIC_ACTION_PREFIXES = (
    "/api/math/generate",                      # 数学题生成（含 /generate/docx）
    "/api/exam/generate",                      # 试卷生成
    "/api/exam/collection/submit",             # 采集题库提交判分
    "/api/challenge/questions",                # 挑战赛取题
    "/api/challenge/record",                   # 挑战赛保存成绩
    "/api/study/practice-submit",              # 错题练习提交
    "/api/study/cause",                        # 错因自评
    "/api/study/retry",                        # 变式重练抽题
    "/api/study/check-answer",                 # 逐题判分
    "/api/classical/quiz",                     # 古诗文背诵（填空）
    "/api/classical/session-quiz",             # 古诗文会话检测
    "/api/classical/learn",                    # 标记已学
    "/api/classical/review",                   # 提交复习
    "/api/classical/dictate",                  # 默写提交
    "/api/vocab/session-quiz",                 # 背单词会话检测
    "/api/vocab/learn",                        # 标记已学会
    "/api/vocab/review",                       # 提交复习
    "/api/vocab/dictate",                      # 听写判分
    "/api/grammar/quiz",                       # 语法练习生成
    "/api/grammar/submit",                     # 语法答案提交
    "/api/dictation/words",                    # 听写词列表（取词动作）
    "/api/dictation/texts",                    # 古诗文听写句（取句动作）
    "/api/dictation/reward",                   # 听写全对奖励（做题动作）
    "/api/ai-quiz/generate",                   # AI 趣味出题
    "/api/ai-quiz/wrong",                      # AI 回写错题本
    "/api/ai-quiz/reward",                     # AI 全对奖励
)

# /api/exam 下含动态 id 的动作端点（/api/exam/{exam_id}/...），用关键词识别。
# 注意排除 list/stats 等只读端点（它们不含下列关键词）。
EXAM_ACTION_KEYWORDS = (
    "mark-wrong",
    "unmark-wrong",
    "/master",            # /api/exam/{id}/master 与 /api/exam/wrong/batch-master
    "practice",           # /api/exam/wrong/practice、practice-quiz
    "answer-unanswered",  # /api/exam/wrong/answer-unanswered
    "batch-master",       # /api/exam/wrong/batch-master
    "submit-answers",     # /api/exam/submit-answers
)


def _in_quiet(now: time) -> bool:
    return now >= QUIET_START or now < QUIET_END


def _is_blocked_action(path: str) -> bool:
    for p in STATIC_ACTION_PREFIXES:
        if path.startswith(p):
            return True
    if path.startswith("/api/exam/"):
        for kw in EXAM_ACTION_KEYWORDS:
            if kw in path:
                return True
    return False


def check_quiet_hours(request: Request):
    """FastAPI 依赖：静默时段内访问做题/背诵动作端点时拒绝（403）。

    只读查看端点（带 list/stats/today/progress 等）不受限，学生夜间仍可回顾历史。
    """
    now = datetime.now().time()
    if not _in_quiet(now):
        return
    if _is_blocked_action(request.url.path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="现在是夜间休息时间（22:30–07:00），暂不可刷题或背诵，请好好休息～",
        )
