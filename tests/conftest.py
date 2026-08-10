"""pytest 公共夹具：临时 SQLite 库 + 会话级 TestClient + 邮件/AI 打桩

注意：环境变量必须在 import app 之前设置（config/database 在导入时读取）。
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── 测试环境：临时 SQLite，禁止污染真实库 ──
_tmp_dir = Path(tempfile.mkdtemp(prefix="exam_test_"))
os.environ["DB_DRIVER"] = "sqlite"
os.environ["DB_SQLITE_PATH"] = str(_tmp_dir / "test.db")
os.environ["ALLOW_NICKNAME_LOGIN"] = "true"
os.environ.pop("ADMIN_INIT_PASSWORD", None)  # 走默认 Admin@123

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """会话级 TestClient：with 语句触发 lifespan（建表+迁移+种子数据）"""
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def no_ai_judge(monkeypatch):
    """全局禁用 AI 判题复核，避免测试触达外部 AI 服务"""
    import app.services.judge as judge
    monkeypatch.setattr(judge, "judge_wrong_items", lambda db, user_id, items: [])


@pytest.fixture()
def fake_mail(monkeypatch):
    """打桩邮件通道：捕获验证码明文（库内只存哈希，无法反查）"""
    import app.routers.auth as auth_mod
    sent = {}

    def _send(target, code, subject=""):
        sent["target"] = target
        sent["code"] = code
        return True

    monkeypatch.setattr(auth_mod, "send_email", _send)
    monkeypatch.setattr(auth_mod, "mail_configured", lambda: True)
    return sent
