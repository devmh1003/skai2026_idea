"""검토 결과를 Word(.docx)로 내보낸다.

python-docx 없이 OOXML을 직접 만든다. 리포트에 필요한 요소가 문단·표·굵게·색상
정도라 의존성을 하나 더 얹을 이유가 없고, 폐쇄망 반입도 그만큼 쉬워진다.

변경 전/후 문안은 삭제(빨강 취소선)·추가(초록 밑줄)를 문장 단위로 표시해,
워드에서 그대로 상대방에게 보내거나 인쇄해 회의에 들고 갈 수 있게 한다.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

from .. import DISCLAIMER
from ..diffing import sentence_changes
from ..models import ClauseComparison, ReviewResult

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="맑은 고딕" w:eastAsia="맑은 고딕" w:hAnsi="맑은 고딕"/>
<w:sz w:val="20"/></w:rPr></w:rPrDefault></w:docDefaults>
</w:styles>"""

_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)


def _run(text: str, *, bold=False, color="", size=20, strike=False, underline=False) -> str:
    props = [f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>']
    if bold:
        props.append("<w:b/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    if strike:
        props.append("<w:strike/>")
    if underline:
        props.append('<w:u w:val="single"/>')
    body = escape(text).replace("\n", "</w:t><w:br/><w:t xml:space=\"preserve\">")
    return (
        f'<w:r><w:rPr>{"".join(props)}</w:rPr>'
        f'<w:t xml:space="preserve">{body}</w:t></w:r>'
    )


def _para(runs: str, *, spacing=120, indent=0, shade="") -> str:
    props = [f'<w:spacing w:after="{spacing}"/>']
    if indent:
        props.append(f'<w:ind w:left="{indent}"/>')
    if shade:
        props.append(f'<w:shd w:val="clear" w:fill="{shade}"/>')
    return f'<w:p><w:pPr>{"".join(props)}</w:pPr>{runs}</w:p>'


def _heading(text: str, level: int = 1) -> str:
    sizes = {0: 36, 1: 26, 2: 22}
    return _para(
        _run(text, bold=True, size=sizes.get(level, 22), color="101828"),
        spacing=200 if level < 2 else 120,
    )


def _table(rows: list[list[str]], widths: list[int], header: bool = True) -> str:
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    body = []
    for index, row in enumerate(rows):
        cells = []
        for width, cell in zip(widths, row, strict=False):
            shade = 'w:fill="F2F4F7"' if header and index == 0 else 'w:fill="FFFFFF"'
            cells.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>'
                f"<w:shd w:val='clear' {shade}/></w:tcPr>"
                f"{_para(_run(cell, bold=header and index == 0), spacing=0)}</w:tc>"
            )
        body.append(f'<w:tr>{"".join(cells)}</w:tr>')

    return (
        "<w:tbl><w:tblPr><w:tblBorders>"
        + "".join(
            f'<w:{edge} w:val="single" w:sz="4" w:color="D0D5DD"/>'
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        + "</w:tblBorders></w:tblPr>"
        + f'<w:tblGrid>{grid}</w:tblGrid>{"".join(body)}</w:tbl>'
        + _para("", spacing=120)
    )


def _clause_block(comp: ClauseComparison) -> str:
    before = comp.before.full_text if comp.before else ""
    after = comp.after.full_text if comp.after else ""
    removed, added = sentence_changes(before, after)

    out = [_heading(f"{comp.heading} — {comp.status.label}", level=2)]

    if comp.categories:
        out.append(_para(_run("쟁점: " + ", ".join(comp.categories), color="1849A9")))

    impacts = [i for i in comp.impacts if i.mentioned and i.verdict != "neutral"]
    if impacts:
        marks = " · ".join(f"{i.alias} {i.verdict_label}" for i in impacts)
        out.append(_para(_run(f"당사자 영향: {marks}", color="667085")))

    if removed or added:
        out.append(_para(_run("변경 요지", bold=True, color="667085")))
        for text in removed:
            out.append(
                _para(_run("− " + text, color="B42318", strike=True), spacing=40, indent=220)
            )
        for text in added:
            out.append(
                _para(_run("+ " + text, color="087443", underline=True), spacing=40, indent=220)
            )

    if before:
        out.append(_para(_run("변경 전", bold=True, color="667085"), spacing=40))
        out.append(_para(_run(before, color="475467"), indent=220))
    if after:
        out.append(_para(_run("변경 후", bold=True, color="667085"), spacing=40))
        out.append(_para(_run(after), indent=220))

    if comp.flags:
        out.append(_para(_run("자동 탐지", bold=True, color="667085"), spacing=40))
        for flag in comp.flags:
            out.append(
                _para(_run(f"· [{flag.category}] {flag.message}"), spacing=40, indent=220)
            )

    for comment in comp.comments:
        out.append(
            _para(
                _run(f"법무 코멘트 · {comment.party_view or '중립'}", bold=True, color="1849A9"),
                spacing=40,
            )
        )
        if comment.summary:
            out.append(_para(_run(comment.summary), spacing=40, indent=220))
        for point in comment.negotiation_points:
            out.append(_para(_run(f"· {point}"), spacing=40, indent=220))
        if comment.suggested_text:
            out.append(
                _para(_run(f"권장 문안: {comment.suggested_text}", color="087443"), indent=220)
            )

    return "".join(out)


def render_docx(result: ReviewResult, contract_id: str = "") -> bytes:
    counts = result.counts()
    changed = sorted(result.changed(), key=lambda c: (-len(c.flags), c.sort_key))
    versions = ""
    if result.before_doc.version or result.after_doc.version:
        versions = f"{result.before_doc.version} → {result.after_doc.version}"

    body = [
        _heading("계약 검토 의견서", level=0),
        _para(
            _run(
                f"{contract_id or result.contract_id}   "
                f"{result.before_doc.name} → {result.after_doc.name}"
                + (f"   ({versions})" if versions else ""),
                color="667085",
            )
        ),
        _para(_run(f"작성일 {result.generated_at}", color="667085")),
        _para(_run(DISCLAIMER, color="B54708", size=18)),
        _heading("요약", level=1),
        _table(
            [
                ["구분", "수정", "신설", "삭제", "검토 필요"],
                [
                    "건수",
                    str(counts["modified"]),
                    str(counts["added"]),
                    str(counts["deleted"]),
                    str(sum(1 for c in changed if c.flags)),
                ],
            ],
            [2000, 1400, 1400, 1400, 1800],
        ),
    ]

    if result.parties:
        body.append(_heading("당사자", level=1))
        body.append(
            _table(
                [["약칭", "상호", "역할"]]
                + [[p.alias, p.name or "-", p.role or "-"] for p in result.parties],
                [1400, 4200, 2400],
            )
        )

    if changed:
        body.append(_heading("변경 조문", level=1))
        body.append(
            _table(
                [["조문", "구분", "쟁점", "불리 당사자"]]
                + [
                    [
                        comp.heading,
                        comp.status.label,
                        ", ".join(comp.categories) or "-",
                        ", ".join(
                            i.alias
                            for i in comp.impacts
                            if i.verdict == "adverse" and i.mentioned
                        )
                        or "-",
                    ]
                    for comp in changed
                ],
                [3000, 1200, 2800, 1800],
            )
        )
        body.append(_heading("조문별 상세", level=1))
        body.extend(_clause_block(comp) for comp in changed)
    else:
        body.append(_para(_run("두 문서 사이에 조문 변경이 없습니다.")))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {_NS}><w:body>{''.join(body)}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _RELS)
        archive.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        archive.writestr("word/styles.xml", _STYLES)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def render_contract_docx(title: str, text: str) -> bytes:
    """계약서 원문(표준 양식)을 Word 문서로 만든다."""
    body = [_heading(title, level=0)]
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        head, _, rest = block.partition("\n")
        is_article = head.startswith("제") and "조" in head[:8]
        body.append(_para(_run(head, bold=is_article, size=22 if is_article else 20)))
        if rest.strip():
            body.append(_para(_run(rest.strip()), indent=220))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {_NS}><w:body>{''.join(body)}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _RELS)
        archive.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        archive.writestr("word/styles.xml", _STYLES)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()
