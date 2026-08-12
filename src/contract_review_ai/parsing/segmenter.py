"""계약서 본문을 조(條) 단위로 자른다.

한국 계약서의 지배적 형식인 `제N조(제목)`을 1순위로 삼고,
그 형식이 없으면 번호 목록(`1.`, `가.`) → 빈 줄 문단 순으로 물러선다.
"""

from __future__ import annotations

import re

from ..models import Clause

# 제 1 조 (목적) / 제1조 [목적] / 제1조. 목적
ARTICLE_RE = re.compile(
    r"^\s*제\s*(?P<num>\d+)\s*조\s*"
    r"(?:[(\[（【]\s*(?P<title1>[^)\]）】\n]*?)\s*[)\]）】]|[.:：]?\s*(?P<title2>[^\n]{0,40}))?\s*$",
    re.MULTILINE,
)

# 조 헤더가 본문과 같은 줄에 붙어 있는 경우까지 잡는 완화 패턴
ARTICLE_INLINE_RE = re.compile(
    r"제\s*(?P<num>\d+)\s*조\s*[(\[（【]\s*(?P<title>[^)\]）】\n]*?)\s*[)\]）】]"
)

NUMBERED_RE = re.compile(r"^\s*(?P<num>\d{1,2})\s*[.)]\s*(?P<rest>\S.*)$", re.MULTILINE)

PREAMBLE_LABEL = "전문"


def normalize(text: str) -> str:
    """줄바꿈·공백·전각문자를 정규화한다. 비교 안정성의 출발점."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("　", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def segment_clauses(text: str) -> list[Clause]:
    text = normalize(text)
    if not text:
        return []

    clauses = _segment_by_article(text)
    if len(clauses) >= 2:
        return clauses

    clauses = _segment_by_inline_article(text)
    if len(clauses) >= 2:
        return clauses

    clauses = _segment_by_numbered_items(text)
    if len(clauses) >= 2:
        return clauses

    return _segment_by_paragraph(text)


def _segment_by_article(text: str) -> list[Clause]:
    matches = list(ARTICLE_RE.finditer(text))
    if not matches:
        return []

    clauses: list[Clause] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        clauses.append(Clause(index=0, number=PREAMBLE_LABEL, title="", body=preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        title = (match.group("title1") or match.group("title2") or "").strip()
        clauses.append(
            Clause(index=len(clauses), number=match.group("num"), title=title, body=body)
        )
    return clauses


def _segment_by_inline_article(text: str) -> list[Clause]:
    matches = list(ARTICLE_INLINE_RE.finditer(text))
    if not matches:
        return []

    clauses: list[Clause] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        clauses.append(Clause(index=0, number=PREAMBLE_LABEL, title="", body=preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clauses.append(
            Clause(
                index=len(clauses),
                number=match.group("num"),
                title=(match.group("title") or "").strip(),
                body=text[match.end() : end].strip(),
            )
        )
    return clauses


def _segment_by_numbered_items(text: str) -> list[Clause]:
    matches = list(NUMBERED_RE.finditer(text))
    if len(matches) < 2:
        return []

    clauses: list[Clause] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        clauses.append(Clause(index=0, number=PREAMBLE_LABEL, title="", body=preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        rest = match.group("rest").strip()
        title, body = _split_title(rest)
        clauses.append(
            Clause(
                index=len(clauses),
                number=match.group("num"),
                title=title,
                body=(body + "\n" + text[match.end() : end].strip()).strip(),
            )
        )
    return clauses


def _segment_by_paragraph(text: str) -> list[Clause]:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    clauses = []
    for i, block in enumerate(blocks):
        title, body = _split_title(block.split("\n", 1)[0])
        clauses.append(
            Clause(
                index=i,
                number=f"단락{i + 1}",
                title=title,
                body=block if body == "" else block,
            )
        )
    return clauses


def _split_title(line: str) -> tuple[str, str]:
    """`손해배상: 을은 ...` 처럼 제목-본문이 한 줄에 붙은 경우를 분리."""
    match = re.match(r"^\s*(?P<title>[^:：]{1,25})\s*[:：]\s*(?P<body>.*)$", line)
    if match:
        return match.group("title").strip(), match.group("body").strip()
    if len(line) <= 25:
        return line.strip(), ""
    return "", line.strip()
