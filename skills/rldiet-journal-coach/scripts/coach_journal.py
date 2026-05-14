"""
Solar Chat로 한국어 다이어트 저널을 구조화 JSON으로 변환합니다.
의존성: 표준 라이브러리만 사용합니다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _find_repo_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".git").is_dir():
            return p
    return None


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        key, val = k.strip(), v.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _ensure_api_key() -> str:
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    repo = _find_repo_root(script_dir)
    paths: list[Path] = []
    if repo:
        paths.append(repo / ".env")
    paths.append(skill_dir / "assets" / ".env")
    if repo:
        paths.append(repo / "skills" / "solar-skill-creator" / "assets" / ".env")
    for p in paths:
        _load_dotenv(p)
    key = os.environ.get("UPSTAGE_API_KEY", "").strip()
    if not key:
        print("UPSTAGE_API_KEY가 없습니다. 리포 루트 .env 또는 assets/.env를 설정하세요.", file=sys.stderr)
        sys.exit(1)
    return key


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise RuntimeError(f"JSON 파싱 실패: {e}") from e
    raise RuntimeError("응답에서 JSON 객체를 찾지 못했습니다.")


SYSTEM = """당신은 비의료 다이어트 생활 코치입니다. 의학적 진단·처방·검사 해석은 하지 마세요.
사용자 저널을 읽고 반드시 JSON 한 개만 출력하세요. 마크다운·코드펜스·설명 문장 금지.
스키마:
{"summary_ko": string, "focus_tomorrow": [string, ...], "signals": [string, ...], "risk_flags": [string, ...]}
risk_flags 예: extreme_calorie_restriction, severe_sleep_deprivation 등 (해당 없으면 [])
"""


def run_solar(journal: str, api_key: str, model: str = "solar-mini") -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": f"아래 저널만 보고 JSON만 출력하세요.\n\n---\n{journal}\n---",
            },
        ],
        "temperature": 0.3,
        "max_tokens": 512,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.upstage.ai/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err}") from e
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"예상치 못한 응답 형식: {payload!r}") from e
    return _extract_json_object(content)


def main() -> None:
    p = argparse.ArgumentParser(description="다이어트 저널 → Solar JSON 코칭")
    p.add_argument("--journal", "-j", help="저널 한 덩어리 문자열")
    p.add_argument("--model", default="solar-mini", help="Solar 모델 id")
    args = p.parse_args()

    if args.journal is not None:
        journal = args.journal
    else:
        if sys.stdin.isatty():
            p.print_help()
            sys.exit(2)
        journal = sys.stdin.read().strip()
    if not journal:
        print("저널 내용이 비었습니다.", file=sys.stderr)
        sys.exit(2)

    key = _ensure_api_key()
    out = run_solar(journal, key, model=args.model)
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
