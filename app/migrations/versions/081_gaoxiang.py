"""081 - 软考高项备考模块（面向非学生成人用户）

新建 6 张 gx_ 前缀表（模型单一真相源见 `app/models/gaoxiang.py`）：
- gx_knowledge    知识点（AI 生成后落库复用，不重复扣费）
- gx_questions    题库（单选/多选/案例；source=ai|import，year 为真题导入预留）
- gx_attempts     作答记录（进度聚合数据源）
- gx_wrongs       错题本（user_id+question_id 唯一，连对 3 次自动掌握）
- gx_case_grades  案例分析 AI 批改记录
- gx_progress     分知识域学习进度（user_id+domain 唯一）

与小学题库完全解耦（成人职业考试维度不同，强行复用会污染小学侧全部口径）。
全部 create_all(checkfirst=True) 幂等；create_all 自动建新表，
显式迁移仅为回滚与审计。
"""


def upgrade(db):
    from app.models.gaoxiang import (GxKnowledge, GxQuestion, GxAttempt,
                                     GxWrong, GxCaseGrade, GxProgress)
    for model in (GxKnowledge, GxQuestion, GxAttempt, GxWrong, GxCaseGrade, GxProgress):
        model.__table__.create(bind=db.get_bind(), checkfirst=True)
    db.commit()
