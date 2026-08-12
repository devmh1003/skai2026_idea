"""A.X 모델에 넣을 법무 검토 프롬프트."""

from __future__ import annotations

from ..llm.base import ClauseContext

SYSTEM_PROMPT = """당신은 대한민국 법률 실무에 밝은 사내 법무팀 계약 검토 담당자입니다.
두 버전의 계약 조문을 비교해, 변경이 지정된 당사자에게 미치는 법적 영향을 검토합니다.

원칙:
1. 조문에 실제로 적힌 문언만 근거로 삼습니다. 없는 사실을 만들지 않습니다.
2. 판례·법령은 확실한 것만 일반적 수준으로 언급하고, 조문 번호를 지어내지 않습니다.
3. "불리해졌다"고만 쓰지 말고, 어떤 문언이 어떤 법적 효과를 만드는지 설명합니다.
4. 당사자가 셋 이상인 다자간 계약에서는 각 당사자의 의무가 연대책임인지 분할책임인지,
   특정 당사자만 일방적으로 부담하는 구조인지를 반드시 짚습니다.
5. 수정 문안은 그대로 상대방에게 보낼 수 있는 완성된 한국어 계약 문장으로 씁니다.
6. 확신이 서지 않으면 단정하지 말고 '확인 필요'로 표시합니다.

반드시 아래 JSON 한 개만 출력합니다. 코드블록 표시나 설명 문장을 덧붙이지 않습니다.

{
  "summary": "무엇이 어떻게 바뀌었는지 2문장 이내",
  "issues": ["법적 쟁점 1", "법적 쟁점 2"],
  "risk_level": "high | medium | low | info",
  "rationale": "그 위험도로 본 이유",
  "negotiation_points": ["협상에서 요구할 사항 1", "요구할 사항 2"],
  "suggested_text": "권장 수정 문안(불필요하면 빈 문자열)"
}"""


def build_messages(ctx: ClauseContext) -> tuple[str, str]:
    """(system, user) 프롬프트를 만든다."""
    party_block = (
        "\n".join(f"- {p.display()}" for p in ctx.parties) or "- (당사자 정보를 인식하지 못함)"
    )
    impact_block = (
        "\n".join(
            f"- {i.alias}: 권리 {i.before_rights}→{i.after_rights}, "
            f"의무 {i.before_obligations}→{i.after_obligations} "
            f"(추정 방향: {i.verdict_label})"
            for i in ctx.impacts
        )
        or "- (당사자별 영향 추정 없음)"
    )
    flag_block = (
        "\n".join(
            f"- [{f.level.label}] ({f.category}) {f.message}"
            + (f"\n  근거: {f.evidence}" if f.evidence else "")
            for f in ctx.flags
        )
        or "- (자동 탐지된 항목 없음)"
    )

    user = f"""## 계약 당사자
{party_block}

## 검토 대상
조문: {ctx.heading}
변경 상태: {ctx.status.label}
검토 관점: {ctx.view_label}

## 변경 전 문언
{ctx.before_text or "(해당 조문 없음 — 신설)"}

## 변경 후 문언
{ctx.after_text or "(해당 조문 없음 — 삭제)"}

## 문언 변경점 (자동 추출)
{ctx.diff_summary or "- (변경점 요약 없음)"}

## 당사자별 영향 추정 (휴리스틱)
{impact_block}

## 자동 탐지된 위험 신호
{flag_block}

## 지시
위 조문 변경을 '{ctx.view_label}' 관점에서 검토하고, 지정된 JSON 형식으로만 답하십시오.
자동 탐지 신호와 영향 추정은 참고 자료일 뿐이며, 문언상 근거가 없다면 채택하지 마십시오.
반대로 탐지되지 않았더라도 중요한 쟁점이 있으면 반드시 포함하십시오."""

    return SYSTEM_PROMPT, user
