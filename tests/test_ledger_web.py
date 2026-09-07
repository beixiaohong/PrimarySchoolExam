# -*- coding: utf-8 -*-
"""账本 Web 端接入验收测试（P1/P2，对应 docs/IM与账本前端实现方案.md 验收标准）。

覆盖：
- AC-L1  支出记账后账户余额联动
- AC-L2  转账双账户余额联动（转出减少、转入增加）
- AC-L3  交易列表多维筛选（类型/分类/金额区间/关键词/日期）
- AC-L9  B9 全量到期周期交易自动生成账单并联动余额（停用条目跳过）
- AC-L10 B9 幂等：紧接着重跑不产生重复账单，next_run 已推进到未来

说明：
- 金额口径为「元」（Numeric(15,2)），与 schema float 一致，不做分转换。
- 所有请求 URL 均带 ?user_id=，使 conftest.AuthClient 能按该 uid 签发绑定 token
  （账本接口 require_self：token 账号必须与路径 user_id 一致）。
"""
from datetime import datetime, timedelta

import pytest

from app.database import SessionLocal
from app.domains.frozen.services.ledger_recurring import run_due_recurring_all
from app.models import ledger as model_ledger


def _q(uid, extra=""):
    """账本 URL 统一追加 user_id 查询参数（供 AuthClient 提取签发 token）。"""
    sep = "&" if extra else ""
    return f"?user_id={uid}{sep}{extra}"


def _mk_account(client, uid, name, balance=1000.0):
    r = client.post(f"/api/ledger/users/{uid}/accounts/" + _q(uid), json={
        "account_name": name, "account_type": "savings_card", "balance": balance,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _mk_category(client, uid, level1="餐饮", category_type="EXPENSE"):
    r = client.post(f"/api/ledger/users/{uid}/categories/" + _q(uid), json={
        "category_type": category_type, "level1": level1,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _get_balance(client, uid, account_id):
    r = client.get(f"/api/ledger/users/{uid}/accounts/" + _q(uid))
    assert r.status_code == 200, r.text
    for a in r.json():
        if a["id"] == account_id:
            return float(a["balance"])
    raise AssertionError(f"账户 {account_id} 不在列表中")


def test_ac_l1_expense_updates_balance(client):
    """AC-L1：记一笔支出后，付款账户余额减少对应金额。"""
    uid = "ledger_l1_uid"
    acc = _mk_account(client, uid, "零花钱卡", balance=500.0)
    cat = _mk_category(client, uid, "文具")

    r = client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid), json={
        "transaction_type": "expense", "amount": 12.34,
        "from_account_id": acc["id"], "category_id": cat["id"], "note": "买笔",
    })
    assert r.status_code == 200, r.text

    assert _get_balance(client, uid, acc["id"]) == pytest.approx(500.0 - 12.34, abs=0.01)


def test_ac_l2_transfer_both_accounts(client):
    """AC-L2：转账后转出账户减少、转入账户增加；缺收入账户应 400。"""
    uid = "ledger_l2_uid"
    a1 = _mk_account(client, uid, "储蓄卡", balance=800.0)
    a2 = _mk_account(client, uid, "虚拟账户", balance=100.0)
    cat = _mk_category(client, uid, "转账手续费")

    r = client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid), json={
        "transaction_type": "transfer", "amount": 200.0,
        "from_account_id": a1["id"], "to_account_id": a2["id"], "category_id": cat["id"],
    })
    assert r.status_code == 200, r.text

    assert _get_balance(client, uid, a1["id"]) == pytest.approx(600.0, abs=0.01)
    assert _get_balance(client, uid, a2["id"]) == pytest.approx(300.0, abs=0.01)

    r = client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid), json={
        "transaction_type": "transfer", "amount": 10.0,
        "from_account_id": a1["id"], "category_id": cat["id"],
    })
    assert r.status_code == 400


def test_ac_l3_transaction_filters(client):
    """AC-L3：按类型/分类/金额区间/关键词/日期多维筛选。"""
    uid = "ledger_l3_uid"
    acc = _mk_account(client, uid, "生活卡", balance=1000.0)
    cat_food = _mk_category(client, uid, "餐饮")
    cat_book = _mk_category(client, uid, "图书")

    for amount, cat, note in [(15.5, cat_food, "午饭"), (88.0, cat_book, "买书"), (200.0, cat_food, "大餐")]:
        r = client.post(f"/api/ledger/users/{uid}/transactions/" + _q(uid), json={
            "transaction_type": "expense", "amount": amount,
            "from_account_id": acc["id"], "category_id": cat["id"], "note": note,
        })
        assert r.status_code == 200, r.text

    base = f"/api/ledger/users/{uid}/transactions/"

    r = client.get(base + _q(uid, "transaction_type=expense"))
    assert r.status_code == 200 and len(r.json()) == 3

    r = client.get(base + _q(uid, f"category_id={cat_book['id']}"))
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.get(base + _q(uid, "min_amount=50&max_amount=100"))
    assert r.status_code == 200 and len(r.json()) == 1
    assert float(r.json()[0]["amount"]) == pytest.approx(88.0, abs=0.01)

    r = client.get(base + _q(uid, "keyword=买书"))
    assert r.status_code == 200 and len(r.json()) == 1

    today = datetime.now().strftime("%Y-%m-%d")
    r = client.get(base + _q(uid, f"start_date={today}&end_date={today}"))
    assert r.status_code == 200 and len(r.json()) == 3


def _setup_due_recurring(client, uid, amount=30.0):
    """建账户+分类+一条已到期（next_run 在昨天）的每日周期交易。"""
    acc = _mk_account(client, uid, "房租卡", balance=1000.0)
    cat = _mk_category(client, uid, "房租")
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    r = client.post(f"/api/ledger/users/{uid}/recurring/" + _q(uid), json={
        "name": "每日零花扣款", "transaction_type": "expense", "amount": amount,
        "from_account_id": acc["id"], "category_id": cat["id"],
        "frequency": "daily", "next_run": yesterday,
    })
    assert r.status_code == 200, r.text
    return acc, r.json()


def _user_bills(db, uid):
    return db.query(model_ledger.Bill).filter(model_ledger.Bill.user_id == uid).all()


def test_ac_l9_l10_recurring_all_and_idempotent(client):
    """AC-L9/L10：B9 全量执行到期周期交易生成账单+联动余额；重跑幂等不重复。"""
    uid = "ledger_l9_uid"
    acc, rt = _setup_due_recurring(client, uid, amount=30.0)

    db = SessionLocal()
    try:
        # AC-L9：到期周期交易被处理，账单生成
        result = run_due_recurring_all(db)
        assert result["scanned"] >= 1 and result["failed"] == 0
        bills = _user_bills(db, uid)
        assert len(bills) == 1
        assert float(bills[0].amount) == pytest.approx(30.0, abs=0.01)

        # next_run 已推进到未来（幂等的前提）
        rt_row = db.query(model_ledger.RecurringTransaction).filter(
            model_ledger.RecurringTransaction.id == rt["id"]).first()
        assert rt_row is not None and rt_row.next_run > datetime.now()

        # AC-L10：紧接着重跑，不产生重复账单（幂等）
        result2 = run_due_recurring_all(db)
        assert result2["failed"] == 0
        assert len(_user_bills(db, uid)) == 1
    finally:
        db.close()

    # 余额通过接口再验一次：1000 - 30
    assert _get_balance(client, uid, acc["id"]) == pytest.approx(970.0, abs=0.01)


def test_ac_l9_inactive_recurring_skipped(client):
    """B9 只处理启用的周期交易：停用后到期也不生成账单。"""
    uid = "ledger_l9b_uid"
    acc, rt = _setup_due_recurring(client, uid, amount=50.0)

    r = client.post(f"/api/ledger/users/{uid}/recurring/{rt['id']}/toggle" + _q(uid))
    assert r.status_code == 200 and r.json()["is_active"] is False

    db = SessionLocal()
    try:
        run_due_recurring_all(db)
        assert len(_user_bills(db, uid)) == 0
    finally:
        db.close()
