"""표준 입출력을 UTF-8로 고정한다. (diet_coach/encoding_bootstrap.py 와 동일 목적)"""

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
