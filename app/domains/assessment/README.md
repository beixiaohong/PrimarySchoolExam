# D3 练习与测评域

出题引擎（数学/英语/语文/初中）、组卷、判分（规则+AI 复核）、Word/PDF/图片/音频渲染。

- 数据归属：questions middle_questions exam_records exam_attempts attempt_answers essay_grades 等
- 迁入代码：math.py english.py exam/ grading.py ai_quiz.py dictation.py challenge.py teach.py + generators judge.py docx_service.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
