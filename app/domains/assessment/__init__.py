"""D3 练习与测评域（assessment）

职责：出题引擎（数学/英语/语文/初中）、组卷、判分（规则+AI 复核）、Word/PDF/图片/音频渲染。

边界纪律（S1-R）：
- 数据归属：questions middle_questions exam_records exam_attempts attempt_answers essay_grades 等
- 迁入代码：math.py english.py exam/ grading.py ai_quiz.py dictation.py challenge.py teach.py + generators judge.py docx_service.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
