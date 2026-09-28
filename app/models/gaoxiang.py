"""软考高项（信息系统项目管理师）备考模块数据模型（面向非学生成人用户）

与小学题库完全解耦的设计理由：
- 小学侧 `questions` / `wrong_records` 深度绑定 subject(语数英...) + grade(年级整数)
  维度，错题本/统计/收藏等大量下游按此假设工作；高项是成人职业考试，
  维度是「知识域 + 单选/多选/案例/论文」，强行复用会污染小学侧全部口径。
- 因此独立 7 张表（gx_ 前缀），错题闭环/进度聚合自成一域，互不干扰。

题目来源两口径：
- `source`      = ai（AI 动态生成）/ import（备考资料导入）—— 分「谁产出的」
- `source_kind` = 每日一练 / 章节练习 / 仿真模拟 / 冲刺汇总 / 计算专题 / 案例专题 /
                  回家作业 / 论文练习 / 论文冲刺 —— 分「来自哪套资料」
导入的每条记录都带 `fingerprint`（内容指纹），加唯一索引保证重复导入不翻倍。

`fingerprint` 必须**可空**：MySQL 的唯一索引允许多个 NULL，但只允许一个 ''，
AI 动态生成的题目不参与去重（NULL），否则第二条 AI 题就会撞唯一键。

注意：本表含 MEDIUMTEXT 列（question/content/analysis/feedback），MySQL 的 TEXT/
MEDIUMTEXT 不允许 DEFAULT —— 这些列一律不给 default；其余短列可安全给默认值。
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, Integer, String, DateTime, Text, BigInteger,
                        ForeignKey, Index)

from ..database import Base
from .paper import _longtext


class GxKnowledge(Base):
    """知识点（按考纲章节/知识域组织；AI 预生成或备考资料导入后落库，可反复阅读）"""
    __tablename__ = "gx_knowledge"
    __table_args__ = (
        Index("ux_gx_knowledge_fingerprint", "fingerprint", unique=True),
        {"comment": "高项备考：知识点（考纲章节，AI 生成或资料导入）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    domain = Column(String(50), nullable=False, comment="知识域（如 整体管理/范围管理）",
                    index=True)
    code = Column(String(20), default="", comment="考纲编号（如 1.1，可空）")
    title = Column(String(200), nullable=False, comment="知识点标题")
    summary = Column(String(500), default="", comment="一句话摘要（列表页展示）")
    content = Column(_longtext(), nullable=False, comment="正文（Markdown 纯文本）")
    source = Column(String(10), default="ai", comment="来源：ai=AI 生成 / import=资料导入")
    # ── 资料导入扩展（082）──
    chapter = Column(String(50), default="", comment="考纲章节（如 第10章 项目进度管理）",
                     index=True)
    kind = Column(String(20), default="", comment="资料子类：list/mindmap/recite/must/"
                                                 "formula/mnemonic/itto/slide/textbook/ref",
                  index=True)
    source_file = Column(String(500), default="", comment="来源资料相对路径")
    seq = Column(Integer, default=0, comment="在来源资料内的序号（保持原顺序）")
    fingerprint = Column(String(32), default=None, comment="内容指纹（sha1 前 16 位，幂等导入键；"
                                                           "AI 生成为 NULL 不参与去重）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class GxQuestion(Base):
    """题目（单选/多选/案例/论文；AI 生成后落库或备考资料导入）"""
    __tablename__ = "gx_questions"
    __table_args__ = (
        Index("ux_gx_question_fingerprint", "fingerprint", unique=True),
        Index("ix_gx_question_kind_chapter", "source_kind", "chapter"),
        {"comment": "高项备考：题库（single/multi/case/essay，source 区分 AI 与资料导入）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    domain = Column(String(50), nullable=False, comment="知识域", index=True)
    qtype = Column(String(10), nullable=False, default="single",
                   comment="题型：single=单选 / multi=多选 / case=案例分析 / essay=论文")
    question = Column(_longtext(), nullable=False, comment="题干（案例/论文为背景材料全文）")
    options_json = Column(Text, default=None,
                          comment="选项 JSON 数组（案例/论文题无选项为 NULL）")
    answer = Column(Text, default="", comment="参考答案（单/多选为选项字母串，案例为要点）")
    analysis = Column(Text, default="", comment="解析（AI 生成或资料自带解析）")
    sub_questions = Column(Text, default=None,
                           comment="子问题 JSON：[{q, answer, points}]（案例子问 / 论文论述要求）")
    source = Column(String(10), default="ai", comment="来源：ai / import")
    year = Column(Integer, default=None, comment="真题年份（非真题为 NULL）")
    # ── 资料导入扩展（082）──
    title = Column(String(200), default="", comment="题目标题（论文题必填，选择题可空）")
    chapter = Column(String(50), default="", comment="考纲章节", index=True)
    source_kind = Column(String(20), default="", comment="来源子类：每日一练/章节练习/"
                                                        "仿真模拟/冲刺汇总/计算专题/案例专题/"
                                                        "回家作业/论文练习/论文冲刺", index=True)
    source_file = Column(String(500), default="", comment="来源资料相对路径")
    deck = Column(String(20), default="", comment="试卷编号（如 仿真模拟（一）），空=无套卷区分")
    seq = Column(Integer, default=0, comment="在来源资料内的题号/序号")
    fingerprint = Column(String(32), default=None, comment="内容指纹（sha1 前 16 位，幂等导入键；"
                                                           "AI 生成为 NULL 不参与去重）")
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
                        comment="是否答对（案例/论文题为 NULL，判分走 GxCaseGrade）")
    duration_ms = Column(Integer, default=0, comment="本题用时（毫秒），0=未采集")
    created_at = Column(DateTime, default=datetime.now, comment="作答时间")


class GxWrong(Base):
    """错题本（与小学错题闭环同构：重做连对 3 次自动掌握）

    选择题判错即入本；案例/论文按 AI 评分低于及格线（SUBJECTIVE_PASS_SCORE=60）入本，
    用 best_score/last_score 记录主观题得分轨迹。
    `wrong_reason` 缓存 AI 错因分析（懒生成 + 落库复用），避免每次打开错题本都调 AI。
    """
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
    # ── 错题分析扩展（082）──
    kind = Column(String(20), default="choice", comment="题型分类：choice=选择 / case=案例 / "
                                                        "essay=论文", index=True)
    best_score = Column(Integer, default=0, comment="主观题历史最高分（选择题恒 0）")
    last_score = Column(Integer, default=0, comment="主观题最近一次得分（选择题恒 0）")
    wrong_reason = Column(Text, default=None, comment="AI 错因分析（懒生成后缓存复用）")
    reason_at = Column(DateTime, default=None, comment="错因分析生成时间")


class GxCaseGrade(Base):
    """案例/论文批改记录（AI 按要点评分 + 逐条反馈 + 四维评分明细）"""
    __tablename__ = "gx_case_grades"
    __table_args__ = {"comment": "高项备考：案例/论文 AI 批改记录（评分 + 逐条反馈）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户标识", index=True)
    question_id = Column(Integer, ForeignKey("gx_questions.id"), default=None,
                         comment="题目 id（现场 AI 临时出题时为 NULL）")
    question_text = Column(_longtext(), nullable=False, comment="题干快照（含背景材料）")
    user_answer = Column(_longtext(), nullable=False, comment="用户作答全文")
    score = Column(Integer, default=0, comment="AI 评分（0-100）")
    feedback = Column(_longtext(), default=None, comment="AI 反馈（要点命中/遗漏/改进建议）")
    # ── 批改扩展（082）──
    kind = Column(String(20), default="case", comment="批改类型：case=案例 / essay=论文",
                  index=True)
    rubric_json = Column(Text, default=None,
                         comment="四维评分明细 JSON：[{dim, score, comment}]（论文用：切题/"
                                 "结构/实践/文字）")
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


class GxMaterial(Base):
    """备考资料归档清单（源文件 → 类别 → 解析条目数的审计表）

    存在的意义：解析是「一次性人工可核」的环节，线上必须能回答
    「这份资料归到哪一类了、解析出多少题、为什么被跳过」——否则出现漏题无从追溯。
    数据来自 `tools/gx_pack.py` 生成的 manifest.json，由导入工具写入。
    """
    __tablename__ = "gx_materials"
    __table_args__ = (
        Index("ux_gx_material_relpath", "rel_path", unique=True),
        {"comment": "高项备考：备考资料归档清单（分类与解析审计）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    rel_path = Column(String(500), nullable=False, comment="资料相对路径（唯一）")
    category = Column(String(20), default="", comment="类别：知识点/选择题练习/案例分析练习/"
                                                     "论文练习/其他", index=True)
    sub_kind = Column(String(20), default="", comment="子类（每日一练/仿真模拟/课件/教材…）",
                      index=True)
    title = Column(String(200), default="", comment="资料标题（文件名去扩展名）")
    ext = Column(String(10), default="", comment="扩展名（pdf/mp3/pptx…）")
    size_bytes = Column(BigInteger, default=0, comment="文件字节数（0=未采集）")
    items = Column(Integer, default=0, comment="解析出的条目数")
    reason = Column(String(300), default="", comment="分类依据（命中规则）")
    note = Column(String(300), default="", comment="备注")
    skipped = Column(String(300), default="", comment="跳过原因（非空=未解析）")
    error = Column(String(300), default="", comment="解析错误（非空=失败）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
