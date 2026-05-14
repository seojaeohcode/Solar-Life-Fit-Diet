"""Heuristic policy A1~A9 (diet.md §5.2).

Decides next (diet, activity) mode and a one-line guidance message from the
current journal + freshly-saved entry + reward breakdown.

Action map:
  A1 — exploit / maintain (progressing well)
  A2 — exploit / slight diet bump (mild stagnation, low risk)
  A3 — exploit / slight activity bump (mild stagnation, low risk)
  A4 — exploit / reduce intensity (rapid loss but no risk flag yet)
  A5 — explore / sleep recovery focus (sleep deficit dominant)
  A6 — explore / hydration & meal regularity (low-cal pattern but no alert)
  A7 — explore / cycle diet+activity bump (stagnation ≥2 days)
  A8 — safety / fall back to Normal+Active (risk_penalty ≥ 8)
  A9 — exploit / micro-adjust (catch-all default)
"""

from __future__ import annotations

import os
import statistics
from typing import Optional

from models import (
    ActivityMode,
    DailyEntry,
    DietMode,
    Journal,
    Phase,
    PolicyDecision,
    RewardBreakdown,
)
from stats import RISK_WINDOW_DAYS, STAGNATION_REWARD_EPS, detect_phase
from utils import slope_last_n

RISK_PENALTY_SAFETY_THRESHOLD = float(os.getenv("RLDIET_SAFETY_THRESHOLD", "8.0"))
GAMMA = float(os.getenv("RLDIET_DISCOUNT", "0.9"))


def _bump_diet(d: DietMode) -> DietMode:
    return {DietMode.FAST: DietMode.NORMAL, DietMode.NORMAL: DietMode.DEFICIT, DietMode.DEFICIT: DietMode.NORMAL}[d]


def _bump_activity(a: ActivityMode) -> ActivityMode:
    return {ActivityMode.REST: ActivityMode.ACTIVE, ActivityMode.ACTIVE: ActivityMode.INTENSE, ActivityMode.INTENSE: ActivityMode.ACTIVE}[a]


def _is_stagnant(journal: Journal, reward: RewardBreakdown) -> bool:
    if len(journal.entries) < 3:
        return False
    weights = [e.weight_kg for e in journal.entries]
    slope = slope_last_n(weights, n=7)
    if slope is None:
        return False
    return abs(slope) < 0.02 and abs(reward.total) < STAGNATION_REWARD_EPS * 100.0


def _explore_bump_plateau_or_stagnation(journal: Journal, reward: RewardBreakdown) -> bool:
    """평가지표(로직 일관성): stats의 Plateau phase이거나 정체 보상 패턴이면 A7 탐색을 허용."""
    if len(journal.entries) < 7:
        return _is_stagnant(journal, reward)
    phase = detect_phase(journal)
    weights = [e.weight_kg for e in journal.entries]
    slope = slope_last_n(weights, n=7)
    flat = slope is not None and abs(slope) < 0.03
    if phase == Phase.PLATEAU and flat:
        return True
    return _is_stagnant(journal, reward)


def _is_progressing(reward: RewardBreakdown, journal: Journal) -> bool:
    if reward.total <= 0:
        return False
    weights = [e.weight_kg for e in journal.entries]
    slope = slope_last_n(weights, n=7)
    return slope is None or slope < 0.0


def _sleep_deficit(journal: Journal) -> bool:
    recent = journal.entries[-RISK_WINDOW_DAYS:]
    sleeps = [e.sleep_hours for e in recent if e.sleep_hours is not None]
    return bool(sleeps) and statistics.mean(sleeps) < 5.5


def _low_cal_pattern(journal: Journal) -> bool:
    recent = journal.entries[-RISK_WINDOW_DAYS:]
    cals = [e.calories_in for e in recent if e.calories_in is not None]
    return bool(cals) and 1000.0 <= statistics.mean(cals) < 1300.0


def _rapid_loss_no_risk(journal: Journal, reward: RewardBreakdown) -> bool:
    if reward.P_risk >= RISK_PENALTY_SAFETY_THRESHOLD:
        return False
    weights = [e.weight_kg for e in journal.entries[-RISK_WINDOW_DAYS:]]
    if len(weights) < 2:
        return False
    return (weights[0] - weights[-1]) > 1.2


def decide(journal: Journal, last_entry: DailyEntry, reward: RewardBreakdown) -> PolicyDecision:
    diet = last_entry.diet
    activity = last_entry.activity

    # A8 — safety overrides everything
    if reward.P_risk >= RISK_PENALTY_SAFETY_THRESHOLD:
        new_activity = ActivityMode.ACTIVE if activity == ActivityMode.INTENSE else activity
        return PolicyDecision(
            mode="safety",
            action_id="A8",
            diet=DietMode.NORMAL,
            activity=new_activity,
            message="위험 신호가 누적됐어요. 강도를 낮추고 정상 식이로 회복에 집중하세요.",
        )

    # A4 — rapid loss but no alert yet → slow down before it becomes risk
    if _rapid_loss_no_risk(journal, reward):
        new_activity = ActivityMode.ACTIVE if activity == ActivityMode.INTENSE else activity
        return PolicyDecision(
            mode="exploit",
            action_id="A4",
            diet=DietMode.NORMAL if diet != DietMode.NORMAL else diet,
            activity=new_activity,
            message="감량 속도가 빠릅니다. 칼로리·운동 강도를 살짝 완화해 안정적인 페이스로 이어가세요.",
        )

    # A5 — sleep deficit dominant
    if _sleep_deficit(journal):
        return PolicyDecision(
            mode="explore",
            action_id="A5",
            diet=diet,
            activity=ActivityMode.ACTIVE,
            message="최근 수면이 부족해요. 오늘은 강도보다 회복을 우선하고 잠을 1시간 더 확보해 보세요.",
        )

    # A6 — low-cal pattern (1000~1300) without risk alert → meal regularity
    if _low_cal_pattern(journal):
        return PolicyDecision(
            mode="explore",
            action_id="A6",
            diet=DietMode.NORMAL,
            activity=activity,
            message="섭취가 다소 낮습니다. 끼니 거르지 말고 단백질·물 섭취를 보강하세요.",
        )

    # A7 — Plateau phase 또는 정체(MA 기울기≈0 + 낮은 보상) → 탐색적으로 식단·활동 순환
    if _explore_bump_plateau_or_stagnation(journal, reward) and len(journal.entries) >= 2:
        return PolicyDecision(
            mode="explore",
            action_id="A7",
            diet=_bump_diet(diet),
            activity=_bump_activity(activity),
            message="정체기(Plateau) 또는 MA 기준 횡보 구간으로 보입니다. 식단·활동 단계를 한 칸씩 바꿔 새 자극을 줘 봅시다.",
        )

    # A1 — progressing well (total > 0 AND slope ≤ 0 or unknown)
    if _is_progressing(reward, journal):
        return PolicyDecision(
            mode="exploit",
            action_id="A1",
            diet=diet,
            activity=activity,
            message="현 페이스가 좋습니다. 같은 식이·활동을 유지하세요.",
        )

    # A2 — mild stagnation, low risk → small diet tweak
    if reward.total <= 0 and reward.P_risk < RISK_PENALTY_SAFETY_THRESHOLD / 2:
        return PolicyDecision(
            mode="exploit",
            action_id="A2",
            diet=_bump_diet(diet),
            activity=activity,
            message="총보상이 약합니다. 식단만 한 단계 조정해 반응을 확인하세요.",
        )

    # A3 — mild stagnation, low risk, but want activity change instead
    if reward.R_weight <= 0 and reward.R_habit > 0.4:
        return PolicyDecision(
            mode="exploit",
            action_id="A3",
            diet=diet,
            activity=_bump_activity(activity),
            message="습관 점수는 괜찮으니 활동 강도만 한 단계 올려 봅시다.",
        )

    # A9 — catch-all default
    return PolicyDecision(
        mode="exploit",
        action_id="A9",
        diet=diet,
        activity=activity,
        message="현 상태를 유지하면서 수분·끼니 간격 같은 미세 조정에 집중하세요.",
    )
