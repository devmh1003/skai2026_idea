"""콘솔 출력 인코딩 보정."""

from __future__ import annotations

import sys


def force_utf8() -> None:
    """한국어 Windows 콘솔의 기본 코드페이지(cp949)에서도 깨지지 않게 한다.

    조문 제목·법무 문구가 전부 한글이라, 이 처리가 없으면 출력이 깨지거나
    em-dash 같은 문자에서 UnicodeEncodeError로 죽는다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # 리다이렉트된 스트림 등
            pass
