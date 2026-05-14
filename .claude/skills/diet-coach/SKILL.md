---
name: solar-diet-master
description: Upstage Solar 기반 다이어트 코칭(MA 보상·A1~A9·자연어 추출). Claude Code `/skills`·`/diet-coach` 진입점 — 실제 코드는 skills/diet_coach/ 에 있다. 체중·식단 일기·RL-Diet·보상 질문 시 사용.
---

# Solar Diet Master (Claude Code 진입)

## 심사·시연

- **`skills/diet_coach/references/시연·검증_시나리오.md`** — 말로 테스트할 때 읽을 문서입니다.
- **`skills/diet_coach/SKILL.md`** — 작품이 무엇을 하는지, 안전과 한계, 그다음 기술 세부입니다.

실제 코드와 서버는 **`skills/diet_coach/`** 입니다.

## 개발할 때만

상세 스펙과 주소 목록은 `skills/diet_coach/SKILL.md`에 있습니다. 서버는 그 폴더에서 `uvicorn main:app --reload --port 8001`, 로직 스모크는 `python scripts/verify_metrics.py` 입니다.

이 파일은 Claude Code가 `/skills`에서 잡기 위한 **짧은 안내**이고, 제출 본체는 **`skills/diet_coach/`** 입니다.
