"""等级 / 成长体系 API（新功能 C，2026Q4）

对外只暴露一个**只读**端点：`GET /api/level`。

为什么不提供 `POST /api/level/add-exp`：经验若可由客户端提交数值，等级体系即可被刷
（随便 POST 几次就满级），而等级直接挂钩升级钻石奖励 → 等于把钻石白送。因此经验一律由
服务端**行为埋点**驱动（`services/events.award`，在交卷/掌握错题/完成任务/打卡/签到/
专注等真实行为 commit 之后触发），前端只能读、不能写。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.contracts import require_self
from app.models.user import User

router = APIRouter(tags=["level"])


@router.get("")
def get_level(current_user: User = Depends(require_self),
              db: Session = Depends(get_db)) -> dict:
    """我的等级详情：等级 / 累计经验 / 称号 / 特权 / 距下一级进度 / 完整阶梯表。

    需要登录（Bearer token），只能查自己（`require_self` 保证）。
    返回字段：level、exp、title、perk、level_min_exp、next_level、next_title、
    next_level_exp、exp_to_next、progress_pct、is_max、max_level、reward_diamond、ladder[]。
    `progress_pct` 是**当前等级区间内**的完成百分比（0~100），满级固定 100。
    """
    from app.domains.engagement.services.level import get_level_info
    return get_level_info(db, current_user.user_id)
