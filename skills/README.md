# `skills/` 디렉터리 안내

| 폴더 | 역할 |
|------|------|
| `solar-skill-creator/` | 템플릿 플러그인 — **수정·삭제하지 마세요.** |
| `diet_coach/` | **본 리포의 주 제출 스킬(Solar Diet Master)** — FastAPI + MA 보상·정책·Solar 추출/코칭. |
| `rldiet-journal-coach/` | 보조 예시 스킬(경량 Solar 저널 JSON). 대회 서류에는 **`diet_coach`를 대표 스킬**로 적는 것을 권장합니다. |

런타임 데이터: `diet_coach/data/*.json` 은 루트 `.gitignore`로 **커밋에서 제외**됩니다. 서버 기동 시 디렉터리가 비어 있으면 자동 생성됩니다.
