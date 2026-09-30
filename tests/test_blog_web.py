# -*- coding: utf-8 -*-
"""内容 / Blog 与工作台后端验收测试（对应 docs/Blog与Workspace设计方案.md）。

覆盖：
- AC-B1  文章生命周期：建草稿 → 不在公开列表 → 发布 → 公开可见 → 详情自增浏览量
         → 编辑 → 取消发布 → 删除
- AC-B2  归属边界：非作者改他人文章 403；草稿对他人不可见（404）
- AC-B3  分类/标签：后台 admin 才能增删改；前台只读；同名标签拒绝；分类有文章时禁删
- AC-B4  检索：关键词命中标题/正文；标签筛选；mine 只看自己
- AC-B5  工作台：模块访问记录累加 + 最新内容只返回已发布且不含正文

说明：
- 所有请求 URL 带 ?user_id=，使 conftest.AuthClient 按该 uid 签发绑定 token
  （/api/blog 与 /api/workspace 均挂 require_self）。
- 后台管理端点走 /api/admin（不挂 user_auth_deps），用 admin_headers 夹具。
"""
import pytest

from app.database import SessionLocal

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"


@pytest.fixture(scope="module")
def admin_headers(client):
    """后台管理员鉴权头 —— **本模块自备，不复用 conftest 的 session 级夹具**。

    原因（本项目铁律）：admin token 是「单槽」的，任何一次新登录都会让旧 token 失效。
    conftest 的 admin_headers 是 session 级（首次被请求时才登录），而本文件按字母序排在
    test_observability_compliance / test_push 之前——若这里先触发它，后面 test_novel 等文件的
    管理员登录会把它的 token 顶掉，导致那两个文件拿到 401（全量跑才暴露的假失败）。
    因此本文件自己登录一次，把 session 夹具的首次使用留给更靠后的文件。
    """
    r = client.post("/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _q(uid, extra=""):
    """拼接 user_id 查询参数（AuthClient 从中提取 uid 签发 token）。"""
    sep = "&" if extra else ""
    return f"?user_id={uid}{sep}{extra}"


def _mk_article(client, uid, title, **kw):
    body = {"title": title, "content_md": kw.pop("content_md", "正文"), "status": "draft"}
    body.update(kw)
    r = client.post(f"/api/blog/articles{_q(uid)}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _mk_category(admin_headers, client, name, sort_order=0):
    r = client.post("/api/admin/blog/categories", json={"name": name, "sort_order": sort_order},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _mk_tag(admin_headers, client, name):
    r = client.post("/api/admin/blog/tags", json={"name": name}, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_ac_b1_article_lifecycle(client):
    """AC-B1：草稿 → 发布 → 公开可见 → 详情自增浏览 → 编辑 → 取消发布 → 删除。"""
    uid = "blog_b1_uid"
    art = _mk_article(client, uid, "B1 生命周期", summary="摘要", content_md="正文内容")

    # 草稿不出现在公开列表，但出现在「我的」
    r = client.get(f"/api/blog/articles{_q(uid)}")
    assert r.status_code == 200, r.text
    assert art["id"] not in [a["id"] for a in r.json()["items"]]

    r = client.get(f"/api/blog/articles{_q(uid, 'mine=true')}")
    assert art["id"] in [a["id"] for a in r.json()["items"]]

    # 发布后公开可见，且 published_at 已落
    r = client.post(f"/api/blog/articles/{art['id']}/publish{_q(uid)}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"
    assert r.json()["published_at"]

    r = client.get(f"/api/blog/articles{_q(uid)}")
    assert art["id"] in [a["id"] for a in r.json()["items"]]

    # 详情自增浏览量（已发布才自增）
    r = client.get(f"/api/blog/articles/{art['id']}{_q(uid)}")
    assert r.status_code == 200, r.text
    assert r.json()["view_count"] >= 1

    # 编辑标题
    r = client.put(f"/api/blog/articles/{art['id']}{_q(uid)}", json={"title": "B1 已改名"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "B1 已改名"

    # 取消发布 → 从公开列表消失
    r = client.post(f"/api/blog/articles/{art['id']}/unpublish{_q(uid)}")
    assert r.status_code == 200, r.text
    r = client.get(f"/api/blog/articles{_q(uid)}")
    assert art["id"] not in [a["id"] for a in r.json()["items"]]

    # 删除
    r = client.delete(f"/api/blog/articles/{art['id']}{_q(uid)}")
    assert r.status_code == 200, r.text
    r = client.get(f"/api/blog/articles/{art['id']}{_q(uid)}")
    assert r.status_code == 404


def test_ac_b2_owner_boundary(client):
    """AC-B2：非作者不能改他人文章（403），也不能看他人草稿（404）。"""
    uid = "blog_b2_owner"
    other = "blog_b2_other"
    art = _mk_article(client, uid, "B2 我的草稿")

    # 他人看不到草稿（按不存在处理，避免泄露存在性）
    r = client.get(f"/api/blog/articles/{art['id']}{_q(other)}")
    assert r.status_code == 404, r.text

    # 他人改 → 403
    r = client.put(f"/api/blog/articles/{art['id']}{_q(other)}", json={"title": "被篡改"})
    assert r.status_code == 403, r.text

    # 他人删 → 403
    r = client.delete(f"/api/blog/articles/{art['id']}{_q(other)}")
    assert r.status_code == 403, r.text

    client.delete(f"/api/blog/articles/{art['id']}{_q(uid)}")


def test_ac_b3_taxonomy_admin_only(client, admin_headers):
    """AC-B3：分类/标签写操作仅管理员；前台只读；同名标签拒绝；分类有文章时禁删。"""
    # 无管理员 token → 401
    r = client.post("/api/admin/blog/categories", json={"name": "未授权分类"})
    assert r.status_code == 401, r.text

    cat = _mk_category(admin_headers, client, "B3 分类", sort_order=5)
    r = client.put(f"/api/admin/blog/categories/{cat['id']}", json={"sort_order": 1},
                   headers=admin_headers)
    assert r.status_code == 200 and r.json()["sort_order"] == 1

    # 前台可读（普通用户 token）
    r = client.get(f"/api/blog/categories{_q('blog_b3_uid')}")
    assert r.status_code == 200, r.text
    assert any(c["id"] == cat["id"] for c in r.json())

    tag = _mk_tag(admin_headers, client, "B3 标签")
    # 同名标签拒绝
    r = client.post("/api/admin/blog/tags", json={"name": "B3 标签"}, headers=admin_headers)
    assert r.status_code == 400, r.text

    # 分类被文章引用时禁删
    art = _mk_article(client, "blog_b3_uid", "B3 文章", category_id=cat["id"])
    r = client.delete(f"/api/admin/blog/categories/{cat['id']}", headers=admin_headers)
    assert r.status_code == 400, r.text

    # 清理后可删
    client.delete(f"/api/admin/blog/articles/{art['id']}", headers=admin_headers)
    r = client.delete(f"/api/admin/blog/categories/{cat['id']}", headers=admin_headers)
    assert r.status_code == 200, r.text
    r = client.delete(f"/api/admin/blog/tags/{tag['id']}", headers=admin_headers)
    assert r.status_code == 200, r.text


def test_ac_b4_search_and_tag_filter(client, admin_headers):
    """AC-B4：关键词命中标题/正文；标签筛选；mine 只看自己。"""
    uid = "blog_b4_uid"
    tag = _mk_tag(admin_headers, client, "B4 标签")
    a1 = _mk_article(client, uid, "B4 苹果派做法", content_md="烤箱预热",
                     tag_ids=[tag["id"]], status="published")
    a2 = _mk_article(client, uid, "B4 香蕉面包", content_md="不含苹果", status="published")

    # 关键词命中标题
    r = client.get(f"/api/blog/articles{_q(uid, 'keyword=苹果派')}")
    ids = [a["id"] for a in r.json()["items"]]
    assert a1["id"] in ids and a2["id"] not in ids

    # 关键词命中正文
    r = client.get(f"/api/blog/articles{_q(uid, 'keyword=烤箱')}")
    ids = [a["id"] for a in r.json()["items"]]
    assert a1["id"] in ids and a2["id"] not in ids

    # 标签筛选
    r = client.get(f"/api/blog/articles{_q(uid, 'tag_id=' + str(tag['id']))}")
    ids = [a["id"] for a in r.json()["items"]]
    assert a1["id"] in ids and a2["id"] not in ids

    # mine 只看自己：换一个 uid 查 mine 应不含这两篇
    r = client.get(f"/api/blog/articles{_q('blog_b4_other', 'mine=true')}")
    assert a1["id"] not in [a["id"] for a in r.json()["items"]]

    # 文章详情带回标签
    r = client.get(f"/api/blog/articles/{a1['id']}{_q(uid)}")
    assert any(t["id"] == tag["id"] for t in r.json()["tags"])

    for aid in (a1["id"], a2["id"]):
        client.delete(f"/api/blog/articles/{aid}{_q(uid)}")
    client.delete(f"/api/admin/blog/tags/{tag['id']}", headers=admin_headers)


def test_ac_b5_workspace_usage_and_latest(client):
    """AC-B5：模块访问记录累加；最新内容只返回已发布且不带正文。"""
    uid = "blog_b5_uid"
    art = _mk_article(client, uid, "B5 已发布", content_md="很长很长的内容", status="published")
    _mk_article(client, uid, "B5 草稿", status="draft")

    # 记录两次访问 → 次数累加
    r = client.post(f"/api/workspace/usage{_q(uid)}", json={"app_key": "ledger"})
    assert r.status_code == 200 and r.json()["visit_count"] == 1
    r = client.post(f"/api/workspace/usage{_q(uid)}", json={"app_key": "ledger"})
    assert r.json()["visit_count"] == 2

    r = client.get(f"/api/workspace/usage{_q(uid)}")
    assert r.status_code == 200, r.text
    rows = {x["app_key"]: x for x in r.json()}
    assert rows["ledger"]["visit_count"] == 2

    # 最新内容：只含已发布，且不含 content_md 字段
    r = client.get(f"/api/workspace/latest{_q(uid, 'limit=10')}")
    assert r.status_code == 200, r.text
    items = r.json()
    assert any(i["id"] == art["id"] for i in items)
    assert all(i["title"] != "B5 草稿" for i in items)
    assert "content_md" not in items[0]

    client.delete(f"/api/blog/articles/{art['id']}{_q(uid)}")


def test_blog_tables_created():
    """迁移 089 建表校验：五张新表均存在（防止只建部分表就上线）。"""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name LIKE 'db_blog%' "
            "OR table_schema = DATABASE() AND table_name = 'db_workspace_app_usage'"
        )).all()
        names = {r[0] for r in rows}
        for t in ("db_blog_articles", "db_blog_categories", "db_blog_tags",
                  "db_blog_article_tags", "db_workspace_app_usage"):
            assert t in names, f"缺表 {t}，实际 {sorted(names)}"
    finally:
        db.close()
