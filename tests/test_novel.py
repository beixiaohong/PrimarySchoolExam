"""小说站模块测试

覆盖三块：
1. TXT 分章算法（纯函数，不依赖 DB）：能分章 / 不能分章走流式分块 / GBK 编码识别；
2. 后台上传导入 → 读者端可查（端到端，含 multipart 上传）；
3. 阅读加载契约：目录分页、/read 下滑增量（next 指针推进到底）、游客可读、
   进度与书架必须登录。
"""
import io

import pytest

from app.domains.content.services.novel_splitter import parse_txt, split_stream

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"

_PARA = ("这是一段用于测试的正文内容，描述主角在修炼过程中的所见所闻，"
         "包含环境描写与心理活动，长度足以撑起平均字数判定。") * 3


def _chaptered_txt() -> bytes:
    """标准分章 TXT（UTF-8）"""
    return f"""测试小说
作者：测试君

第一章 初入江湖
{_PARA}

第二章 拜师学艺
{_PARA}
{_PARA}

第三章 小有所成
{_PARA}

第四章 名动一方
{_PARA}
""".encode("utf-8")


def _plain_txt() -> bytes:
    """无章节标记的 TXT（应走流式分块）"""
    return "\n\n".join(
        f"这是没有章节标记的普通正文段落第{i}段，内容足够长以触发按块切片的逻辑分支。"
        for i in range(80)
    ).encode("utf-8")


# ───────────────── 1. 分章算法 ─────────────────
def test_splitter_chapter_mode():
    """能识别「第X章」→ chapter 模式，章节数/标题正确，前言并入首章"""
    r = parse_txt(_chaptered_txt())
    assert r["mode"] == "chapter", r
    assert len(r["chapters"]) == 4, [c[0] for c in r["chapters"]]
    titles = [t for t, _ in r["chapters"]]
    assert titles[0].startswith("第一章")
    assert "初入江湖" in titles[0]
    # 第一个标题之前的「测试小说 / 作者」前缀不能丢（并入第一章开头）
    assert "测试小说" in r["chapters"][0][1]
    assert r["word_count"] > 0


def test_splitter_stream_mode():
    """无章节标记 → stream 模式，切成多块且总字数不丢"""
    raw = _plain_txt()
    r = parse_txt(raw)
    assert r["mode"] == "stream", r
    assert len(r["chapters"]) >= 2
    # 所有块内容拼接后应覆盖原文段落（允许空白规范化差异）
    joined = "".join(c for _, c in r["chapters"])
    assert "第0段" in joined and "第79段" in joined
    # 块大小受控（不超过硬上限）
    assert all(len(c) <= 4000 * 2 for _, c in r["chapters"])


def test_splitter_gbk_encoding():
    """GBK 编码 TXT 能被正确识别并解析（中文占比探测）"""
    r = parse_txt(_chaptered_txt().decode("utf-8").encode("gbk"))
    assert r["encoding"] == "gbk", r["encoding"]
    assert r["mode"] == "chapter"
    assert "初入江湖" in r["chapters"][0][0]


def test_split_stream_respects_chunk_size():
    """流式分块：单块不超过目标大小（超长段落除外）"""
    text = "\n\n".join(["短段落内容ABC" * 5 for _ in range(200)])
    blocks = split_stream(text, chunk_size=800)
    assert len(blocks) >= 2
    assert all(len(b) <= 800 * 2 for _, b in blocks)


# ───────────────── 2~3. 端到端 ─────────────────
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
        data=data,
        headers=headers,
    )


def test_novel_upload_and_read_flow(client, admin_headers):
    """后台上传分章 TXT → 读者端列表/详情/目录/read 下滑加载全链路"""
    # 1) 上传导入
    r = _upload(client, admin_headers, _chaptered_txt(), "链路测试小说")
    assert r.status_code == 200, r.text
    imported = r.json()
    assert imported["mode"] == "chapter"
    assert imported["chapter_count"] == 4
    novel_id = imported["id"]

    try:
        # 2) 书城列表能查到
        r = client.get("/api/novel/list", params={"keyword": "链路测试小说"})
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert any(i["id"] == novel_id for i in items)

        # 3) 详情（含人气累加）
        r = client.get(f"/api/novel/{novel_id}")
        assert r.status_code == 200, r.text
        assert r.json()["chapter_mode"] == "chapter"
        assert r.json()["chapter_count"] == 4

        # 4) 目录分页（只给元信息，不该带 content）
        r = client.get(f"/api/novel/{novel_id}/chapters", params={"limit": 2})
        assert r.status_code == 200, r.text
        cat = r.json()
        assert cat["total"] == 4 and len(cat["items"]) == 2
        assert cat["has_more"] is True
        assert "content" not in cat["items"][0]

        # 5) 下滑增量加载：逐段推进 next 直到读完
        seen, cursor, guard = [], 1, 0
        while cursor and guard < 20:
            rr = client.get(f"/api/novel/{novel_id}/read",
                            params={"from": cursor, "limit": 1})
            assert rr.status_code == 200, rr.text
            body = rr.json()
            assert len(body["items"]) == 1
            seen.append(body["items"][0])
            cursor = body["next"]
            guard += 1
        assert len(seen) == 4, "应恰好分 4 段读完"
        assert [s["idx"] for s in seen] == [1, 2, 3, 4]
        assert seen[0]["title"].startswith("第一章")
        assert seen[0]["content"]

        # 6) 读完之后 next 为 None（前端据此显示「全文完」）
        r = client.get(f"/api/novel/{novel_id}/read", params={"from": 4, "limit": 1})
        assert r.json()["next"] is None
    finally:
        client.delete(f"/api/admin/novel/{novel_id}", headers=admin_headers)


def test_novel_stream_mode_import_and_read(client, admin_headers):
    """无章节 TXT → stream 模式入库，read 仍可按块顺序读完（title 为空）"""
    r = _upload(client, admin_headers, _plain_txt(), "流式测试小说")
    assert r.status_code == 200, r.text
    imported = r.json()
    assert imported["mode"] == "stream"
    novel_id = imported["id"]

    try:
        r = client.get(f"/api/novel/{novel_id}/read", params={"from": 1, "limit": 1})
        assert r.status_code == 200, r.text
        seg = r.json()["items"][0]
        assert seg["title"] == "", "流式模式不渲染章节标题"
        assert seg["content"]
        assert r.json()["has_more"] is True
    finally:
        client.delete(f"/api/admin/novel/{novel_id}", headers=admin_headers)


def test_novel_visitor_reads_but_progress_needs_login(client, admin_headers):
    """游客可读（200）；进度与书架必须登录（401）"""
    r = _upload(client, admin_headers, _chaptered_txt(), "游客测试小说")
    assert r.status_code == 200, r.text
    novel_id = r.json()["id"]

    try:
        # 游客（绕开 AuthClient 的自动 token 注入，直接用裸 TestClient）
        raw = client._c
        assert raw.get("/api/novel/list").status_code == 200
        assert raw.get(f"/api/novel/{novel_id}").status_code == 200
        assert raw.get(f"/api/novel/{novel_id}/read",
                       params={"from": 1, "limit": 1}).status_code == 200
        # 未登录写进度 / 加书架 → 401
        assert raw.post(f"/api/novel/{novel_id}/progress",
                        json={"chapter_idx": 2}).status_code == 401
        assert raw.post(f"/api/novel/{novel_id}/shelf",
                        json={"in_shelf": True}).status_code == 401

        # 登录后可写并回查书架
        uid = "novel_reader_uid"
        r = client.post(f"/api/novel/{novel_id}/progress?user_id={uid}",
                        json={"chapter_idx": 3})
        assert r.status_code == 200, r.text
        r = client.post(f"/api/novel/{novel_id}/shelf?user_id={uid}",
                        json={"in_shelf": True})
        assert r.status_code == 200, r.text
        r = client.get(f"/api/novel/shelf?user_id={uid}")
        assert r.status_code == 200, r.text
        assert any(b["id"] == novel_id for b in r.json())
        # 详情回显进度
        r = client.get(f"/api/novel/{novel_id}?user_id={uid}")
        assert r.json()["chapter_idx"] == 3
        assert r.json()["in_shelf"] is True
    finally:
        client.delete(f"/api/admin/novel/{novel_id}", headers=admin_headers)


def test_novel_upload_rejects_non_txt(client, admin_headers):
    """非 txt 文件应被拒绝"""
    r = client.post(
        "/api/admin/novel/upload",
        files={"file": ("bad.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        data={"title": "非法文件"},
        headers=admin_headers,
    )
    assert r.status_code == 400, r.text
