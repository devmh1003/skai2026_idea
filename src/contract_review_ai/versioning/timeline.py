"""버전 체인 전체의 변경 이력 요약.

연속한 두 버전마다 정렬·diff·룰만 돌린다(LLM 호출 없음). 20개 버전이 쌓여도
수 초 안에 끝나므로 대시보드 '변경 이력' 탭에 항상 붙일 수 있다.
"""

from __future__ import annotations

from ..diffing import align_documents
from ..models import ChangeStatus, RiskLevel, TimelineStep
from ..parsing import load_document
from ..risk import analyze_comparison
from .store import VersionStore


def build_timeline(store: VersionStore, contract_id: str, max_headings: int = 6) -> list[TimelineStep]:
    records = store.versions(contract_id)
    if len(records) < 2:
        return []

    steps: list[TimelineStep] = []
    previous = load_document(store.resolve(contract_id, records[0].version))

    for record in records[1:]:
        current = load_document(store.resolve(contract_id, record.version))
        comparisons = align_documents(previous, current)
        for comp in comparisons:
            comp.flags = analyze_comparison(comp)

        changed = [c for c in comparisons if c.status is not ChangeStatus.UNCHANGED]
        risky = sorted(
            (c for c in changed if c.rule_level.rank >= RiskLevel.MEDIUM.rank),
            key=lambda c: (-c.rule_level.rank, c.sort_key),
        )
        steps.append(
            TimelineStep(
                from_version=previous.version or records[len(steps)].version,
                to_version=record.version,
                modified=sum(1 for c in changed if c.status is ChangeStatus.MODIFIED),
                added=sum(1 for c in changed if c.status is ChangeStatus.ADDED),
                deleted=sum(1 for c in changed if c.status is ChangeStatus.DELETED),
                high=sum(1 for c in changed if c.rule_level is RiskLevel.HIGH),
                medium=sum(1 for c in changed if c.rule_level is RiskLevel.MEDIUM),
                headings=[c.heading for c in risky[:max_headings]],
            )
        )
        previous = current
        previous.version = record.version

    return steps
