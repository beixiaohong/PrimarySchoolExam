"""掌握度计算纯函数（S3-M2 / 07-技术实施方案 §5.1.2）

纯函数 `compute_mastery(records, params)`：给定**单个**知识点的作答记录与配置参数，
输出掌握度（0-100）。无 IO、无 DB、无外部阻塞调用 —— 便于单测、增量计算与离线全量重算
（07 §5.1.1 计算架构：答题写库释放连接后再算；严格遵守持连铁律）。

设计要点（07 §5.1.2 + 全部可配置化，支持 A/B 实验 / system_config 下发）：
1. 仅消费「有 kp 标注」的作答记录（BR-M0-1-04：上游按 kp 分组后传入，本函数不再过滤）；
2. 时间衰减加权：w_i = exp(-(now - answered_at).days / lambda_days)；
3. 难度权重：难题正确的贡献更大（difficulty_weight = difficulty / max_difficulty）；
4. 加权正确率 C_adj（时间权重 × 难度权重）；
5. 用时因子 T：duration_ms=0 视为「无用时数据」，取中性 1.0（07 §3.2.2），不污染计算；
6. 连续正确 streak_bonus；
7. 与先验 prior 按总权重混合，clamp 到 [0,100]；
8. confidence = min(1, 有效样本数 / confidence_n)。

未作答知识点（records 为空）按 prior=20 兜底（BR-M0-1-02），但掌握度不可上线
（BR-M0-1-04），由上层 M3/M5 的 DoD 控制。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import exp
from typing import List, Optional

from app.models.mastery import level_from_mastery

ALGO_VERSION = "v1"


@dataclass
class AnswerRecord:
    """单条作答记录（上游按 kp 分组后传入 compute_mastery）。"""
    answered_at: datetime
    is_correct: bool
    duration_ms: int = 0            # 0 = 无用时数据（07 §3.2.2）
    difficulty: int = 3             # 1-5，缺省中等难度
    kp_id: int = 0                  # 冗余携带，便于上游分组/校验


@dataclass
class MasteryParams:
    """掌握度算法参数（全部可配置，支持 A/B 实验 / system_config 下发）。"""
    lambda_days: float = 30.0       # 时间衰减尺度：days/lambda 越大，权重越小
    prior: float = 20.0             # 先验掌握度（BR-M0-1-02：未作答 = 20 兜底）
    prior_weight: float = 2.0       # 先验等效样本权重（越大越保守，向 prior 拉）
    confidence_n: float = 20.0      # 达到满置信度所需有效样本数
    duration_ref_ms: int = 30000    # 参考用时：快于它 → T>1（加成），慢于 → T<1（减成）
    duration_t_min: float = 0.7     # 用时因子下界
    duration_t_max: float = 1.3     # 用时因子上界
    streak_bonus_per: float = 2.0   # 每连对 1 题的掌握度加分（百分点）
    streak_bonus_max: float = 10.0  # streak 加成上限（百分点）
    max_difficulty: int = 5         # 难度上限（用于难度权重归一）
    now: Optional[datetime] = None  # 衰减参考时刻；None → 取作答记录中最晚一条


@dataclass
class MasteryResult:
    """掌握度计算结果（对应 mastery_records 一列）。"""
    mastery: int
    level: str
    answer_count: int
    correct_count: int
    correct_rate: float             # 原始正确率 0-1（用于展示）
    avg_duration_ms: int
    last_answer_at: Optional[datetime]
    correct_streak: int
    confidence: float
    algo_version: str = ALGO_VERSION


def _time_weight(answered_at: datetime, now: datetime, lambda_days: float) -> float:
    """时间衰减权重：越近的作答权重越大。"""
    days = max(0.0, (now - answered_at).total_seconds() / 86400.0)
    return exp(-days / lambda_days)


def _difficulty_weight(difficulty: int, max_difficulty: int) -> float:
    """难度权重：难题正确的贡献更大，归一化到 (0, 1]。"""
    d = max(1, min(max_difficulty, difficulty))
    return d / float(max_difficulty)


def _duration_factor(duration_ms: int, p: MasteryParams) -> float:
    """用时因子 T：duration_ms=0 取中性 1.0；快于参考 → 加成，慢于 → 减成。"""
    if duration_ms <= 0:
        return 1.0
    ratio = p.duration_ref_ms / float(duration_ms)
    return max(p.duration_t_min, min(p.duration_t_max, ratio))


def _trailing_correct_streak(records: List[AnswerRecord]) -> int:
    """末尾连续正确次数（按时间升序，从最新一条往前数）。"""
    ordered = sorted(records, key=lambda r: r.answered_at)
    streak = 0
    for r in reversed(ordered):
        if r.is_correct:
            streak += 1
        else:
            break
    return streak


def compute_mastery(
    records: List[AnswerRecord],
    params: Optional[MasteryParams] = None,
) -> MasteryResult:
    """纯函数：计算单个知识点的掌握度。无 IO、无 DB、无外部调用。

    Args:
        records: 该知识点的作答记录（已按 kp 分组；空列表 → 走 prior 兜底）。
        params: 算法参数；None 用默认值（prior=20 等）。

    Returns:
        MasteryResult：掌握度分数/等级/统计字段/置信度。
    """
    p = params or MasteryParams()

    # BR-M0-1-02：未作答知识点按 prior 兜底，但不可上线（上层 DoD 控制）
    if not records:
        prior_int = int(round(p.prior))
        return MasteryResult(
            mastery=prior_int, level=level_from_mastery(prior_int),
            answer_count=0, correct_count=0, correct_rate=0.0,
            avg_duration_ms=0, last_answer_at=None, correct_streak=0,
            confidence=0.0,
        )

    now = p.now or max(r.answered_at for r in records)

    # 时间权重 × 难度权重 → 有效权重
    weights = [_time_weight(r.answered_at, now, p.lambda_days) for r in records]
    diff_w = [_difficulty_weight(r.difficulty, p.max_difficulty) for r in records]
    eff_w = [w * dw for w, dw in zip(weights, diff_w)]
    sum_eff = sum(eff_w)
    sum_time_w = sum(weights)

    # 加权正确率 C_adj（难度加权后的正确占比）
    weighted_correct = sum(
        e * (1 if r.is_correct else 0) for e, r in zip(eff_w, records)
    )
    c_adj = weighted_correct / sum_eff if sum_eff > 0 else 0.0

    # 用时因子（时间加权均值；0 用时已在 _duration_factor 内取中性 1.0）
    t_factors = [_duration_factor(r.duration_ms, p) for r in records]
    t = (sum(w * tf for w, tf in zip(weights, t_factors)) / sum_time_w
         if sum_time_w > 0 else 1.0)

    # 与先验混合：有效样本越多越偏离 prior
    m_prior = (c_adj * 100.0 * sum_eff + p.prior * p.prior_weight) / (
        sum_eff + p.prior_weight)

    # 连续正确加成
    streak = _trailing_correct_streak(records)
    streak_bonus = min(p.streak_bonus_max, streak * p.streak_bonus_per)

    mastery_raw = m_prior * t + streak_bonus
    mastery = int(max(0, min(100, round(mastery_raw))))

    # 展示用统计字段
    answer_count = len(records)
    correct_count = sum(1 for r in records if r.is_correct)
    correct_rate = correct_count / answer_count
    non_zero_dur = [r.duration_ms for r in records if r.duration_ms > 0]
    avg_duration_ms = int(sum(non_zero_dur) / len(non_zero_dur)) if non_zero_dur else 0
    confidence = min(1.0, sum_eff / p.confidence_n)

    return MasteryResult(
        mastery=mastery, level=level_from_mastery(mastery),
        answer_count=answer_count, correct_count=correct_count,
        correct_rate=correct_rate, avg_duration_ms=avg_duration_ms,
        last_answer_at=now, correct_streak=streak, confidence=confidence,
    )
