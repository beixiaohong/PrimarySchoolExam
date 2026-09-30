# -*- coding: utf-8 -*-
"""账本(ledger) API 集成测试 —— Tier 2 上帝文件拆分前的回归安全网。

覆盖核心业务路径，重点锁定 `_adjust_balance`（余额变更核心逻辑，Tier 2 将被抽到
app/domains/frozen/services/ledger_calc.py）。拆分前后行为必须完全一致，本文件即回归闸门。

鉴权：沿用 AuthClient —— 请求里的 user_id 自动 mint 绑定 token，ledger 端点的
`require_user` + `user_id == current_user.user_id` 校验因此通过。

跑法：
    DB_NAME=schoolexam_test pytest tests/test_ledger_api.py -v
"""
import pytest

from datetime import datetime as _dt

from app.models.ledger import Account, Bill, Category
from app.domains.frozen.services.ledger_calc import _advance_next_run


def _q(uid, extra=""):
    sep = "&" if extra else ""
    return f"?user_id={uid}{sep}{extra}"


def _make_account(client, uid, balance=0.0, name="测试账户"):
    r = client.post(
        f"/api/ledger/users/{uid}/accounts/" + _q(uid),
        json={"account_name": name, "account_type": "savings_card", "balance": balance},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _make_category(client, uid, ctype="EXPENSE", level1="测试分类"):
    r = client.post(
        f"/api/ledger/users/{uid}/categories/" + _q(uid),
        json={"category_type": ctype, "level1": level1},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _make_transaction(client, uid, ttype, amount, from_account_id, category_id,
                      to_account_id=None):
    body = {
        "transaction_type": ttype,
        "amount": amount,
        "from_account_id": from_account_id,
        "category_id": category_id,
    }
    if to_account_id is not None:
        body["to_account_id"] = to_account_id
    r = client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _balance_of(client, uid, account_id):
    r = client.get(f"/api/ledger/users/{uid}/accounts/" + _q(uid))
    assert r.status_code == 200, r.text
    for a in r.json():
        if a["id"] == account_id:
            return float(a["balance"])
    raise AssertionError(f"账户 {account_id} 不在列表: {r.json()}")


# ──────────────── 账户 CRUD ────────────────

def test_create_account_and_list(client):
    uid = "ledger_acc_uid"
    acc = _make_account(client, uid, balance=500)
    assert acc["balance"] == 500.0
    assert acc["account_name"] == "测试账户"

    r = client.get(f"/api/ledger/users/{uid}/accounts/" + _q(uid))
    assert r.status_code == 200, r.text
    ids = [a["id"] for a in r.json()]
    assert acc["id"] in ids


# ──────────────── 余额变更（锁定 _adjust_balance） ────────────────

def test_expense_reduces_balance(client):
    uid = "ledger_exp_uid"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    _make_transaction(client, uid, "expense", 100, acc["id"], cat["id"])
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(-100.0)


def test_income_increases_balance(client):
    uid = "ledger_inc_uid"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "INCOME")
    _make_transaction(client, uid, "income", 250, acc["id"], cat["id"])
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(250.0)


def test_transfer_moves_balance(client):
    uid = "ledger_xfer_uid"
    src = _make_account(client, uid, balance=1000, name="源账户")
    dst = _make_account(client, uid, balance=0, name="目标账户")
    cat = _make_category(client, uid, "EXPENSE")
    _make_transaction(client, uid, "transfer", 300, src["id"], cat["id"],
                      to_account_id=dst["id"])
    assert _balance_of(client, uid, src["id"]) == pytest.approx(700.0)
    assert _balance_of(client, uid, dst["id"]) == pytest.approx(300.0)


def test_transaction_requires_existing_category(client):
    uid = "ledger_cat_uid"
    acc = _make_account(client, uid, balance=0)
    # 引用不存在的分类 → 404
    r = client.post(
        f"/api/ledger/users/{uid}/transactions/" + _q(uid),
        json={"transaction_type": "expense", "amount": 10,
              "from_account_id": acc["id"], "category_id": 999999},
    )
    assert r.status_code == 404, r.text


def test_update_transaction_rebalances(client):
    uid = "ledger_upd_uid"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    tx = _make_transaction(client, uid, "expense", 100, acc["id"], cat["id"])
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(-100.0)

    # 金额 100 → 50：先恢复(+100) 再重算(-50) → -50
    r = client.put(f"/api/ledger/users/{uid}/transactions/{tx['id']}" + _q(uid),
                   json={"amount": 50})
    assert r.status_code == 200, r.text
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(-50.0)


def test_delete_transaction_restores_balance(client):
    uid = "ledger_del_uid"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    tx = _make_transaction(client, uid, "expense", 100, acc["id"], cat["id"])
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(-100.0)

    r = client.delete(f"/api/ledger/users/{uid}/transactions/{tx['id']}" + _q(uid))
    assert r.status_code == 200, r.text
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(0.0)


# ──────────────── 统计概览 ────────────────

def test_summary_structure(client):
    uid = "ledger_sum_uid"
    acc = _make_account(client, uid, balance=0)
    cat_exp = _make_category(client, uid, "EXPENSE")
    cat_inc = _make_category(client, uid, "INCOME")
    _make_transaction(client, uid, "expense", 100, acc["id"], cat_exp["id"])
    _make_transaction(client, uid, "income", 400, acc["id"], cat_inc["id"])

    r = client.get(f"/api/ledger/users/{uid}/statistics/summary" + _q(uid))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"total_assets", "monthly_income",
                                "monthly_expense", "monthly_balance", "month_budget"}
    # 总资产负债 = 账户余额 = -100 + 400 = 300
    assert body["total_assets"] == pytest.approx(300.0)
    assert body["monthly_income"] == pytest.approx(400.0)
    assert body["monthly_expense"] == pytest.approx(100.0)
    assert body["monthly_balance"] == pytest.approx(300.0)
    # 未设预算时 month_budget 应为 None
    assert body["month_budget"] is None


# ──────────────── 跨用户越权拦截 ────────────────

def test_cross_user_forbidden(client):
    uid_a = "ledger_x_a"
    uid_b = "ledger_x_b"
    _make_account(client, uid_a)  # 以 A 身份建资源
    token_b = client._mint_token(uid_b)  # 显式取 B 的 token 覆盖自动注入
    r = client.get(
        f"/api/ledger/users/{uid_a}/accounts/",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403, r.text


# ──────────────── M0 健壮性：周期推进 / 边界校验 / 余额守恒 ────────────────

def test_advance_next_run_month_end_clamp():
    # 1/31 按月推进必须夹紧到 2/28（旧实现 +30 天会给 3/2，造成月末漂移）
    nr = _dt(2026, 1, 31, 9, 0, 0)
    out = _advance_next_run(nr, "monthly", _dt(2026, 2, 1, 0, 0, 0))
    assert out == _dt(2026, 2, 28, 9, 0, 0)


def test_advance_next_run_leap_year_clamp():
    # 闰年 2/29 按年推进到次年 2/28（旧实现 +365 天会跨到 3/1 附近）
    nr = _dt(2024, 2, 29, 8, 0, 0)
    out = _advance_next_run(nr, "yearly", _dt(2025, 1, 1, 0, 0, 0))
    assert out == _dt(2025, 2, 28, 8, 0, 0)


def test_advance_next_run_weekly_no_drift():
    # 每周 +7 天，时间分量保留，不应有日漂移
    nr = _dt(2026, 1, 1, 12, 0, 0)
    out = _advance_next_run(nr, "weekly", _dt(2026, 1, 21, 0, 0, 0))
    assert out == _dt(2026, 1, 22, 12, 0, 0)


def test_amount_must_be_positive(client):
    uid = "ledger_amt_m0"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    r = client.post(
        f"/api/ledger/users/{uid}/transactions/" + _q(uid),
        json={"transaction_type": "expense", "amount": 0,
              "from_account_id": acc["id"], "category_id": cat["id"]},
    )
    assert r.status_code == 400, r.text


def test_transfer_self_account_rejected(client):
    uid = "ledger_xfer_self_m0"
    acc = _make_account(client, uid, balance=1000)
    cat = _make_category(client, uid, "EXPENSE")
    r = client.post(
        f"/api/ledger/users/{uid}/transactions/" + _q(uid),
        json={"transaction_type": "transfer", "amount": 100,
              "from_account_id": acc["id"], "to_account_id": acc["id"],
              "category_id": cat["id"]},
    )
    assert r.status_code == 400, r.text


def test_update_to_transfer_without_to_account_rejected(client):
    uid = "ledger_upd_xfer_m0"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    tx = _make_transaction(client, uid, "expense", 100, acc["id"], cat["id"])
    r = client.put(
        f"/api/ledger/users/{uid}/transactions/{tx['id']}" + _q(uid),
        json={"transaction_type": "transfer"},
    )
    assert r.status_code == 400, r.text


def test_transfer_conserves_total_assets(client):
    uid = "ledger_cons_m0"
    src = _make_account(client, uid, balance=1000, name="源账户")
    dst = _make_account(client, uid, balance=200, name="目标账户")
    cat = _make_category(client, uid, "EXPENSE")
    _make_transaction(client, uid, "transfer", 300, src["id"], cat["id"],
                      to_account_id=dst["id"])
    # 转账不改变总资产：1000+200 = 700+500 = 1200
    r = client.get(f"/api/ledger/users/{uid}/statistics/summary" + _q(uid))
    assert r.status_code == 200, r.text
    assert r.json()["total_assets"] == pytest.approx(1200.0)


# ──────────────── M1 多账本 ────────────────

def test_book_crud_and_default(client):
    uid = "ledger_book_m1"
    # 首次获取账本列表应自动含默认「日常账本」
    r = client.get(f"/api/ledger/users/{uid}/books/" + _q(uid))
    assert r.status_code == 200, r.text
    assert any(b["is_default"] for b in r.json())

    # 新建旅行账本
    r = client.post(f"/api/ledger/users/{uid}/books/" + _q(uid),
                    json={"name": "旅行账本", "book_type": "travel", "color": "#FF5722"})
    assert r.status_code == 200, r.text
    travel_id = r.json()["id"]

    r = client.get(f"/api/ledger/users/{uid}/books/" + _q(uid))
    assert len(r.json()) == 2

    # 设为默认：原默认应被取消，全局仅一个默认
    r = client.put(f"/api/ledger/users/{uid}/books/{travel_id}" + _q(uid),
                   json={"is_default": True})
    assert r.status_code == 200, r.text
    assert r.json()["is_default"] is True
    r = client.get(f"/api/ledger/users/{uid}/books/" + _q(uid))
    defaults = [b for b in r.json() if b["is_default"]]
    assert len(defaults) == 1 and defaults[0]["id"] == travel_id

    # 默认账本不可删
    r = client.delete(f"/api/ledger/users/{uid}/books/{travel_id}" + _q(uid))
    assert r.status_code == 400, r.text


def test_book_isolation(client):
    uid = "ledger_iso_m1"
    r = client.post(f"/api/ledger/users/{uid}/books/" + _q(uid),
                    json={"name": "日常账本", "is_default": True})
    assert r.status_code == 200, r.text
    daily_id = r.json()["id"]
    r = client.post(f"/api/ledger/users/{uid}/books/" + _q(uid), json={"name": "旅行账本"})
    assert r.status_code == 200, r.text
    travel_id = r.json()["id"]

    acc_d = client.post(f"/api/ledger/users/{uid}/accounts/" + _q(uid),
                        json={"account_name": "工资卡", "account_type": "savings_card",
                              "book_id": daily_id})
    assert acc_d.status_code == 200, acc_d.text
    acc_t = client.post(f"/api/ledger/users/{uid}/accounts/" + _q(uid),
                        json={"account_name": "旅行钱包", "account_type": "virtual_account",
                              "book_id": travel_id})
    assert acc_t.status_code == 200, acc_t.text
    cat = _make_category(client, uid, "EXPENSE")

    client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid),
                json={"transaction_type": "expense", "amount": 100,
                      "from_account_id": acc_d.json()["id"], "category_id": cat["id"],
                      "book_id": daily_id})
    client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid),
                json={"transaction_type": "expense", "amount": 50,
                      "from_account_id": acc_t.json()["id"], "category_id": cat["id"],
                      "book_id": travel_id})

    # 日常账本概览：月支出 100，总资产 -100
    r = client.get(f"/api/ledger/users/{uid}/statistics/summary" + _q(uid) + f"&book_id={daily_id}")
    assert r.status_code == 200, r.text
    assert r.json()["monthly_expense"] == pytest.approx(100.0)
    assert r.json()["total_assets"] == pytest.approx(-100.0)

    # 旅行账本概览：月支出 50，总资产 -50（两本账本互不串扰）
    r = client.get(f"/api/ledger/users/{uid}/statistics/summary" + _q(uid) + f"&book_id={travel_id}")
    assert r.status_code == 200, r.text
    assert r.json()["monthly_expense"] == pytest.approx(50.0)
    assert r.json()["total_assets"] == pytest.approx(-50.0)

    # 不传 book_id 取默认账本（日常）→ 月支出 100
    r = client.get(f"/api/ledger/users/{uid}/statistics/summary" + _q(uid))
    assert r.json()["monthly_expense"] == pytest.approx(100.0)


# ──────────────── M2 预算与超支提醒 ────────────────

def _make_budget(client, uid, scope_type, amount, scope_id=None, threshold=0.8, book_id=None):
    body = {"scope_type": scope_type, "amount": amount, "notify_threshold": threshold}
    if scope_id is not None:
        body["scope_id"] = scope_id
    if book_id is not None:
        body["book_id"] = book_id
    r = client.post(f"/api/ledger/users/{uid}/budgets/" + _q(uid), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_budget_crud_and_validation(client):
    uid = "ledger_budget_m2"
    # scope_type 非法 → 400
    r = client.post(f"/api/ledger/users/{uid}/budgets/" + _q(uid),
                    json={"scope_type": "weekly", "amount": 100})
    assert r.status_code == 400, r.text
    # category 预算缺 scope_id → 400
    r = client.post(f"/api/ledger/users/{uid}/budgets/" + _q(uid),
                    json={"scope_type": "category", "amount": 100})
    assert r.status_code == 400, r.text
    # 金额 <= 0 → 400
    r = client.post(f"/api/ledger/users/{uid}/budgets/" + _q(uid),
                    json={"scope_type": "month", "amount": 0})
    assert r.status_code == 400, r.text

    b = _make_budget(client, uid, "month", 1000, threshold=0.8)
    assert b["scope_type"] == "month"
    assert b["amount"] == 1000.0
    assert b["notify_threshold"] == 0.8

    # 列表
    r = client.get(f"/api/ledger/users/{uid}/budgets/" + _q(uid))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1

    # 更新阈值
    r = client.put(f"/api/ledger/users/{uid}/budgets/{b['id']}" + _q(uid),
                   json={"amount": 2000, "notify_threshold": 1.0})
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 2000.0
    assert r.json()["notify_threshold"] == 1.0

    # 删除
    r = client.delete(f"/api/ledger/users/{uid}/budgets/{b['id']}" + _q(uid))
    assert r.status_code == 200, r.text
    r = client.get(f"/api/ledger/users/{uid}/budgets/" + _q(uid))
    assert r.json() == []


def test_budget_execution_rate_and_overage(client):
    uid = "ledger_budget_exec_m2"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    # 月度总预算 1000，阈值 0.8 → 花到 800 预警，1000 超支
    _make_budget(client, uid, "month", 1000, threshold=0.8)

    # 先记一笔 500（ratio=0.5，status=ok，不应写通知）
    _make_transaction(client, uid, "expense", 500, acc["id"], cat["id"])
    r = client.get(f"/api/ledger/users/{uid}/statistics/budgets" + _q(uid))
    assert r.status_code == 200, r.text
    bd = r.json()["budgets"][0]
    assert bd["spent"] == pytest.approx(500.0)
    assert bd["ratio"] == pytest.approx(0.5)
    assert bd["status"] == "ok"

    # 再记 350（累计 850，ratio=0.85 >= 0.8 → warning，应写 1 条通知）
    _make_transaction(client, uid, "expense", 350, acc["id"], cat["id"])
    r = client.get(f"/api/ledger/users/{uid}/statistics/budgets" + _q(uid))
    bd = r.json()["budgets"][0]
    assert bd["ratio"] == pytest.approx(0.85)
    assert bd["status"] == "warning"

    # 通知落库：此时应有 1 条 pending（阈值 0.8 触发）
    r = client.get(f"/api/ledger/users/{uid}/notifications/" + _q(uid))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["status"] == "pending"

    # 重复调用 budgets 端点不应重复写通知（去重）
    client.get(f"/api/ledger/users/{uid}/statistics/budgets" + _q(uid))
    r = client.get(f"/api/ledger/users/{uid}/notifications/" + _q(uid))
    assert len(r.json()) == 1

    # 再记 200（累计 1050，ratio=1.05 → over，仍只有 1 条同月通知）
    _make_transaction(client, uid, "expense", 200, acc["id"], cat["id"])
    r = client.get(f"/api/ledger/users/{uid}/statistics/budgets" + _q(uid))
    bd = r.json()["budgets"][0]
    assert bd["ratio"] == pytest.approx(1.05)
    assert bd["status"] == "over"
    r = client.get(f"/api/ledger/users/{uid}/notifications/" + _q(uid))
    assert len(r.json()) == 1


def test_budget_summary_month_budget_field(client):
    uid = "ledger_budget_sum_m2"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    _make_budget(client, uid, "month", 1000, threshold=0.8)
    _make_transaction(client, uid, "expense", 600, acc["id"], cat["id"])

    r = client.get(f"/api/ledger/users/{uid}/statistics/summary" + _q(uid))
    assert r.status_code == 200, r.text
    mb = r.json()["month_budget"]
    assert mb is not None
    assert mb["amount"] == 1000.0
    assert mb["spent"] == pytest.approx(600.0)
    assert mb["ratio"] == pytest.approx(0.6)
    # 0.6 < 阈值 0.8 → 未预警
    assert mb["status"] == "ok"


def test_budget_category_scope(client):
    uid = "ledger_budget_cat_m2"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE", level1="餐饮")
    _make_budget(client, uid, "category", 200, scope_id=cat["id"], threshold=1.0)
    _make_transaction(client, uid, "expense", 150, acc["id"], cat["id"])
    r = client.get(f"/api/ledger/users/{uid}/statistics/budgets" + _q(uid))
    assert r.status_code == 200, r.text
    bd = r.json()["budgets"][0]
    assert bd["scope_name"] == "餐饮"
    assert bd["spent"] == pytest.approx(150.0)
    assert bd["ratio"] == pytest.approx(0.75)
    assert bd["status"] == "ok"


# ──────────────── M3 借贷 + 退款 + 净资产 ────────────────

def _make_person(client, uid, name="张三"):
    r = client.post(f"/api/ledger/users/{uid}/persons/" + _q(uid), json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def _make_book(client, uid, name, is_default=False):
    r = client.post(f"/api/ledger/users/{uid}/books/" + _q(uid),
                    json={"name": name, "is_default": is_default})
    assert r.status_code == 200, r.text
    return r.json()


def _make_debt(client, uid, direction, total, person_id=None, book_id=None, repaid=0):
    body = {"direction": direction, "total": total, "repaid": repaid}
    if person_id is not None:
        body["person_id"] = person_id
    if book_id is not None:
        body["book_id"] = book_id
    r = client.post(f"/api/ledger/users/{uid}/debts/" + _q(uid), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_debt_crud_and_validation(client):
    uid = "ledger_debt_m3"
    # direction 非法 → 400
    r = client.post(f"/api/ledger/users/{uid}/debts/" + _q(uid),
                    json={"direction": "gift", "total": 100})
    assert r.status_code == 400, r.text
    # 金额 <= 0 → 400
    r = client.post(f"/api/ledger/users/{uid}/debts/" + _q(uid),
                    json={"direction": "lend", "total": 0})
    assert r.status_code == 400, r.text

    person = _make_person(client, uid)
    d = _make_debt(client, uid, "lend", 1000, person_id=person["id"], repaid=200)
    assert d["direction"] == "lend"
    assert d["total"] == 1000.0
    assert d["repaid"] == 200.0
    assert d["balance"] == 800.0
    assert d["status"] == "active"

    # 列表 + 筛选
    r = client.get(f"/api/ledger/users/{uid}/debts/" + _q(uid) + "&direction=lend")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1

    # 更新 total → 重算 balance
    r = client.put(f"/api/ledger/users/{uid}/debts/{d['id']}" + _q(uid), json={"total": 1200})
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == pytest.approx(1000.0)

    # 删除
    r = client.delete(f"/api/ledger/users/{uid}/debts/{d['id']}" + _q(uid))
    assert r.status_code == 200, r.text


def test_debt_repay_links_balance_and_account(client):
    uid = "ledger_debt_repay_m3"
    acc = _make_account(client, uid, balance=0)
    d = _make_debt(client, uid, "lend", 1000)

    # 收款 400（income）：账户 +400，债务 repaid=400/balance=600
    r = client.post(f"/api/ledger/users/{uid}/debts/{d['id']}/repay" + _q(uid),
                    json={"amount": 400, "from_account_id": acc["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["repaid"] == pytest.approx(400.0)
    assert r.json()["balance"] == pytest.approx(600.0)
    assert r.json()["status"] == "active"
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(400.0)

    # 收款 600 → 结清
    r = client.post(f"/api/ledger/users/{uid}/debts/{d['id']}/repay" + _q(uid),
                    json={"amount": 600, "from_account_id": acc["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 0.0
    assert r.json()["status"] == "cleared"
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(1000.0)

    # 已结清再还款 → 400
    r = client.post(f"/api/ledger/users/{uid}/debts/{d['id']}/repay" + _q(uid),
                    json={"amount": 100, "from_account_id": acc["id"]})
    assert r.status_code == 400, r.text


def test_borrow_repay_is_expense(client):
    uid = "ledger_borrow_m3"
    acc = _make_account(client, uid, balance=1000)
    d = _make_debt(client, uid, "borrow", 500)
    # 还款 300（expense）：账户 -300，债务 balance=200
    r = client.post(f"/api/ledger/users/{uid}/debts/{d['id']}/repay" + _q(uid),
                    json={"amount": 300, "from_account_id": acc["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == pytest.approx(200.0)
    assert _balance_of(client, uid, acc["id"]) == pytest.approx(700.0)


def test_networth_calculation(client):
    uid = "ledger_nw_m3"
    sav = _make_account(client, uid, balance=1000, name="储蓄卡")
    cc = client.post(f"/api/ledger/users/{uid}/accounts/" + _q(uid),
                     json={"account_name": "信用卡", "account_type": "credit_card", "balance": 500})
    assert cc.status_code == 200, cc.text
    _make_debt(client, uid, "lend", 300)      # 借出未收（资产）
    _make_debt(client, uid, "borrow", 200)    # 借入未还（负债）

    r = client.get(f"/api/ledger/users/{uid}/statistics/networth" + _q(uid))
    assert r.status_code == 200, r.text
    body = r.json()
    # 资产 = 储蓄1000 + 借出300 = 1300；负债 = 借入200 + 信用卡500 = 700；净资产 = 600
    assert body["account_balance"] == pytest.approx(1000.0)
    assert body["lent_outstanding"] == pytest.approx(300.0)
    assert body["borrowed_outstanding"] == pytest.approx(200.0)
    assert body["credit_payable"] == pytest.approx(500.0)
    assert body["assets"] == pytest.approx(1300.0)
    assert body["liabilities"] == pytest.approx(700.0)
    assert body["net_worth"] == pytest.approx(600.0)


def test_refund_links_to_original_expense(client):
    uid = "ledger_refund_m3"
    acc = _make_account(client, uid, balance=0)
    cat = _make_category(client, uid, "EXPENSE")
    orig = _make_transaction(client, uid, "expense", 200, acc["id"], cat["id"])
    # 退款（income）关联原支出
    r = client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid), json={
        "transaction_type": "income", "amount": 200,
        "from_account_id": acc["id"], "category_id": cat["id"],
        "refund_of_id": orig["id"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["refund_of_id"] == orig["id"]
