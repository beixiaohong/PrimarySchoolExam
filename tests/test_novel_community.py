"""小说站社区功能测试：书签 + 评论 + 阅读榜单

复用 test_novel.py 的上传流程构造小说，验证：
1. 书签：登录后增/查/删；同章再标=更新便签（唯一约束）
2. 评论：登录发布 / 列表 / 仅本人删除；空内容 400；敏感词命中 400
3. 阅读榜单：热门榜按 view_count 降序、公开可查
"""
import io

import pytest

from app.database import SessionLocal
from app.models.im import SensitiveWord
from app.models.novel import Novel

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"

_PARAS = ("这是用于测试的正文内容，描述主角在修炼过程中的所见所闻，"
          "包含环境描写与心理活动，长度足以撑起平均字数判定。") * 3


def _chaptered_txt() -> bytes:
    return f"""测试小说
作者：测试君

第一章 初入江湖
{_PARAS}

第二章 拜师学艺
{_PARAS}
""".encode("utf-8")


@pytest.fixture(scope="module")
def admin_headers(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _upload(client, headers, raw: bytes, title: str, **extra):
    data = {"title": title, "author": "测试君", "category": "测试分类", "enabled": "true"}
    data.update(extra)
    return client.post(
        "/api/admin/novel/upload",
        files={"file": (f"{title}.txt", io.BytesIO(raw), "text/plain")},
        data=data, headers=headers,
    )


def _new_novel(client, admin_headers, title="社区测试小说"):
    r = _upload(client, admin_headers, _chaptered_txt(), title)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ───────────────── 1. 书签 ─────────────────
def test_bookmark_crud(client, admin_headers):
    """登录后增/查/删；同章再标=覆盖便签（返回同一 id）"""
    nid = _new_novel(client, admin_headers, "书签测试小说")
    uid = "bk_user"
    try:
        # 增
        r = client.post(f"/api/novel/{nid}/bookmarks?user_id={uid}",
                        json={"chapter_idx": 2, "note": "此处伏笔"})
        assert r.status_code == 200, r.text
        bid = r.json()["id"]
        # 查
        r = client.get(f"/api/novel/{nid}/bookmarks?user_id={uid}")
        assert r.status_code == 200, r.text
        items = r.json()
        assert any(b["id"] == bid and b["chapter_idx"] == 2 for b in items)
        # 同章再标 → 更新便签（唯一约束，不新增）
        r = client.post(f"/api/novel/{nid}/bookmarks?user_id={uid}",
                        json={"chapter_idx": 2, "note": "改：重要转折"})
        assert r.status_code == 200, r.text
        assert r.json()["id"] == bid
        r = client.get(f"/api/novel/{nid}/bookmarks?user_id={uid}")
        same = [b for b in r.json() if b["id"] == bid][0]
        assert same["note"] == "改：重要转折"
        # 删
        r = client.delete(f"/api/novel/{nid}/bookmarks/{bid}?user_id={uid}")
        assert r.status_code == 200, r.text
        r = client.get(f"/api/novel/{nid}/bookmarks?user_id={uid}")
        assert not any(b["id"] == bid for b in r.json())
    finally:
        client.delete(f"/api/admin/novel/{nid}", headers=admin_headers)


def test_bookmark_requires_login(client, admin_headers):
    """未登录增书签 → 401"""
    nid = _new_novel(client, admin_headers, "书签登录测试")
    try:
        raw = client._c
        assert raw.post(f"/api/novel/{nid}/bookmarks",
                        json={"chapter_idx": 1}).status_code == 401
    finally:
        client.delete(f"/api/admin/novel/{nid}", headers=admin_headers)


# ───────────────── 2. 评论 ─────────────────
def test_comment_crud_and_security(client, admin_headers):
    """发布/列表/仅本人删除；空内容 400；敏感词命中 400"""
    nid = _new_novel(client, admin_headers, "评论测试小说")
    uid = "cm_user"
    db = SessionLocal()
    try:
        # 正常发布
        r = client.post(f"/api/novel/{nid}/comments?user_id={uid}",
                        json={"content": "这章写得很精彩", "chapter_idx": 1})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        # 列表公开可读
        r = client.get(f"/api/novel/{nid}/comments")
        assert r.status_code == 200, r.text
        assert any(c["id"] == cid for c in r.json()["items"])
        # 空内容 → 400
        r = client.post(f"/api/novel/{nid}/comments?user_id={uid}", json={"content": "   "})
        assert r.status_code == 400, r.text
        # 敏感词命中 → 400（临时插词，仅本测试）
        db.add(SensitiveWord(word="测试违禁词xyz", is_active=True))
        db.commit()
        r = client.post(f"/api/novel/{nid}/comments?user_id={uid}",
                        json={"content": "包含测试违禁词xyz的内容"})
        assert r.status_code == 400, r.text
        # 仅本人可删（用另一个账号删 → 403）
        other = "cm_other"
        client.post(f"/api/novel/{nid}/comments?user_id={other}",
                    json={"content": "路人评论"})
        r = client.delete(f"/api/novel/{nid}/comments/{cid}?user_id={other}")
        assert r.status_code == 403, r.text
        # 本人删 → 200，软删后列表消失
        r = client.delete(f"/api/novel/{nid}/comments/{cid}?user_id={uid}")
        assert r.status_code == 200, r.text
        r = client.get(f"/api/novel/{nid}/comments")
        assert not any(c["id"] == cid for c in r.json()["items"])
    finally:
        db.close()
        client.delete(f"/api/admin/novel/{nid}", headers=admin_headers)


# ───────────────── 3. 阅读榜单 ─────────────────
def test_reading_rank_public(client, admin_headers):
    """热门榜按 view_count 降序、公开可查；上榜小说含目标 id"""
    nid = _new_novel(client, admin_headers, "榜单测试小说")
    db = SessionLocal()
    try:
        # 拉高人气（detail 接口累加 view_count），并直接置高位确保进 top
        for _ in range(3):
            client.get(f"/api/novel/{nid}")
        nov = db.query(Novel).filter(Novel.id == nid).first()
        nov.view_count = 99999
        db.commit()
        # 公开（裸客户端，无 token）可查
        r = client._c.get("/api/novel/rank?top=10")
        assert r.status_code == 200, r.text
        items = r.json()
        assert items and items[0]["id"] == nid, \
            f"榜单首条应为人气最高小说 {nid}，实际：{items[:3] if items else '空'}"
    finally:
        db.close()
        client.delete(f"/api/admin/novel/{nid}", headers=admin_headers)
