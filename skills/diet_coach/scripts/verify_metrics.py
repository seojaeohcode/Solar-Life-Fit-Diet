"""대회 성공 지표 중 로직 일관성 부분을 API 없이 스모크 검증한다.

실행: cd skills/diet_coach && python scripts/verify_metrics.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 패키지 없이 로컬 모듈 로드
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import encoding_bootstrap  # noqa: E402, F401

from models import ActivityMode, DailyEntry, DietMode, Journal, Phase  # noqa: E402
from policy import decide  # noqa: E402
from stats import detect_phase, reward_breakdown_last_step  # noqa: E402


def _entry(d: str, w: float) -> DailyEntry:
    return DailyEntry(date=d, weight_kg=w, diet=DietMode.NORMAL, activity=ActivityMode.ACTIVE)


def test_weight_up_lowers_r_weight_vs_down() -> None:
    """감량 추세 vs 증량 추세에서 R_weight 부호/크기 경향이 반대인지 (MA 기반)."""
    down = Journal(
        entries=[_entry(f"2026-05-{i:02d}", 80.0 - i * 0.15) for i in range(1, 12)]
    )
    up = Journal(
        entries=[_entry(f"2026-05-{i:02d}", 70.0 + i * 0.15) for i in range(1, 12)]
    )
    rd = reward_breakdown_last_step(down)
    ru = reward_breakdown_last_step(up)
    assert rd.R_weight > ru.R_weight, (rd.R_weight, ru.R_weight)


def test_plateau_triggers_a7() -> None:
    """평평한 체중 + plateau phase에서 탐색 A7이 나오는지."""
    os.environ["RLDIET_GOAL_KG"] = "65"
    flat = [72.0 + (i % 2) * 0.02 for i in range(10)]
    entries = [_entry(f"2026-04-{10+i:02d}", w) for i, w in enumerate(flat)]
    j = Journal(entries=entries)
    ph = detect_phase(j)
    assert ph == Phase.PLATEAU, ph
    rb = reward_breakdown_last_step(j)
    pol = decide(j, entries[-1], rb)
    assert pol.action_id == "A7", pol


def main() -> None:
    test_weight_up_lowers_r_weight_vs_down()
    test_plateau_triggers_a7()
    print("verify_metrics: OK")


if __name__ == "__main__":
    main()
