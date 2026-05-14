"""Pure numeric helpers: moving averages and reward composition.

Kept dependency-free so it can be unit-tested without FastAPI / Pydantic loaded.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

MA_WINDOW_DAYS = 7
DELAYED_OFFSET_DAYS = 3  # R_delayed compares t vs t-3 MA


def moving_average(values: Sequence[float], window: int = MA_WINDOW_DAYS) -> List[Optional[float]]:
    """Trailing simple moving average. None for indices where window isn't full yet."""
    if window <= 0:
        raise ValueError("window must be positive")
    out: List[Optional[float]] = []
    acc = 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= window:
            acc -= values[i - window]
        if i + 1 >= window:
            out.append(acc / window)
        else:
            out.append(None)
    return out


def ema(values: Sequence[float], alpha: float = 0.3) -> List[float]:
    """Exponential moving average. First value seeds the EMA."""
    if not values:
        return []
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    out: List[float] = [float(values[0])]
    for v in values[1:]:
        out.append(alpha * float(v) + (1.0 - alpha) * out[-1])
    return out


def reward_t(ma_series: Sequence[Optional[float]]) -> Optional[float]:
    """R_t = (W_avg,t-1 − W_avg,t) × 100. Needs at least 2 non-None tail values."""
    if len(ma_series) < 2:
        return None
    cur, prev = ma_series[-1], ma_series[-2]
    if cur is None or prev is None:
        return None
    return (prev - cur) * 100.0


def reward_delayed(ma_series: Sequence[Optional[float]], offset: int = DELAYED_OFFSET_DAYS) -> Optional[float]:
    """R_delayed compares MA at t vs t-offset; larger drop = larger reward."""
    if len(ma_series) <= offset:
        return None
    cur = ma_series[-1]
    past = ma_series[-1 - offset]
    if cur is None or past is None:
        return None
    return (past - cur) * 100.0 / offset


def compose_reward(
    r_weight: float,
    r_consistency: float,
    r_habit: float,
    r_goal: float,
    p_risk: float,
    *,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 1.0,
    delta: float = 1.0,
    lam: float = 1.0,
) -> float:
    """total = α·R_weight + β·R_consistency + γ·R_habit + δ·R_goal − λ·P_risk."""
    return (
        alpha * r_weight
        + beta * r_consistency
        + gamma * r_habit
        + delta * r_goal
        - lam * p_risk
    )


def blended_weight_reward(r_t: Optional[float], r_delayed: Optional[float]) -> float:
    """R_weight = 0.6·R_t + 0.4·R_delayed; fallback to whichever exists."""
    if r_t is None and r_delayed is None:
        return 0.0
    if r_delayed is None:
        return float(r_t or 0.0)
    if r_t is None:
        return float(r_delayed)
    return 0.6 * r_t + 0.4 * r_delayed


def slope_last_n(values: Sequence[float], n: int = 7) -> Optional[float]:
    """Least-squares slope over the last n points. None if fewer than 2 points."""
    series = [v for v in values[-n:] if v is not None]
    if len(series) < 2:
        return None
    xs = list(range(len(series)))
    mean_x = sum(xs) / len(xs)
    mean_y = sum(series) / len(series)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
