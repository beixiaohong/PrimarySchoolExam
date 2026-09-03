"""学习目标管理台 API（/api/learning-goals）

设计要点：
- 鉴权：每个接口经 require_self 取当前登录用户（严格账号绑定，禁止查/改他人数据）。
- 数据全部在线（MySQL）：新建/打卡/补记/删记录/存周报均即时落库，换设备/换浏览器数据都在。
- 计算均在服务端完成，前端只渲染：
  * 今日建议量 = 剩余量 ÷ 剩余天数（打卡表单预填，允许修改）
  * 连续打卡天数：每周一重置，每周允许 1 个休息日（本周第一次漏打不中断，第二次才断）
  * 预计完成日：按近 7 天平均速度推算；样本不足（近 7 天无打卡）显示 has_est=False，前端显示「暂无推算」
  * 与截止日比较 → delta_days（<=0 提前 / >0 拖后）
  * 昨日漏打 → pinned（今日置顶）+ 黄/红卡解释休息日与滚入
  * 逾期 → 红卡 + 逾期天数 + 立即打卡/调整计划出口
- 一天可多次打卡；补记最近 6 天带 is_backfill 标，按真实日期参与连续天数与推算。
- 预置 3 个示例目标 + 几天记录；清空全部需 confirm=="清空"。
"""
from datetime import date, datetime, timedelta
import math

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.routers.auth import require_self
from app.models.user import User
from app.models.learning_goal import LearningGoal, LearningCheckin, LearningWeeklyReview

router = APIRouter()


# ════════════════════════ 工具函数 ════════════════════════

def _monday_of(d: date) -> date:
    """返回 d 所在周的周一（weekday(): 周一=0）。"""
    return d - timedelta(days=d.weekday())


def _compute_streak(date_set, today: date) -> int:
    """连续打卡天数（允许每周 1 个休息日）。

    - 从最近一次打卡日向后（更早）逐日回溯；
    - 本周（周一~周日）内第一次漏打 = 休息日，不中断，继续往前；
    - 本周第二次漏打 → 中断；
    - 今天尚未打卡不算断（只停止计数，不计入连续天数）。
    返回连续天数（整数）。
    """
    if not date_set:
        return 0
    streak = 0
    d = max(date_set)
    cur_monday = None
    miss_in_week = 0
    safety = 0
    while safety < 600:
        safety += 1
        if d > today:  # 防御：不应出现未来日期
            d -= timedelta(days=1)
            continue
        monday = _monday_of(d)
        if monday != cur_monday:
            cur_monday = monday
            miss_in_week = 0
        if d in date_set:
            streak += 1
            d -= timedelta(days=1)
            continue
        # 漏打当天
        if d == today:
            break  # 今天还没打卡，未中断，停止计数
        miss_in_week += 1
        if miss_in_week >= 2:
            break
        d -= timedelta(days=1)
    return streak


def _estimate(date_amounts: dict, today: date, current: float, total: float, deadline):
    """预计完成日：近 7 天平均速度推算。

    返回 {has_est, est_date(ISO|None), avg(每天均量), delta_days(与截止日差:<=0提前/>0拖后/None无截止日)}。
    近 7 天无任何打卡 → has_est=False（样本不足，前端显示「暂无推算」，不编数字）。
    """
    last7 = sum(v for d, v in date_amounts.items() if today - timedelta(days=6) <= d <= today)
    if last7 <= 0:
        return {"has_est": False, "est_date": None, "avg": 0.0, "delta_days": None}
    avg = last7 / 7.0
    remaining = max(total - current, 0.0)
    if remaining <= 0:
        return {"has_est": True, "est_date": today.isoformat(), "avg": avg, "delta_days": 0}
    if avg <= 0:
        return {"has_est": False, "est_date": None, "avg": avg, "delta_days": None}
    days_needed = max(1, math.ceil(remaining / avg))
    est = today + timedelta(days=days_needed)
    delta = (est - deadline).days if deadline else None
    return {"has_est": True, "est_date": est.isoformat(), "avg": round(avg, 2), "delta_days": delta}


def _week_miss_upto_yesterday(date_set, today: date) -> int:
    """本周一~昨天之间漏打的天数（用于判断休息日是否已被占用）。"""
    monday = _monday_of(today)
    cnt = 0
    d = monday
    while d < today:
        if d not in date_set:
            cnt += 1
        d += timedelta(days=1)
    return cnt


def _goal_stats(goal: LearningGoal, db: Session, today: date) -> dict:
    """聚合单个目标的所有展示字段。"""
    checkins = db.query(LearningCheckin).filter(
        LearningCheckin.user_id == goal.user_id,
        LearningCheckin.goal_id == goal.id,
    ).order_by(LearningCheckin.date.asc()).all()

    date_set = set()
    date_amounts = {}
    current = 0.0
    for c in checkins:
        date_set.add(c.date)
        date_amounts[c.date] = date_amounts.get(c.date, 0.0) + (c.amount or 0.0)
        current += (c.amount or 0.0)
    current = round(current, 4)

    total = goal.total or 0.0
    pct = round(min(current / total, 1.0) * 100) if total > 0 else 0
    achieved = current >= total and total > 0

    days_left = None
    overdue = False
    overdue_days = 0
    daily_suggestion = None
    if goal.deadline:
        days_left = (goal.deadline - today).days
        overdue = days_left < 0 and not achieved
        overdue_days = -days_left if days_left < 0 else 0
        if days_left > 0 and not achieved:
            daily_suggestion = round((total - current) / days_left, 1)

    streak = _compute_streak(date_set, today)

    est = _estimate(date_amounts, today, current, total, goal.deadline)

    yesterday = today - timedelta(days=1)
    missed_yesterday = (yesterday not in date_set) and not achieved and goal.status == "active"

    week_miss = _week_miss_upto_yesterday(date_set, today)
    rest_available = week_miss == 0  # 本周休息日尚未占用
    # 卡片类型：overdue(红) / rest(黄,休息日生效) / broken(红,连续已中断) / None
    card_kind = None
    if overdue:
        card_kind = "overdue"
    elif missed_yesterday:
        card_kind = "rest" if rest_available else "broken"

    pinned = bool(missed_yesterday or overdue)  # 今日自动置顶

    # 最近 10 条记录（看板）
    recent = []
    for c in sorted(checkins, key=lambda x: (x.created_at or datetime.min), reverse=True)[:10]:
        recent.append({
            "id": c.id, "date": str(c.date), "amount": c.amount,
            "minutes": c.minutes, "is_backfill": c.is_backfill,
        })

    return {
        "id": goal.id, "name": goal.name, "unit": goal.unit,
        "total": total, "deadline": str(goal.deadline) if goal.deadline else None,
        "color": goal.color, "obstacle": goal.obstacle or "", "counter": goal.counter or "",
        "status": goal.status, "achieved": achieved,
        "current": current, "pct": pct,
        "days_left": days_left, "overdue": overdue, "overdue_days": overdue_days,
        "daily_suggestion": daily_suggestion,
        "streak": streak,
        "est": est,
        "missed_yesterday": missed_yesterday,
        "rest_available": rest_available,
        "week_miss": week_miss,
        "card_kind": card_kind,
        "pinned": pinned,
        "recent": recent,
        "checkin_count": len(checkins),
    }


# ════════════════════════ 请求模型 ════════════════════════

class CreateGoalReq(BaseModel):
    name: str
    unit: str = "个"
    total: float
    deadline: str = ""        # YYYY-MM-DD，空=无截止日
    color: str = "purple"
    obstacle: str = ""
    counter: str = ""


class UpdateGoalReq(BaseModel):
    name: str = None
    unit: str = None
    total: float = None
    deadline: str = None      # "" 表示清除截止日
    color: str = None
    obstacle: str = None
    counter: str = None


class CheckinReq(BaseModel):
    amount: float
    minutes: int = None
    date: str = ""            # YYYY-MM-DD；空=今天；过去 1~6 天=补记


class WeeklyReq(BaseModel):
    week_start: str = ""      # YYYY-MM-DD；空=本周一
    keep: str = ""
    problem: str = ""
    try_plan: str = ""
    next_plan: str = ""


class ClearReq(BaseModel):
    confirm: str


# ════════════════════════ 接口 ════════════════════════

@router.get("", summary="学习目标列表（含全部计算字段）")
def list_goals(current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    today = date.today()
    goals = db.query(LearningGoal).filter(
        LearningGoal.user_id == current_user.user_id,
        LearningGoal.status.in_(("active", "done")),
    ).order_by(LearningGoal.id.desc()).all()
    out = [_goal_stats(g, db, today) for g in goals]
    # 置顶：pinned（昨日漏打/逾期）优先
    out.sort(key=lambda x: (0 if x["pinned"] else 1, -x["id"]))
    has_examples = len(out) > 0
    return {"goals": out, "server_date": today.isoformat(), "has_examples": has_examples}


@router.post("", summary="新建学习目标")
def create_goal(req: CreateGoalReq, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "目标名称不能为空")
    if req.total <= 0:
        raise HTTPException(400, "总量需大于 0")
    deadline = None
    if req.deadline:
        try:
            deadline = date.fromisoformat(req.deadline)
        except ValueError:
            raise HTTPException(400, "截止日期格式应为 YYYY-MM-DD")
    g = LearningGoal(
        user_id=current_user.user_id, name=name, unit=(req.unit or "个").strip() or "个",
        total=req.total, deadline=deadline, color=req.color or "purple",
        obstacle=(req.obstacle or "").strip(), counter=(req.counter or "").strip(),
        status="active",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _goal_stats(g, db, date.today())


@router.put("/{gid}", summary="编辑学习目标")
def update_goal(gid: int, req: UpdateGoalReq, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    g = db.query(LearningGoal).filter(
        LearningGoal.id == gid, LearningGoal.user_id == current_user.user_id).first()
    if not g:
        raise HTTPException(404, "目标不存在")
    if req.name is not None and req.name.strip():
        g.name = req.name.strip()
    if req.unit is not None:
        g.unit = req.unit.strip() or g.unit
    if req.total is not None:
        if req.total <= 0:
            raise HTTPException(400, "总量需大于 0")
        g.total = req.total
    if req.deadline is not None:
        if req.deadline == "":
            g.deadline = None
        else:
            try:
                g.deadline = date.fromisoformat(req.deadline)
            except ValueError:
                raise HTTPException(400, "截止日期格式应为 YYYY-MM-DD")
    if req.color is not None:
        g.color = req.color
    if req.obstacle is not None:
        g.obstacle = req.obstacle.strip()
    if req.counter is not None:
        g.counter = req.counter.strip()
    db.commit()
    return _goal_stats(g, db, date.today())


@router.delete("/{gid}", summary="删除目标（含其打卡记录）")
def delete_goal(gid: int, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    g = db.query(LearningGoal).filter(
        LearningGoal.id == gid, LearningGoal.user_id == current_user.user_id).first()
    if not g:
        raise HTTPException(404, "目标不存在")
    db.query(LearningCheckin).filter(
        LearningCheckin.goal_id == gid, LearningCheckin.user_id == current_user.user_id).delete()
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.post("/{gid}/checkin", summary="打卡（支持补记最近 6 天）")
def add_checkin(gid: int, req: CheckinReq, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    g = db.query(LearningGoal).filter(
        LearningGoal.id == gid, LearningGoal.user_id == current_user.user_id).first()
    if not g:
        raise HTTPException(404, "目标不存在")
    if req.amount is None or req.amount <= 0:
        raise HTTPException(400, "完成量需大于 0")
    today = date.today()
    cdate = today
    if req.date:
        try:
            cdate = date.fromisoformat(req.date)
        except ValueError:
            raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    if cdate > today:
        raise HTTPException(400, "不能给未来的日期打卡")
    if (today - cdate).days > 6:
        raise HTTPException(400, "补记仅支持最近 6 天")
    minutes = req.minutes
    if minutes is not None:
        if minutes < 0:
            raise HTTPException(400, "分钟数不能为负")
        minutes = int(minutes)
    is_backfill = cdate < today
    c = LearningCheckin(
        goal_id=gid, user_id=current_user.user_id, date=cdate,
        amount=req.amount, minutes=minutes, is_backfill=is_backfill,
    )
    db.add(c)
    # 达成判定
    just_achieved = False
    if g.status != "done":
        total_amount = db.query(LearningCheckin).filter(
            LearningCheckin.goal_id == gid, LearningCheckin.user_id == current_user.user_id
        ).with_entities(LearningCheckin.amount).all()
        cur = sum((r[0] or 0) for r in total_amount)
        if cur >= (g.total or 0) and (g.total or 0) > 0:
            g.status = "done"
            g.achieved_at = datetime.now()
            just_achieved = True
    db.commit()
    stats = _goal_stats(g, db, today)
    stats["just_achieved"] = just_achieved
    return stats


@router.delete("/checkins/{cid}", summary="删除一条打卡记录")
def delete_checkin(cid: int, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    c = db.query(LearningCheckin).filter(
        LearningCheckin.id == cid, LearningCheckin.user_id == current_user.user_id).first()
    if not c:
        raise HTTPException(404, "记录不存在")
    gid = c.goal_id
    db.delete(c)
    # 若曾因该目标达成而置 done，删除后若未达成立即恢复 active
    g = db.query(LearningGoal).filter(LearningGoal.id == gid).first()
    if g and g.status == "done":
        cur = db.query(LearningCheckin).filter(
            LearningCheckin.goal_id == gid, LearningCheckin.user_id == current_user.user_id
        ).with_entities(LearningCheckin.amount).all()
        if sum((r[0] or 0) for r in cur) < (g.total or 0):
            g.status = "active"
            g.achieved_at = None
    db.commit()
    return {"ok": True}


@router.get("/weekly", summary="周报数据（含上周环比 + 已存复盘）")
def get_weekly(week: str = "", current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    today = date.today()
    if week:
        try:
            ws = date.fromisoformat(week)
        except ValueError:
            raise HTTPException(400, "week 格式应为 YYYY-MM-DD（周一）")
    else:
        ws = _monday_of(today)
    # 校验 ws 是周一
    if ws.weekday() != 0:
        ws = _monday_of(ws)

    def _week_agg(start: date):
        end = start + timedelta(days=6)
        rows = db.query(LearningCheckin).filter(
            LearningCheckin.user_id == current_user.user_id,
            LearningCheckin.date >= start, LearningCheckin.date <= end,
        ).all()
        amount = sum((r.amount or 0) for r in rows)
        days = len(set(r.date for r in rows))
        minutes = sum((r.minutes or 0) for r in rows if r.minutes is not None)
        return {"amount": round(amount, 2), "days": days, "minutes": minutes}

    this_week = _week_agg(ws)
    last_week = _week_agg(ws - timedelta(days=7))
    rev = db.query(LearningWeeklyReview).filter(
        LearningWeeklyReview.user_id == current_user.user_id,
        LearningWeeklyReview.week_start == ws).first()
    review = None
    if rev:
        review = {"keep": rev.keep, "problem": rev.problem,
                  "try_plan": rev.try_plan, "next_plan": rev.next_plan}
    return {"week_start": ws.isoformat(), "this_week": this_week,
            "last_week": last_week, "review": review}


@router.post("/weekly", summary="保存周报（四栏，幂等 upsert）")
def save_weekly(req: WeeklyReq, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    today = date.today()
    if req.week_start:
        try:
            ws = date.fromisoformat(req.week_start)
        except ValueError:
            raise HTTPException(400, "week_start 格式应为 YYYY-MM-DD")
    else:
        ws = _monday_of(today)
    if ws.weekday() != 0:
        ws = _monday_of(ws)
    rev = db.query(LearningWeeklyReview).filter(
        LearningWeeklyReview.user_id == current_user.user_id,
        LearningWeeklyReview.week_start == ws).first()
    if not rev:
        rev = LearningWeeklyReview(user_id=current_user.user_id, week_start=ws)
        db.add(rev)
    rev.keep = (req.keep or "").strip()
    rev.problem = (req.problem or "").strip()
    rev.try_plan = (req.try_plan or "").strip()
    rev.next_plan = (req.next_plan or "").strip()
    db.commit()
    return {"ok": True, "week_start": ws.isoformat()}


@router.get("/minutes", summary="近 N 天分钟分目标堆叠数据")
def get_minutes(days: int = 14, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    days = max(1, min(60, days))
    today = date.today()
    start = today - timedelta(days=days - 1)
    rows = db.query(LearningCheckin).filter(
        LearningCheckin.user_id == current_user.user_id,
        LearningCheckin.date >= start, LearningCheckin.date <= today,
        LearningCheckin.minutes.isnot(None),
    ).all()
    goals = db.query(LearningGoal).filter(
        LearningGoal.user_id == current_user.user_id).all()
    gmap = {g.id: g for g in goals}
    by_date = {}
    for c in rows:
        by_date.setdefault(str(c.date), {})
        by_date[str(c.date)][c.goal_id] = by_date[str(c.date)].get(c.goal_id, 0) + (c.minutes or 0)
    dates = [(start + timedelta(days=i)) for i in range(days)]
    return {
        "dates": [str(d) for d in dates],
        "goals": [{"id": g.id, "name": g.name, "color": g.color} for g in goals],
        "series": {str(d): by_date.get(str(d), {}) for d in dates},
    }


@router.get("/sync", summary="同步状态（最近一次写入时间）")
def sync_status(current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    uid = current_user.user_id
    g_max = db.query(LearningGoal.updated_at).filter(LearningGoal.user_id == uid).order_by(
        LearningGoal.updated_at.desc()).first()
    c_max = db.query(LearningCheckin.created_at).filter(LearningCheckin.user_id == uid).order_by(
        LearningCheckin.created_at.desc()).first()
    r_max = db.query(LearningWeeklyReview.updated_at).filter(LearningWeeklyReview.user_id == uid).order_by(
        LearningWeeklyReview.updated_at.desc()).first()
    candidates = [x[0] for x in (g_max, c_max, r_max) if x and x[0]]
    last = max(candidates) if candidates else None
    return {"online": True, "last_sync": last.isoformat() if last else None}


@router.post("/seed-examples", summary="载入 3 个示例目标 + 几天记录（幂等）")
def seed_examples(current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    uid = current_user.user_id
    existing = db.query(LearningGoal).filter(LearningGoal.user_id == uid).count()
    if existing > 0:
        return {"ok": True, "seeded": False, "msg": "已有目标，跳过示例"}
    today = date.today()

    def _add(name, unit, total, dl_offset, color, obstacle, counter):
        dl = today + timedelta(days=dl_offset)
        g = LearningGoal(user_id=uid, name=name, unit=unit, total=total,
                         deadline=dl, color=color, obstacle=obstacle, counter=counter,
                         status="active")
        db.add(g)
        db.flush()
        return g

    def _ck(g, offset, amount, minutes, backfill=False):
        cdate = today - timedelta(days=offset)
        db.add(LearningCheckin(goal_id=g.id, user_id=uid, date=cdate,
                               amount=amount, minutes=minutes, is_backfill=backfill))

    # 1) 背英语单词（紫）：连续每日，含 1 条补记（3 天前）
    g1 = _add("背英语单词", "个", 2000, 60, "purple",
              "早上起不来，碎片时间全刷手机", "把单词卡设成手机锁屏，等公交先背 10 个")
    for off in [10, 9, 8, 7, 6, 5, 4, 2, 1]:
        _ck(g1, off, 30, 15)
    _ck(g1, 3, 25, 12, backfill=True)  # 补记

    # 2) 读《人类简史》（蓝）：昨天漏打 → 触发休息日黄卡（本周首次漏打）
    g2 = _add("读《人类简史》", "页", 440, 90, "blue",
              "晚上太累只想刷短视频", "睡前把视频换成读 5 页，书放书桌不放床头")
    for off in [8, 7, 6, 5, 4, 3, 2]:
        _ck(g2, off, 12, 20)
    _ck(g2, 0, 10, 18)  # 今天有，昨天(1)无 → 昨日漏打

    # 3) Python 入门课（绿）：出现连续两天漏打 → 触发红卡/连续中断
    g3 = _add("Python 入门课", "节", 60, 45, "green",
              "遇到报错就卡住想放弃", "报错先截图问 AI 助手，卡 15 分钟就标记跳过")
    for off in [9, 8, 7, 6, 5]:
        _ck(g3, off, 1, 30)
    for off in [2, 1]:
        _ck(g3, off, 1, 25)
    # 中间 4、3 两天漏打（连续两日）→ 本周第二次漏打，连续中断

    db.commit()
    return {"ok": True, "seeded": True, "msg": "已载入 3 个示例目标"}


@router.post("/clear", summary="清空全部（需 confirm=='清空'）")
def clear_all(req: ClearReq, current_user: User = Depends(require_self), db: Session = Depends(get_db)):
    if (req.confirm or "").strip() != "清空":
        raise HTTPException(400, "请在确认框输入「清空」以继续")
    uid = current_user.user_id
    goal_ids = [r[0] for r in db.query(LearningGoal.id).filter(LearningGoal.user_id == uid).all()]
    for gid in goal_ids:
        db.query(LearningCheckin).filter(
            LearningCheckin.goal_id == gid, LearningCheckin.user_id == uid).delete()
    db.query(LearningGoal).filter(LearningGoal.user_id == uid).delete()
    db.query(LearningWeeklyReview).filter(LearningWeeklyReview.user_id == uid).delete()
    db.commit()
    return {"ok": True}
