# -*- coding: utf-8 -*-
"""网课模块回归测试（app/routers/courses.py）

覆盖：家长添加网课 → 用户端列表可见 → 家长删除 → 列表移除。
"""
from app.database import SessionLocal
from app.models.online_course import OnlineCourse


def test_courses_parent_add_list_delete(client):
    uid = "网课测试生"
    r = client.post("/api/courses/parent", json={
        "user_id": uid, "title": "网课测试课", "video_url": "https://example.com/v.mp4",
        "subject": "数学", "grade": 6, "description": "测试",
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    try:
        # 用户端列表（家长配置 + 系统合并）
        r2 = client.get(f"/api/courses?user_id={uid}&grade=6")
        assert r2.status_code == 200, r2.text
        titles = [c["title"] for c in r2.json()["courses"]]
        assert "网课测试课" in titles, "家长添加的网课应在用户端列表可见"
        found = next(c for c in r2.json()["courses"] if c["title"] == "网课测试课")
        assert found["source"] == "parent"
        assert found["video_url"].startswith("https://")

        # 学科筛选：数学可见
        r3 = client.get(f"/api/courses?user_id={uid}&grade=6&subject=数学")
        assert any(c["title"] == "网课测试课" for c in r3.json()["courses"])

        # 家长管理列表
        r4 = client.get(f"/api/courses/parent?user_id={uid}")
        assert any(c["id"] == cid for c in r4.json()["courses"])

        # 删除
        r5 = client.delete(f"/api/courses/parent/{cid}?user_id={uid}")
        assert r5.status_code == 200, r5.text
        r6 = client.get(f"/api/courses?user_id={uid}&grade=6")
        assert all(c["title"] != "网课测试课" for c in r6.json()["courses"]), "删除后不应再出现"
    finally:
        db = SessionLocal()
        db.query(OnlineCourse).filter(OnlineCourse.parent_uid == uid).delete()
        db.commit()
        db.close()
