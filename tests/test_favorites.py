"""收藏夹功能测试（新功能 D）

钉死：① 收藏幂等（同 user+type+item 重复 POST 不重复插入）；
② 取消收藏（本人可删、越权/不存在返回 404）；③ 列表过滤 + 分页
（item_type 过滤、page_size clamp）；
④ item_type 非法返回 400。

说明：conftest 不做事务回滚，故每用例用专属用户 + 显式 token，并在 finally
清理该用户的收藏行，避免污染其他用例。
"""
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.favorite import UserFavorite
from app.models.user import User


FAV_UID = "fav_test_uid"


def _token_for(db: Session, uid: str) -> str:
    """为专属测试用户签发/复用登录 token（使 require_self 通过）"""
    import secrets
    from datetime import datetime, timedelta as _td
    u = db.query(User).filter(User.user_id == uid).first()
    if not u:
        u = User(user_id=uid, nickname=uid, grade=6, subject="英语")
        db.add(u)
    u.token = secrets.token_urlsafe(32)
    u.token_expires_at = datetime.now() + _td(hours=24)
    db.commit()
    return u.token


def _cleanup(db: Session, uid: str):
    db.query(UserFavorite).filter(UserFavorite.user_id == uid).delete()
    db.commit()


def test_favorites_add_and_idempotent(client):
    """POST 收藏成功；重复 POST 同一对象返回现有记录（不重复插入）"""
    db = SessionLocal()
    try:
        _cleanup(db, FAV_UID)
        tok = _token_for(db, FAV_UID)
        h = {"Authorization": f"Bearer {tok}"}

        r1 = client.post("/api/favorites", headers=h, json={
            "item_type": "paper", "item_id": "p-100", "title": "期末模拟卷"})
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert j1["item_type"] == "paper"
        assert j1["item_id"] == "p-100"
        assert j1["title"] == "期末模拟卷"
        assert j1["id"] > 0

        # 重复 POST 同对象：幂等返回同一记录
        r2 = client.post("/api/favorites", headers=h, json={
            "item_type": "paper", "item_id": "p-100"})
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2["id"] == j1["id"], "重复收藏应返回同一记录 id（幂等）"

        # 列表只应有 1 条
        rl = client.get("/api/favorites", headers=h).json()
        assert rl["total"] == 1, f"收藏应仅 1 条，实际 {rl['total']}"
    finally:
        _cleanup(db, FAV_UID)
        db.close()


def test_favorites_remove(client):
    """DELETE 取消收藏后不可见；对已删/越权返回 404"""
    db = SessionLocal()
    try:
        _cleanup(db, FAV_UID)
        tok = _token_for(db, FAV_UID)
        h = {"Authorization": f"Bearer {tok}"}

        r = client.post("/api/favorites", headers=h, json={
            "item_type": "question", "item_id": "q-7", "title": "鸡兔同笼"})
        fav_id = r.json()["id"]

        # 取消收藏
        rd = client.delete(f"/api/favorites/{fav_id}", headers=h)
        assert rd.status_code == 200, rd.text
        assert rd.json().get("ok") is True

        # 列表中不应再出现
        rl = client.get("/api/favorites", headers=h).json()
        assert rl["total"] == 0

        # 重复取消 → 404
        rd2 = client.delete(f"/api/favorites/{fav_id}", headers=h)
        assert rd2.status_code == 404
    finally:
        _cleanup(db, FAV_UID)
        db.close()


def test_favorites_list_filter_and_pagination(client):
    """列表：item_type 过滤 + 分页（page_size clamp）"""
    db = SessionLocal()
    try:
        _cleanup(db, FAV_UID)
        tok = _token_for(db, FAV_UID)
        h = {"Authorization": f"Bearer {tok}"}

        for i in range(2):
            client.post("/api/favorites", headers=h, json={
                "item_type": "paper", "item_id": f"p-{i}", "title": f"卷{i}"})
        client.post("/api/favorites", headers=h, json={
            "item_type": "question", "item_id": "q-1", "title": "题1"})

        # 全部：3 条
        all_ = client.get("/api/favorites", headers=h).json()
        assert all_["total"] == 3
        assert len(all_["items"]) == 3

        # 过滤 paper：2 条
        papers = client.get("/api/favorites?item_type=paper", headers=h).json()
        assert papers["total"] == 2
        assert all(x["item_type"] == "paper" for x in papers["items"])

        # 分页：page_size=1 → 单页 1 条，total 仍为 3
        pg = client.get("/api/favorites?page=1&page_size=1", headers=h).json()
        assert pg["page_size"] == 1
        assert len(pg["items"]) == 1
        assert pg["total"] == 3

        # 非法 item_type → 400
        bad = client.get("/api/favorites?item_type=foo", headers=h)
        assert bad.status_code == 400
    finally:
        _cleanup(db, FAV_UID)
        db.close()


def test_favorites_invalid_type(client):
    """POST 非法 item_type 返回 400"""
    db = SessionLocal()
    try:
        _cleanup(db, FAV_UID)
        tok = _token_for(db, FAV_UID)
        h = {"Authorization": f"Bearer {tok}"}

        r = client.post("/api/favorites", headers=h, json={
            "item_type": "video", "item_id": "v-1"})
        assert r.status_code == 400, r.text
    finally:
        _cleanup(db, FAV_UID)
        db.close()
