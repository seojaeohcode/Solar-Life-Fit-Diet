# skills 폴더 안내

## 심사위원·발표자께

대회 제출 형식으로 실제 작품은 **`diet_coach`** 폴더에 있습니다. 말로 시연해 보실 때는 **`diet_coach/references/시연·검증_시나리오.md`** 를 먼저 봐 주시면 됩니다. 코드와 API 설명은 같은 폴더의 `SKILL.md`에 있습니다.

## Claude Code 사용자께

이 저장소에서는 `/skills` 목록이 **`skills/`** 가 아니라 **`.claude/skills/`** 아래의 짧은 안내 파일을 읽습니다. 진입용은 `diet-coach`, `rldiet-journal-coach` 두 곳이고, 구현과 제출 본문은 아래 표의 `skills/...` 쪽입니다.

| 폴더 | 설명 |
|------|------|
| `solar-skill-creator/` | 대회 템플릿 플러그인입니다. 삭제하거나 고치지 마세요. |
| `diet_coach/` | 출품 작품(다이어트 저널·보상·코칭). 시연 문서는 `references/시연·검증_시나리오.md`. |
| `rldiet-journal-coach/` | 가벼운 예시 스킬입니다. 서류에는 `diet_coach`를 대표로 쓰는 것을 권합니다. |

`diet_coach/data/` 안의 일기 JSON은 Git에 올라가지 않게 막아 두었습니다. 개인 기록이 저장소에 섞이지 않도록 한 설정입니다.
