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
# 昵称快捷登录开关：正式上线前置为 false
ALLOW_NICKNAME_LOGIN = os.environ.get("ALLOW_NICKNAME_LOGIN", "true").strip().lower() in ("1", "true", "yes", "on")
