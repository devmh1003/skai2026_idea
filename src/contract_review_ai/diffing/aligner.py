"""두 계약서의 조문을 서로 짝지어 신설·삭제·수정을 판정한다.

조 번호는 개정 과정에서 밀리거나 재배열되므로 번호만 믿을 수 없다.
본문 유사도를 주 신호로, 번호·제목 일치를 보조 신호로 쓴다.
"""

from __future__ import annotations

from ..models import ChangeStatus, Clause, ClauseComparison, Document
from .similarity import similarity
from .textdiff import diff_segments

MATCH_THRESHOLD = 0.45
"""이 값 미만이면 짝을 짓지 않고 삭제/신설로 본다."""

BODY_WEIGHT = 0.65
TITLE_WEIGHT = 0.35
NUMBER_BONUS = 0.10
TITLE_MATCH_BONUS = 0.15
"""제목이 완전히 같으면 본문이 통째로 바뀌었어도 같은 조문으로 본다.

실무에서 '제7조(손해배상)'의 내용을 전부 갈아엎는 개정이 흔한데, 이때 본문
유사도만 보면 삭제+신설로 잡혀 무엇이 바뀌었는지 대조할 수 없게 된다.
"""


def pair_score(before: Clause, after: Clause) -> float:
    body = similarity(before.body, after.body)
    same_title = bool(before.title) and before.title == after.title
    title = similarity(before.title, after.title) if (before.title or after.title) else body

    score = BODY_WEIGHT * body + TITLE_WEIGHT * title
    if before.number == after.number:
        score += NUMBER_BONUS
    if same_title:
        score += TITLE_MATCH_BONUS
    return min(score, 1.0)


def align_documents(before_doc: Document, after_doc: Document) -> list[ClauseComparison]:
    candidates: list[tuple[float, int, int]] = []
    for i, before in enumerate(before_doc.clauses):
        for j, after in enumerate(after_doc.clauses):
            score = pair_score(before, after)
            if score >= MATCH_THRESHOLD:
                candidates.append((score, i, j))

    # 점수 내림차순, 동점은 인덱스 순 — 실행할 때마다 같은 결과가 나오도록.
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    used_before: set[int] = set()
    used_after: set[int] = set()
    matched: list[tuple[int, int, float]] = []
    for score, i, j in candidates:
        if i in used_before or j in used_after:
            continue
        used_before.add(i)
        used_after.add(j)
        matched.append((i, j, score))

    comparisons: list[ClauseComparison] = []

    for i, j, score in matched:
        before = before_doc.clauses[i]
        after = after_doc.clauses[j]
        identical = _canonical(before) == _canonical(after)
        comparisons.append(
            ClauseComparison(
                status=ChangeStatus.UNCHANGED if identical else ChangeStatus.MODIFIED,
                before=before,
                after=after,
                similarity=1.0 if identical else score,
                segments=[] if identical else diff_segments(before.full_text, after.full_text),
            )
        )

    for i, clause in enumerate(before_doc.clauses):
        if i not in used_before:
            comparisons.append(
                ClauseComparison(
                    status=ChangeStatus.DELETED,
                    before=clause,
                    after=None,
                    similarity=0.0,
                    segments=diff_segments(clause.full_text, ""),
                )
            )

    for j, clause in enumerate(after_doc.clauses):
        if j not in used_after:
            comparisons.append(
                ClauseComparison(
                    status=ChangeStatus.ADDED,
                    before=None,
                    after=clause,
                    similarity=0.0,
                    segments=diff_segments("", clause.full_text),
                )
            )

    comparisons.sort(key=lambda c: c.sort_key)
    return comparisons


def _canonical(clause: Clause) -> str:
    return "".join(clause.full_text.split())
