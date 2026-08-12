"""采集试卷与题目数据模型（第一试卷网等来源自动采集入库）

设计要点：
- 与主项目原有 `questions` / `exam_records` 完全解耦（那是「出题式」题库），
  这里用独立的 `papers` / `paper_questions` 两张表承载「采集式」题库。
- 试卷只以 HTML 富文本（图片 base64 内联）持久化，不再保存 .doc/.docx 原件。
- `source_url` 作为去重主键：已采集过的试卷不会重复采集。
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index

try:
    from sqlalchemy.dialects.mysql import MEDIUMTEXT
except Exception:  # pragma: no cover
    MEDIUMTEXT = None

from ..config import DB_DRIVER
from ..database import Base


def _longtext():
    """大文本：MySQL 用 MEDIUMTEXT（>64KB，承载 base64 图片），SQLite 用 TEXT。"""
    return MEDIUMTEXT() if (DB_DRIVER == "mysql" and MEDIUMTEXT) else Text()


class Paper(Base):
    """一份采集到的试卷（如第一试卷网下载并转 HTML 后入库）"""
    __tablename__ = "papers"
    __table_args__ = {"comment": "采集试卷：HTML 富文本入库，不保存 doc 原件；source_url 为去重键"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    subject = Column(String(20), default="", index=True, comment="学科，如 语文 / 数学")
    grade = Column(String(20), default="", index=True, comment="年级，如 一年级")
    title = Column(Text, nullable=False, comment="试卷标题")

    # ── 来源与去重 ──
    source_url = Column(Text, default="", comment="采集来源详情页 URL（去重键）")
    download_url = Column(Text, default="", comment="原始压缩包下载链接")

    # ── 内容（唯一持久化载体：HTML 富文本）──
    html_content = Column(_longtext(), default="", comment="试卷 HTML 富文本，图片 base64 内联")
    answers = Column(_longtext(), default="", comment="整段参考答案原文（供题目级答案回退/人工核对）")
    total_questions = Column(Integer, default=0, comment="解析出的题目数")

    # ── 元信息 ──
    year = Column(Integer, default=0, comment="试卷年份（可选）")
    semester = Column(String(10), default="", comment="学期 上/下（可选）")
    created_at = Column(DateTime, default=datetime.now, comment="入库时间")

    def __repr__(self):
        return f"<Paper id={self.id} subject={self.subject} grade={self.grade} title={self.title!r}>"


class PaperQuestion(Base):
    """采集试卷解析出的单题，构成「采集式」题库的最小单元"""
    __tablename__ = "paper_questions"
    __table_args__ = {"comment": "采集试卷单题：HTML 富文本 + base64 图片，构成题库"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True,
                      comment="所属试卷")
    seq = Column(Integer, default=0, comment="试卷内全局序号（从1开始）")

    # ── 层级与题型 ──
    section = Column(String(50), default="", comment="大题标题，如 一、")
    section_idx = Column(Integer, default=0, comment="大题序号")
    qnum = Column(Integer, default=0, comment="小题号（无编号为0）")
    qtype = Column(String(20), default="qa", comment="题型：choice / fill_blank / qa")

    # ── 年级 / 学科（冗余自所属试卷，便于「按年级+学科+题型」独立抽题，不依赖 JOIN）──
    grade = Column(String(20), default="", index=True, comment="年级，如 一年级")
    subject = Column(String(20), default="", index=True, comment="学科，如 数学")

    __table_args__ = (
        Index("ix_pq_grade_subject_type", "grade", "subject", "qtype"),
        {"comment": "采集试卷单题：HTML 富文本 + base64 图片，构成题库"},
    )

    # ── 内容 ──
    question_text = Column(_longtext(), default="", comment="题目纯文本（可检索）")
    question_html = Column(_longtext(), default="", comment="题目 HTML 富文本（含 base64 图片）")
    options = Column(Text, default="", comment="选项 JSON 数组（选择题有值）")
    correct_answer = Column(Text, default="", comment="参考答案")
    image_base64 = Column(_longtext(), default="", comment="题目配图 base64（便于直接渲染）")

    created_at = Column(DateTime, default=datetime.now, comment="入库时间")

    def __repr__(self):
        return f"<PaperQuestion id={self.id} paper={self.paper_id} seq={self.seq} type={self.qtype}>"
