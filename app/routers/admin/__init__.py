"""管理后台 API：管理员登录、用户管理、资产调整、VIP、三方配置、审计日志

- 会话 token 制：登录发 token（12h），Authorization: Bearer <token> 鉴权
- 所有敏感操作落 admin_operation_logs 审计表
- 三方配置读写 system_config 表（优先级高于 .env，60s 缓存，保存后立即失效）
"""
from fastapi import APIRouter

router = APIRouter()

# 导入各子模块以触发路由注册（必须在 router 定义之后）
from . import common
from . import auth
from . import users
from . import assets
from . import vip
from . import dashboard
from . import log
from . import config
from . import review
from . import study_records
from . import ledger
from . import analytics
from . import textbooks
from . import content

# 重新导出所有原始顶层名字（含下划线辅助函数）
from .common import *        # logger, TOKEN_TTL_HOURS, CONFIG_GROUPS, SECRET_HINTS, _require_admin, _audit
from .auth import *          # LoginReq, ChangePwdReq, admin_login, admin_me, admin_change_pwd
from .users import *         # AccountReq, UserProfileUpdate, list_users, handle_account, update_user_profile
from .assets import *        # AssetAdjustReq, adjust_assets
from .vip import *           # VipReq, manage_vip
from .dashboard import *     # dashboard
from .log import *           # list_logs
from .config import *        # ConfigSaveReq, _mask, list_config, save_config
from .review import *        # ReviewRunReq, ReviewResolveReq, reviews_run, reviews_queue, reviews_resolve
from .study_records import * # STUDY_CATS, user_study_records
from .ledger import *        # LEDGER_KINDS, user_ledger
from .analytics import *     # analytics
