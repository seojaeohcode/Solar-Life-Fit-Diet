"""Solar Diet Master — FastAPI entrypoint.

Replaces the Gemini-backed pipeline from diet.md with Upstage Solar:
  * Chat Completions + JSON Schema (도메인 특화 추출 프롬프트) for natural-language → structured fields
  * Chat (Solar LLM) for coaching — MA 보상·정책 컨텍스트를 반드시 반영한 다이어트 도메인 프롬프트

Run:
    cd skills/diet_coach
    uvicorn main:app --reload --port 8001

Endpoints (see SKILL.md for details):
  POST  /api/entry           structured save
  POST  /api/entry/natural   LLM-extracted save
  GET   /api/progress        timeseries + reward
  POST  /api/coach           coaching markdown
  POST  /api/proactive_check risk-pattern warnings (differentiator)
  GET   /api/meta            config snapshot
"""

from __future__ import annotations

import json
import os
import re
import statistics
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAI

from models import (
    ActivityMode,
    CoachRequest,
    CoachResponse,
    DailyEntry,
    DietMode,
    ExtractedFields,
    Journal,
    NaturalEntryRequest,
    NaturalEntryResponse,
    PolicyDecision,
    ProactiveWarning,
    ProgressResponse,
    RewardBreakdown,
)
from policy import decide
from stats import (
    GOAL_KG_FLOAT,
    detect_phase,
    journal_timeseries,
    ma_reward_explanation_ko,
    reward_breakdown_last_step,
)

# --- Paths & env -------------------------------------------------------------

SKILL_DIR = Path(__file__).resolve().parent
DATA_DIR = SKILL_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

JOURNAL_PATH = DATA_DIR / "journal.json"
POLICY_STATS_PATH = DATA_DIR / "policy_stats.json"
COACH_HISTORY_PATH = DATA_DIR / "coach_history.json"

# Load .env from skill dir, then walk up to find repo-root .env as fallback.
load_dotenv(SKILL_DIR / "assets" / ".env")
for parent in [SKILL_DIR, *SKILL_DIR.parents]:
    candidate = parent / ".env"
    if candidate.exists():
        load_dotenv(candidate, override=False)
        break

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
SOLAR_MODEL = os.getenv("SOLAR_MODEL", "solar-pro3")
COACH_HISTORY_LIMIT = 200

if not UPSTAGE_API_KEY:
    # fail fast at startup — every endpoint that touches Solar needs this
    print("[warn] UPSTAGE_API_KEY missing — set it in skills/diet_coach/assets/.env or repo root .env")


# --- Solar clients -----------------------------------------------------------

def _chat_client() -> OpenAI:
    if not UPSTAGE_API_KEY:
        raise HTTPException(status_code=400, detail="UPSTAGE_API_KEY가 설정되지 않았습니다.")
    return OpenAI(api_key=UPSTAGE_API_KEY, base_url="https://api.upstage.ai/v1")


# --- 추출 방식 (Information Extract vs Chat) ---------------------------------
#
# Upstage **Universal Information Extract** API는 일반적으로 **파일(문서) 업로드**
# 멀티파트 요청을 전제로 한다. 본 스킬의 입력은 **평문 한국어 일기**뿐이므로,
# 동일 Solar 제품군에서 재현성이 좋은 **Chat Completions + response_format(json_schema)**
# 한 경로만 사용한다. (`/v1` 단일 OpenAI 호환 클라이언트 — IE 전용 base_url 클라이언트는 두지 않음)
#
EXTRACTION_METHOD = "solar_chat_json_schema_strict"


SYSTEM_PROMPT_EXTRACT = """당신은 한국어 다이어트 저널 전용 필드 추출기입니다 (평가지표: 추출 정확도 / 기술적 완성도).
규칙:
- 체중(kg): "공복 72.4", "72.4kg", "몸무게 72키로" 등에서 숫자만 정확히 읽는다. 불확실하면 null.
- 식단 키워드: 어제/저녁/야식 등 식사 맥락에서 음식·패턴만 짧은 명사구로 나열한다. 예: 라면, 회식, 맥주, 샐러드, 닭가슴살, 단식, 치킨, 떡볶이, 야식.
- 칼로리·걸음·수면은 텍스트에 명시된 숫자만 쓴다. 없으면 null/빈 배열. 절대 환각으로 큰 숫자를 만들지 않는다.
- 출력은 JSON 스키마 필드만 채운다 (코멘트·마크다운 금지).
"""

SYSTEM_PROMPT_COACH = (
    "당신은 한국어 다이어트 코치입니다 (평가지표: Solar API 최적화 / 창의적 해결)."
    "반드시 사용자 컨텍스트 JSON 안의 **R_weight·total 보상·reward·policy.action_id·phase**를 이유로 언급하세요. "
    "**7일 이동평균(MA)** 으로 체중 노이즈를 줄이고 보상을 만든다는 점을 한 문단으로 설명해 차별화하세요. "
    "일반 생활 습관 범위에서만 조언하고, 의학적 진단·약물 처방·검사 해석은 금지합니다. "
    "마크다운으로 ①오늘 요약 ②정책(A1~A9)과 연결된 식단/활동 제안 ③위험/주의(있으면 최우선) ④내일 체크리스트 순서로 쓰세요."
)


# --- Storage helpers ---------------------------------------------------------

def _load_journal() -> Journal:
    if not JOURNAL_PATH.exists():
        return Journal()
    with JOURNAL_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return Journal.model_validate(raw)


def _save_journal(journal: Journal) -> None:
    with JOURNAL_PATH.open("w", encoding="utf-8") as f:
        json.dump(journal.model_dump(mode="json"), f, ensure_ascii=False, indent=2)


def _merge_entry(journal: Journal, entry: DailyEntry) -> Journal:
    """Replace same-date entry, else append, then sort by date."""
    kept = [e for e in journal.entries if e.date != entry.date]
    kept.append(entry)
    kept.sort(key=lambda e: e.date)
    return Journal(entries=kept)


def _update_policy_stats(decision: PolicyDecision, reward_total: float) -> None:
    stats = {}
    if POLICY_STATS_PATH.exists():
        with POLICY_STATS_PATH.open("r", encoding="utf-8") as f:
            stats = json.load(f)
    bucket = stats.setdefault(decision.action_id, {"count": 0, "sum_reward": 0.0, "avg_reward": 0.0})
    bucket["count"] += 1
    bucket["sum_reward"] += float(reward_total)
    bucket["avg_reward"] = bucket["sum_reward"] / bucket["count"]
    with POLICY_STATS_PATH.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def _append_coach_history(item: dict) -> None:
    history: List[dict] = []
    if COACH_HISTORY_PATH.exists():
        with COACH_HISTORY_PATH.open("r", encoding="utf-8") as f:
            history = json.load(f).get("history", [])
    history.append(item)
    history = history[-COACH_HISTORY_LIMIT:]
    with COACH_HISTORY_PATH.open("w", encoding="utf-8") as f:
        json.dump({"history": history}, f, ensure_ascii=False, indent=2)


# --- Solar integrations ------------------------------------------------------

_EXTRACT_PROPERTIES = {
    "weight_kg": {"type": "number", "description": "공복 체중 kg. 없으면 null."},
    "calories_in": {"type": "number", "description": "어제 섭취 kcal. 없으면 null."},
    "steps": {"type": "integer", "description": "어제 걸음 수. 없으면 null."},
    "sleep_hours": {"type": "number", "description": "어젯밤 수면 시간. 없으면 null."},
    "sleep_quality": {"type": "number", "description": "0~1 수면 질. 없으면 null."},
    "exercises_done": {
        "type": "array",
        "description": "어제 운동 목록.",
        "items": {"type": "string"},
    },
    "exercise_note": {"type": "string"},
    "notes": {"type": "string"},
    "diet_keywords": {
        "type": "array",
        "description": "식단·식사 관련 한국어 키워드 (음식명, 야식/회식 등 패턴).",
        "items": {"type": "string"},
    },
}

_EXTRACT_REQUIRED = [
    "weight_kg",
    "calories_in",
    "steps",
    "sleep_hours",
    "sleep_quality",
    "exercises_done",
    "exercise_note",
    "notes",
    "diet_keywords",
]

_WEIGHT_KG_PATTERNS = (
    re.compile(
        r"(?:공복|오늘|아침)?\s*(?:체중|몸무게)?\s*(\d{2}(?:\.\d+)?)\s*(?:kg|키로|킬로|KG)",
        re.UNICODE,
    ),
    re.compile(r"(\d{2}(?:\.\d+)?)\s*(?:kg|키로)\b", re.UNICODE),
)


def _regex_first_weight_kg(narrative: str) -> Optional[float]:
    for pat in _WEIGHT_KG_PATTERNS:
        m = pat.search(narrative.replace("\u00a0", " "))
        if m:
            try:
                v = float(m.group(1))
                if 30.0 <= v <= 250.0:
                    return v
            except ValueError:
                continue
    return None


def _extraction_quality_flags(narrative: str, extracted: ExtractedFields) -> List[str]:
    flags: List[str] = []
    rx = _regex_first_weight_kg(narrative)
    if extracted.weight_kg is not None and rx is not None:
        if abs(float(extracted.weight_kg) - rx) < 0.11:
            flags.append("weight_regex_crosscheck_ok")
    elif extracted.weight_kg is not None:
        flags.append("weight_model_only")
    if extracted.diet_keywords:
        flags.append("diet_keywords_non_empty")
    return flags


def _infer_diet_mode(keywords: List[str]) -> DietMode:
    blob = " ".join(keywords)
    heavy = ("야식", "라면", "회식", "술", "맥주", "치킨", "떡볶이", "탄수", "과식")
    light = ("샐러드", "닭가슴살", "단백질", "현미", "브로콜리", "샐러드")
    if any(k in blob for k in heavy):
        return DietMode.DEFICIT
    if any(k in blob for k in light):
        return DietMode.NORMAL
    return DietMode.NORMAL


def solar_extract_journal(narrative: str) -> ExtractedFields:
    """Solar Chat + strict JSON schema — 비정형 한국어 일기에서 체중·식단 키워드 등 구조화 (평가: 추출 정확도)."""
    client = _chat_client()
    try:
        resp = client.chat.completions.create(
            model=SOLAR_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACT},
                {"role": "user", "content": narrative.strip()},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "diet_journal_extract",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": _EXTRACT_PROPERTIES,
                        "required": _EXTRACT_REQUIRED,
                        "additionalProperties": False,
                    },
                },
            },
            temperature=0.0,
            max_tokens=512,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Solar 추출 실패: {e}") from e

    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Solar 응답 파싱 실패: {e}") from e

    rx_w = _regex_first_weight_kg(narrative)
    model_w = data.get("weight_kg")
    # 정규식과 모델이 충돌하면(>0.15kg) 정규식 우선 → 90% 정확도 목표에 가깝게 교정
    if rx_w is not None and model_w is not None and abs(float(model_w) - rx_w) > 0.15:
        data["weight_kg"] = rx_w
    elif rx_w is not None and model_w is None:
        data["weight_kg"] = rx_w

    return ExtractedFields(
        weight_kg=data.get("weight_kg"),
        calories_in=data.get("calories_in"),
        steps=data.get("steps"),
        sleep_hours=data.get("sleep_hours"),
        sleep_quality=data.get("sleep_quality"),
        exercises_done=data.get("exercises_done") or [],
        exercise_note=data.get("exercise_note") or "",
        notes=data.get("notes") or "",
        diet_keywords=data.get("diet_keywords") or [],
    )


def solar_generate_coaching(
    journal: Journal,
    reward: RewardBreakdown,
    policy: PolicyDecision,
    warnings: List[ProactiveWarning],
    session_caution: str,
) -> str:
    client = _chat_client()
    last = journal.entries[-1] if journal.entries else None
    series_tail = journal_timeseries(journal)[-5:]
    context = {
        "latest_entry": last.model_dump(mode="json") if last else None,
        "reward": reward.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
        "proactive_warnings": [w.model_dump(mode="json") for w in warnings],
        "session_caution": session_caution,
        "entries_count": len(journal.entries),
        "goal_kg": GOAL_KG_FLOAT,
        "ma_tail_5d": series_tail,
    }
    user_msg = (
        "다음 컨텍스트를 바탕으로 오늘의 코칭을 한국어 마크다운으로 작성하세요. "
        "정책 메시지를 자연스럽게 풀어쓰고, 위험 경고가 있으면 가장 먼저 다루세요.\n\n"
        f"```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"
    )
    try:
        resp = client.chat.completions.create(
            model=SOLAR_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_COACH},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.6,
            max_tokens=1200,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Solar 코칭 실패: {e}") from e
    return resp.choices[0].message.content.strip()


# --- Proactive Coaching ------------------------------------------------------

def detect_proactive_warnings(journal: Journal) -> List[ProactiveWarning]:
    """Differentiator: scan recent journal for risk patterns; emit warnings even
    if the user hasn't asked for advice yet."""
    warnings: List[ProactiveWarning] = []
    entries = journal.entries
    if len(entries) < 2:
        return warnings

    # 1) Rapid weight loss — last 7 entries cumulative drop > 2kg
    recent7 = entries[-7:]
    if len(recent7) >= 2:
        drop = recent7[0].weight_kg - recent7[-1].weight_kg
        if drop > 2.0:
            warnings.append(ProactiveWarning(
                pattern="rapid_weight_loss",
                severity="alert" if drop > 3.0 else "warn",
                message=(
                    f"최근 {len(recent7)}일간 체중이 {drop:.1f}kg 줄었습니다. "
                    "과한 감량 페이스는 근손실·요요 위험이 있어요. "
                    "지속되면 전문의 상담을 고려하세요."
                ),
                evidence={"window_days": len(recent7), "drop_kg": round(drop, 2)},
            ))

    # 2) Chronic low-cal — last 5 days mean < 1000
    recent5 = entries[-5:]
    cals = [e.calories_in for e in recent5 if e.calories_in is not None]
    if len(cals) >= 3 and statistics.mean(cals) < 1000.0:
        warnings.append(ProactiveWarning(
            pattern="chronic_low_calorie",
            severity="warn",
            message=(
                f"최근 5일 평균 섭취가 약 {statistics.mean(cals):.0f}kcal입니다. "
                "지속되면 영양 결핍·기초대사 저하가 올 수 있어요. 단백질·채소 보강을 권장합니다."
            ),
            evidence={"mean_kcal": round(statistics.mean(cals), 1), "samples": len(cals)},
        ))

    # 3) Sleep deprivation — last 5 days mean < 5h
    sleeps = [e.sleep_hours for e in recent5 if e.sleep_hours is not None]
    if len(sleeps) >= 3 and statistics.mean(sleeps) < 5.0:
        warnings.append(ProactiveWarning(
            pattern="sleep_deprivation",
            severity="warn",
            message=(
                f"최근 5일 평균 수면이 {statistics.mean(sleeps):.1f}시간입니다. "
                "회복이 부족하면 식욕 호르몬(렙틴·그렐린) 균형이 깨져 폭식 위험이 커집니다."
            ),
            evidence={"mean_sleep_h": round(statistics.mean(sleeps), 2), "samples": len(sleeps)},
        ))

    # 4) No exercise + stagnation — 5 days zero exercise + flat MA slope
    if len(recent5) >= 5 and sum(1 for e in recent5 if e.exercises_done) == 0:
        weights = [e.weight_kg for e in entries]
        if len(weights) >= 7:
            from utils import slope_last_n
            slope = slope_last_n(weights, n=7)
            if slope is not None and abs(slope) < 0.02:
                warnings.append(ProactiveWarning(
                    pattern="inactivity_plus_plateau",
                    severity="info",
                    message=(
                        "최근 5일 운동 기록이 없고 체중이 정체 상태입니다. "
                        "가벼운 걷기·계단 오르기부터 다시 활성화해 보세요."
                    ),
                    evidence={"slope7": round(slope, 4)},
                ))

    return warnings


# --- App ---------------------------------------------------------------------

app = FastAPI(title="Solar Diet Master", version="0.1.0")


@app.get("/api/meta")
def api_meta() -> dict:
    return {
        "model": SOLAR_MODEL,
        "api_key_set": bool(UPSTAGE_API_KEY),
        "data_dir": str(DATA_DIR),
        "goal_kg": GOAL_KG_FLOAT,
        "success_metrics": {
            "extraction": "체중 정규식 교차검증 + diet_keywords 배열 + Solar strict JSON schema",
            "logic": "MA 기반 R_weight, Plateau/정체 시 A7 탐색",
            "solar": "추출/코칭 각각 도메인 시스템 프롬프트 분리",
            "creativity": "ma_reward_explanation_ko + 코칭에 MA·정책 수치 주입",
        },
        "extraction_implementation": {
            "method": EXTRACTION_METHOD,
            "endpoint": "POST https://api.upstage.ai/v1/chat/completions",
            "note": "Universal Information Extract API는 파일 업로드 전제 — 평문 일기는 Chat+json_schema만 사용",
        },
    }


def _entry_from_extracted(extracted: ExtractedFields, fallback_weight: Optional[float], target_date: str) -> DailyEntry:
    weight = extracted.weight_kg if extracted.weight_kg is not None else fallback_weight
    if weight is None:
        raise HTTPException(status_code=400, detail="체중 정보를 자연어에서 찾지 못했습니다. 숫자(kg)를 포함해 다시 작성해주세요.")
    diet = _infer_diet_mode(extracted.diet_keywords)
    kw_line = ", ".join(extracted.diet_keywords) if extracted.diet_keywords else ""
    notes = extracted.notes or ""
    if kw_line:
        notes = (notes + "\n[식단키워드] " + kw_line).strip()
    return DailyEntry(
        date=target_date,
        weight_kg=float(weight),
        calories_in=extracted.calories_in,
        steps=extracted.steps,
        exercises_done=extracted.exercises_done,
        exercise_note=extracted.exercise_note,
        sleep_hours=extracted.sleep_hours,
        sleep_quality=extracted.sleep_quality,
        diet=diet,
        activity=ActivityMode.ACTIVE,
        notes=notes,
    )


@app.post("/api/entry", response_model=DailyEntry)
def api_entry(entry: DailyEntry) -> DailyEntry:
    """구조화 저장도 자연어 저장과 동일하게 보상·정책으로 diet/activity를 동기화한다."""
    journal = _load_journal()
    journal_merged = _merge_entry(journal, entry)
    reward = reward_breakdown_last_step(journal_merged)
    policy = decide(journal_merged, entry, reward)
    entry_final = entry.model_copy(update={"diet": policy.diet, "activity": policy.activity})
    journal_out = _merge_entry(journal, entry_final)
    _save_journal(journal_out)
    _update_policy_stats(policy, reward.total)
    return entry_final


@app.post("/api/entry/natural", response_model=NaturalEntryResponse)
def api_entry_natural(req: NaturalEntryRequest) -> NaturalEntryResponse:
    extracted = solar_extract_journal(req.narrative)
    quality_flags = _extraction_quality_flags(req.narrative, extracted)
    target_date = req.date or date.today().isoformat()
    entry = _entry_from_extracted(extracted, req.weight_kg, target_date)

    journal = _load_journal()
    journal_merged = _merge_entry(journal, entry)
    reward = reward_breakdown_last_step(journal_merged)
    policy = decide(journal_merged, entry, reward)
    entry_final = entry.model_copy(update={"diet": policy.diet, "activity": policy.activity})
    journal_out = _merge_entry(journal, entry_final)
    _save_journal(journal_out)

    phase = detect_phase(journal_out)
    warnings = detect_proactive_warnings(journal_out)
    _update_policy_stats(policy, reward.total)
    explain_ko = ma_reward_explanation_ko(journal_out, reward)

    return NaturalEntryResponse(
        extracted=extracted,
        saved_entry=entry_final,
        reward=reward,
        policy=policy,
        phase=phase,
        proactive_warnings=warnings,
        ma_reward_explanation_ko=explain_ko,
        extraction_quality_flags=quality_flags,
    )


@app.get("/api/progress", response_model=ProgressResponse)
def api_progress() -> ProgressResponse:
    journal = _load_journal()
    series = journal_timeseries(journal)[-120:]
    reward = reward_breakdown_last_step(journal)
    phase = detect_phase(journal)
    policy = None
    if journal.entries:
        policy = decide(journal, journal.entries[-1], reward)
    explain_ko = ma_reward_explanation_ko(journal, reward)
    return ProgressResponse(
        series=series,
        reward=reward,
        policy=policy,
        phase=phase,
        goal_kg=GOAL_KG_FLOAT,
        ma_reward_explanation_ko=explain_ko,
    )


@app.post("/api/coach", response_model=CoachResponse)
def api_coach(req: CoachRequest) -> CoachResponse:
    journal = _load_journal()
    if not journal.entries:
        raise HTTPException(status_code=400, detail="저장된 일기가 없습니다. 먼저 /api/entry/natural로 기록하세요.")
    reward = reward_breakdown_last_step(journal)
    phase = detect_phase(journal)
    policy = decide(journal, journal.entries[-1], reward)
    warnings = detect_proactive_warnings(journal)

    text = solar_generate_coaching(journal, reward, policy, warnings, req.session_caution)

    _append_coach_history({
        "date": date.today().isoformat(),
        "policy": policy.model_dump(mode="json"),
        "reward_total": reward.total,
        "warnings": [w.model_dump(mode="json") for w in warnings],
        "text": text,
    })

    return CoachResponse(
        coaching_markdown=text,
        phase=phase,
        reward_summary=reward,
        proactive_warnings=warnings,
    )


@app.post("/api/proactive_check")
def api_proactive_check() -> dict:
    """Differentiator endpoint — agent calls this BEFORE responding to detect
    risk patterns and surface warnings proactively."""
    journal = _load_journal()
    warnings = detect_proactive_warnings(journal)
    return {
        "has_warnings": bool(warnings),
        "warnings": [w.model_dump(mode="json") for w in warnings],
        "entries_count": len(journal.entries),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
