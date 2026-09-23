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

from app.models.ledger import Account, Bill, Category


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
                                "monthly_expense", "monthly_balance"}
    # 总资产负债 = 账户余额 = -100 + 400 = 300
    assert body["total_assets"] == pytest.approx(300.0)
    assert body["monthly_income"] == pytest.approx(400.0)
    assert body["monthly_expense"] == pytest.approx(100.0)
    assert body["monthly_balance"] == pytest.approx(300.0)


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
