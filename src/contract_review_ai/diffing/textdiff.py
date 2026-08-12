"""조문 본문의 단어 단위 diff."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..models import DiffSegment

_TOKEN_RE = re.compile(r"\s+|[^\s]+")


def tokenize(text: str) -> list[str]:
    """공백까지 토큰으로 보존해 원문 복원이 가능하게 한다."""
    return _TOKEN_RE.findall(text)


def diff_segments(before: str, after: str) -> list[DiffSegment]:
    a, b = tokenize(before), tokenize(after)
    matcher = SequenceMatcher(a=a, b=b, autojunk=False)
    segments: list[DiffSegment] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append(DiffSegment("equal", "".join(a[i1:i2])))
        elif tag == "delete":
            segments.append(DiffSegment("delete", "".join(a[i1:i2])))
        elif tag == "insert":
            segments.append(DiffSegment("insert", "".join(b[j1:j2])))
        else:  # replace → 삭제 후 삽입으로 펼친다
            segments.append(DiffSegment("delete", "".join(a[i1:i2])))
            segments.append(DiffSegment("insert", "".join(b[j1:j2])))

    return [s for s in segments if s.text]


def summarize_segments(segments: list[DiffSegment], limit: int = 6) -> str:
    """LLM 프롬프트에 넣을 변경점 요약. 공백만 바뀐 조각은 버린다."""
    removed = [s.text.strip() for s in segments if s.op == "delete" and s.text.strip()]
    added = [s.text.strip() for s in segments if s.op == "insert" and s.text.strip()]

    lines: list[str] = []
    for text in removed[:limit]:
        lines.append(f"- 삭제: {_clip(text)}")
    if len(removed) > limit:
        lines.append(f"- (삭제 {len(removed) - limit}건 더)")
    for text in added[:limit]:
        lines.append(f"- 추가: {_clip(text)}")
    if len(added) > limit:
        lines.append(f"- (추가 {len(added) - limit}건 더)")

    return "\n".join(lines) if lines else "- (문언상 유의미한 변경 없음)"


def _clip(text: str, width: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width] + " …"
