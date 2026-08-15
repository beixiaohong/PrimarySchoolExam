"""默认管理员种子数据

库内无管理员时创建默认管理员账号，凭证来自环境变量，缺省 admin/Admin@123。
"""
import csv
import os
from pathlib import Path

from app.database import SessionLocal
from app.models.word import Word, WordBook
from app.models.phrase import Phrase, Sentence
from app.models.problem_type import ProblemType, ProblemCategory
from app.models.grammar import GrammarPoint, GrammarExercise
from app.config import WORD_CSV_PATH, MIDDLE_WORD_CSV_PATH, DATA_DIR

def _seed_admin(db):
    """种子默认管理员账号（库内无管理员时创建，凭证来自环境变量，缺省 admin/Admin@123）

    注意：默认口令仅用于首次启动，请上线后立即在后台「修改密码」或配置
    ADMIN_USERNAME / ADMIN_PASSWORD 环境变量后重启。
    """
    import logging
    from app.models.admin import Admin
    from app.routers.parent import _hash_pwd

    if db.query(Admin).count() > 0:
        return
    uname = (os.environ.get("ADMIN_USERNAME") or "admin").strip()
    # 与 tests/conftest.py 的 ADMIN_INIT_PASSWORD 约定保持一致，默认 Admin@123
    pwd = (os.environ.get("ADMIN_INIT_PASSWORD") or "Admin@123").strip()
    db.add(Admin(username=uname, password_hash=_hash_pwd(pwd), role="super"))
    db.commit()
    logging.getLogger("app.init_data").warning(
        "已创建默认管理员账号 user=%s（环境变量 ADMIN_USERNAME/ADMIN_INIT_PASSWORD 可覆盖，"
        "请尽快修改默认密码）", uname)

__all__ = [
    "_seed_admin",
]
