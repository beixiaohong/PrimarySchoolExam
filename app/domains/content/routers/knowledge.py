"""知识点互动学习 API（学习体验优化 P1：把 knowledge_points 死数据变成「讲解→例子→挖空自测」互动卡）

设计要点：
- 纯读 + 确定性生成，零 AI 调用，不消耗任何外部配额。
- 挖空自测（cloze）从知识点自身的 content / examples 中确定性抽取关键词挖空，
  全学科通用、可自动判分，正好消化刚整理的 674 条知识点文本。
- 掌握即发金币（+3）复用 coin_ledger，短会话、无外部阻塞调用（遵守连接池铁律）。

接口（前缀 /api/knowledge，挂载于 main.py，依赖 user_auth_deps 统一鉴权）：
- GET  /           列表：?subject&grade&unit
- GET  /units      该学科+年级下的单元去重列表（用于前端筛选）
- GET  /{id}       详情：summary/content/examples
- GET  /{id}/cloze 挖空自测（确定性，无 AI）
- POST /{id}/master 自测全对/标记掌握 → 发 +3 金币 + 鼓励文案
"""
import random
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.knowledge import KnowledgePoint
from app.models.pet import CoinLedger

router = APIRouter()

# 鼓励文案池（连对自测/标记掌握时随机返回，制造正反馈）
ENCOURAGE = [
    "太棒了，这个知识点你已经吃透啦！",
    "稳！又拿下一个考点 💪",
    "理解到位，继续冲！",
    "漂亮，自测全对，记牢了！",
    "识记成功，金币 +3 🪙",
]


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════

class KnowledgeOut(BaseModel):
    id: int
    subject: str
    grade: int
    unit: str
    title: str
    summary: str
    difficulty: int


class KnowledgeDetail(KnowledgeOut):
    content: str = ""
    examples: List[str] = []


class ClozeItem(BaseModel):
    sentence: str
    answer: str


class ClozeOut(BaseModel):
    items: List[ClozeItem] = []


class MasterReq(BaseModel):
    user_id: str
    all_correct: bool = True


class MasterOut(BaseModel):
    granted: int = 0
    coins: int = 0
    message: str = ""


# ═══════════════════════════════════════════════════════════
# 列表 / 单元
# ═══════════════════════════════════════════════════════════

@router.get("", response_model=List[KnowledgeOut])
def list_knowledge(
    subject: str = Query(..., description="学科，如 数学/语文/英语"),
    grade: int = Query(..., description="年级 1-9"),
    unit: Optional[str] = Query(None, description="单元筛选（可空）"),
    db: Session = Depends(get_db),
):
    """知识点列表（按学科+年级，可选单元）。只读。"""
    q = db.query(KnowledgePoint).filter(
        KnowledgePoint.subject == subject, KnowledgePoint.grade == grade
    )
    if unit:
        q = q.filter(KnowledgePoint.unit == unit)
    rows = q.order_by(KnowledgePoint.unit, KnowledgePoint.id).all()
    return [
        KnowledgeOut(
            id=r.id, subject=r.subject, grade=r.grade, unit=r.unit or "",
            title=r.title, summary=r.summary or "", difficulty=r.difficulty or 2,
        )
        for r in rows
    ]


@router.get("/units", response_model=List[str])
def knowledge_units(
    subject: str = Query(...),
    grade: int = Query(...),
    db: Session = Depends(get_db),
):
    """该学科+年级下的单元去重列表（用于前端筛选下拉）。只读。"""
    rows = (
        db.query(KnowledgePoint.unit)
        .filter(KnowledgePoint.subject == subject, KnowledgePoint.grade == grade)
        .distinct()
        .order_by(KnowledgePoint.unit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


# ═══════════════════════════════════════════════════════════
# 详情
# ═══════════════════════════════════════════════════════════

@router.get("/{kp_id}", response_model=KnowledgeDetail)
def knowledge_detail(kp_id: int, db: Session = Depends(get_db)):
    """知识点详情：summary + content（讲解）+ examples（例子，按行拆分）。只读。"""
    kp = db.get(KnowledgePoint, kp_id)
    if not kp:
        raise HTTPException(404, "知识点不存在")
    examples = [e for e in (kp.examples or "").split("\n") if e.strip()]
    return KnowledgeDetail(
        id=kp.id, subject=kp.subject, grade=kp.grade, unit=kp.unit or "",
        title=kp.title, summary=kp.summary or "", difficulty=kp.difficulty or 2,
        content=kp.content or "", examples=examples,
    )


# ═══════════════════════════════════════════════════════════
# 挖空自测（确定性，无 AI）
# ═══════════════════════════════════════════════════════════

def _build_cloze(kp: KnowledgePoint) -> List[ClozeItem]:
    """从 content / examples 抽取关键词挖空：优先挖标题中的概念词，否则挖最长中文词。"""
    chunks: List[str] = []
    if kp.content:
        for s in re.split(r"[。；\n]", kp.content or ""):
            s = s.strip()
            if s:
                chunks.append(s)
    if kp.examples:
        for s in (kp.examples or "").split("\n"):
            s = s.strip()
            if s:
                chunks.append(s)

    title_terms = re.findall(r"[一-鿿]{2,}", kp.title or "")
    items: List[ClozeItem] = []
    for c in chunks:
        term = None
        # 1) 优先挖标题中的中文概念词（如「有理数加法法则」）
        for t in title_terms:
            if t in c:
                term = t
                break
        # 2) 否则挖最长中文词
        if not term:
            cjk = re.findall(r"[一-鿿]{2,}", c)
            if cjk:
                term = max(cjk, key=len)
        # 3) 仍无（纯英文例句，如英语知识点）：挖最长英文词
        if not term:
            en = re.findall(r"[A-Za-z]{3,}", c)
            if en:
                term = max(en, key=len)
        if not term or len(term) < 2:
            continue
        cloze = c.replace(term, "＿＿＿", 1)
        items.append(ClozeItem(sentence=cloze, answer=term))
        if len(items) >= 3:
            break
    return items


@router.get("/{kp_id}/cloze", response_model=ClozeOut)
def knowledge_cloze(kp_id: int, db: Session = Depends(get_db)):
    """生成挖空自测：从知识点正文/例子中确定性抽取 1-3 个填空，可自动判分。只读，无 AI。"""
    kp = db.get(KnowledgePoint, kp_id)
    if not kp:
        raise HTTPException(404, "知识点不存在")
    items = _build_cloze(kp)
    if not items:
        raise HTTPException(404, "该知识点暂无可用于自测的文本")
    return ClozeOut(items=items)


# ═══════════════════════════════════════════════════════════
# 掌握发币（短会话，无外部调用）
# ═══════════════════════════════════════════════════════════

@router.post("/{kp_id}/master", response_model=MasterOut)
def knowledge_master(kp_id: int, req: MasterReq, db: Session = Depends(get_db)):
    """标记掌握：自测全对或主动标记 → 发 +3 金币 + 鼓励文案。短会话落库，无外部阻塞调用。"""
    kp = db.get(KnowledgePoint, kp_id)
    if not kp:
        raise HTTPException(404, "知识点不存在")
    granted = 0
    if req.all_correct:
        db.add(CoinLedger(user_id=req.user_id, amount=3, reason=f"知识点掌握：{kp.title}"))
        db.commit()
        granted = 3
    bal = int(db.query(func.coalesce(func.sum(CoinLedger.amount), 0)).filter(
        CoinLedger.user_id == req.user_id).scalar() or 0)
    msg = random.choice(ENCOURAGE) if granted else "再看看例子，连对自测就发金币～"
    return MasterOut(granted=granted, coins=bal, message=msg)
