"""파이프라인 전 구간에서 공유하는 데이터 구조."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ChangeStatus(StrEnum):
    """조문 하나가 두 계약서 사이에서 어떤 상태인지."""

    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"

    @property
    def label(self) -> str:
        return {"unchanged": "동일", "modified": "수정", "added": "신설", "deleted": "삭제"}[
            self.value
        ]


class RiskLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def label(self) -> str:
        return {"high": "높음", "medium": "중간", "low": "낮음", "info": "참고"}[self.value]

    @property
    def rank(self) -> int:
        return {"high": 3, "medium": 2, "low": 1, "info": 0}[self.value]


@dataclass
class Party:
    """계약 당사자. 2자 계약이든 다자 계약이든 동일하게 다룬다."""

    id: str
    """식별자. 보통 약칭과 같다. 예: "갑", "병"."""

    alias: str
    """계약서 본문에서 쓰이는 약칭."""

    name: str
    """정식 명칭. 예: "주식회사 가나다"."""

    role: str = ""
    """실무 라벨. 예: "발주자", "수급인", "연대보증인"."""

    def display(self) -> str:
        parts = [self.alias]
        if self.name and self.name != self.alias:
            parts.append(f"({self.name})")
        if self.role:
            parts.append(f"· {self.role}")
        return " ".join(parts)


@dataclass
class PartyImpact:
    """조문 변경이 특정 당사자에게 유리해졌는지 불리해졌는지.

    문장 단위로 '의무 표현'과 '권리 표현'을 세어 점수화한 휴리스틱이다.
    법적 판단이 아니라, 검토자가 어디를 먼저 볼지 정하는 신호로 쓴다.
    """

    party_id: str
    alias: str
    before_obligations: int = 0
    before_rights: int = 0
    after_obligations: int = 0
    after_rights: int = 0

    @property
    def before_score(self) -> int:
        return self.before_rights - self.before_obligations

    @property
    def after_score(self) -> int:
        return self.after_rights - self.after_obligations

    @property
    def delta(self) -> int:
        return self.after_score - self.before_score

    @property
    def verdict(self) -> str:
        if self.delta > 0:
            return "favorable"
        if self.delta < 0:
            return "adverse"
        return "neutral"

    @property
    def verdict_label(self) -> str:
        return {"favorable": "유리", "adverse": "불리", "neutral": "중립"}[self.verdict]

    @property
    def mentioned(self) -> bool:
        return (
            self.before_obligations
            + self.before_rights
            + self.after_obligations
            + self.after_rights
        ) > 0


@dataclass
class Clause:
    """계약서의 조(條) 하나. 항·호는 본문에 그대로 담는다."""

    index: int
    """문서 내 등장 순서 (0부터)."""

    number: str
    """조 번호 문자열. 예: "3". 번호를 못 찾으면 "전문", "부칙" 등 라벨."""

    title: str
    """조 제목. 예: "손해배상". 없으면 빈 문자열."""

    body: str
    """조 본문 (제목 줄 제외)."""

    @property
    def heading(self) -> str:
        if self.number.isdigit():
            base = f"제{self.number}조"
        else:
            base = self.number
        return f"{base}({self.title})" if self.title else base

    @property
    def full_text(self) -> str:
        return f"{self.heading}\n{self.body}".strip()


@dataclass
class Document:
    name: str
    path: str
    clauses: list[Clause]
    parties: list[Party] = field(default_factory=list)
    version: str = ""
    """버전 저장소에 등록된 경우의 버전 라벨. 예: "v2"."""

    @property
    def text(self) -> str:
        return "\n\n".join(clause.full_text for clause in self.clauses)


@dataclass
class DiffSegment:
    """단어 단위 diff 조각."""

    op: str  # "equal" | "insert" | "delete"
    text: str


@dataclass
class RiskFlag:
    """룰 기반으로 탐지한 위험 신호. LLM 코멘트의 근거로 함께 전달된다."""

    code: str
    category: str
    level: RiskLevel
    message: str
    evidence: str = ""
    side: str = "both"  # "before" | "after" | "both" — 어느 쪽 문안에서 탐지됐는지


@dataclass
class LegalComment:
    """LLM이 생성한 법무 코멘트."""

    summary: str = ""
    issues: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.INFO
    rationale: str = ""
    negotiation_points: list[str] = field(default_factory=list)
    suggested_text: str = ""
    party_view: str = ""
    """어느 당사자 관점에서 작성된 코멘트인지."""

    source: str = "offline"
    """코멘트를 만든 백엔드 이름 — 리포트에 표기해 책임 소재를 남긴다."""

    raw: str = ""


@dataclass
class ClauseComparison:
    """조문 한 쌍(또는 한쪽만)의 비교 결과."""

    status: ChangeStatus
    before: Clause | None
    after: Clause | None
    similarity: float = 1.0
    segments: list[DiffSegment] = field(default_factory=list)
    flags: list[RiskFlag] = field(default_factory=list)
    impacts: list[PartyImpact] = field(default_factory=list)
    comments: list[LegalComment] = field(default_factory=list)

    @property
    def comment(self) -> LegalComment | None:
        return self.comments[0] if self.comments else None

    @property
    def heading(self) -> str:
        clause = self.after or self.before
        return clause.heading if clause else "(알 수 없음)"

    @property
    def sort_key(self) -> tuple[int, int]:
        clause = self.after or self.before
        if clause is None:
            return (9999, 0)
        num = int(clause.number) if clause.number.isdigit() else 9998
        return (num, clause.index)

    @property
    def categories(self) -> list[str]:
        return sorted({f.category for f in self.flags})

    @property
    def rule_level(self) -> RiskLevel:
        if not self.flags:
            return RiskLevel.INFO
        return max((f.level for f in self.flags), key=lambda lv: lv.rank)

    @property
    def effective_level(self) -> RiskLevel:
        """룰과 LLM 판정 중 더 보수적인(높은) 쪽을 채택한다."""
        levels = [self.rule_level] + [c.risk_level for c in self.comments]
        return max(levels, key=lambda lv: lv.rank)

    def adverse_parties(self) -> list[str]:
        return [i.party_id for i in self.impacts if i.verdict == "adverse"]


@dataclass
class VersionRecord:
    """버전 저장소에 등록된 계약서 한 버전."""

    version: str
    label: str
    file: str
    sha256: str
    imported_at: str
    note: str = ""

    @property
    def order(self) -> int:
        digits = "".join(ch for ch in self.version if ch.isdigit())
        return int(digits) if digits else 0


@dataclass
class TimelineStep:
    """연속한 두 버전 사이의 변경 요약 (대시보드 이력 탭용)."""

    from_version: str
    to_version: str
    modified: int
    added: int
    deleted: int
    high: int
    medium: int
    flagged: int = 0
    """쟁점 신호가 붙은 조문 수."""

    headings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.modified + self.added + self.deleted


@dataclass
class ReviewResult:
    before_doc: Document
    after_doc: Document
    comparisons: list[ClauseComparison]
    parties: list[Party] = field(default_factory=list)
    timeline: list[TimelineStep] = field(default_factory=list)
    contract_id: str = ""
    backend: str = "offline"
    model: str = ""
    generated_at: str = ""

    def changed(self) -> list[ClauseComparison]:
        return [c for c in self.comparisons if c.status is not ChangeStatus.UNCHANGED]

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in ChangeStatus}
        for comp in self.comparisons:
            out[comp.status.value] += 1
        return out

    def risk_counts(self) -> dict[str, int]:
        out = {lv.value: 0 for lv in RiskLevel}
        for comp in self.changed():
            out[comp.effective_level.value] += 1
        return out

    def category_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for comp in self.changed():
            for category in comp.categories:
                out[category] = out.get(category, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    def party_summary(self) -> list[dict[str, Any]]:
        """당사자별 유리/불리 조문 수."""
        summary = {
            p.id: {"party_id": p.id, "alias": p.alias, "name": p.name, "role": p.role,
                   "favorable": 0, "adverse": 0, "neutral": 0, "high": 0}
            for p in self.parties
        }
        for comp in self.changed():
            for impact in comp.impacts:
                row = summary.get(impact.party_id)
                if row is None or not impact.mentioned:
                    continue
                row[impact.verdict] += 1
                if impact.verdict == "adverse" and comp.effective_level is RiskLevel.HIGH:
                    row["high"] += 1
        return list(summary.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "before": {
                "name": self.before_doc.name,
                "path": self.before_doc.path,
                "version": self.before_doc.version,
            },
            "after": {
                "name": self.after_doc.name,
                "path": self.after_doc.path,
                "version": self.after_doc.version,
            },
            "backend": self.backend,
            "model": self.model,
            "generated_at": self.generated_at,
            "parties": [
                {"id": p.id, "alias": p.alias, "name": p.name, "role": p.role}
                for p in self.parties
            ],
            "counts": self.counts(),
            "risk_counts": self.risk_counts(),
            "category_counts": self.category_counts(),
            "party_summary": self.party_summary(),
            "timeline": [
                {
                    "from": t.from_version,
                    "to": t.to_version,
                    "modified": t.modified,
                    "added": t.added,
                    "deleted": t.deleted,
                    "high": t.high,
                    "medium": t.medium,
                    "flagged": t.flagged,
                    "headings": t.headings,
                }
                for t in self.timeline
            ],
            "comparisons": [
                {
                    "status": c.status.value,
                    "heading": c.heading,
                    "similarity": round(c.similarity, 4),
                    "risk_level": c.effective_level.value,
                    "categories": c.categories,
                    "before": c.before.full_text if c.before else None,
                    "after": c.after.full_text if c.after else None,
                    "flags": [
                        {
                            "code": f.code,
                            "category": f.category,
                            "level": f.level.value,
                            "message": f.message,
                            "evidence": f.evidence,
                            "side": f.side,
                        }
                        for f in c.flags
                    ],
                    "impacts": [
                        {
                            "party_id": i.party_id,
                            "alias": i.alias,
                            "delta": i.delta,
                            "verdict": i.verdict,
                            "before_score": i.before_score,
                            "after_score": i.after_score,
                        }
                        for i in c.impacts
                        if i.mentioned
                    ],
                    "comments": [
                        {
                            "summary": cm.summary,
                            "issues": cm.issues,
                            "risk_level": cm.risk_level.value,
                            "rationale": cm.rationale,
                            "negotiation_points": cm.negotiation_points,
                            "suggested_text": cm.suggested_text,
                            "party_view": cm.party_view,
                            "source": cm.source,
                        }
                        for cm in c.comments
                    ],
                }
                for c in self.comparisons
            ],
        }
