"""应用配置：项目根目录 .env 驱动（python-dotenv 加载）

数据库：本项目仅支持 MySQL（生产 / 本地统一），由 .env 的
DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 拼 pymysql 连接串。
已移除 SQLite 支持（DB_DRIVER 即便误设为其它值也会回退到 mysql）。
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

# 项目根目录（通过当前文件路径向上追溯）
BASE_DIR = Path(__file__).resolve().parent.parent
# 加载 .env（不覆盖已有环境变量，与 ai.py 的加载策略一致）
load_dotenv(BASE_DIR / ".env", override=False)

# 数据存储目录
DATA_DIR = BASE_DIR / "app" / "data"

# ── 数据库驱动（仅 MySQL）──
# 历史曾支持 sqlite 本地零配置开发，现已统一为 MySQL；
# 即使环境变量误配，也强制回退到 mysql，避免误用已移除的 SQLite 路径。
DB_DRIVER = os.environ.get("DB_DRIVER", "mysql").strip().lower()
if DB_DRIVER != "mysql":
    DB_DRIVER = "mysql"

DATABASE_URL = (
    f"mysql+pymysql://{quote_plus(os.environ.get('DB_USER', 'root'))}"
    f":{quote_plus(os.environ.get('DB_PASSWORD', ''))}"
    f"@{os.environ.get('DB_HOST', '127.0.0.1')}:{os.environ.get('DB_PORT', '3306')}"
    f"/{os.environ.get('DB_NAME', 'primary_school')}?charset=utf8mb4"
)

# 输出目录（生成的试卷存放位置）
OUTPUT_DIR = BASE_DIR / "output"
# 如果输出目录不存在则创建
OUTPUT_DIR.mkdir(exist_ok=True)

# 词库文件路径
WORD_CSV_PATH = DATA_DIR / "words_primary_school.csv"
MIDDLE_WORD_CSV_PATH = DATA_DIR / "words_middle_school.csv"

# 分页默认值
DEFAULT_PAGE_SIZE = 50

# ── 用户体系（P2） ──
# 昵称快捷登录开关：登录方式已统一为「邮箱 + 密码」，关闭昵称快捷登录
ALLOW_NICKNAME_LOGIN = os.environ.get("ALLOW_NICKNAME_LOGIN", "false").strip().lower() in ("1", "true", "yes", "on")

# ── 钻石充值（手动充值：扫码付款 + 客服核对账号后手动发放）──
# 收款二维码为图片 URL（可放图床或本站 /output 静态目录）；留空则前端提示「联系客服获取收款码」。
# 收款 / 客服二维码：图片放在 web/public/qr/ 下，构建后由 FastAPI 的 /qr 静态路由托管。
# 默认指向 /qr/xxx.png（与 public/qr 对应）；如需改用外链图床或自定义文件名，用环境变量覆盖即可。
RECHARGE_WECHAT_QR = os.environ.get("RECHARGE_WECHAT_QR", "/qr/wx.png").strip()    # 微信收款二维码
RECHARGE_ALIPAY_QR = os.environ.get("RECHARGE_ALIPAY_QR", "/qr/zfb.jpg").strip()   # 支付宝收款二维码
RECHARGE_CS_CONTACT = os.environ.get("RECHARGE_CS_CONTACT", "beidou669").strip()  # 客服联系方式（微信号 / QQ 等），需自行填写
RECHARGE_RATE = 1  # 汇率：1 元 = RECHARGE_RATE 钻石（固定 1:1）

# ── 文档与鉴权（安全） ──
# 生产环境默认关闭 Swagger(/docs) / ReDoc(/redoc) / OpenAPI(/openapi.json)，避免接口结构暴露。
# 本地调试可设 ENABLE_DOCS=true 临时开启。
ENABLE_DOCS = os.environ.get("ENABLE_DOCS", "false").strip().lower() in ("1", "true", "yes", "on")
# 普通用户登录会话 token 有效期（小时），与管理员一致
USER_TOKEN_TTL_HOURS = int(os.environ.get("USER_TOKEN_TTL_HOURS", "12"))
# 同步学单元小测答案令牌的 HMAC 签名密钥（原硬编码于 sync_service.py，现外置以便轮换）
QUIZ_SECRET = os.environ.get("QUIZ_SECRET", "zhixue_sync_quiz_v1")
