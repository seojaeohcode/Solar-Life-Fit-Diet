# assets

업스테이지 API 키는 **`.env`** 파일에만 넣습니다. 이 폴더의 `.env`나 저장소 맨 위의 `.env` 중 **한 곳**에 두면 됩니다. Git에는 올리지 마세요. 복사용 예시는 **`.env.example`** 입니다.

```bash
cp assets/.env.example assets/.env
# 편집기로 assets/.env 열어 UPSTAGE_API_KEY 설정
```

## 환경 변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `UPSTAGE_API_KEY` | 예 | Upstage 콘솔에서 발급한 API 키 |
| `SOLAR_MODEL` | 아니오 | 추출·코칭에 쓸 모델 id. 생략 시 기본값 `solar-pro3` (`main.py` 및 스크립트와 동일 규칙) |

`diet_coach` 서버(`main.py`)는 **`skills/diet_coach/assets/.env`를 먼저** 읽은 뒤, 같은 폴더의 `.env` 또는 상위 디렉터리에서 만나는 **첫 번째** `.env`로 비어 있는 변수만 채운다(`override=False` — 이미 `assets/.env`에 있는 키는 덮어쓰지 않음).

`SKILL.md` 사전 준비 절을 함께 보면 된다.
