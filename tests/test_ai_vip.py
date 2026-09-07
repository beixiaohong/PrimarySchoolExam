"""AI 服务 VIP 到期过滤测试（test_ai_vip）

覆盖：
- _load_vip_users SQL 过滤：NULL=永久 / 未到期=包含 / 已到期=排除
- _is_vip 缓存行为：命中缓存 / TTL 过期后刷新
- _chain_for 链路组合：非 VIP 仅免费链 / 有效 VIP 追加付费链 / 已到期 VIP 仅免费链
- chat_with VIP 门控：非 VIP 拒绝付费链 / 有效 VIP 允许 / 已到期 VIP 拒绝

测试库 vip_users 表由 conftest.py 的 drop_all + lifespan（迁移 009 + 071）自动建表。
数据靠 fixture 自建（conftest 每次 drop_all）。
"""
from datetime import datetime, timedelta

import pytest

from app.database import SessionLocal
from app.models.user import VipUser
from app.domains.platform.services import ai as ai_svc


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _reset_vip_cache():
    """每个用例前强制刷新 VIP 缓存，避免上一个用例的缓存污染"""
    ai_svc._vip_cache = set()
    ai_svc._vip_cache_ts = 0.0
    yield
    ai_svc._vip_cache = set()
    ai_svc._vip_cache_ts = 0.0


def _seed_vip(db, user_id, expire_at=None, note="test"):
    """插入一条 VIP 记录（expire_at=None 表示永久）"""
    existing = db.query(VipUser).filter(VipUser.user_id == user_id).first()
    if existing:
        existing.expire_at = expire_at
        existing.note = note
    else:
        db.add(VipUser(user_id=user_id, note=note, expire_at=expire_at))
    db.commit()


def _cleanup_vip(db, *user_ids):
    """清理测试 VIP 记录"""
    for uid in user_ids:
        db.query(VipUser).filter(VipUser.user_id == uid).delete()
    db.commit()


class TestLoadVipUsers:
    """_load_vip_users SQL 过滤逻辑"""

    def test_empty_table(self, db):
        """空表返回空集"""
        _cleanup_vip(db, "vip_empty")
        result = ai_svc._load_vip_users()
        assert isinstance(result, set)
        assert "vip_empty" not in result

    def test_permanent_vip_included(self, db):
        """expire_at=NULL（永久 VIP）应包含"""
        uid = "vip_permanent_test"
        _seed_vip(db, uid, expire_at=None)
        try:
            result = ai_svc._load_vip_users()
            assert uid in result
        finally:
            _cleanup_vip(db, uid)

    def test_future_vip_included(self, db):
        """expire_at > NOW()（未到期）应包含"""
        uid = "vip_future_test"
        _seed_vip(db, uid, expire_at=datetime.now() + timedelta(days=30))
        try:
            result = ai_svc._load_vip_users()
            assert uid in result
        finally:
            _cleanup_vip(db, uid)

    def test_expired_vip_excluded(self, db):
        """expire_at < NOW()（已到期）应排除"""
        uid = "vip_expired_test"
        _seed_vip(db, uid, expire_at=datetime.now() - timedelta(days=1))
        try:
            result = ai_svc._load_vip_users()
            assert uid not in result
        finally:
            _cleanup_vip(db, uid)

    def test_mixed_vip_only_active(self, db):
        """混合场景：只返回永久 + 未到期的，排除已到期的"""
        uids = {
            "vip_mix_perm": None,
            "vip_mix_future": datetime.now() + timedelta(days=30),
            "vip_mix_expired": datetime.now() - timedelta(days=10),
        }
        for uid, exp in uids.items():
            _seed_vip(db, uid, expire_at=exp)
        try:
            result = ai_svc._load_vip_users()
            assert "vip_mix_perm" in result, "永久 VIP 应包含"
            assert "vip_mix_future" in result, "未到期 VIP 应包含"
            assert "vip_mix_expired" not in result, "已到期 VIP 应排除"
        finally:
            _cleanup_vip(db, *uids.keys())

    def test_just_expired_excluded(self, db):
        """刚好到期（expire_at = NOW() - 10 秒）应排除"""
        uid = "vip_just_expired"
        # 使用 10 秒前以确保 MySQL NOW() 与 Python datetime.now() 的时钟偏差不会影响测试
        _seed_vip(db, uid, expire_at=datetime.now() - timedelta(seconds=10))
        try:
            result = ai_svc._load_vip_users()
            assert uid not in result
        finally:
            _cleanup_vip(db, uid)

    def test_far_future_included(self, db):
        """远期 VIP（expire_at = NOW() + 365 天）应包含"""
        uid = "vip_far_future"
        _seed_vip(db, uid, expire_at=datetime.now() + timedelta(days=365))
        try:
            result = ai_svc._load_vip_users()
            assert uid in result
        finally:
            _cleanup_vip(db, uid)


class TestIsVip:
    """_is_vip 缓存行为"""

    def test_vip_returns_true(self, db):
        """有效 VIP 返回 True"""
        uid = "is_vip_true_test"
        _seed_vip(db, uid, expire_at=datetime.now() + timedelta(days=30))
        try:
            assert ai_svc._is_vip(uid) is True
        finally:
            _cleanup_vip(db, uid)

    def test_non_vip_returns_false(self, db):
        """非 VIP 返回 False"""
        uid = "is_vip_false_test"
        _cleanup_vip(db, uid)
        assert ai_svc._is_vip(uid) is False

    def test_expired_vip_returns_false(self, db):
        """已到期 VIP 返回 False（核心改动验证）"""
        uid = "is_vip_expired_test"
        _seed_vip(db, uid, expire_at=datetime.now() - timedelta(days=1))
        try:
            assert ai_svc._is_vip(uid) is False
        finally:
            _cleanup_vip(db, uid)

    def test_cache_refresh_after_ttl(self, db, monkeypatch):
        """TTL 过期后缓存刷新：新插入的 VIP 应被识别"""
        uid = "cache_refresh_test"
        monkeypatch.setattr(ai_svc, "VIP_CACHE_TTL", 0)
        _cleanup_vip(db, uid)
        assert ai_svc._is_vip(uid) is False

        _seed_vip(db, uid, expire_at=datetime.now() + timedelta(days=30))
        try:
            assert ai_svc._is_vip(uid) is True
        finally:
            _cleanup_vip(db, uid)


class TestChainFor:
    """_chain_for 链路组合"""

    def test_non_vip_free_only(self, db):
        """非 VIP 只有免费链"""
        uid = "chain_non_vip"
        _cleanup_vip(db, uid)
        chain = ai_svc._chain_for(uid)
        assert chain == list(ai_svc.FREE_CHAIN)
        assert "deepseek" not in chain

    def test_active_vip_includes_paid(self, db):
        """有效 VIP 追加付费链"""
        uid = "chain_active_vip"
        _seed_vip(db, uid, expire_at=datetime.now() + timedelta(days=30))
        try:
            chain = ai_svc._chain_for(uid)
            assert chain[:len(ai_svc.FREE_CHAIN)] == list(ai_svc.FREE_CHAIN)
            assert "deepseek" in chain
        finally:
            _cleanup_vip(db, uid)

    def test_expired_vip_free_only(self, db):
        """已到期 VIP 只有免费链（核心改动验证）"""
        uid = "chain_expired_vip"
        _seed_vip(db, uid, expire_at=datetime.now() - timedelta(days=1))
        try:
            chain = ai_svc._chain_for(uid)
            assert chain == list(ai_svc.FREE_CHAIN)
            assert "deepseek" not in chain
        finally:
            _cleanup_vip(db, uid)

    def test_permanent_vip_includes_paid(self, db):
        """永久 VIP（expire_at=NULL）追加付费链"""
        uid = "chain_perm_vip"
        _seed_vip(db, uid, expire_at=None)
        try:
            chain = ai_svc._chain_for(uid)
            assert "deepseek" in chain
        finally:
            _cleanup_vip(db, uid)


class TestChatWithVipGating:
    """chat_with VIP 门控：付费链只对有效 VIP 开放"""

    def test_non_vip_rejected_for_paid_chain(self, db):
        """非 VIP 请求 deepseek 返回 None"""
        uid = "chatwith_nonvip"
        _cleanup_vip(db, uid)
        result = ai_svc.chat_with(uid, "system", "user", provider="deepseek")
        assert result is None

    def test_expired_vip_rejected_for_paid_chain(self, db):
        """已到期 VIP 请求 deepseek 返回 None（核心改动验证）"""
        uid = "chatwith_expired"
        _seed_vip(db, uid, expire_at=datetime.now() - timedelta(days=1))
        try:
            result = ai_svc.chat_with(uid, "system", "user", provider="deepseek")
            assert result is None
        finally:
            _cleanup_vip(db, uid)

    def test_active_vip_allowed_for_paid_chain(self, db, monkeypatch):
        """有效 VIP 请求 deepseek 不会因 VIP 校验被拒绝。

        注意：若未配置 DEEPSEEK_API_KEY，chat_with 会因 Key 缺失返回 None，
        但那不是 VIP 校验拒绝。这里用 monkeypatch 模拟 Key 存在，
        并 mock _call_provider 避免真实网络调用。
        """
        uid = "chatwith_active"
        _seed_vip(db, uid, expire_at=datetime.now() + timedelta(days=30))

        monkeypatch.setattr(ai_svc, "_config_provider", lambda name: {
            "api_key": "fake-key",
            "base_url": "https://fake.api",
            "model": "fake-model",
            "timeout": 5,
        })
        monkeypatch.setattr(ai_svc, "_call_provider", lambda *a, **kw: {
            "text": "ok", "prompt_tokens": 1, "completion_tokens": 1, "model": "fake"
        })
        monkeypatch.setattr(ai_svc, "rate_limit", lambda *a, **kw: True)

        try:
            result = ai_svc.chat_with(uid, "system", "user", provider="deepseek")
            assert result is not None
            assert result["text"] == "ok"
            assert result["provider"] == "deepseek"
        finally:
            _cleanup_vip(db, uid)
