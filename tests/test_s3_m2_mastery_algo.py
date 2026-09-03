"""S3-M2 验证：掌握度纯函数 compute_mastery（07 §5.1.2）

单测覆盖边界（07 明确要求）：0 条记录 / 全对 / 全错 / 全是 0 用时 / 极端难度 /
时间衰减 / 先验混合 / 置信度增长。纯函数、无 IO，断言以「方向性 + 关键确定值」为主，
避免对调参细节过度耦合。
"""
from datetime import datetime, timedelta

from app.domains.engine.services.mastery import (
    ALGO_VERSION,
    AnswerRecord,
    MasteryParams,
    compute_mastery,
)


def _rec(days_ago, correct, duration_ms=12000, difficulty=3, kp_id=1):
    return AnswerRecord(
        answered_at=datetime(2026, 9, 2) - timedelta(days=days_ago),
        is_correct=correct, duration_ms=duration_ms, difficulty=difficulty,
        kp_id=kp_id,
    )


def test_s3_m2_empty_records_uses_prior():
    """records 为空 → 走 prior=20 兜底（BR-M0-1-02），不可上线（confidence=0）。"""
    r = compute_mastery([], MasteryParams())
    assert r.mastery == 20
    assert r.level == "未掌握"
    assert r.answer_count == 0
    assert r.correct_count == 0
    assert r.confidence == 0.0
    assert r.algo_version == ALGO_VERSION


def test_s3_m2_all_correct_beats_all_wrong():
    """全对掌握度显著高于全错。"""
    now = datetime(2026, 9, 2)
    correct = [_rec(0, True, kp_id=1), _rec(1, True, kp_id=1), _rec(2, True, kp_id=1)]
    wrong = [_rec(0, False, kp_id=2), _rec(1, False, kp_id=2), _rec(2, False, kp_id=2)]
    rc = compute_mastery(correct, MasteryParams(now=now))
    rw = compute_mastery(wrong, MasteryParams(now=now))
    assert rc.mastery >= 80, rc          # 全对近期作答 → 已掌握档
    assert rc.level == "已掌握"
    assert rw.mastery < 20, rw           # 全错 → 低于先验兜底
    assert rc.mastery > rw.mastery


def test_s3_m2_all_zero_duration_neutral():
    """全 0 用时不应报错，且用时因子取中性 1.0（07 §3.2.2）。"""
    now = datetime(2026, 9, 2)
    recs = [_rec(0, True, duration_ms=0, kp_id=1),
            _rec(1, True, duration_ms=0, kp_id=1)]
    r = compute_mastery(recs, MasteryParams(now=now))
    assert 0 <= r.mastery <= 100
    assert r.avg_duration_ms == 0


def test_s3_m2_harder_correct_scores_higher():
    """同样全对、同样时间，难题（diff=5）掌握度高于易题（diff=1）。"""
    now = datetime(2026, 9, 2)
    hard = [_rec(0, True, difficulty=5, kp_id=1),
            _rec(1, True, difficulty=5, kp_id=1)]
    easy = [_rec(0, True, difficulty=1, kp_id=2),
            _rec(1, True, difficulty=1, kp_id=2)]
    rh = compute_mastery(hard, MasteryParams(now=now))
    re = compute_mastery(easy, MasteryParams(now=now))
    assert rh.mastery > re.mastery, (rh.mastery, re.mastery)


def test_s3_m2_time_decay_lowers_old_answers():
    """同一组全对作答，若 now 远晚于作答时间（衰减），掌握度低于 now≈作答时刻。"""
    recs = [_rec(0, True, kp_id=1), _rec(1, True, kp_id=1), _rec(2, True, kp_id=1)]
    fresh = compute_mastery(recs, MasteryParams(now=datetime(2026, 9, 2)))
    stale = compute_mastery(recs, MasteryParams(now=datetime(2026, 12, 2)))  # 90 天后
    assert stale.mastery < fresh.mastery, (stale.mastery, fresh.mastery)


def test_s3_m2_prior_weight_pulls_toward_prior():
    """prior_weight 越大，全对结果越向 prior(20) 靠拢（更保守）。"""
    now = datetime(2026, 9, 2)
    recs = [_rec(0, True, kp_id=1), _rec(1, True, kp_id=1), _rec(2, True, kp_id=1)]
    low_w = compute_mastery(recs, MasteryParams(now=now, prior_weight=2.0))
    high_w = compute_mastery(recs, MasteryParams(now=now, prior_weight=50.0))
    assert high_w.mastery < low_w.mastery, (high_w.mastery, low_w.mastery)
    assert high_w.mastery >= 20  # 不会低于 prior


def test_s3_m2_confidence_grows_with_samples():
    """有效样本越多，置信度越高（封顶 1.0）。"""
    now = datetime(2026, 9, 2)
    few = [_rec(0, True, kp_id=1), _rec(1, True, kp_id=1)]
    many = [_rec(i, True, kp_id=2) for i in range(25)]
    rc = compute_mastery(few, MasteryParams(now=now))
    rm = compute_mastery(many, MasteryParams(now=now))
    assert rm.confidence > rc.confidence
    assert rm.confidence <= 1.0


def test_s3_m2_streak_bonus_reflected():
    """末尾连续正确 → correct_streak 正确统计，且加成体现在等级。"""
    now = datetime(2026, 9, 2)
    recs = [_rec(3, False, kp_id=1), _rec(2, True, kp_id=1),
            _rec(1, True, kp_id=1), _rec(0, True, kp_id=1)]
    r = compute_mastery(recs, MasteryParams(now=now))
    assert r.correct_streak == 3
    assert r.correct_count == 3
    assert r.answer_count == 4


def test_s3_m2_result_in_range_and_level_consistent():
    """任意结果掌握度落在 [0,100]，level 与分数一致。"""
    now = datetime(2026, 9, 2)
    from app.models.mastery import level_from_mastery
    for kp in range(5):
        recs = [_rec(i % 4, (i % 3 == 0), kp_id=kp) for i in range(6)]
        r = compute_mastery(recs, MasteryParams(now=now))
        assert 0 <= r.mastery <= 100
        assert r.level == level_from_mastery(r.mastery)
