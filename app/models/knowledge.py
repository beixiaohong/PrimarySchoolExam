"""九科通用知识点模型（区别于仅英语语法的 GrammarPoint）

覆盖初中九科（语数英 + 物化生 + 政史地）按 学科+年级+单元 组织的知识点，
由内容采集/录入管线（tools/seed_junior_grade7.py）批量生成，后台「内容管理-知识点」可查。
"""
from datetime import datetime

from sqlalchemy import (Column, DateTime, Integer, String, Text,
                        UniqueConstraint)

from ..database import Base


class KnowledgePoint(Base):
    """九科通用知识点：某学科某年级某单元下的一个考点/知识条目"""
    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint("subject", "grade", "unit", "title",
                         name="uq_kp_subject_grade_unit_title"),
        {"comment": "九科通用知识点：学科+年级+单元+标题 唯一"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    subject = Column(String(20), nullable=False, index=True, comment="学科：数学/语文/英语/物理/化学/生物/道德与法治/历史/地理")
    grade = Column(Integer, nullable=False, index=True, comment="年级 7-9（初中）")
    unit = Column(String(100), default="", comment="教材章节单元标识，如 七上·第1章 有理数")
    title = Column(String(200), nullable=False, comment="知识点标题，如 有理数的加减法")
    summary = Column(String(500), default="", comment="一句话要点/结论")
    content = Column(Text, default="", comment="详细讲解（规则/推导/易错点）")
    examples = Column(Text, default="", comment="示例，每行一个")
    difficulty = Column(Integer, default=2, comment="难度 1-5")
    source = Column(String(30), default="seed", comment="来源：seed=批量生成 / manual=后台录入")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # ── S2-M1 扩展字段（07 §3.2.1：知识点树/层级/教材版本）──
    parent_id = Column(Integer, default=0, index=True,
                       comment="父知识点ID（层级，0=根）")
    code = Column(String(64), default="", index=True, comment="知识点编码")
    sort_order = Column(Integer, default=0, comment="同级排序")
    status = Column(String(16), default="active",
                    comment="状态：active/deprecated")
    textbook_ver = Column(String(32), default="", comment="教材版本标识")
    updated_at = Column(DateTime, nullable=True, comment="更新时间")

    def __repr__(self):
        return f"<KnowledgePoint {self.subject} G{self.grade} {self.title}>"
