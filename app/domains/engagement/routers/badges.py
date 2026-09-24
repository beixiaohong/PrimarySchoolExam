"""成就徽章墙（新功能 B 升级后：本文件退化为薄 HTTP 层）

规则与授予逻辑已下沉到 `app/domains/engagement/services/achievement.py`
（单一真相源 BADGE_RULES + 事件驱动 try_grant）。此处只负责：
- 组装 HTTP 响应（含每枚徽章的 progress 进度与 category 分类，供前端进度条/分类 tab）；
- 保持 `GET /api/badges` 的**兜底全量授予**语义（登录/进入徽章墙时补齐历史达标徽章）。
实时授予由各写操作埋点调用 `AchievementService.try_grant`（见 engagement/contracts.py）。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.engagement.services.achievement import list_badges

router = APIRouter(tags=["badges"])


@router.get("", summary="成就徽章墙：扫描并授予新徽章，返回全部徽章状态（含进度/分类）")
def get_badges(user_id: str = Query(...), db: Session = Depends(get_db)):
    """成就徽章墙：兜底授予新徽章，返回全部徽章状态与进度。

    查询参数：user_id；无需家长密码。
    返回：{total, earned(已得数), newly(本次新解锁 code 列表),
          categories:[{key,label,total,earned}],
          items:[{code,emoji,name,desc,category,earned,earned_at,
                  progress:{current,target,pct}}]}。
    副作用：一次性统计学习数据，对首次达成阈值且未记录的徽章新增 badge_earned 落库
          （阈值与分类见 services/achievement.py 的 BADGE_RULES）。
    """
    return list_badges(db, user_id)
