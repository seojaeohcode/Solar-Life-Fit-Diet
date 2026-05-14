---
name: solar-diet-master
description: Upstage Solar 기반 한국어 다이어트 코칭 에이전트 스킬. 자유 서술형 일기에서 Solar Chat(strict JSON schema)으로 체중(kg)·식단 키워드(diet_keywords) 등을 추출하고, 7일 이동평균(MA) 기반 R_weight와 휴리스틱 정책(A1~A9)을 적용한다. Plateau phase·정체 시 A7 탐색, Proactive 경고, API 응답의 ma_reward_explanation_ko로 MA 보상을 사용자에게 투명히 설명한다. 체중 기록·식단 일기·코칭·보상 진척도·RL-Diet 언급 시 반드시 사용. 의학적 진단·약 처방은 하지 않는다.
---

# Solar Diet Master

## 목적

`diet.md`(RL-Diet 솔루션 인수인계 문서)에 정의된 1인용 다이어트 저널 + 강화학습 스타일 보상·정책 힌트 워크플로를 **Anthropic 표준 Skill 포맷**으로 이식한 에이전트 스킬이다. 기존 Gemini API 호출 경로는 **Upstage Solar API**로 전면 교체되었으며, 역할을 다음처럼 나눈다:

- **Solar Chat + strict JSON schema** — 비정형 한국어 일기에서 체중·`diet_keywords`·수면·운동 등 필드 추출 (평가: 추출 정확도 / Upstage 활용도)
- **Solar Chat (solar-pro3 등)** — MA·보상·정책 JSON을 컨텍스트로 넣은 **다이어트 도메인 코칭** (평가: Solar 최적화)

> **구현 선택:** Upstage **Universal Information Extract** API는 보통 **문서 파일 업로드**가 필요하다. 이 스킬의 입력은 **평문 일기**이므로, 동일 Solar 계열에서 **Chat Completions + `response_format` strict JSON schema** 로만 추출한다 (`GET /api/meta` → `extraction_implementation` 참고). IE 전용 HTTP 클라이언트는 사용하지 않는다.

## 대회 성공 지표 대응 (요약)

| 지표 | 스킬 내 대응 |
|------|----------------|
| **추출 정확도** (체중+식단 키워드 ~90% 목표) | 도메인 전용 `SYSTEM_PROMPT_EXTRACT` + `diet_keywords[]` 필드 + 체중 **정규식 교차검증**(모델과 불일치 시 보정) + 응답 `extraction_quality_flags` |
| **로직 일관성** (체중↑ 시 MA 보상 약화, Plateau→A7) | `stats.py`/`utils.py` MA·`R_weight`, `policy.py`에서 **Phase.PLATEAU + MA 기울기 평탄** 시 `A7` 탐색, 오프라인 검증 `scripts/verify_metrics.py` |
| **Solar API 최적화** | 추출/코칭 **시스템 프롬프트 분리**, 코칭에 `reward`·`policy`·`ma_tail_5d` 주입 (단순 요약 금지) |
| **창의적 해결** (MA 보상 차별화) | `GET/POST natural` 응답의 **`ma_reward_explanation_ko`** — MA가 노이즈를 줄이는 이유를 한국어로 고정 생성 |
| **사용성·확장성** | 본 절 아래 **에이전트 입출력 계약**, `GET /api/meta.success_metrics` 요약 |

## 에이전트 입출력 계약 (사용성)

- **저장(구조화):** `POST /api/entry` 바디는 `DailyEntry` JSON — 저장 후 **`diet`/`activity`를 정책 결과로 덮어씀** (자연어 경로와 동일 규칙)
- **저장(자연어):** `POST /api/entry/natural` 바디 `{ "narrative": string, "date"?: "YYYY-MM-DD", "weight_kg"?: number }`
  - 응답: `extracted`(체중·`diet_keywords` 등), `saved_entry`, `reward`, `policy`, `phase`, `proactive_warnings`, **`ma_reward_explanation_ko`**, **`extraction_quality_flags`**
- **진척도:** `GET /api/progress` → `series[]`(date, weight_kg, ma7), `reward`, `policy`, `phase`, **`ma_reward_explanation_ko`**
- **코칭:** `POST /api/coach` 바디 `{ "session_caution"?: string, ... }` → `coaching_markdown` + 경고·보상 요약
- **선제 경고:** `POST /api/proactive_check` (바디 없음) → `warnings[]`

에이전트는 사용자 메시지 처리 전 **`/api/proactive_check`** 를 1회 호출해 선제 경고를 붙일 수 있다.

## 언제 트리거하나

- "어제 라면 야식 먹고 잤어, 오늘 공복 72.4kg" 같은 **다이어트 회고형 메시지**
- "내 체중 추이 보여줘", "보상 점수 알려줘" 같은 **진척도 조회**
- "오늘 뭐 먹어야 해?", "다이어트 코치 받고 싶어" 같은 **코칭 요청**
- "급격하게 빠지는데 괜찮나?" 같은 **위험 신호 질문**

## 언제 트리거하지 않나

- 임상 진단·약물 처방·검사 결과 해석 → **거절하고 전문의 상담 안내**
- 영수증·PDF에서 필드만 추출 → Document Parse / Information Extract 스킬을 직접 사용
- 일반 칼로리표 조회 → 다이어트 저널 컨텍스트가 아니면 스킵

## 실행 방법

### 사전 준비

1. `UPSTAGE_API_KEY`를 리포 루트 `.env` 또는 `skills/diet_coach/assets/.env`에 둔다 (`assets/.env.example` 참고).
2. `pip install -r requirements.txt` (또는 동등 패키지).

### 서버 기동

```bash
cd skills/diet_coach
pip install -r requirements.txt
python scripts/verify_metrics.py
uvicorn main:app --reload --port 8001
```

### 핵심 엔드포인트

| Method | Path | 용도 |
|--------|------|------|
| POST | `/api/entry/natural` | 자연어 → Solar strict JSON 추출 → 정책 반영 저장 + `ma_reward_explanation_ko` |
| POST | `/api/entry` | 구조화 JSON 저장 — 저장 직후 **정책으로 `diet`/`activity` 동기화** |
| GET | `/api/progress` | 시계열 + 보상 브레이크다운 + phase |
| POST | `/api/coach` | Solar Chat으로 한국어 코칭 문구 생성 |
| POST | `/api/proactive_check` | **차별화 기능** — 최근 저널의 위험 패턴 감지 → 경고 메시지 |
| GET | `/api/meta` | 모델·저장 경로·기록창 설정 |

## 데이터 저장

`./data/` 폴더 내 JSON으로 저장 (DB 없음):

| 파일 | 용도 |
|------|------|
| `journal.json` | 일별 `DailyEntry` 배열 |
| `policy_stats.json` | `action_id`별 count / avg_reward 누적 |
| `coach_history.json` | 코칭 요청·응답 이력 (최대 200건) |

경로는 `main.py`의 `DATA_DIR`에서 일괄 관리한다. **이 JSON 파일들은 리포 루트 `.gitignore`에 의해 Git에 포함되지 않는다**(개인 일기 유출 방지). 클론 직후에는 폴더만 있고, 서버 실행 후 자동 생성된다.

## 보상 설계 (이식 위치: `stats.py`, `utils.py`)

**복합 보상 (단일 스텝):**

```
total = α·R_weight + β·R_consistency + γ·R_habit + δ·R_goal − λ·P_risk
```

- `R_weight = 0.6·R_t + 0.4·R_delayed` — `R_t = (W_avg,t-1 − W_avg,t) × 100`, MA 창 = 7일
- `R_consistency = (adherence − 0.5) × 20` — 최근 14일 기록 빈도
- `R_habit` — 수면·걸음·운동·식이 휴리스틱 점수
- `R_goal` — `RLDIET_GOAL_KG`와 phase 정합도
- `P_risk` — 저칼로리·수면 부족·급격 변동성 페널티

가중치 α, β, γ, δ, λ는 환경변수로 오버라이드 가능 (`stats.py` 상단 상수).

## 정책 (이식 위치: `policy.py`)

| 조건 | mode | action_id | 식단/활동 |
|------|------|-----------|-----------|
| `risk_penalty >= 8` | safety | A8 | Normal + (Intense→Active 강제 완화) |
| 정체 / **Plateau phase** | explore | A7 | MA 기울기 평탄 + `detect_phase==plateau` 시 탐색 bump |
| `progressing` (total>0 & slope7<0) | exploit | A1 | 유지 |
| 그 외 | exploit | A9 | 유지 + 미세 조정 |

A2~A6은 보조 분기 (체중 급변, 운동 부재, 수면 부족 등 특화 케이스) — `policy.py` 참고.

## 차별화 기능: Proactive Coaching

`POST /api/proactive_check`는 사용자가 묻지 않아도 다음 패턴이 감지되면 경고를 반환한다:

| 패턴 | 트리거 | 메시지 톤 |
|------|--------|-----------|
| **급격한 체중 감소** | 최근 7일 누적 −2kg 초과 | 안전 경고 (의학적 우려는 전문의 상담 권고) |
| **만성 저칼로리** | 최근 5일 평균 `calories_in < 1000` | 영양·근손실 경고 |
| **수면 부족 연속** | 최근 5일 평균 `sleep_hours < 5` | 회복 부족 경고 |
| **운동 부재 + 정체** | 5일 운동 0회 & MA 기울기 ≈ 0 | 활동 활성화 제안 |

에이전트는 사용자 메시지를 받은 직후, **답변 생성 전**에 이 엔드포인트를 1회 호출해 위험 신호를 사전 확인할 수 있다.

## 출력 스키마 (대표)

`POST /api/entry/natural` 응답:

```json
{
  "extracted": {
    "weight_kg": 72.4,
    "diet_keywords": ["라면", "야식"],
    "calories_in": 1450,
    "sleep_hours": 6.0,
    "exercises_done": ["걷기 30분"]
  },
  "saved_entry": {"date": "2026-05-14", "diet": "Deficit", "activity": "Active", "...": "..."},
  "reward": {"total": 0.82, "R_weight": 1.4, "R_consistency": 0.6, "R_habit": 0.3, "R_goal": 0.2, "P_risk": 0.15},
  "policy": {"mode": "exploit", "action_id": "A1", "diet": "Deficit", "activity": "Active", "message": "..."},
  "proactive_warnings": [],
  "ma_reward_explanation_ko": "【이동평균 보상】...",
  "extraction_quality_flags": ["weight_regex_crosscheck_ok", "diet_keywords_non_empty"]
}
```

## 안전·정책

- **비의료:** 일반 생활 습관 범위로만 조언한다. "처방"·"진단" 단어 사용 금지.
- 코칭 시스템 프롬프트에 "의학적 진단 금지" 명시 (`main.py` `SYSTEM_PROMPT_COACH`).
- `UPSTAGE_API_KEY`는 절대 응답에 포함하지 않으며, `.env`는 `.gitignore`로 차단되어 있다.
- 추출 결과가 비합리적이면 (체중 30kg 미만/250kg 초과 등) 저장 거부하고 사용자에게 재서술 요청.

## 파일 맵

| 파일 | 역할 |
|------|------|
| `SKILL.md` | 본 문서 (메타데이터 + 트리거 + 사용 안내) |
| `main.py` | FastAPI 앱 + Solar API 어댑터 + 서비스 로직 |
| `models.py` | Pydantic 스키마 (`DailyEntry`, `Journal`, `ExtractedFields`, `RewardBreakdown` …) |
| `stats.py` | MA, 보상 항목별 계산, phase 판정 |
| `policy.py` | 휴리스틱 정책 분기 (A1~A9) |
| `utils.py` | MA 윈도우 계산 + 보상 합성 공식 |
| `requirements.txt` | Python 의존성 고정 |
| `scripts/verify_metrics.py` | 성공 지표 중 로직 일관성 오프라인 검증 |
| `assets/.env.example` | API 키 템플릿 (복사 후 `assets/.env` 또는 리포 루트 `.env`) |
| `assets/README.md` | `assets/` 사용 안내 |
| `data/*.json` | 저널·정책 통계·코칭 이력 |
