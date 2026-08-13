"""pytest 公共夹具：独立 MySQL 测试库 + 会话级 TestClient + 邮件/AI 打桩

注意：
- 环境变量须在 import app 之前设置（config/database 在导入时读取）。
- 数据库驱动强制为 MySQL（与线上一致）；本项目已移除 SQLite 支持。
- 测试库名：优先取环境变量 DB_NAME_TEST；否则取 DB_NAME + "_test"，与线上库隔离。
- 启动前自动 CREATE DATABASE IF NOT EXISTS（需对应 MySQL 账号具备建库权限）；
  会话开始时 drop_all 重建，保证测试干净、**绝不污染线上库**。
- 测试库连接信息完全复用 .env 中的 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD，仅库名不同。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── 测试环境：强制 MySQL + 独立测试库（不碰线上库）──
os.environ["DB_DRIVER"] = "mysql"
_test_db = os.environ.get("DB_NAME_TEST")
if not _test_db:
    _base = os.environ.get("DB_NAME") or "primary_school"
    _test_db = f"{_base}_test"
os.environ["DB_NAME"] = _test_db
os.environ["ALLOW_NICKNAME_LOGIN"] = "true"
os.environ.pop("ADMIN_INIT_PASSWORD", None)  # 走默认 Admin@123

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

# 复用 app.config 已算好的连接串，仅把库名替换为“服务节点”以便建库
from app import config as _cfg  # noqa: E402

_server_url = _cfg.DATABASE_URL.split("?", 1)[0].rsplit("/", 1)[0] + "/"
_engine_srv = create_engine(_server_url, pool_pre_ping=True)
try:
    with _engine_srv.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{_test_db}` CHARACTER SET utf8mb4"))
    print(f"[conftest] 已确保测试库存在: {_test_db}")
except Exception as e:  # 无建库权限或库已存在时降级，连接阶段会再报错
    print(f"[conftest] 警告：无法自动建库 {_test_db}（需 CREATE 权限或库已存在）：{e}")

from fastapi.testclient import TestClient  # noqa: E402


class AuthClient:
    """测试用客户端：自动为所有业务请求注入一个已登录用户的 Bearer token。

    业务接口现已统一要求登录（require_user）。集成测试只需关注业务逻辑，
    不必逐条带 token；管理员接口仍可在调用时显式传 headers（会覆盖此处注入）。
    """

    def __init__(self, client, token):
        self._c = client
        self._h = {"Authorization": f"Bearer {token}"}

    def _merge(self, kwargs):
        h = dict(self._h)
        h.update(kwargs.pop("headers", None) or {})
        kwargs["headers"] = h
        return kwargs

    def get(self, *a, **k):
        return self._c.get(*a, **self._merge(k))

    def post(self, *a, **k):
        return self._c.post(*a, **self._merge(k))

    def put(self, *a, **k):
        return self._c.put(*a, **self._merge(k))

    def delete(self, *a, **k):
        return self._c.delete(*a, **self._merge(k))

    def __getattr__(self, name):
        return getattr(self._c, name)


@pytest.fixture(scope="session")
def client():
    """会话级 TestClient：进入前 drop_all 重建测试库，lifespan 负责建表+迁移+种子。

    同时注入一个已登录测试用户（test_auth_uid）的 token，使业务接口鉴权在测试中可通过。
    """
    from app.database import Base, engine, SessionLocal
    from app.models.user import User
    from app.config import USER_TOKEN_TTL_HOURS
    import secrets
    from datetime import datetime, timedelta
    # 清空测试库，保证每次测试会话从干净状态开始（仅作用于 _test 库）
    Base.metadata.drop_all(bind=engine)
    from app.main import app
    with TestClient(app) as c:
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.user_id == "test_auth_uid").first()
            if not u:
                u = User(user_id="test_auth_uid", nickname="test",
                         email="test_auth@test.com", auth_type="email",
                         email_verified=True, grade=6, subject="英语")
                db.add(u)
            u.token = secrets.token_urlsafe(32)
            u.token_expires_at = datetime.now() + timedelta(hours=USER_TOKEN_TTL_HOURS)
            db.commit()
            token = u.token
        finally:
            db.close()
        yield AuthClient(c, token)


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
