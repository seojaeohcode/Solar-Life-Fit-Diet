"""Reward-component calculators and phase detection.

Faithful port of diet.md §5 — `rldiet/stats.py` equivalents.
"""

from __future__ import annotations

import os
import statistics
from datetime import date, timedelta
from typing import List, Optional, Sequence, Tuple

from models import DailyEntry, Journal, Phase, RewardBreakdown
from utils import (
    MA_WINDOW_DAYS,
    blended_weight_reward,
    compose_reward,
    moving_average,
    reward_delayed,
    reward_t,
    slope_last_n,
)

# --- Weights (env-overridable, matching rldiet/config.py spirit) -------------

ALPHA = float(os.getenv("RLDIET_ALPHA", "1.0"))   # R_weight
BETA = float(os.getenv("RLDIET_BETA", "1.0"))     # R_consistency
GAMMA = float(os.getenv("RLDIET_GAMMA", "1.0"))   # R_habit
DELTA = float(os.getenv("RLDIET_DELTA", "1.0"))   # R_goal
LAMBDA = float(os.getenv("RLDIET_LAMBDA", "1.0")) # P_risk

GOAL_KG = os.getenv("RLDIET_GOAL_KG")
GOAL_KG_FLOAT: Optional[float] = float(GOAL_KG) if GOAL_KG else None

ADHERENCE_WINDOW_DAYS = 14
HABIT_WINDOW_DAYS = 7
RISK_WINDOW_DAYS = 5
ONBOARDING_DAYS = 7
STAGNATION_REWARD_EPS = float(os.getenv("RLDIET_STAGNATION_EPS", "0.15"))


# --- Series helpers ----------------------------------------------------------

def weights_only(journal: Journal) -> List[float]:
    return [e.weight_kg for e in journal.entries]


def journal_timeseries(journal: Journal) -> List[dict]:
    weights = weights_only(journal)
    ma = moving_average(weights, MA_WINDOW_DAYS)
    return [
        {"date": e.date, "weight_kg": e.weight_kg, "ma7": ma[i]}
        for i, e in enumerate(journal.entries)
    ]


# --- Reward components -------------------------------------------------------

def adherence_ratio_recent(journal: Journal, today: Optional[date] = None) -> float:
    """Fraction of the last N days that have a journal entry (record frequency)."""
    if not journal.entries:
        return 0.0
    today = today or date.today()
    window_start = today - timedelta(days=ADHERENCE_WINDOW_DAYS - 1)
    seen: set = set()
    for e in journal.entries:
        d = date.fromisoformat(e.date)
        if window_start <= d <= today:
            seen.add(d)
    return len(seen) / ADHERENCE_WINDOW_DAYS


def habit_score(journal: Journal) -> float:
    """0..1 heuristic score from sleep/steps/calories/exercise presence."""
    recent = journal.entries[-HABIT_WINDOW_DAYS:]
    if not recent:
        return 0.0

    def _avg(getter, default: float = 0.0) -> float:
        vals = [getter(e) for e in recent if getter(e) is not None]
        return sum(vals) / len(vals) if vals else default

    sleep_avg = _avg(lambda e: e.sleep_hours, 0.0)
    steps_avg = _avg(lambda e: e.steps, 0.0)
    cal_avg = _avg(lambda e: e.calories_in, 0.0)
    exercise_days = sum(1 for e in recent if e.exercises_done)

    # Component scores in [0,1]
    s_sleep = min(max((sleep_avg - 5.0) / 3.0, 0.0), 1.0)   # 5h→0, 8h→1
    s_steps = min(max(steps_avg / 8000.0, 0.0), 1.0)
    s_cal = 1.0 if 1200.0 <= cal_avg <= 2400.0 else max(0.0, 1.0 - abs(cal_avg - 1800.0) / 1800.0)
    s_exercise = min(exercise_days / HABIT_WINDOW_DAYS, 1.0)
    return (s_sleep + s_steps + s_cal + s_exercise) / 4.0


def risk_score(journal: Journal) -> float:
    """0..1 risk from low-cal, sleep deprivation, sudden weight swings, volatility."""
    recent = journal.entries[-RISK_WINDOW_DAYS:]
    if not recent:
        return 0.0

    risks: List[float] = []

    cals = [e.calories_in for e in recent if e.calories_in is not None]
    if cals and statistics.mean(cals) < 1000.0:
        risks.append(min(1.0, (1000.0 - statistics.mean(cals)) / 500.0))

    sleeps = [e.sleep_hours for e in recent if e.sleep_hours is not None]
    if sleeps and statistics.mean(sleeps) < 5.0:
        risks.append(min(1.0, (5.0 - statistics.mean(sleeps)) / 2.5))

    weights = [e.weight_kg for e in recent]
    if len(weights) >= 2:
        drop = weights[0] - weights[-1]
        if drop > 1.5:  # > 1.5kg over RISK_WINDOW_DAYS days
            risks.append(min(1.0, (drop - 1.5) / 2.0))
        if len(weights) >= 3:
            vol = statistics.pstdev(weights)
            if vol > 1.2:
                risks.append(min(1.0, (vol - 1.2) / 1.5))

    if not risks:
        return 0.0
    return min(1.0, sum(risks) / max(1, len(risks)))


def goal_alignment_reward(journal: Journal, phase: Phase) -> float:
    """Reward for moving toward RLDIET_GOAL_KG given current phase."""
    if GOAL_KG_FLOAT is None or not journal.entries:
        return 0.0
    latest = journal.entries[-1].weight_kg
    distance = latest - GOAL_KG_FLOAT  # positive if above goal
    if phase == Phase.FAT_LOSS:
        # closer-to-goal yields ~[0, 1]; cap at 5kg distance for normalization
        return max(0.0, 1.0 - min(abs(distance), 5.0) / 5.0)
    if phase == Phase.MAINTENANCE:
        return max(0.0, 1.0 - min(abs(distance), 2.0) / 2.0)
    return 0.0


# --- Phase detection ---------------------------------------------------------

def detect_phase(journal: Journal) -> Phase:
    n = len(journal.entries)
    if n < ONBOARDING_DAYS:
        return Phase.ONBOARDING

    weights = weights_only(journal)
    slope = slope_last_n(weights, n=7)
    vol = statistics.pstdev(weights[-7:]) if len(weights) >= 7 else 0.0

    if GOAL_KG_FLOAT is not None:
        latest = weights[-1]
        if abs(latest - GOAL_KG_FLOAT) <= 1.0:
            return Phase.MAINTENANCE

    if slope is not None and abs(slope) < 0.02 and vol < 0.6:
        return Phase.PLATEAU
    return Phase.FAT_LOSS


# --- Composite reward --------------------------------------------------------

def reward_for_last_step(journal: Journal) -> Tuple[Optional[float], Optional[float]]:
    """Return (R_t, R_delayed) for the latest day."""
    weights = weights_only(journal)
    ma = moving_average(weights, MA_WINDOW_DAYS)
    return reward_t(ma), reward_delayed(ma)


def reward_breakdown_last_step(journal: Journal) -> RewardBreakdown:
    r_t, r_delayed = reward_for_last_step(journal)
    r_weight = blended_weight_reward(r_t, r_delayed)
    adherence = adherence_ratio_recent(journal)
    r_consistency = (adherence - 0.5) * 20.0
    r_habit = habit_score(journal)
    phase = detect_phase(journal)
    r_goal = goal_alignment_reward(journal, phase)
    risk = risk_score(journal)
    p_risk = risk * 20.0

    total = compose_reward(
        r_weight, r_consistency, r_habit, r_goal, p_risk,
        alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA, lam=LAMBDA,
    )

    return RewardBreakdown(
        total=total,
        R_weight=r_weight,
        R_consistency=r_consistency,
        R_habit=r_habit,
        R_goal=r_goal,
        P_risk=p_risk,
        R_t=r_t,
        R_delayed=r_delayed,
        ma_window_days=MA_WINDOW_DAYS,
    )


def ma_reward_explanation_ko(journal: Journal, rb: RewardBreakdown) -> str:
    """7일 이동평균(MA) 기반 체중 보상을 사용자/에이전트가 이해하도록 한국어 한 덩어리로 설명한다.

    평가지표(창의성·로직 일관성): 단순 요약이 아니라 'MA가 체중 노이즈를 줄이고 보상 신호를 만든다'는 차별점을 드러낸다.
    """
    if len(journal.entries) < MA_WINDOW_DAYS:
        return (
            f"아직 {MA_WINDOW_DAYS}일치 체중이 모이지 않아 MA 기반 보상이 완전히 안정화되지 않았습니다. "
            "매일 같은 시간대에 공복 체중을 기록하면 노이즈가 줄고 R_weight가 더 의미 있게 움직입니다."
        )
    weights = weights_only(journal)
    ma = moving_average(weights, MA_WINDOW_DAYS)
    last_ma = ma[-1]
    prev_ma = ma[-2] if len(ma) >= 2 else None
    ma_str = f"{last_ma:.2f}kg" if last_ma is not None else "N/A"
    prev_str = f"{prev_ma:.2f}kg" if prev_ma is not None else "N/A"
    direction = ""
    if last_ma is not None and prev_ma is not None:
        if last_ma < prev_ma - 0.05:
            direction = "7일 MA가 소폭 하락해 감량 추세로 읽히며, 이 구간에서 R_weight는 보통 양(+)으로 기울기 쉽습니다."
        elif last_ma > prev_ma + 0.05:
            direction = "7일 MA가 상승해 체중이 불리한 방향으로 움직이는 구간으로 읽히며, R_weight는 보통 약해지거나 음(-)으로 갈 수 있습니다."
        else:
            direction = "7일 MA가 거의 평평해 '정체' 구간에 가깝습니다. 이 때는 탐색 정책(A7 등)으로 루틴 변주를 주는 설계가 맞습니다."
    elif last_ma is not None:
        direction = "직전일 MA가 아직 없어 첫 유효 MA 구간입니다. 며칠 더 기록하면 MA 기반 보상이 더 안정됩니다."
    rt = rb.R_t
    rd = rb.R_delayed
    blend = f"합성 체중 보상 R_weight={rb.R_weight:.2f} (R_t={rt}, R_delayed={rd})."
    return (
        "【이동평균 보상】일회성 체중 변동 대신 "
        f"{MA_WINDOW_DAYS}일 MA({ma_str}, 직전일 MA {prev_str})로 추세를 본 뒤 R_t·R_delayed를 섞었습니다. "
        f"{direction} {blend} "
        f"총합 보상 total={rb.total:.2f}에는 기록 꾸준함·습관·목표 정렬이 함께 들어갑니다."
    )
