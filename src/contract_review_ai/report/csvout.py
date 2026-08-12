"""표 형식 내보내기.

법무팀이 실제로 하는 일은 검토 결과를 엑셀에 붙여 협상 대응표를 만드는 것이다.
조문 한 건 = 한 행으로 떨어지게 해서 그 작업을 그대로 이어받게 한다.
BOM을 붙여 Excel에서 한글이 깨지지 않는다.
"""

from __future__ import annotations

import csv
import io

from ..models import ReviewResult

CLAUSE_HEADER = [
    "계약",
    "구간",
    "조문",
    "구분",
    "위험도",
    "유사도",
    "쟁점",
    "불리 당사자",
    "유리 당사자",
    "탐지 신호",
    "변경 전",
    "변경 후",
    "코멘트 관점",
    "코멘트 요약",
    "협상 포인트",
    "권장 수정 문안",
]


def render_csv(result: ReviewResult, contract_id: str = "") -> str:
    """변경 조문을 행 단위로 펼친다. 코멘트가 여러 관점이면 관점마다 한 행."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CLAUSE_HEADER)

    span = f"{result.before_doc.name} → {result.after_doc.name}"
    for comp in sorted(result.changed(), key=lambda c: (-c.effective_level.rank, c.sort_key)):
        base = [
            contract_id or result.contract_id,
            span,
            comp.heading,
            comp.status.label,
            comp.effective_level.label,
            f"{comp.similarity:.2f}",
            ", ".join(comp.categories),
            ", ".join(i.alias for i in comp.impacts if i.verdict == "adverse" and i.mentioned),
            ", ".join(i.alias for i in comp.impacts if i.verdict == "favorable" and i.mentioned),
            " / ".join(f"[{f.level.label}] {f.message}" for f in comp.flags),
            comp.before.full_text if comp.before else "",
            comp.after.full_text if comp.after else "",
        ]
        if not comp.comments:
            writer.writerow(base + ["", "", "", ""])
            continue
        for comment in comp.comments:
            writer.writerow(
                base
                + [
                    comment.party_view,
                    comment.summary,
                    " / ".join(comment.negotiation_points),
                    comment.suggested_text,
                ]
            )

    return "﻿" + buffer.getvalue()


def render_contract_index_csv(rows: list[dict]) -> str:
    """워크스페이스 전체 계약 목록."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["계약 ID", "계약명", "분류", "버전 수", "최신 버전", "고위험", "최종 등록"])
    for row in rows:
        writer.writerow(
            [
                row["contract_id"],
                row["title"],
                row["category"],
                row["versions"],
                row["latest"],
                row["high"],
                row["updated_at"],
            ]
        )
    return "﻿" + buffer.getvalue()


def render_version_index_csv(rows: list[dict]) -> str:
    """워크스페이스 전체 버전 대장. 감사 대응용."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["계약 ID", "계약명", "버전", "라벨", "등록 일시", "SHA-256", "메모", "파일"])
    for row in rows:
        writer.writerow(
            [
                row["contract_id"],
                row["title"],
                row["version"],
                row["label"],
                row["imported_at"],
                row["sha256"],
                row["note"],
                row["file"],
            ]
        )
    return "﻿" + buffer.getvalue()
