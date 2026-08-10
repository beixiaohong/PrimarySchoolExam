"""每日任务：今日任务列表 + 配置读写守卫 + 自定义任务流转"""

UID = "任务测试生"
PARENT_PWD = "8888"


def _ensure_parent_pwd(client, uid=UID):
    r = client.get("/api/parent/status", params={"user_id": uid})
    if not r.json()["has_password"]:
        r = client.post("/api/parent/setup", json={
            "user_id": uid, "password": PARENT_PWD,
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


def test_optional_config_roundtrip(client):
    """可选任务：家长配置 → settings 回显 → 今日任务按配置生成"""
    uid = "可选任务配置生"
    _ensure_parent_pwd(client, uid)
    codes = ["math_fix", "chi_read"]

    # 保存可选任务列表 + 目标数
    r = client.post("/api/tasks/settings", json={
        "user_id": uid,
        "settings": {"optional": codes, "targets": {"math_fix": 5}},
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text
    assert r.json()["optional"] == codes

    # 重新读设置：回显仍在（重开配置弹窗可见）
    r = client.get("/api/tasks/settings", params={"user_id": uid})
    assert r.json()["optional"] == codes

    # 今日任务列表包含家长配置的可选任务
    r = client.get("/api/tasks/daily", params={"user_id": uid})
    opt_codes = {t["task_code"] for t in r.json()["tasks"] if not t["mandatory"]}
    assert set(codes) <= opt_codes

    # 非法 code 被拒
    r = client.post("/api/tasks/settings", json={
        "user_id": uid, "settings": {"optional": ["not_a_task"]},
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


def test_recitation_target_roundtrip(client):
    """背诵类强制任务的数量可保存回显，重开设置弹窗不重置"""
    uid = "背诵数量测试生"
    _ensure_parent_pwd(client, uid)
    r = client.post("/api/tasks/settings", json={
        "user_id": uid,
        "settings": {"targets": {"chi_classical": 4, "eng_vocab": 8}},
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200, r.text

    r = client.get("/api/tasks/settings", params={"user_id": uid})
    items = {i["code"]: i for i in r.json()["items"]}
    assert items["chi_classical"]["target"] == 4
    assert items["eng_vocab"]["target"] == 8


def test_optional_backfill_missing_rows(client):
    """可选任务：今日缺失的行按家长配置补齐（不是只在无行时生成）"""
    from datetime import date
    from app.database import SessionLocal
    from app.models.daily_task import DailyTask

    uid = "可选补齐测试生"
    _ensure_parent_pwd(client, uid)
    codes = ["math_fix", "chi_read", "chi_dictation"]
    r = client.post("/api/tasks/settings", json={
        "user_id": uid, "settings": {"optional": codes},
    }, headers={"X-Parent-Pwd": PARENT_PWD})
    assert r.status_code == 200
    client.get("/api/tasks/daily", params={"user_id": uid})  # 首次生成

    # 删掉一条未完成的可选行 → 下次 /daily 应补齐
    db = SessionLocal()
    try:
        row = db.query(DailyTask).filter(
            DailyTask.user_id == uid, DailyTask.task_date == date.today(),
            DailyTask.task_code == "chi_dictation").first()
        assert row
        db.delete(row)
        db.commit()
    finally:
        db.close()

    r = client.get("/api/tasks/daily", params={"user_id": uid})
    opt = {t["task_code"] for t in r.json()["tasks"] if not t["mandatory"]}
    assert set(codes) <= opt


def test_makeup_card_granted_once(client):
    """补签卡：每天只发 1 张，重复刷新不重复发放"""
    from datetime import date
    from app.database import SessionLocal
    from app.models.daily_task import DailyTask
    from app.routers.tasks import _build_payload, _get_makeup_balance

    uid = "补签卡防重测试生"
    client.get("/api/tasks/daily", params={"user_id": uid})  # 生成今日任务
    db = SessionLocal()
    try:
        base = _get_makeup_balance(db, uid)
        # 全部可选任务置为完成 → 触发发补签卡
        for row in db.query(DailyTask).filter(
                DailyTask.user_id == uid, DailyTask.task_date == date.today(),
                DailyTask.task_type == "optional").all():
            row.status = "done"
        db.commit()
        _build_payload(db, uid)
        _build_payload(db, uid)  # 重复调用（模拟登录后多次请求）
        assert _get_makeup_balance(db, uid) == base + 1
    finally:
        db.close()
