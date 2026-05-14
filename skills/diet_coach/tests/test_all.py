"""Solar Diet Master — 4단계 통합 테스트.

심사위원/사용자가 별도 환경 설정 없이 그대로 실행할 수 있도록 만든다.
콘솔이 cp949든 utf-8이든 한글이 깨지지 않는다 (encoding_bootstrap 자동 적용).

실행:
    cd skills/diet_coach
    python tests/test_all.py

단계:
    1) 자연어 추출      — Solar API가 "75.5kg, 삼겹살, 만보" 입력에서 필드 추출
    2) 7일 보상 계산    — MA 기반 R_weight, 정책 결정이 stats.py 로직대로 산출
    3) Solar 코칭 API   — UPSTAGE_API_KEY로 /api/coach 호출해 한국어 마크다운 응답
    4) 스킬 등록 확인   — SKILL.md frontmatter 유효성 + /skills 노출 조건
"""

from __future__ import annotations

import sys
from pathlib import Path

# 스킬 루트를 sys.path에 추가하고 콘솔 인코딩을 먼저 고정한다.
SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

import encoding_bootstrap  # noqa: F401, E402 — 가장 먼저 import

import datetime as dt  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from typing import Callable, List, Tuple  # noqa: E402


# --- 작은 테스트 유틸 --------------------------------------------------------

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[ ok ]"


def _header(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _expect(cond: bool, label: str) -> bool:
    print(f"  {PASS if cond else FAIL} {label}")
    return cond


# --- Test 1: 자연어 추출 -----------------------------------------------------

def test_extraction() -> bool:
    _header("Test 1: 자연어 추출 (Solar Chat + strict JSON schema)")
    from main import solar_extract_journal

    narrative = "오늘 아침 75.5kg, 어제 삼겹살 먹었지만 만보 걸었어"
    print(f"  입력: {narrative}")
    out = solar_extract_journal(narrative)
    payload = out.model_dump(mode="json")
    print(f"  추출 JSON: {json.dumps(payload, ensure_ascii=False)}")

    ok = True
    ok &= _expect(out.weight_kg == 75.5, f"weight_kg == 75.5 (got {out.weight_kg})")
    ok &= _expect(out.steps == 10000, f"steps == 10000 ('만보' 해석, got {out.steps})")
    ok &= _expect(out.calories_in is None, f"calories_in is null (got {out.calories_in})")
    ok &= _expect(out.sleep_hours is None, f"sleep_hours is null (got {out.sleep_hours})")
    ok &= _expect(
        any("삼겹살" in k for k in out.diet_keywords),
        f"diet_keywords 에 '삼겹살' 포함 (got {out.diet_keywords})",
    )
    return ok


# --- Test 2: 7일 보상 계산 ---------------------------------------------------

def test_reward_seven_days() -> bool:
    _header("Test 2: 7일 보상 계산 (MA → R_weight → 정책)")
    from models import ActivityMode, DailyEntry, DietMode, Journal
    from policy import decide
    from stats import detect_phase, journal_timeseries, reward_breakdown_last_step
    from utils import MA_WINDOW_DAYS

    # 10일치 가짜 데이터: 75.0 → 73.65 (약 -0.15kg/일)
    entries: List[DailyEntry] = []
    base = dt.date(2026, 5, 5)
    for i in range(10):
        entries.append(
            DailyEntry(
                date=(base + dt.timedelta(days=i)).isoformat(),
                weight_kg=75.0 - i * 0.15,
                calories_in=1600.0,
                steps=8500,
                sleep_hours=6.8,
                sleep_quality=0.7,
                exercises_done=["걷기 30분"] if i % 2 else [],
                diet=DietMode.NORMAL,
                activity=ActivityMode.ACTIVE,
            )
        )
    journal = Journal(entries=entries)

    series = journal_timeseries(journal)
    last_ma = series[-1]["ma7"]
    expected_ma = sum(e.weight_kg for e in entries[-MA_WINDOW_DAYS:]) / MA_WINDOW_DAYS
    print(f"  최신 MA7 = {last_ma:.4f}  (직접 평균 = {expected_ma:.4f})")

    rb = reward_breakdown_last_step(journal)
    print(
        f"  R_t={rb.R_t}  R_delayed={rb.R_delayed}  R_weight={rb.R_weight:.3f}  "
        f"R_habit={rb.R_habit:.3f}  P_risk={rb.P_risk:.3f}  total={rb.total:.3f}"
    )

    phase = detect_phase(journal)
    decision = decide(journal, entries[-1], rb)
    print(f"  phase={phase}  policy={decision.action_id} ({decision.mode})  msg={decision.message}")

    ok = True
    ok &= _expect(abs(last_ma - expected_ma) < 1e-9, "MA7 == 수동 평균")
    ok &= _expect(rb.R_weight > 0, f"감량 추세 → R_weight > 0 (got {rb.R_weight:.3f})")
    ok &= _expect(rb.total > 0, f"total > 0 (got {rb.total:.3f})")
    ok &= _expect(decision.action_id in {"A1", "A4", "A9"}, f"감량 정책 → A1/A4/A9 (got {decision.action_id})")
    return ok


# --- Test 3: Solar 코칭 API --------------------------------------------------

def test_coach_api() -> bool:
    _header("Test 3: Solar API 코칭 (.env의 UPSTAGE_API_KEY → 한국어 마크다운)")
    import datetime as _dt

    from fastapi.testclient import TestClient

    import main as m
    from models import ActivityMode, DailyEntry, DietMode, Journal

    # 8일 시드: MA 보상이 첫 값을 갖도록
    seed = Journal(
        entries=[
            DailyEntry(
                date=(_dt.date(2026, 5, 7) + _dt.timedelta(days=i)).isoformat(),
                weight_kg=75.0 - i * 0.1,
                calories_in=1600.0,
                steps=8500,
                sleep_hours=6.8,
                sleep_quality=0.7,
                exercises_done=["걷기 30분"] if i % 2 else [],
                diet=DietMode.NORMAL,
                activity=ActivityMode.ACTIVE,
            )
            for i in range(8)
        ]
    )
    m._save_journal(seed)

    client = TestClient(m.app)

    meta = client.get("/api/meta").json()
    print(f"  /api/meta model={meta['model']}  api_key_set={meta['api_key_set']}")

    prog = client.get("/api/progress").json()
    print(
        f"  /api/progress reward.total={prog['reward']['total']:.3f}  "
        f"R_weight={prog['reward']['R_weight']:.3f}  "
        f"policy={prog['policy']['action_id']}  phase={prog['phase']}"
    )

    pc = client.post("/api/proactive_check").json()
    print(f"  /api/proactive_check has_warnings={pc['has_warnings']}")

    r = client.post("/api/coach", json={"session_caution": "무리하지 않게"})
    data = r.json()
    print(f"  /api/coach status={r.status_code}  warnings={len(data['proactive_warnings'])}")
    print("  --- coaching markdown (앞 400자) ---")
    print(data["coaching_markdown"][:400])
    print("  ------------------------------------")

    ok = True
    ok &= _expect(meta["api_key_set"], "UPSTAGE_API_KEY 로드됨")
    ok &= _expect(r.status_code == 200, f"/api/coach 200 (got {r.status_code})")
    md = data["coaching_markdown"]
    ok &= _expect(len(md) > 200, f"마크다운 길이 > 200 (got {len(md)})")
    ok &= _expect(re.search(r"[가-힣]", md) is not None, "한글이 포함됨")
    ok &= _expect("MA" in md or "이동평균" in md, "MA/이동평균 언급")
    return ok


# --- Test 4: 스킬 등록 / 발견 ------------------------------------------------

def test_skill_registration() -> bool:
    _header("Test 4: 스킬 등록 — SKILL.md frontmatter & /skills 노출")
    skill_md = SKILL_DIR / "SKILL.md"
    ok = True
    ok &= _expect(skill_md.exists(), "SKILL.md 존재")
    text = skill_md.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    ok &= _expect(fm is not None, "YAML frontmatter 블록 존재")
    if fm:
        block = fm.group(1)
        # 의존성 없이 간단 파싱 (key: value 단일라인만)
        meta = {}
        for line in block.splitlines():
            mline = re.match(r"^(\w+):\s*(.+)$", line)
            if mline:
                meta[mline.group(1)] = mline.group(2).strip()
        print(f"  frontmatter.name = {meta.get('name')}")
        print(f"  frontmatter.description (앞 80자) = {meta.get('description','')[:80]}...")
        ok &= _expect(meta.get("name") == "solar-diet-master", "name == 'solar-diet-master'")
        ok &= _expect(len(meta.get("description", "")) > 80, "description 길이 > 80자 (트리거 신호 충분)")

    expected = {"SKILL.md", "main.py", "models.py", "stats.py", "policy.py", "utils.py", "encoding_bootstrap.py"}
    actual = {p.name for p in SKILL_DIR.iterdir() if p.is_file()}
    missing = expected - actual
    ok &= _expect(not missing, f"필수 파일 모두 존재 (누락 {missing or '없음'})")

    data_dir = SKILL_DIR / "data"
    ok &= _expect(data_dir.is_dir(), "data/ 폴더 존재")

    print()
    print("  /skills 자동 노출 안내:")
    print("    - 이 스킬은 표준 Anthropic Skill 포맷이며 frontmatter가 유효합니다.")
    print("    - Claude Code 세션이 이 디렉터리를 인식하면 /skills 목록에 'solar-diet-master'로 나타납니다.")
    print("    - 다른 스킬과 함께 marketplace 배포가 필요하면 .claude-plugin/marketplace.json의")
    print("      plugins 배열에 diet_coach 항목을 추가하고 /plugin install로 등록하면 됩니다.")
    return ok


# --- Runner ------------------------------------------------------------------

def main() -> int:
    print("Solar Diet Master — Skillthon 4단계 통합 테스트")
    print(f"스킬 디렉터리: {SKILL_DIR}")

    tests: List[Tuple[str, Callable[[], bool]]] = [
        ("자연어 추출", test_extraction),
        ("7일 보상 계산", test_reward_seven_days),
        ("Solar 코칭 API", test_coach_api),
        ("스킬 등록 확인", test_skill_registration),
    ]

    results: List[Tuple[str, bool, str]] = []
    for name, fn in tests:
        try:
            ok = fn()
            results.append((name, ok, ""))
        except Exception as e:  # noqa: BLE001 — 한 테스트가 실패해도 나머지 진행
            results.append((name, False, f"{type(e).__name__}: {e}"))
            print(f"  {FAIL} 예외 발생: {type(e).__name__}: {e}")

    _header("최종 요약")
    all_ok = True
    for name, ok, err in results:
        tag = PASS if ok else FAIL
        line = f"  {tag} {name}"
        if err:
            line += f"  ({err})"
        print(line)
        all_ok = all_ok and ok

    print()
    print("종합:", PASS if all_ok else FAIL)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
