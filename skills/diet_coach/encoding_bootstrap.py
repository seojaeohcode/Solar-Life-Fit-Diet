"""표준 입출력을 UTF-8로 고정한다.

Windows 콘솔 기본 코드 페이지(cp949)에서도 `print`·로그·JSON 출력이 한글로 깨지지 않도록,
`PYTHONUTF8`·`chcp 65001` 등 외부 설정 없이 이 모듈을 **가장 먼저** import하면 된다.
"""

from __future__ import annotations

import io
import sys


def ensure_utf8_stdio() -> None:
    for name in ("stdout", "stderr", "stdin"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
            continue


ensure_utf8_stdio()
