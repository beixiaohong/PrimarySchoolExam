"""严格账号绑定（require_self）越权防护回归

背景与易错点
------------
`require_self` 在「登录校验」之上再强制「请求中的 user_id == 当前登录账号」，
不一致直接 **403**（见 `app/domains/identity/routers/auth.py`）。
但绝大多数路由的鉴权**不在 router 文件内部**，而来自 `app/main.py` 的挂载处：

    user_auth_deps = [Depends(require_self)]
    app.include_router(focus.router, prefix="/api/focus", dependencies=user_auth_deps)

因此**只看 router 文件里的 `Depends(get_db)` 会误判为「无鉴权」**（本项目回归时真踩过这个误判）。
本文件用真实请求把这条不变量钉死：以后若有人误删挂载处的 `dependencies=user_auth_deps`，
或把 body/query 的 user_id 当成了可信输入，这里会立刻变红。

为什么挑 focus 覆盖：它的 `user_id` 直接来自请求体 / 查询串（而非 token），
是典型 IDOR（越权对象引用）暴露面，最能反映绑定是否真的生效。

注意：conftest 的 AuthClient 在**显式传 Authorization 时不会覆盖**，
所以这里能构造「A 的 token + B 的 user_id」这种越权请求。
"""
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.focus import FocusSession
from app.models.user import User

UID_A = "bind_test_uid_a"
UID_B = "bind_test_uid_b"


def _mint(uid: str) -> str:
    """为指定用户签发 token（落库，使登录校验通过）"""
    db: Session = SessionLocal()
    try:
        u = db.query(User).filter(User.user_id == uid).first()
        if not u:
            u = User(user_id=uid, nickname=uid, grade=6, subject="英语")
            db.add(u)
        u.token = secrets.token_urlsafe(32)
        u.token_expires_at = datetime.now() + timedelta(hours=24)
        db.commit()
        return u.token
    finally:
        db.close()


def _cleanup(uid: str):
    db: Session = SessionLocal()
    try:
        db.query(FocusSession).filter(FocusSession.user_id == uid).delete()
        db.commit()
    finally:
        db.close()


def test_write_api_rejects_other_user_id(client):
    """POST /api/focus/complete：带 A 的 token 却传 B 的 user_id，必须 403（不得代他人记专注）"""
    tok_a = _mint(UID_A)
    h = {"Authorization": f"Bearer {tok_a}"}

    r = client.post("/api/focus/complete", headers=h, json={"user_id": UID_B, "minutes": 10})
    assert r.status_code == 403, (
        f"越权写入未被拦截（期望 403，实际 {r.status_code}）：{r.text}")

    # 且确实没有落到 B 的账上（拦截要发生在写库之前）
    db: Session = SessionLocal()
    try:
        n = db.query(FocusSession).filter(FocusSession.user_id == UID_B).count()
    finally:
        db.close()
    assert n == 0, "越权请求被拒但已写入他人数据（鉴权应在写库前拦住）"


def test_read_api_rejects_other_user_id(client):
    """GET /api/focus/today：带 A 的 token 查 B 的数据，必须 403（不得读他人数据）"""
    tok_a = _mint(UID_A)
    h = {"Authorization": f"Bearer {tok_a}"}

    r = client.get(f"/api/focus/today?user_id={UID_B}", headers=h)
    assert r.status_code == 403, (
        f"越权读取未被拦截（期望 403，实际 {r.status_code}）：{r.text}")


def test_own_user_id_still_allowed(client):
    """带自己的 user_id 必须正常放行（确认 403 拦截没有误伤正常请求）"""
    tok_a = _mint(UID_A)
    h = {"Authorization": f"Bearer {tok_a}"}
    _cleanup(UID_A)

    r = client.post("/api/focus/complete", headers=h, json={"user_id": UID_A, "minutes": 10})
    assert r.status_code == 200, f"本人请求被误拦：{r.text}"

    r2 = client.get(f"/api/focus/today?user_id={UID_A}", headers=h)
    assert r2.status_code == 200, r2.text
    _cleanup(UID_A)


def test_unauthenticated_rejected(client):
    """不带 token 必须 401（挂载处的 user_auth_deps 生效）"""
    r = client.get(f"/api/focus/today?user_id={UID_A}", headers={"Authorization": ""})
    assert r.status_code == 401, (
        f"未登录未被拦截（期望 401，实际 {r.status_code}）：{r.text}")
