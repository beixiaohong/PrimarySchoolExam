"""钻石服务回归测试：扣费/充值 + 并发行锁防超发

锁住 P0-2 修复成果（diamond.deduct/grant 已加 WITH FOR UPDATE 行锁），
防止未来重构把锁误删导致并发超发/负余额资损竞态。

测试库为独立 MySQL（conftest 强制），WITH FOR UPDATE 在 MySQL 下真实生效；
若误回退为「读改写无锁」，test_concurrent_deduct_no_overspend 会失败。
"""
import secrets
import threading

import pytest

from app.database import SessionLocal
from app.domains.commerce.services import diamond as diamond_svc


def _new_uid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def test_deduct_success_reduces_balance():
    """余额充足时扣费成功且精确减少"""
    db = SessionLocal()
    try:
        uid = _new_uid("deduct_ok")
        init = diamond_svc.get_balance(db, uid)  # 自动建账户并赠送注册钻石(10)
        assert init == 10.0
        ok = diamond_svc.deduct(db, uid, 3.0, reason="test_deduct")
        assert ok is True
        assert diamond_svc.get_balance(db, uid) == 7.0
    finally:
        db.close()


def test_deduct_insufficient_returns_false():
    """余额不足时返回 False 且不改变余额"""
    db = SessionLocal()
    try:
        uid = _new_uid("deduct_low")
        diamond_svc.get_balance(db, uid)
        ok = diamond_svc.deduct(db, uid, 999.0, reason="test_deduct")
        assert ok is False
        assert diamond_svc.get_balance(db, uid) == 10.0  # 不变
    finally:
        db.close()


def test_deduct_non_positive_is_noop():
    """amount<=0 视为 no-op，返回 True 且不改动余额"""
    db = SessionLocal()
    try:
        uid = _new_uid("deduct_zero")
        before = diamond_svc.get_balance(db, uid)
        assert diamond_svc.deduct(db, uid, 0) is True
        assert diamond_svc.deduct(db, uid, -5.0) is True
        assert diamond_svc.get_balance(db, uid) == before
    finally:
        db.close()


def test_grant_increases_balance():
    """充值时余额精确增加"""
    db = SessionLocal()
    try:
        uid = _new_uid("grant_ok")
        before = diamond_svc.get_balance(db, uid)
        new = diamond_svc.grant(db, uid, 5.0, reason="test_grant")
        assert new == before + 5.0
    finally:
        db.close()


def test_concurrent_deduct_no_overspend():
    """并发扣费在行锁下不超发：余额 50 时 80 个并发请求最多成功 50 次。

    若 deduct 误回退为无锁读改写，多个请求会同时通过余额判断 → 超发/负余额，
    本测试会断言失败，作为 P0-2 资损竞态的回归护栏。
    """
    db = SessionLocal()
    try:
        uid = _new_uid("concurrent")
        diamond_svc.get_balance(db, uid)          # 建账户(10)
        diamond_svc.grant(db, uid, 40.0, reason="seed")  # 余额 50
        seed_balance = diamond_svc.get_balance(db, uid)
        assert seed_balance == 50.0

        results = []
        lock = threading.Lock()

        def worker():
            d = SessionLocal()
            try:
                r = diamond_svc.deduct(d, uid, 1.0, reason="concurrent")
                with lock:
                    results.append(r)
            finally:
                d.close()

        threads = [threading.Thread(target=worker) for _ in range(80)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success = sum(1 for r in results if r is True)
        # 必须用独立会话读取最终余额：主线程 db 在 MySQL Repeatable Read 下持有旧
        # 快照，读不到并发 worker 已提交的扣减，会导致假阳性/假阴性。
        verify = SessionLocal()
        try:
            after = diamond_svc.get_balance(verify, uid)
        finally:
            verify.close()
        assert success <= 50, f"并发超发：成功 {success} 次 > 余额 50"
        assert after >= 0, f"出现负余额：{after}"
        assert after == 50 - success, f"余额不守恒：期望 {50 - success}，实际 {after}"
    finally:
        db.close()
