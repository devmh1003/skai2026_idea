"""회의 내용을 조문 수정안으로 옮긴다.

협상 회의가 끝나면 "3조 지급기일 45일로, 7조 배상 한도는 계약금액 100%로" 같은
합의가 회의록에 남는다. 그 합의를 다시 계약서 문안으로 옮기는 일은 사람이 조문을
찾아가며 손으로 하는데, 이 모듈이 그 사이를 잇는다.

    1. 회의록을 합의 항목 단위로 쪼갠다(줄·불릿·번호 목록).
    2. 각 항목이 어느 조문을 가리키는지 찾는다.
       - 조 번호를 직접 적었으면(3조, 제7조) 그 조문
       - 아니면 제목·본문과의 문자 3-gram 유사도로 가장 가까운 조문
    3. 조문별로 수정 문안을 만든다.
       - 언어모델이 붙어 있으면 합의 내용을 반영한 문안을 생성
       - 없으면 원문과 근거를 그대로 보여주고 사람이 고치게 한다

어느 쪽이든 결과는 '제안'이며, 채택 여부는 사용자가 조문마다 고른다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .diffing import similarity
from .llm.base import CommentBackend
from .models import Clause

_BULLET = re.compile(r"^\s*(?:[-*·•]|\d+[.)]|[가-힣][.)])\s*")
_ARTICLE_REF = re.compile(r"제?\s*(\d{1,3})\s*조")
_MATCH_FLOOR = 0.12
"""이보다 낮으면 어느 조문을 가리키는지 모르겠다고 본다 — 억지로 붙이지 않는다."""


@dataclass
class MeetingItem:
    """회의록에서 뽑은 합의 항목 하나."""

    text: str
    clause_index: int | None = None
    score: float = 0.0
    basis: str = ""
    """왜 이 조문에 붙였는지 — '3조 명시' 또는 '문언 유사도'."""


@dataclass
class ClauseProposal:
    """조문 하나에 대한 수정 제안."""

    heading: str
    current: str
    proposed: str = ""
    items: list[str] = field(default_factory=list)
    note: str = ""
    source: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.proposed) and _norm(self.proposed) != _norm(self.current)


def split_items(minutes: str) -> list[str]:
    """회의록을 합의 항목으로 쪼갠다.

    불릿·번호 목록이면 그 단위로, 아니면 문장 단위로 나눈다. 회의록은 형식이
    제각각이라 둘 다 받아 준다.
    """
    lines = [line.strip() for line in minutes.splitlines()]
    bullets = [_BULLET.sub("", line) for line in lines if line and _BULLET.match(line)]
    if len(bullets) >= 2:
        return [b for b in bullets if b]

    chunks = re.split(r"(?<=[.。])\s+|\n+", minutes)
    return [c.strip() for c in chunks if len(c.strip()) >= 6]


def match_items(items: list[str], clauses: list[Clause]) -> list[MeetingItem]:
    """각 합의 항목을 조문에 붙인다."""
    matched: list[MeetingItem] = []
    by_number = {c.number: index for index, c in enumerate(clauses)}

    for text in items:
        reference = _ARTICLE_REF.search(text)
        if reference and reference.group(1) in by_number:
            matched.append(
                MeetingItem(
                    text=text,
                    clause_index=by_number[reference.group(1)],
                    score=1.0,
                    basis=f"제{reference.group(1)}조 명시",
                )
            )
            continue

        best_index, best_score = None, 0.0
        for index, clause in enumerate(clauses):
            score = max(
                similarity(text, clause.title) if clause.title else 0.0,
                similarity(text, clause.body) * 0.9,
            )
            if score > best_score:
                best_index, best_score = index, score

        if best_index is not None and best_score >= _MATCH_FLOOR:
            matched.append(
                MeetingItem(
                    text=text,
                    clause_index=best_index,
                    score=best_score,
                    basis="문언 유사도",
                )
            )
        else:
            matched.append(MeetingItem(text=text, basis="관련 조문 미확인"))

    return matched


SYSTEM_PROMPT = """당신은 대한민국 법률 실무에 밝은 사내 법무팀 계약 담당자입니다.
협상 회의에서 합의된 내용을 계약 조문에 반영하는 수정 문안을 작성합니다.

원칙:
1. 합의된 사항만 반영합니다. 합의에 없는 내용을 새로 넣지 않습니다.
2. 기존 조문의 문체와 구조를 유지하고, 바뀌어야 할 부분만 고칩니다.
3. 숫자(기간·요율·금액)는 회의에서 정한 값을 그대로 씁니다.
4. 합의 내용이 조문에 반영하기에 모호하면 수정하지 말고 무엇이 불분명한지 적습니다.

반드시 아래 JSON 한 개만 출력합니다. 다른 말을 덧붙이지 않습니다.

{
  "revised": "수정된 조문 본문 전체(제목 줄 제외). 수정이 불필요하면 빈 문자열",
  "note": "무엇을 어떻게 반영했는지 또는 반영하지 못한 이유 한 문장"
}"""


def build_prompt(clause: Clause, items: list[str]) -> tuple[str, str]:
    agreed = "\n".join(f"- {item}" for item in items)
    user = f"""## 현재 조문
{clause.full_text}

## 회의에서 합의된 사항
{agreed}

## 지시
합의된 사항을 반영한 조문 본문을 작성하고, 지정된 JSON 형식으로만 답하십시오."""
    return SYSTEM_PROMPT, user


def build_proposals(
    clauses: list[Clause], minutes: str, backend: CommentBackend | None = None
) -> tuple[list[ClauseProposal], list[MeetingItem]]:
    """회의록 → 조문별 수정 제안."""
    items = match_items(split_items(minutes), clauses)

    grouped: dict[int, list[str]] = {}
    for item in items:
        if item.clause_index is not None:
            grouped.setdefault(item.clause_index, []).append(item.text)

    proposals: list[ClauseProposal] = []
    for index in sorted(grouped):
        clause = clauses[index]
        proposal = ClauseProposal(
            heading=clause.heading, current=clause.body, items=grouped[index]
        )
        _fill(proposal, clause, backend)
        proposals.append(proposal)

    return proposals, items


def _fill(proposal: ClauseProposal, clause: Clause, backend: CommentBackend | None) -> None:
    """수정 문안을 채운다. 언어모델이 없으면 원문을 그대로 두고 안내만 남긴다."""
    chat = getattr(backend, "chat", None)
    if chat is None:
        proposal.proposed = clause.body
        proposal.note = "합의 사항이 이 조문에 걸립니다. 문안을 직접 수정하십시오."
        proposal.source = "규정 검토 엔진"
        return

    system, user = build_prompt(clause, proposal.items)
    try:
        raw = chat(system, user)
    except Exception as exc:
        proposal.proposed = clause.body
        proposal.note = f"문안 생성에 실패했습니다: {type(exc).__name__}"
        proposal.source = "오류"
        return

    revised, note = _parse(raw)
    proposal.proposed = revised or clause.body
    proposal.note = note or ("수정 제안 없음" if not revised else "")
    proposal.source = getattr(backend, "name", "언어모델")


def _parse(raw: str) -> tuple[str, str]:
    import json

    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return "", (raw or "").strip()[:200]
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return "", (raw or "").strip()[:200]
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("revised", "")).strip(), str(data.get("note", "")).strip()


def _norm(text: str) -> str:
    return "".join(text.split())
