"""应用配置：项目根目录 .env 驱动（python-dotenv 加载）

数据库驱动由 DB_DRIVER 控制：
- sqlite（默认）：使用项目根目录 primary_school.db，本地开发零门槛
- mysql：从 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 拼 pymysql 连接串
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
# SQLite 数据库文件路径（可用 DB_SQLITE_PATH 环境变量覆盖，测试用临时库）
DB_PATH = Path(os.environ.get("DB_SQLITE_PATH", "")) if os.environ.get("DB_SQLITE_PATH", "").strip() \
    else BASE_DIR / "primary_school.db"

# ── 数据库驱动 ──
DB_DRIVER = os.environ.get("DB_DRIVER", "sqlite").strip().lower()
if DB_DRIVER == "mysql":
    DATABASE_URL = (
        f"mysql+pymysql://{quote_plus(os.environ.get('DB_USER', 'root'))}"
        f":{quote_plus(os.environ.get('DB_PASSWORD', ''))}"
        f"@{os.environ.get('DB_HOST', '127.0.0.1')}:{os.environ.get('DB_PORT', '3306')}"
        f"/{os.environ.get('DB_NAME', 'primary_school')}?charset=utf8mb4"
    )
else:
    DATABASE_URL = f"sqlite:///{DB_PATH}"

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
# 昵称快捷登录开关：正式上线前置为 false
ALLOW_NICKNAME_LOGIN = os.environ.get("ALLOW_NICKNAME_LOGIN", "true").strip().lower() in ("1", "true", "yes", "on")
