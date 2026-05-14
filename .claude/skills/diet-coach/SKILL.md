---
name: solar-diet-master
description: Upstage Solar 기반 다이어트 코칭(MA 보상·A1~A9·자연어 추출). Claude Code `/skills`·`/diet-coach` 진입점 — 실제 코드는 skills/diet_coach/ 에 있다. 체중·식단 일기·RL-Diet·보상 질문 시 사용.
---

# Solar Diet Master (Claude Code 진입)

Claude Code는 **`/skills` 목록과 `/diet-coach` 명령**을 **`.claude/skills/<이름>/SKILL.md`** 기준으로만 잡는다.  
대회 제출용 전체 구현·FastAPI·엔드포인트는 **`skills/diet_coach/`** 에 있다.

## 에이전트가 할 일

1. 상세 스펙·API 표·성공 지표는 **`skills/diet_coach/SKILL.md`** 를 읽는다.
2. 코드 편집·실행은 **`skills/diet_coach/`** 를 작업 디렉터리로 삼는다.
3. 로컬 서버: `cd skills/diet_coach` 후 `uvicorn main:app --reload --port 8001`
4. 오프라인 검증: `python scripts/verify_metrics.py` (같은 폴더 기준)

## 한 줄

**`/skills`에 보이는 이 파일 = 진입 안내**이고, **제출·구현의 본체 = `skills/diet_coach/`** 이다.
