"""迁移约定护栏测试

防 078 类坑复发：项目为自定义迁移 runner（app/migrations/runner.py 调用
module.upgrade(db)，db 为 SQLAlchemy Session），**未安装 alembic**，也绝不使用
alembic 的 op 写法。一旦某迁移误用 `from alembic import op`，import 阶段即
ModuleNotFoundError，导致 app 启动期迁移失败、全站测试大面积 ERROR。

本测试把该约定固化为 CI 级护栏：
1. versions/ 下任何迁移不得 import alembic；
2. 每个迁移必须定义可调用 upgrade(db)（首参名为 db）。
"""
import importlib
import inspect
import os
import re

import pytest

VERSIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "app", "migrations", "versions")


def _list_migration_files():
    files = []
    for f in sorted(os.listdir(VERSIONS_DIR)):
        if f.endswith(".py") and not f.startswith("__"):
            files.append(f)
    return files


@pytest.mark.parametrize("fname", _list_migration_files())
def test_no_alembic_import(fname):
    """迁移不得依赖 alembic（项目为自定义 runner）"""
    path = os.path.join(VERSIONS_DIR, fname)
    src = open(path, encoding="utf-8", errors="ignore").read()
    assert not re.search(r"^\s*(from|import)\s+alembic", src, re.M), \
        f"{fname} 误用 alembic（本项目为自定义迁移 runner，请勿 import alembic）"


@pytest.mark.parametrize("fname", _list_migration_files())
def test_upgrade_signature(fname):
    """每个迁移必须提供 upgrade(db) 可调用入口（首参 db）"""
    mod = importlib.import_module(
        f"app.migrations.versions.{fname[:-3]}")
    assert hasattr(mod, "upgrade"), f"{fname} 缺少 upgrade(db)"
    assert callable(mod.upgrade), f"{fname}.upgrade 不可调用"
    params = list(inspect.signature(mod.upgrade).parameters)
    assert params and params[0] == "db", \
        f"{fname}.upgrade 首参应为 db，实际：{params}"
