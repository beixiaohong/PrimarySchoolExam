"""应用配置"""
import os
from pathlib import Path

# 项目根目录（通过当前文件路径向上追溯）
BASE_DIR = Path(__file__).resolve().parent.parent
# 数据存储目录
DATA_DIR = BASE_DIR / "app" / "data"
# SQLite 数据库文件路径
DB_PATH = BASE_DIR / "primary_school.db"
# 数据库连接字符串
DATABASE_URL = f"sqlite:///{DB_PATH}"

# 输出目录（生成的试卷存放位置）
OUTPUT_DIR = BASE_DIR / "output"
# 如果输出目录不存在则创建
OUTPUT_DIR.mkdir(exist_ok=True)

# 词库文件路径
WORD_CSV_PATH = DATA_DIR / "words_primary_school.csv"

# 分页默认值
DEFAULT_PAGE_SIZE = 50