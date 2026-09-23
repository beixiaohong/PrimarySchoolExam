"""062 - 后台 RBAC 补全：IM / 账本 / 公告 管理权限点

背景：060 已建表并种子基础权限目录；commerce/users/assets/vip/rbac/config/
audit/annotation 等后台高危写接口已接 require_perm。但 freeze 域（D9）的
IM / 账本 与 platform 的公告管理写接口此前仅挂 _require_admin（任意已登录
管理员可写），在 RBAC_STRICT=true（默认）下构成越权面。

本次新增三个权限点并授予 admin（运营）/ super（全部）角色：
- im:manage         IM 数据管理（删会话/好友/红包/消息、敏感词增删改）
- ledger:manage     账本数据管理（删账单/账户/分类）
- announcement:manage 系统公告管理（发布/删除）

配套代码改动：对应写接口加 dependencies=[Depends(require_perm(...))]，
未改变既有 _audit 审计行为，且无权限时返回 403，超管/运营角色不受影响。

幂等：seed_rbac 仅追加不存在的权限点与角色映射，重复执行安全；已应用的
060 不会被重跑。
"""
import logging

from app.core.permissions import seed_rbac

logger = logging.getLogger("migrations")


def upgrade(db):
    # 幂等种子：把新增的 im:manage / ledger:manage / announcement:manage
    # 及角色映射（admin + super）写入权限目录与角色映射表。
    seed_rbac(db)
    db.commit()
    logger.info("062 IM/账本/公告管理权限点已种子（im:manage / ledger:manage / announcement:manage）")
