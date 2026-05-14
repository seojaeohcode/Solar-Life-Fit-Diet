# `skills/` 디렉터리 안내

## Claude Code `/skills` 와의 관계

Claude Code는 **`skills/`(리포 루트)** 가 아니라 **`.claude/skills/<이름>/SKILL.md`** 만 `/skills`·`/<이름>` 명령으로 읽는다.  
그래서 **`.claude/skills/diet-coach/`**, **`.claude/skills/rldiet-journal-coach/`** 에 진입용 `SKILL.md`를 두었고, 상세 구현·제출물은 아래 **`skills/`** 쪽이 본체다.

| 폴더 | 역할 |
|------|------|
| `solar-skill-creator/` | 템플릿 플러그인 — **수정·삭제하지 마세요.** |
| `diet_coach/` | **본 리포의 주 제출 스킬(Solar Diet Master)** — FastAPI + MA 보상·정책·Solar 추출/코칭. |
| `rldiet-journal-coach/` | 보조 예시 스킬(경량 Solar 저널 JSON). 대회 서류에는 **`diet_coach`를 대표 스킬**로 적는 것을 권장합니다. |

런타임 데이터: `diet_coach/data/*.json` 은 루트 `.gitignore`로 **커밋에서 제외**됩니다. 서버 기동 시 디렉터리가 비어 있으면 자동 생성됩니다.
