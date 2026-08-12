"""마크다운 리포트 — 메일·이슈트래커에 붙여 넣기 좋은 형태."""

from __future__ import annotations

from .. import DISCLAIMER
from ..models import ClauseComparison, LegalComment, ReviewResult

_VERDICT_MARK = {"adverse": "▼ 불리", "favorable": "▲ 유리", "neutral": "– 중립"}


def render_markdown(result: ReviewResult) -> str:
    counts = result.counts()
    changed = sorted(result.changed(), key=lambda c: (-len(c.flags), c.sort_key))

    versions = ""
    if result.before_doc.version or result.after_doc.version:
        versions = f" ({result.before_doc.version or '?'} → {result.after_doc.version or '?'})"

    lines: list[str] = [
        "# 계약서 비교 검토 리포트",
        "",
        f"- 원본: `{result.before_doc.path}`",
        f"- 개정본: `{result.after_doc.path}`{versions}",
        f"- 당사자: {', '.join(p.display() for p in result.parties) or '인식 실패'}",
        f"- 생성 시각: {result.generated_at}",
        "",
        f"> {DISCLAIMER}",
        "",
        "## 요약",
        "",
        "| 구분 | 수정 | 신설 | 삭제 | 동일 |",
        "|---|---|---|---|---|",
        f"| 건수 | {counts['modified']} | {counts['added']} | {counts['deleted']} "
        f"| {counts['unchanged']} |",
        "",
    ]

    if result.parties:
        lines += _party_summary(result)
    if result.timeline:
        lines += _timeline(result)

    if not changed:
        lines += ["## 결과", "", "두 문서 사이에 조문 변경이 없습니다.", ""]
        return "\n".join(lines)

    lines += [
        "## 변경 조문 목록",
        "",
        "| 조문 | 구분 | 유사도 | 쟁점 | 불리 당사자 |",
        "|---|---|---|---|---|",
    ]
    for comp in changed:
        adverse = ", ".join(i.alias for i in comp.impacts if i.verdict == "adverse" and i.mentioned)
        lines.append(
            f"| {comp.heading} | {comp.status.label} "
            f"| {comp.similarity:.2f} | {', '.join(comp.categories) or '-'} | {adverse or '-'} |"
        )
    lines += ["", "## 조문별 상세", ""]
    for comp in changed:
        lines += _render_clause(comp)

    return "\n".join(lines)


def _party_summary(result: ReviewResult) -> list[str]:
    lines = [
        "## 당사자별 영향 (휴리스틱 추정)",
        "",
        "| 당사자 | 불리 | 중립 | 유리 | 중점 검토 |",
        "|---|---|---|---|---|",
    ]
    for row in result.party_summary():
        label = row["alias"] + (f" · {row['role']}" if row["role"] else "")
        lines.append(
            f"| {label} | {row['adverse']} | {row['neutral']} | {row['favorable']} "
            f"| {row['high']} |"
        )
    lines += ["", "> 문장 단위 권리·의무 표현을 센 추정치입니다. 검토 우선순위 신호로만 쓰십시오.", ""]
    return lines


def _timeline(result: ReviewResult) -> list[str]:
    lines = [
        f"## 버전 변경 이력 — {result.contract_id}",
        "",
        "| 구간 | 수정 | 신설 | 삭제 | 쟁점 | 주요 변경 조문 |",
        "|---|---|---|---|---|---|",
    ]
    for step in result.timeline:
        lines.append(
            f"| {step.from_version} → {step.to_version} | {step.modified} | {step.added} "
            f"| {step.deleted} | {step.flagged} | {', '.join(step.headings) or '-'} |"
        )
    lines.append("")
    return lines


def _render_clause(comp: ClauseComparison) -> list[str]:
    lines = [
        f"### {comp.heading} — {comp.status.label}",
        "",
    ]

    impacts = [i for i in comp.impacts if i.mentioned]
    if impacts:
        marks = " · ".join(
            f"{i.alias} {_VERDICT_MARK[i.verdict]}({i.delta:+d})" for i in impacts
        )
        lines += [f"당사자 영향: {marks}", ""]

    if comp.before:
        lines += ["**변경 전**", "", "```", comp.before.full_text, "```", ""]
    if comp.after:
        lines += ["**변경 후**", "", "```", comp.after.full_text, "```", ""]

    if comp.segments:
        removed = [s.text.strip() for s in comp.segments if s.op == "delete" and s.text.strip()]
        added = [s.text.strip() for s in comp.segments if s.op == "insert" and s.text.strip()]
        lines += ["**문언 변경점**", ""]
        lines += [f"- ~~{_inline(t)}~~" for t in removed[:10]]
        lines += [f"- **{_inline(t)}**" for t in added[:10]]
        lines.append("")

    if comp.flags:
        lines += ["**자동 탐지 위험 신호**", ""]
        for flag in comp.flags:
            lines.append(f"- `{flag.category}` {flag.message}")
            if flag.evidence:
                lines.append(f"  - 근거: {flag.evidence}")
        lines.append("")

    for comment in comp.comments:
        lines += _render_comment(comment)

    lines += ["---", ""]
    return lines


def _render_comment(comment: LegalComment) -> list[str]:
    lines = [
        f"**법무 코멘트 · {comment.party_view or '중립'}**",
        "",
    ]
    if comment.summary:
        lines += [comment.summary, ""]
    if comment.issues:
        lines += ["법적 쟁점:", ""] + [f"- {i}" for i in comment.issues] + [""]
    if comment.rationale:
        lines += [f"판단 근거: {comment.rationale}", ""]
    if comment.negotiation_points:
        lines += ["협상 포인트:", ""] + [f"- {p}" for p in comment.negotiation_points] + [""]
    if comment.suggested_text:
        lines += ["권장 수정 문안:", "", "```", comment.suggested_text, "```", ""]
    return lines


def _inline(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > 300:
        text = text[:300] + " …"
    return text.replace("|", "\\|")
