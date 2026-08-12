"""金币宠物（创意 6）：金币流水 + 宠物养成

金币：余额 = coin_ledger.amount 之和。行为挂钩发币见各模块（_grant_coins 注入）。
宠物：等级 1-10，经验 = 10 + level*5 升级；形态按等级段变化（前端 emoji）。
喂养：消耗 10 金币 → +5 经验；抚摸：每天 3 次 → +1 经验。
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.pet import CoinLedger, PetProfile

router = APIRouter(tags=["pet"])

FEED_COST = 10      # 喂食消耗金币
FEED_EXP = 5        # 喂食获得经验
PAT_LIMIT = 3       # 每日抚摸次数上限
PAT_EXP = 1         # 抚摸获得经验
MAX_LEVEL = 10


def _exp_needed(level: int) -> int:
    """升到下一级所需经验"""
    return 10 + level * 5


def _grant_coins(db: Session, user_id: str, amount: int, reason: str) -> None:
    """发金币（内部钩子，供任务/答题/错题/小老师模块调用）"""
    if not user_id or amount == 0:
        return
    db.add(CoinLedger(user_id=user_id, amount=amount, reason=reason))


def _balance(db: Session, user_id: str) -> int:
    total = db.query(func.coalesce(func.sum(CoinLedger.amount), 0)).filter(
        CoinLedger.user_id == user_id).scalar()
    return int(total)


def _get_or_create(db: Session, user_id: str) -> PetProfile:
    p = db.query(PetProfile).filter(PetProfile.user_id == user_id).first()
    if not p:
        p = PetProfile(user_id=user_id)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _add_exp(db: Session, p: PetProfile, exp: int) -> bool:
    """加经验并处理升级，返回是否升级"""
    p.exp += exp
    leveled = False
    while p.level < MAX_LEVEL and p.exp >= _exp_needed(p.level):
        p.exp -= _exp_needed(p.level)
        p.level += 1
        leveled = True
    if p.level >= MAX_LEVEL:
        p.exp = min(p.exp, _exp_needed(MAX_LEVEL) - 1)
    return leveled


def _profile_out(p: PetProfile, balance: int) -> dict:
    return {
        "pet_key": p.pet_key,
        "level": p.level,
        "exp": p.exp,
        "exp_next": _exp_needed(p.level) if p.level < MAX_LEVEL else None,
        "max_level": p.level >= MAX_LEVEL,
        "pats_today": p.pats_today,
        "feeds_today": p.feeds_today,
        "fed_count": p.fed_count,
        "coins": balance,
    }


class FeedReq(BaseModel):
    user_id: str


@router.get("", summary="宠物档案 + 金币余额")
def get_pet(user_id: str = Query(...), db: Session = Depends(get_db)):
    """获取宠物档案与金币余额（不存在则自动创建 1 级空档案）。

    参数（Query）：user_id。
    返回：宠物档案（pet_key/level/exp/exp_next/max_level）+ 今日喂/摸次数 + coins（金币余额）。
    副作用：无（只读，若不存在仅创建档案不提交额外数据）。无需家长密码。
    """
    p = _get_or_create(db, user_id)
    return _profile_out(p, _balance(db, user_id))


@router.post("/feed", summary="喂食：-10 金币 +5 经验")
def feed_pet(req: FeedReq, db: Session = Depends(get_db)):
    """喂食宠物：消耗 10 金币换 5 经验（每日喂食次数累加）。

    参数（Body）：user_id。
    返回：宠物档案 + leveled（是否升级）；金币不足或已满级返回 400。
    副作用：写入 CoinLedger（amount=-10）、加经验（可能升级）、累加 feeds_today/fed_count。
    无需家长密码。阈值：FEED_COST=10、FEED_EXP=5、MAX_LEVEL=10。
    """
    p = _get_or_create(db, req.user_id)
    balance = _balance(db, req.user_id)
    if balance < FEED_COST:
        raise HTTPException(400, f"金币不够啦（喂食需 {FEED_COST} 币），先去完成任务赚金币吧")
    if p.level >= MAX_LEVEL:
        raise HTTPException(400, "宠物已满级，不需要再喂啦")
    # 扣币 + 加经验
    db.add(CoinLedger(user_id=req.user_id, amount=-FEED_COST, reason="喂食宠物"))
    leveled = _add_exp(db, p, FEED_EXP)
    p.fed_count += 1
    today = str(date.today())
    p.feeds_today = p.feeds_today + 1 if p.feed_date == today else 1
    p.feed_date = today
    db.commit()
    out = _profile_out(p, _balance(db, req.user_id))
    out["leveled"] = leveled
    return out


@router.post("/pat", summary="抚摸：每天 3 次 +1 经验")
def pat_pet(req: FeedReq, db: Session = Depends(get_db)):
    """抚摸宠物：每日限 3 次，每次 +1 经验（不消耗金币）。

    参数（Body）：user_id。
    返回：宠物档案 + leveled；今日已摸满 3 次或已满级返回 400。
    副作用：累加 pats_today（跨天自动归零）、加经验（可能升级）。
    无需家长密码。阈值：PAT_LIMIT=3、PAT_EXP=1。
    """
    p = _get_or_create(db, req.user_id)
    today = str(date.today())
    if p.pat_date != today:
        p.pats_today = 0
        p.pat_date = today
    if p.pats_today >= PAT_LIMIT:
        raise HTTPException(400, "今天已经摸够 3 次啦，明天再来吧")
    if p.level >= MAX_LEVEL:
        raise HTTPException(400, "宠物已满级，不需要再摸啦")
    p.pats_today += 1
    leveled = _add_exp(db, p, PAT_EXP)
    db.commit()
    out = _profile_out(p, _balance(db, req.user_id))
    out["leveled"] = leveled
    return out


@router.get("/ledger", summary="金币流水（最近 30 条）")
def ledger(user_id: str = Query(...), db: Session = Depends(get_db)):
    """查询金币流水（最近 30 条，倒序）。

    参数（Query）：user_id。
    返回：[{amount, reason, created_at(%m-%d %H:%M)}]。
    副作用：无（只读）。无需家长密码。
    """
    rows = db.query(CoinLedger).filter(CoinLedger.user_id == user_id).order_by(
        CoinLedger.id.desc()).limit(30).all()
    return [{
        "amount": r.amount,
        "reason": r.reason,
        "created_at": r.created_at.strftime("%m-%d %H:%M") if r.created_at else "",
    } for r in rows]


@router.get("/rules", summary="金币获取规则说明")
def rules():
    """返回金币获取/消耗规则说明（前端展示用，无副作用）。

    返回：{items[{action, coins, desc}]}。
    """
    return {
        "items": [
            {"action": "完成任务", "coins": 5, "desc": "每天各科任务完成，每完成一科 +5"},
            {"action": "答题全对", "coins": 10, "desc": "一份试卷全部答对 +10（每题答对 +1）"},
            {"action": "错题掌握", "coins": 3, "desc": "重做错题并掌握 +3"},
            {"action": "小老师讲清", "coins": 10, "desc": "家长答错/答对后孩子批改完成 +10"},
            {"action": "喂食宠物", "coins": -10, "desc": "每次喂食消耗 10 金币，宠物 +5 经验"},
        ]
    }
