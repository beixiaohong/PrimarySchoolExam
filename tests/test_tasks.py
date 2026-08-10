"""每日任务：今日任务列表 + 配置读写守卫 + 自定义任务流转"""

UID = "任务测试生"
PARENT_PWD = "8888"


def _ensure_parent_pwd(client):
    r = client.get("/api/parent/status", params={"user_id": UID})
    if not r.json()["has_password"]:
        r = client.post("/api/parent/setup", json={
            "user_id": UID, "password": PARENT_PWD,
            "hint_question": "测试密保？", "hint_answer": "测试答案",
        })
        assert r.status_code == 200


def test_daily_tasks_list(client):
    """今日任务：强制+可选双轨结构"""
    r = client.get("/api/tasks/daily", params={"user_id": UID})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["date"]
    assert isinstance(body["tasks"], list)
    assert len(body["tasks"]) >= 3  # 至少 3 条强制任务
    codes = {t["task_code"] for t in body["tasks"]}
    assert all(t["status"] in ("pending", "done") for t in body["tasks"])
    assert any(t["mandatory"] for t in body["tasks"])
    assert any(not t["mandatory"] for t in body["tasks"])


def test_task_settings_guard(client):
    """任务配置：读自由，写需家长密码"""
    r = client.get("/api/tasks/settings", params={"user_id": UID})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list) and body["items"]
    code = body["items"][0]["code"]
    new_target = min(body["items"][0]["default"] + 1, 50)

    # 未带家长密码 → 403
    r = client.post("/api/tasks/settings", json={
        "user_id": UID, "settings": {"targets": {code: new_target}},
    })
    assert r.status_code == 403

    # 带正确家长密码 → 写入成功
    _ensure_parent_pwd(client)
    r = client.post("/api/tasks/settings", json={
        "user_id": UID, "settings": {"targets": {code: new_target}},
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text

    # 读回确认目标已生效
    r = client.get("/api/tasks/settings", params={"user_id": UID})
    item = next(i for i in r.json()["items"] if i["code"] == code)
    assert item["target"] == new_target


def test_settings_unconfigurable_codes_ignored(client):
    """背诵类（chi_classical/eng_vocab）被连带提交时静默忽略，不得报「不支持的任务类型」"""
    _ensure_parent_pwd(client)
    r = client.post("/api/tasks/settings", json={
        "user_id": UID,
        "settings": {
            # 模拟前端弹窗整体提交：targets/enabled 含背诵类，mandatory 带默认强制任务
            "targets": {"chi_classical": 1, "eng_vocab": 5, "math_exam": 2},
            "enabled": {"chi_classical": True, "eng_vocab": True, "math_exam": True},
            "mandatory": {"数学": "math_exam", "语文": "chi_classical", "英语": "eng_vocab"},
        },
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text

    # 真正非法的 code 仍然报错
    r = client.post("/api/tasks/settings", json={
        "user_id": UID, "settings": {"targets": {"not_a_task": 1}},
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 400


def test_custom_task_flow(client):
    """自定义任务：孩子创建 → pending → 家长确认"""
    r = client.post("/api/tasks/custom",
                    json={"user_id": UID, "title": "额外练一页口算",
                          "subject": "数学"})
    assert r.status_code == 200, r.text

    r = client.get("/api/tasks/custom",
                   params={"user_id": UID, "status": "pending"})
    assert r.status_code == 200
    items = r.json()
    assert any(t["title"] == "额外练一页口算" for t in items)
    task_id = next(t["id"] for t in items if t["title"] == "额外练一页口算")

    r = client.post("/api/tasks/custom/confirm", json={"task_id": task_id})
    assert r.status_code == 200

    # 重复确认被拒
    r = client.post("/api/tasks/custom/confirm", json={"task_id": task_id})
    assert r.status_code == 400
