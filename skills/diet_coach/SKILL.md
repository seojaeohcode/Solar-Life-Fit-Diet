---
name: solar-diet-master
description: Upstage Solar 기반 한국어 다이어트 코칭 에이전트 스킬. 자유 서술형 일기에서 Solar Chat(strict JSON schema)으로 체중(kg)·식단 키워드(diet_keywords) 등을 추출하고, 7일 이동평균(MA) 기반 R_weight와 휴리스틱 정책(A1~A9)을 적용한다. Plateau phase·정체 시 A7 탐색, Proactive 경고, API 응답의 ma_reward_explanation_ko로 MA 보상을 사용자에게 투명히 설명한다. 체중 기록·식단 일기·코칭·보상 진척도·RL-Diet 언급 시 반드시 사용. 의학적 진단·약 처방은 하지 않는다.
---

# Solar Diet Master

## 심사위원·발표자 안내

이 작품은 **말로 적은 하루 일기**에서 체중·식단 단서를 골라 내고, 며칠 치 체중이 쌓이면 **7일 이동평균**으로 잡은 추세를 바탕으로 점수와 행동 안내(코드 A1~A9)를 붙입니다. 코칭 문장은 **업스테이지 Solar**로 생성합니다. 진단·처방은 하지 않으며, 위험해 보이는 패턴이 보이면 완화 쪽으로 돌리거나 경고를 띄웁니다.

**시연만 하실 때**는 `references/시연·검증_시나리오.md` 한 파일이면 됩니다. 말 예시와 “그러면 이렇게 보이면 된다”만 적어 두었습니다.

아래부터는 구현·API·수식을 적은 **개발·에이전트 연동용**입니다.

## 목적

`diet.md`(RL-Diet 인수인계)에 있던 1인용 저널과 보상·정책 흐름을 **Anthropic Skill 형식**으로 옮긴 것입니다. 예전에 쓰던 다른 모델 호출은 **Upstage Solar API**로 바꿨습니다.

- **추출:** 한국어 일기 → Solar 대화 API에 엄격한 JSON 스키마를 걸어 필드 채우기.
- **코칭:** 방금까지의 점수·정책·최근 추세를 JSON으로 넘긴 뒤 Solar로 마크다운 답 생성.

일기는 파일이 아니라 **평문**이므로, 문서 전용 추출 API 대신 **대화형 API + JSON 스키마** 한 경로만 씁니다. (`GET /api/meta`에 구현 요약이 있습니다.)

## 심사에서 보실 수 있는 점

| 보시면 되는 것 | 작품 안에서의 대답 |
|----------------|-------------------|
| 말만으로도 기록이 정리되는지 | 일기 한 줄에서 체중·식단 키워드를 뽑고, 체중은 숫자 정규식과 한 번 더 맞춰 봅니다. 품질 플래그를 응답에 붙입니다. |
| 체중이 들쭉날쭉할 때 점수가 말이 되는지 | 7일 이동평균을 써서 하루치 오차에 덜 흔들리게 했고, 감량·증량 예시는 `scripts/verify_metrics.py`로 자동 검사합니다. |
| 업스테이지 API를 “형식상”이 아니라 쓰는지 | 추출용과 코칭용 **프롬프트를 나눴고**, 코칭에는 점수·정책·최근 추세를 넣어 “그날 상황에 맞는” 답을 유도합니다. |
| MA를 왜 쓰는지 사용자에게 전달되는지 | 저장·조회 응답에 **한국어 한 덩어리**(`ma_reward_explanation_ko`)로 이동평균의 역할을 짧게 설명합니다. |
| 나중에 붙이기 쉬운지 | HTTP로 저장·조회·코칭·선제 경고를 나눠 두었고, `SKILL.md`에 입출력 요약이 있습니다. |

## HTTP로 붙일 때 (에이전트·개발)

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

1. `UPSTAGE_API_KEY`를 `skills/diet_coach/assets/.env` 또는 상위 경로의 `.env`에 둔다 (`assets/.env.example` 참고). 로드 순서는 `main.py` 기준으로 **`assets/.env`가 먼저** 적용되고, 이어 `skills/diet_coach/.env` → 상위 디렉터리에서 **가장 가까운** `.env` 한 파일이 `override=False`로 비어 있는 키만 채운다(동일 키는 **assets 쪽이 우선**).
2. `pip install -r requirements.txt` (또는 동등 패키지).

Windows PowerShell 기본(cp949)에서도 콘솔 한글 출력은 **`encoding_bootstrap.py`** 가 `main`·스크립트 로드 시 자동으로 UTF-8 stdio로 맞춘다. `PYTHONUTF8`·`chcp` 없이 실행하면 된다.

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
| **`P_risk` ≥ 8** (위험 점수; kg이 아님) | safety | A8 | Normal + (Intense→Active 강제 완화) |
| 정체 / **Plateau phase** | explore | A7 | MA 기울기 평탄 + `detect_phase==plateau` 시 탐색 bump |
| `progressing` (total>0 & slope7<0) | exploit | A1 | 유지 |
| 그 외 | exploit | A9 | 유지 + 미세 조정 |

A2~A6은 보조 분기 (체중 급변, 운동 부재, 수면 부족 등 특화 케이스) — `policy.py` 참고.

## 선제 경고 (물어보기 전에)

`POST /api/proactive_check`는 사용자가 묻지 않아도 다음 패턴이 감지되면 경고를 반환한다:

| 패턴 | 트리거 | 메시지 톤 |
|------|--------|-----------|
| **급격한 체중 감소** | 최근 **최대 7개 일기 칸**에서 첫·끝 체중 차이가 2kg 초과 | 안전 경고 (의학적 우려는 전문의 상담 권고) |
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
| `encoding_bootstrap.py` | Windows에서 sys stdio를 UTF-8로 고정 (import 시 1회) |
| `main.py` | FastAPI 앱 + Solar API 어댑터 + 서비스 로직 |
| `models.py` | Pydantic 스키마 (`DailyEntry`, `Journal`, `ExtractedFields`, `RewardBreakdown` …) |
| `stats.py` | MA, 보상 항목별 계산, phase 판정 |
| `policy.py` | 휴리스틱 정책 분기 (A1~A9) |
| `utils.py` | MA 윈도우 계산 + 보상 합성 공식 |
| `requirements.txt` | Python 의존성 고정 |
| `scripts/verify_metrics.py` | 성공 지표 중 로직 일관성 오프라인 검증 |
| `tests/test_all.py` | 스모크 테스트 (서버 없이 호출 가능한 범위) |
| `assets/.env.example` | API 키 템플릿 (복사 후 `assets/.env` 또는 리포 루트 `.env`) |
| `assets/README.md` | `assets/` 사용 안내 |
| `references/시연·검증_시나리오.md` | 심사·시연·비개발 검증용 시나리오 카드 |
| `data/*.json` | 저널·정책 통계·코칭 이력 |
