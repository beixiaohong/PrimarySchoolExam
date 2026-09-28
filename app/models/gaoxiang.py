"""软考高项（信息系统项目管理师）备考模块数据模型（面向非学生成人用户）

与小学题库完全解耦的设计理由：
- 小学侧 `questions` / `wrong_records` 深度绑定 subject(语数英...) + grade(年级整数)
  维度，错题本/统计/收藏等大量下游按此假设工作；高项是成人职业考试，
  维度是「十大知识域 + 单选/多选/案例」，强行复用会污染小学侧全部口径。
- 因此独立 6 张表（gx_ 前缀），错题闭环/进度聚合自成一域，互不干扰。

真题导入口子：`GxQuestion.source` 取 'ai'（AI 动态生成）或 'import'（历年真题导入，
配套导入工具为 M2 规划项），`year` 存真题年份（AI 生成题为 NULL）。
AI 生成内容落库后可复用，不重复扣费生成。

注意：本表含 MEDIUMTEXT 列（question/content/analysis/feedback），MySQL 的 TEXT/
MEDIUMTEXT 不允许 DEFAULT —— 这些列一律不给 default；其余短列可安全给默认值。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, Integer, String, DateTime, Date, Text, ForeignKey, Index

from ..database import Base
from .paper import _longtext


class GxKnowledge(Base):
    """知识点（按考纲知识域组织；内容由 AI 预生成后落库，可反复阅读不重复扣费）"""
    __tablename__ = "gx_knowledge"
    __table_args__ = {"comment": "高项备考：知识点（十大知识域，AI 生成后落库复用）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    domain = Column(String(50), nullable=False, comment="知识域（如 整体管理/范围管理/案例分析）",
                    index=True)
    code = Column(String(20), default="", comment="考纲编号（如 1.1，可空）")
    title = Column(String(200), nullable=False, comment="知识点标题")
    summary = Column(String(500), default="", comment="一句话摘要（列表页展示）")
    content = Column(_longtext(), nullable=False, comment="正文（Markdown 纯文本）")
    source = Column(String(10), default="ai", comment="来源：ai=AI 生成 / import=人工导入")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class GxQuestion(Base):
    """题目（单选/多选/案例；AI 生成后落库或真题导入）"""
    __tablename__ = "gx_questions"
    __table_args__ = {"comment": "高项备考：题库（单选/多选/案例，source 区分 AI 生成与真题导入）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    domain = Column(String(50), nullable=False, comment="知识域", index=True)
    qtype = Column(String(10), nullable=False, default="single",
                   comment="题型：single=单选 / multi=多选 / case=案例分析")
    question = Column(_longtext(), nullable=False, comment="题干（案例题含背景材料全文）")
    options_json = Column(Text, default=None,
                          comment="选项 JSON 数组（案例题无选项为 NULL）")
    answer = Column(Text, default="", comment="参考答案（单/多选为选项字母串，案例为要点）")
    analysis = Column(Text, default="", comment="解析（AI 生成或真题官方解析）")
    sub_questions = Column(Text, default=None,
                           comment="案例题子问题 JSON：[{q, answer, points}]（可空）")
    source = Column(String(10), default="ai", comment="来源：ai / import")
    year = Column(Integer, default=None, comment="真题年份（AI 生成题为 NULL）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class GxAttempt(Base):
    """作答记录（一题一行；判分后写，供进度聚合与回顾）"""
    __tablename__ = "gx_attempts"
    __table_args__ = (
        Index("ix_gx_attempts_user_created", "user_id", "created_at"),
        {"comment": "高项备考：作答记录（供进度聚合与答题回顾）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户标识（账号绑定校验由鉴权层负责）",
                     index=True)
    question_id = Column(Integer, ForeignKey("gx_questions.id"), nullable=False,
                         comment="题目 id")
    user_answer = Column(Text, default="", comment="用户答案（选项字母串或案例作答全文）")
    is_correct = Column(Boolean, default=None,
                        comment="是否答对（案例题为 NULL，判分走 GxCaseGrade）")
    duration_ms = Column(Integer, default=0, comment="本题用时（毫秒），0=未采集")
    created_at = Column(DateTime, default=datetime.now, comment="作答时间")


class GxWrong(Base):
    """错题本（与小学错题闭环同构：重做连对 3 次自动掌握）"""
    __tablename__ = "gx_wrongs"
    __table_args__ = (
        Index("ux_gx_wrong_user_question", "user_id", "question_id", unique=True),
        {"comment": "高项备考：错题本（user_id+question_id 唯一，重做连对 3 次掌握）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户标识", index=True)
    question_id = Column(Integer, ForeignKey("gx_questions.id"), nullable=False,
                         comment="题目 id")
    user_answer = Column(Text, default="", comment="最近一次错误作答")
    wrong_count = Column(Integer, default=1, comment="累计答错次数")
    correct_streak = Column(Integer, default=0, comment="重做连续答对次数（达 3 自动掌握）")
    is_mastered = Column(Boolean, default=False, comment="是否已掌握（不再出现在错题本）",
                         index=True)
    last_wrong_at = Column(DateTime, default=datetime.now, comment="最近答错时间")
    mastered_at = Column(DateTime, default=None, comment="掌握时间")


class GxCaseGrade(Base):
    """案例分析批改记录（AI 按要点评分 + 逐条反馈）"""
    __tablename__ = "gx_case_grades"
    __table_args__ = {"comment": "高项备考：案例分析 AI 批改记录（评分 + 逐条反馈）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户标识", index=True)
    question_id = Column(Integer, ForeignKey("gx_questions.id"), default=None,
                         comment="题目 id（现场 AI 临时出题时为 NULL）")
    question_text = Column(_longtext(), nullable=False, comment="题干快照（含背景材料）")
    user_answer = Column(_longtext(), nullable=False, comment="用户作答全文")
    score = Column(Integer, default=0, comment="AI 评分（0-100）")
    feedback = Column(_longtext(), default=None, comment="AI 反馈（要点命中/遗漏/改进建议）")
    created_at = Column(DateTime, default=datetime.now, comment="批改时间")


class GxProgress(Base):
    """学习进度（user_id+domain 一行，提交作答/读完知识点时增量更新）"""
    __tablename__ = "gx_progress"
    __table_args__ = (
        Index("ux_gx_progress_user_domain", "user_id", "domain", unique=True),
        {"comment": "高项备考：分知识域学习进度（user_id+domain 唯一）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户标识", index=True)
    domain = Column(String(50), nullable=False, comment="知识域")
    knowledge_read = Column(Integer, default=0, comment="已读知识点数（增量累加）")
    quiz_total = Column(Integer, default=0, comment="累计刷题数")
    quiz_correct = Column(Integer, default=0, comment="累计答对数")
    case_count = Column(Integer, default=0, comment="累计案例批改次数")
    last_at = Column(DateTime, default=datetime.now, comment="最近学习时间")
