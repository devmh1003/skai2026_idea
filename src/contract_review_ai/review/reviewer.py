"""파이프라인 오케스트레이션.

로드 → 당사자 인식 → 조문 정렬 → diff → 룰 → 당사자 영향 → LLM 코멘트 → 버전 이력.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..config import Settings
from ..diffing import align_documents, summarize_segments
from ..llm.base import ClauseContext, CommentBackend
from ..llm.factory import create_backend
from ..models import ChangeStatus, Party, ReviewResult, RiskLevel
from ..parsing import load_document
from ..parties import analyze_impacts, merge_parties
from ..risk import analyze_comparison
from ..versioning import VersionStore, build_timeline

ProgressFn = Callable[[str], None]


def _default_progress(message: str) -> None:
    print(message, file=sys.stderr)


def review_contracts(
    before_path: str | Path,
    after_path: str | Path,
    settings: Settings | None = None,
    views: list[str] | None = None,
    min_level: RiskLevel = RiskLevel.INFO,
    backend: CommentBackend | None = None,
    progress: ProgressFn | None = _default_progress,
    contract_id: str = "",
    store: VersionStore | None = None,
    before_version: str = "",
    after_version: str = "",
) -> ReviewResult:
    """두 계약서를 비교하고 변경 조문마다 법무 코멘트를 붙인다.

    views:
        None 또는 [] → 중립 관점 코멘트 1건
        ["을"]        → 을 관점 1건
        ["갑","을"]   → 당사자별로 각각 생성 (다자간 계약 협상 대비용)
    min_level:
        이 값 이상의 룰 위험도를 가진 조문만 LLM에 보낸다. 변경이 수십 건인
        계약서에서 호출 비용과 시간을 통제하기 위한 장치.
    """
    settings = settings or Settings.from_env()
    say = progress or (lambda _: None)

    before_doc = load_document(before_path, name=Path(before_path).stem, version=before_version)
    after_doc = load_document(after_path, name=Path(after_path).stem, version=after_version)
    parties = merge_parties(before_doc.parties, after_doc.parties)
    say(
        f"조문 추출: {before_doc.name} {len(before_doc.clauses)}건 / "
        f"{after_doc.name} {len(after_doc.clauses)}건"
    )
    say(f"당사자 인식: {', '.join(p.display() for p in parties) or '없음'}")

    comparisons = align_documents(before_doc, after_doc)
    for comp in comparisons:
        comp.flags = analyze_comparison(comp)
        comp.impacts = analyze_impacts(comp, parties)

    changed = [c for c in comparisons if c.status is not ChangeStatus.UNCHANGED]
    say(f"변경 조문 {len(changed)}건 탐지 (전체 {len(comparisons)}건)")

    targets = [c for c in changed if c.rule_level.rank >= min_level.rank]
    if len(targets) < len(changed):
        say(f"위험도 {min_level.label} 이상 {len(targets)}건만 코멘트 생성")

    view_parties = _resolve_views(views, parties)
    own_backend = backend is None
    backend = backend or create_backend(settings)
    try:
        for i, comp in enumerate(targets, start=1):
            diff_summary = summarize_segments(comp.segments)
            for view in view_parties:
                tag = view.alias if view else "중립"
                say(f"  [{i}/{len(targets)}] {comp.heading} · {tag} 관점 코멘트 생성 중…")
                ctx = ClauseContext.from_comparison(
                    comp, parties, view=view, max_chars=settings.max_clause_chars
                )
                ctx.diff_summary = diff_summary
                comp.comments.append(backend.comment(ctx))
    finally:
        if own_backend:
            backend.close()

    timeline = []
    if contract_id and store is not None:
        try:
            timeline = build_timeline(store, contract_id)
        except (FileNotFoundError, ValueError) as exc:
            say(f"[경고] 버전 이력을 만들지 못했습니다: {exc}")

    return ReviewResult(
        before_doc=before_doc,
        after_doc=after_doc,
        comparisons=comparisons,
        parties=parties,
        timeline=timeline,
        contract_id=contract_id,
        backend=backend.name,
        model=settings.model,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def review_versions(
    contract_id: str,
    before_spec: str = "first",
    after_spec: str = "latest",
    store: VersionStore | None = None,
    **kwargs,
) -> ReviewResult:
    """버전 저장소에 등록된 두 버전을 비교한다."""
    store = store or VersionStore()
    before_path = store.resolve(contract_id, before_spec)
    after_path = store.resolve(contract_id, after_spec)
    records = {r.version: r for r in store.versions(contract_id)}

    def _version_of(path: Path) -> str:
        for version, record in records.items():
            if record.file == path.name:
                return version
        return ""

    result = review_contracts(
        before_path,
        after_path,
        contract_id=contract_id,
        store=store,
        before_version=_version_of(before_path),
        after_version=_version_of(after_path),
        **kwargs,
    )

    # 저장소 파일명 대신 등록 당시의 라벨을 문서 이름으로 쓴다.
    for doc in (result.before_doc, result.after_doc):
        record = records.get(doc.version)
        if record and record.label:
            doc.name = f"{doc.version} {record.label}"
    return result


def _resolve_views(views: list[str] | None, parties: list[Party]) -> list[Party | None]:
    if not views:
        return [None]

    by_id = {p.id: p for p in parties}
    if len(views) == 1 and views[0].lower() in {"all", "전체"}:
        return list(parties) or [None]

    resolved: list[Party | None] = []
    for name in views:
        party = by_id.get(name)
        if party is None:
            party = Party(id=name, alias=name, name="", role="")
        resolved.append(party)
    return resolved or [None]
