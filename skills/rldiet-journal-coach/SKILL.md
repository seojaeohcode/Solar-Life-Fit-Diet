---
name: rldiet-journal-coach
description: 경량 CLI 예시만 제공한다. 저널 한 덩어리를 Solar Chat으로 넘겨 summary_ko·focus_tomorrow 등 JSON만 받는다. FastAPI·MA 보상·정책 A1~A9·저널 저장은 출품 스킬 solar-diet-master(skills/diet_coach)를 사용한다. HTTP 서버 없이 스크립트만 돌릴 때만 이 스킬을 고른다. 의학적 진단·처방은 하지 않는다.
---

# RL-Diet 저널 코칭 (Upstage Solar)

## 목적

에이전트가 사용자의 **자유 서술형 다이어트 저널**을 받았을 때, Upstage **Chat Completions**로 짧은 구조화 결과를 만들어 후속 답변(코칭 문장, UI 필드 제안 등)에 쓰게 한다.

**출품 본체와의 차이:** `skills/diet_coach`(solar-diet-master)는 같은 Solar를 쓰지만 **저장·이동평균 보상·정책·선제 경고·HTTP API**까지 포함한다. 이 폴더는 **단일 스크립트**로 빠르게 요약 JSON만 필요할 때의 예시이다.

## 사용하지 않는 경우

- PDF·영수증에서 필드만 뽑는 경우 → Information Extract / Document Parse 쪽이 맞다.
- 임상 진단·약 처방·검사 해석을 요구하는 경우 → 거절하고 전문의 상담을 안내한다.

## 실행 방법

1. `UPSTAGE_API_KEY`를 환경 변수로 두거나, **`리포지토리 루트` `.env`** 또는 이 스킬의 **`assets/.env`**에 둔다(템플릿은 `assets/.env.example`). 스크립트 `coach_journal.py`는 **루트 `.env`를 먼저** 읽은 뒤 `rldiet-journal-coach/assets/.env`로 비어 있는 키만 채운다(이미 설정된 키는 덮어쓰지 않음).
2. 결정적 출력이 필요하면 아래 스크립트를 호출한다.

```bash
python scripts/coach_journal.py --journal "어제 야식 라면, 수면 5시간. 오늘 공복 72.4kg."
```

표준 입력으로 넘기려면:

```bash
echo "..." | python scripts/coach_journal.py
```

`cwd`는 **이 스킬 폴더**(`rldiet-journal-coach/`) 또는 리포 루트여도 된다. 스크립트가 `.git`이 있는 디렉터리를 찾아 리포 루트의 `.env`를 읽는다.

Windows(cp949 콘솔)에서도 한글 출력은 `encoding_bootstrap`이 자동으로 UTF-8 stdio로 맞춘다. 별도 `PYTHONUTF8` 설정은 필요 없다.

## 출력 스키마 (스크립트 기본)

스크립트는 모델 응답에서 JSON 한 덩어리를 파싱한다. 기대 필드 예시:

| 필드 | 의미 |
|------|------|
| `summary_ko` | 2~4문장 한국어 요약 |
| `focus_tomorrow` | 내일 행동 1~3가지 (비의료) |
| `signals` | 체중·수면·식사 등 언급된 신호 키워드 배열 |
| `risk_flags` | 과도한 제한·수면 부족 등 주의 표현(없으면 빈 배열) |

파싱 실패 시 stderr에 원문 일부를 남기고 비정상 종료한다.

## 안전·정책

- **비의료:** 체중 감량 목표 조언은 일반 생활 습관 범위로만 쓴다.
- API 키·`.env`는 버전 관리에 넣지 않는다.
