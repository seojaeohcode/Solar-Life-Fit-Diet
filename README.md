# Solar Diet Master

**2026 전남대학교 소프트웨어중심대학 × 업스테이지 교내 디지털 경진대회(SW부문) — Skillthon 출품**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by Upstage](https://img.shields.io/badge/Powered%20by-Upstage%20Solar-blue)](https://upstage.ai)

본 리포지토리의 출품 스킬은 **다이어트 일기**를 **Upstage Solar API**로 구조화하고, **7일 이동평균(MA)** 기반 보상·**휴리스틱 정책(A1~A9)**·선제 경고·한국어 코칭을 제공하는 **Anthropic Agent Skill** 형식(`skills/diet_coach/`)으로 제출한다. 의료 진단·처방은 범위에서 제외한다.

---

## 제출물 및 문서 위치

| 구분 | 경로 | 내용 |
|------|------|------|
| 출품 본체 | [`skills/diet_coach/`](skills/diet_coach/) | Anthropic Skill 디렉터리 (`SKILL.md`, 스크립트, 테스트) |
| 시연·검증 가이드 | [`skills/diet_coach/references/시연·검증_시나리오.md`](skills/diet_coach/references/시연·검증_시나리오.md) | 자연어 시나리오·기대 결과 (API 용어 최소화) |
| 기술·연동 명세 | [`skills/diet_coach/SKILL.md`](skills/diet_coach/SKILL.md) | 에이전트 지침, HTTP 엔드포인트, 보상·정책 요약 |
| 스킬 메타 | `skills/diet_coach/SKILL.md` frontmatter | `name: solar-diet-master`, `description` (에이전트 트리거용) |

제출 폴더명은 `diet_coach`이며, Claude Code `/skills` 목록에는 YAML `name`에 따라 `solar-diet-master`로 표시될 수 있다. 동일 출품이다.

저장소 안에서 **`skills/`** 아래 폴더 역할(Claude Code 진입점 vs 제출 본체)은 [`skills/README.md`](skills/README.md)에 정리해 두었다.

---

## 주요 기능

- 자연어 일기에서 체중·식단 키워드 등 필드 추출, 체중 정규식 교차검증
- 7일 MA 기반 합성 보상 및 phase 판정
- 휴리스틱 정책 A1~A9(예: 정체 시 A7, 위험 점수 기반 A8)
- 선제 경고 API(급감량·저칼로리·수면 부족 등 패턴)
- 보상·정책·최근 추세를 컨텍스트로 한 Solar 기반 한국어 코칭 마크다운
- 로컬 JSON 저장(`data/`), Git 제외 처리

---

## 리포지토리 구조

```
skills/diet_coach/       출품 Skill (SKILL.md, main.py, stats.py, policy.py 등)
skills/solar-skill-creator/   대회 제공 템플릿
skills/rldiet-journal-coach/  보조 예시 스킬
.claude/skills/diet-coach/    Claude Code 진입용 SKILL
```

---

## 구동 방법

**환경:** Python **3.10 이상**을 권장한다. 가상환경(`.venv` 등) 사용을 권장한다.

```bash
cd skills/diet_coach
pip install -r requirements.txt
# UPSTAGE_API_KEY: skills/diet_coach/assets/.env 권장(우선 로드). 없으면 skills/diet_coach/.env 또는 리포 루트 .env
uvicorn main:app --reload --port 8001
```

서버가 뜨면 브라우저에서 **OpenAPI 문서** `http://127.0.0.1:8001/docs` 로 각 엔드포인트를 바로 호출해 볼 수 있다.

보조 검증: `python scripts/verify_metrics.py` · `python tests/test_all.py` (동일 디렉터리)

## 참고

| 항목 | URL |
|------|-----|
| Upstage API 개요 | https://console.upstage.ai/docs/capabilities |
| Skillthon 원본 템플릿(크레딧·공통 안내) | https://github.com/GoBeromsu/JNU-Upstage-Skillthon |

---

## 대회 문의

전남대학교 소프트웨어중심대학사업단 — 조아라 연구원 / 고범수 · 062-530-5364 · 010-4012-1143 · rha852@jnu.ac.kr · gobeumsu@gmail.com
