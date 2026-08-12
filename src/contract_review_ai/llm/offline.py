"""모델 없이 룰만으로 코멘트를 구성하는 폴백 백엔드.

GPU도 API 토큰도 없는 환경에서 파이프라인 전체(파싱→당사자→정렬→diff→리포트)를
그대로 검증할 수 있게 한다. 출력에는 항상 `offline(룰기반)` 출처가 붙어
LLM 코멘트와 혼동되지 않는다.
"""

from __future__ import annotations

from ..models import ChangeStatus, LegalComment, RiskLevel
from .base import ClauseContext, CommentBackend

_STATUS_TEXT = {
    ChangeStatus.MODIFIED: "조문이 수정되었습니다",
    ChangeStatus.ADDED: "조문이 신설되었습니다",
    ChangeStatus.DELETED: "조문이 삭제되었습니다",
    ChangeStatus.UNCHANGED: "변경이 없습니다",
}


class OfflineBackend(CommentBackend):
    name = "offline(룰기반)"

    def comment(self, ctx: ClauseContext) -> LegalComment:
        categories = sorted({f.category for f in ctx.flags})
        level = (
            max((f.level for f in ctx.flags), key=lambda lv: lv.rank)
            if ctx.flags
            else RiskLevel.LOW
        )

        summary = _STATUS_TEXT[ctx.status]
        if categories:
            summary += f". 쟁점 영역: {', '.join(categories)}"
        adverse = [i.alias for i in ctx.impacts if i.verdict == "adverse"]
        if adverse:
            summary += f". 추정 불리 당사자: {', '.join(adverse)}"
        summary += "."

        issues = [f"[{f.category}] {f.message}" for f in ctx.flags]
        for impact in ctx.impacts:
            if impact.verdict == "neutral":
                continue
            issues.append(
                f"[당사자영향] {impact.alias}의 권리·의무 균형이 "
                f"{impact.before_score} → {impact.after_score}로 이동({impact.verdict_label})"
            )

        return LegalComment(
            summary=summary,
            issues=issues,
            risk_level=level,
            rationale=(
                "LLM 백엔드를 사용할 수 없어 룰 엔진과 당사자 영향 휴리스틱만으로 작성한 "
                "코멘트입니다. 조문별 정밀 해석은 A.X 모델 백엔드(local 또는 hf_api)로 "
                "재실행하십시오."
            ),
            negotiation_points=_points(categories),
            party_view=ctx.view_label,
            source=self.name,
        )


_POINT_MAP = {
    "손해배상": "책임 한도(계약금액 100% 등)와 간접·특별·결과적 손해 배제 문언을 명시할 것",
    "위약벌": "'위약벌'이 아닌 '손해배상액의 예정'으로 성질을 명시하고 상한을 둘 것",
    "계약해지": "해지 사유를 한정하고 30일 이상의 시정 기간을 둘 것",
    "지식재산권": "기존 보유 IP와 산출물 IP를 분리하고 업무용 실시권을 확보할 것",
    "면책·보상": "면책 대상 청구를 한정하고 책임 상한을 면책에도 적용할 것",
    "준거법·분쟁해결": "준거법을 대한민국 법으로, 관할을 국내 법원으로 유지할 것",
    "대금지급": "지급 기일과 검수 기간을 분리 명시하고 지연이자를 규정할 것",
    "지체상금": "지체상금 총액 상한(계약금액의 10% 등)을 둘 것",
    "비밀유지": "비밀유지 의무와 존속 기간을 양 당사자 대칭으로 맞출 것",
    "경업금지": "기간·지역·대상 업무를 합리적 범위로 한정할 것",
    "계약기간": "자동 갱신 시 조건 변경 금지와 갱신 거절 통지 기한을 명시할 것",
    "불가항력": "불가항력 면책 조항을 복원하고 통지 절차를 규정할 것",
    "수치변경": "변경된 기간·요율·금액의 산정 근거를 서면으로 확인할 것",
    "조문삭제": "삭제된 권리·의무가 다른 조문으로 이관되었는지 대조할 것",
}


def _points(categories: list[str]) -> list[str]:
    points = [_POINT_MAP[c] for c in categories if c in _POINT_MAP]
    return points or ["변경 취지와 실무 영향에 대해 상대방 설명을 서면으로 받을 것"]
