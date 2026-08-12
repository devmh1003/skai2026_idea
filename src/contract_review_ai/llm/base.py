"""코멘트 백엔드의 공통 골격."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models import (
    ChangeStatus,
    ClauseComparison,
    LegalComment,
    Party,
    PartyImpact,
    RiskFlag,
    RiskLevel,
)

NEUTRAL_VIEW = "특정 당사자에 치우치지 않는 중립"


@dataclass
class ClauseContext:
    """LLM에 넘길 조문 한 건의 검토 맥락."""

    heading: str
    status: ChangeStatus
    before_text: str
    after_text: str
    diff_summary: str = ""
    flags: list[RiskFlag] = field(default_factory=list)
    parties: list[Party] = field(default_factory=list)
    impacts: list[PartyImpact] = field(default_factory=list)
    view: Party | None = None
    """이 코멘트를 어느 당사자 관점에서 쓸지. None이면 중립."""

    @property
    def view_label(self) -> str:
        return self.view.display() if self.view else NEUTRAL_VIEW

    @classmethod
    def from_comparison(
        cls,
        comp: ClauseComparison,
        parties: list[Party],
        view: Party | None = None,
        max_chars: int = 4000,
    ) -> ClauseContext:
        return cls(
            heading=comp.heading,
            status=comp.status,
            before_text=_clip(comp.before.full_text if comp.before else "", max_chars),
            after_text=_clip(comp.after.full_text if comp.after else "", max_chars),
            flags=list(comp.flags),
            parties=list(parties),
            impacts=[i for i in comp.impacts if i.mentioned],
            view=view,
        )


class CommentBackend(ABC):
    """조문 비교 맥락 → 법무 코멘트."""

    name: str = "base"

    @abstractmethod
    def comment(self, ctx: ClauseContext) -> LegalComment: ...

    def close(self) -> None:  # pragma: no cover - 기본은 아무 것도 하지 않음
        return None


class ChatBackend(CommentBackend):
    """채팅형 LLM 위에 올리는 공통 구현: 프롬프트 구성 → 호출 → JSON 파싱."""

    @abstractmethod
    def chat(self, system: str, user: str) -> str: ...

    def comment(self, ctx: ClauseContext) -> LegalComment:
        from ..review.prompts import build_messages

        system, user = build_messages(ctx)
        try:
            raw = self.chat(system, user)
        except Exception as exc:  # 개별 조문 실패가 전체 리뷰를 죽이지 않게 한다
            return LegalComment(
                summary="모델 호출에 실패해 코멘트를 생성하지 못했습니다.",
                rationale=f"{type(exc).__name__}: {exc}",
                risk_level=RiskLevel.INFO,
                party_view=ctx.view_label,
                source=f"{self.name}(오류)",
            )
        return parse_comment(raw, source=self.name, party_view=ctx.view_label)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_LEVEL_MAP = {
    "high": RiskLevel.HIGH,
    "높음": RiskLevel.HIGH,
    "상": RiskLevel.HIGH,
    "medium": RiskLevel.MEDIUM,
    "중간": RiskLevel.MEDIUM,
    "중": RiskLevel.MEDIUM,
    "low": RiskLevel.LOW,
    "낮음": RiskLevel.LOW,
    "하": RiskLevel.LOW,
    "info": RiskLevel.INFO,
    "참고": RiskLevel.INFO,
}


def parse_comment(raw: str, source: str, party_view: str = NEUTRAL_VIEW) -> LegalComment:
    """모델 출력에서 JSON을 건져낸다. 실패해도 원문을 살려 리포트에 남긴다."""
    raw = (raw or "").strip()
    fallback = LegalComment(
        summary=raw[:500], source=source, party_view=party_view, raw=raw
    )

    match = _JSON_RE.search(raw)
    if not match:
        return fallback
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback
    if not isinstance(data, dict):
        return fallback

    level = str(data.get("risk_level", "info")).strip().lower()
    return LegalComment(
        summary=str(data.get("summary", "")).strip(),
        issues=_as_list(data.get("issues")),
        risk_level=_LEVEL_MAP.get(level, RiskLevel.INFO),
        rationale=str(data.get("rationale", "")).strip(),
        negotiation_points=_as_list(data.get("negotiation_points")),
        suggested_text=str(data.get("suggested_text", "")).strip(),
        party_view=party_view,
        source=source,
        raw=raw,
    )


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [line.strip("-• ").strip() for line in value.splitlines() if line.strip()]
    return []


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…(이하 생략)"
