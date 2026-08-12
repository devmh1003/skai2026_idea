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


_SENTENCE_RE = re.compile(r"[^\n.。]+[.。]?")


def sentence_changes(before: str, after: str) -> tuple[list[str], list[str]]:
    """문장 단위로 삭제·추가된 문장을 뽑는다.

    조문을 통째로 다시 쓴 개정에서는 단어 단위 diff가 수십 개의 조각으로
    부서져 오히려 읽기 어렵다. 그럴 때는 문장 단위가 사람 눈에 맞다.
    """
    a = [s.strip() for s in _SENTENCE_RE.findall(before) if s.strip()]
    b = [s.strip() for s in _SENTENCE_RE.findall(after) if s.strip()]

    matcher = SequenceMatcher(a=a, b=b, autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            removed.extend(a[i1:i2])
        if tag in ("insert", "replace"):
            added.extend(b[j1:j2])
    return removed, added


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
