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

from dotenv import load_dotenv

# 关键修正：必须在读取 DB_NAME 之前加载 .env。
# 原代码先读 os.environ["DB_NAME"] 再 import config（config 内才 load_dotenv，
# 且 override=False），导致 .env 中的 DB_NAME 不生效，测试库名误回退到默认
# primary_school_test，而账号无该库建库权限 → pytest 整套 1044 报错。
load_dotenv(ROOT / ".env", override=False)

# ── 测试环境：强制 MySQL + 独立测试库（不碰线上库）──
os.environ["DB_DRIVER"] = "mysql"

# 生产库名（来自 .env，已被上面的 load_dotenv 加载）：用于安全护栏。
PROD_DB_NAME = os.environ.get("DB_NAME") or "primary_school"

# 测试库名：优先 DB_NAME_TEST；否则取生产库名 + "_test"，与生产库隔离。
_test_db = os.environ.get("DB_NAME_TEST") or f"{PROD_DB_NAME}_test"

# 安全护栏：测试库绝不可等于生产库，否则 drop_all 会清空线上数据（灾难性）。
if _test_db == PROD_DB_NAME:
    raise RuntimeError(
        f"[conftest] 安全拦截：测试库名 '{_test_db}' 与生产库名相同，"
        f"drop_all 会清空线上数据！请在 .env 设置 DB_NAME_TEST 指向独立测试库"
        f"（如 '{PROD_DB_NAME}_test'），且绝不将 DB_NAME_TEST 设为生产库。"
    )

os.environ["DB_NAME"] = _test_db
os.environ["ALLOW_NICKNAME_LOGIN"] = "true"
os.environ.pop("ADMIN_INIT_PASSWORD", None)  # 走默认 Admin@123

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

# 复用 app.config 已算好的连接串，仅把库名替换为“服务节点”以便建库
from app import config as _cfg  # noqa: E402

_server_url = _cfg.DATABASE_URL.split("?", 1)[0].rsplit("/", 1)[0] + "/"
_engine_srv = create_engine(_server_url, pool_pre_ping=True)
# 尝试自动建库：本地 MySQL 账号通常有权限；SQLPub 等托管账号无权限时仅警告，
# 不会因此中断——真正的可用性由下方 client fixture 在 setup 阶段探测并干净跳过。
try:
    with _engine_srv.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{_test_db}` CHARACTER SET utf8mb4"))
    print(f"[conftest] 已确保测试库存在: {_test_db}")
except Exception as e:
    print(
        f"[conftest] 警告：无法自动建库 {_test_db}（需 CREATE 权限或库已存在）：{e}\n"
        f"          → 若测试库已由 DBA/面板预先创建并授权可忽略；否则请创建独立测试库"
        f" '{_test_db}' 并授予当前账号 ALL 权限，再运行 pytest。"
    )

from fastapi.testclient import TestClient  # noqa: E402


class AuthClient:
    """测试用客户端：自动为所有业务请求注入一个「与该请求 user_id 绑定」的 Bearer token。

    业务接口现已统一要求登录 + 严格账号绑定（require_self：登录 token 对应的账号
    必须与请求中的 user_id 一致，否则 403）。集成测试多数直接用任意 user_id 当业务主键，
    因此这里按「请求里出现的 user_id」临时签发匹配的 token，保证既有测试行为与鉴权前一致。

    管理员接口调用时显式传 headers 即可覆盖（管理员鉴权走 _require_admin，不受影响）。
    若需测试严格绑定的拒绝路径，可显式传入 mismatched 的 headers（见 test_auth_user 相关用例）。
    """

    def __init__(self, client, db, user_model, token_ttl_hours):
        self._c = client
        self._db = db
        self._User = user_model
        self._ttl = token_ttl_hours

    def _mint_token(self, user_id: str) -> str:
        """为该 user_id 签发/复用登录 token（落库，使 require_self 校验通过）。"""
        import secrets
        from datetime import datetime, timedelta
        u = self._db.query(self._User).filter(
            self._User.user_id == user_id).first()
        if not u:
            u = self._User(user_id=user_id, nickname=user_id,
                           grade=6, subject="英语")
            self._db.add(u)
        u.token = secrets.token_urlsafe(32)
        u.token_expires_at = datetime.now() + timedelta(hours=self._ttl)
        self._db.commit()
        return u.token

    @staticmethod
    def _extract_user_id(args, kwargs) -> str:
        """从请求参数中找 user_id：优先 JSON body，其次 query/params，再次 f-string URL。"""
        # 1) JSON body
        json_body = kwargs.get("json")
        if isinstance(json_body, dict) and json_body.get("user_id"):
            return str(json_body["user_id"])
        # 2) query / params
        params = kwargs.get("params") or kwargs.get("data")
        if isinstance(params, dict) and params.get("user_id"):
            return str(params["user_id"])
        # 3) URL 内联 ?user_id=（含 f-string 已展开）
        for a in args:
            if isinstance(a, str) and "user_id=" in a:
                seg = a.split("user_id=", 1)[1]
                val = seg.split("&", 1)[0]
                if val:
                    return val
        return ""

    def _merge(self, args, kwargs):
        # 显式携带 Authorization（如管理员 token）时不覆盖；
        # 否则注入与请求 user_id 绑定的业务 token，使「仅传额外头（如 X-Parent-Pwd）」
        # 的家长写接口请求仍带登录态（require_self 通过），而非落到 401。
        headers = dict(kwargs.get("headers") or {})
        if "Authorization" not in headers:
            # 提取请求中的 user_id（业务接口主键）；缺省回退到 test_auth_uid，
            # 使「不带 user_id 的业务请求」也能通过 require_self（无 user_id 可比对）。
            uid = self._extract_user_id(args, kwargs) or "test_auth_uid"
            token = self._mint_token(uid)
            headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        return kwargs

    def get(self, *a, **k):
        return self._c.get(*a, **self._merge(a, k))

    def post(self, *a, **k):
        return self._c.post(*a, **self._merge(a, k))

    def put(self, *a, **k):
        return self._c.put(*a, **self._merge(a, k))

    def delete(self, *a, **k):
        return self._c.delete(*a, **self._merge(a, k))

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
    from app.main import app
    from sqlalchemy.exc import OperationalError, DatabaseError
    import secrets
    from datetime import datetime, timedelta
    # 进入前 drop_all 重建测试库；若测试库不可用（无写权限/不存在），干净跳过而非报错。
    # （SQLPub 等托管代理在连接不存在的库时可能自动建空库但无授权，会在此被捕获为跳过。）
    try:
        Base.metadata.drop_all(bind=engine)
        # 写权限探测：SQLPub 等托管代理在连接不存在的库时可能自动建空库但无写授权，
        # drop_all（DDL）会“成功”，但真实写入会被拒绝；这里用临时表 INSERT 验证写能力，
        # 避免跑到用例里才 1044 报错（表现为用例失败，难以定位）。
        with engine.connect() as _pc:
            _pc.execute(text("CREATE TABLE IF NOT EXISTS `__pytest_wprobe` (`id` INT)"))
            _pc.execute(text("INSERT INTO `__pytest_wprobe` (`id`) VALUES (1)"))
            _pc.execute(text("DROP TABLE IF EXISTS `__pytest_wprobe`"))
        app_cm = TestClient(app)
        c = app_cm.__enter__()
    except (OperationalError, DatabaseError) as e:
        pytest.skip(
            f"测试库 '{_test_db}' 不可用（{e}）。\n"
            f"请确认已创建独立测试库 '{_test_db}' 并授予当前账号 ALL 权限，"
            f"或本地启动 MySQL 并在 .env 设置 DB_NAME_TEST 指向可用库，再运行 pytest。"
        )
    try:
        db = SessionLocal()
        u = db.query(User).filter(User.user_id == "test_auth_uid").first()
        if not u:
            u = User(user_id="test_auth_uid", nickname="test",
                     email="test_auth@test.com", auth_type="email",
                     email_verified=True, grade=6, subject="英语")
            db.add(u)
        u.token = secrets.token_urlsafe(32)
        u.token_expires_at = datetime.now() + timedelta(hours=USER_TOKEN_TTL_HOURS)
        db.commit()
        # 注：db 会话保持打开，供 AuthClient 在测试期间按需为新 user_id 签发绑定 token；
        # 测试会话结束后统一关闭。
        yield AuthClient(c, db, User, USER_TOKEN_TTL_HOURS)
    finally:
        db.close()
        app_cm.__exit__(None, None, None)


@pytest.fixture(autouse=True)
def no_ai_judge(monkeypatch):
    """全局禁用 AI 判题复核，避免测试触达外部 AI 服务"""
    import app.services.judge as judge
    monkeypatch.setattr(judge, "judge_wrong_items", lambda user_id, items: [])


@pytest.fixture()
def fake_mail(monkeypatch):
    """打桩邮件通道：捕获验证码明文（库内只存哈希，无法反查）"""
    import app.domains.identity.routers.auth as auth_mod
    sent = {}

    def _send(target, code, subject=""):
        sent["target"] = target
        sent["code"] = code
        return True

    monkeypatch.setattr(auth_mod, "send_email", _send)
    monkeypatch.setattr(auth_mod, "mail_configured", lambda: True)
    return sent
