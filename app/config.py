"""应用配置"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
DB_PATH = BASE_DIR / "primary_school.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# 输出目录（生成的试卷存放位置）
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 词库文件路径
WORD_CSV_PATH = DATA_DIR / "words_primary_school.csv"

# 分页默认值
DEFAULT_PAGE_SIZE = 50
