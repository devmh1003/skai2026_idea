"""실무용 단일 HTML 대시보드.

CDN·외부 파일 의존이 전혀 없다(폐쇄망 반입 가능). 차트는 파이썬이 SVG로 직접
그리고, 상호작용(탭·필터·검색)만 바닐라 JS로 처리한다.

탭 구성
  개요       — 지표 카드, 위험도 도넛, 쟁점 카테고리 막대, 당사자 영향 요약
  조문 비교  — 좌우 대조 diff + 위험도/구분/당사자/카테고리 필터 + 전문 검색
  당사자 영향 — 조문 × 당사자 매트릭스 (다자간 계약에서 누가 무엇을 떠안는지)
  변경 이력  — 버전 체인 타임라인
"""

from __future__ import annotations

import html
import json
import math

from .. import DISCLAIMER
from ..models import ClauseComparison, ReviewResult

_RISK_COLOR = {
    "high": "#d92d20",
    "medium": "#e07b00",
    "low": "#c9a900",
    "info": "#8a919c",
}
_VERDICT_COLOR = {"adverse": "#d92d20", "favorable": "#1a7f4b", "neutral": "#8a919c"}

_CSS = """
:root{--bg:#f5f6f8;--card:#fff;--line:#e3e6eb;--text:#171a1f;--muted:#697079;
--accent:#2b5cd9;--del:#fde3e1;--ins:#dbf3e3;--chip:#eef1f6;}
@media (prefers-color-scheme:dark){:root{--bg:#101317;--card:#191d23;--line:#2a2f38;
--text:#e7eaee;--muted:#98a0ab;--accent:#7aa2ff;--del:#4a2320;--ins:#1c3a29;--chip:#232830;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font-family:"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;line-height:1.6;}
.wrap{max-width:1180px;margin:0 auto;padding:22px 20px 60px}
header h1{font-size:22px;margin:0 0 6px}
.meta{color:var(--muted);font-size:13px}
.meta b{color:var(--text);font-weight:600}
.disclaimer{background:#fff5e0;color:#7a4b00;border:1px solid #efd8a4;border-radius:8px;
padding:9px 13px;font-size:12.5px;margin:14px 0 18px}
@media (prefers-color-scheme:dark){.disclaimer{background:#332710;color:#f0d9a8;border-color:#544120}}
nav{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:20px;flex-wrap:wrap}
nav button{font:inherit;font-size:14px;padding:9px 16px;border:0;background:none;cursor:pointer;
color:var(--muted);border-bottom:2px solid transparent}
nav button[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
section[hidden]{display:none}
.grid{display:grid;gap:12px}
.kpis{grid-template-columns:repeat(auto-fit,minmax(120px,1fr));margin-bottom:16px}
.panels{grid-template-columns:1fr 1fr}
@media(max-width:820px){.panels{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .n{font-size:28px;font-weight:700;line-height:1.2}
.kpi .l{font-size:12px;color:var(--muted)}
h2{font-size:15px;margin:0 0 10px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}
.toolbar input{font:inherit;font-size:13px;padding:7px 12px;border-radius:8px;
border:1px solid var(--line);background:var(--card);color:var(--text);min-width:200px;flex:1 1 220px}
.chip{font:inherit;font-size:12.5px;padding:5px 12px;border-radius:999px;cursor:pointer;
border:1px solid var(--line);background:var(--card);color:var(--text)}
.chip[aria-pressed="true"]{background:var(--text);color:var(--bg);border-color:var(--text)}
.group{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.group .lb{font-size:12px;color:var(--muted);margin-right:2px}
.clause{background:var(--card);border:1px solid var(--line);border-left-width:4px;
border-radius:12px;padding:15px 17px;margin-bottom:12px}
.clause[data-risk="high"]{border-left-color:#d92d20}
.clause[data-risk="medium"]{border-left-color:#e07b00}
.clause[data-risk="low"]{border-left-color:#c9a900}
.clause[data-risk="info"]{border-left-color:#8a919c}
.chead{display:flex;flex-wrap:wrap;align-items:center;gap:7px}
.chead h3{margin:0;font-size:15.5px;flex:1 1 auto}
.tag{font-size:11.5px;padding:2px 9px;border-radius:999px;background:var(--chip);
color:var(--muted);white-space:nowrap}
.tag.high{background:#d92d20;color:#fff}
.tag.medium{background:#e07b00;color:#fff}
.tag.low{background:#f2e5a0;color:#5a4d00}
.tag.adverse{background:#fbe3e1;color:#a01a12}
.tag.favorable{background:#dcf0e5;color:#136139}
@media (prefers-color-scheme:dark){.tag.adverse{background:#4a201d;color:#ffb4ad}
.tag.favorable{background:#173629;color:#8fe0b4}.tag.low{background:#4a4210;color:#f2e5a0}}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:11px}
@media(max-width:760px){.cols{grid-template-columns:1fr}}
pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);
border-radius:8px;padding:10px 12px;margin:5px 0 0;font-size:12.8px;
font-family:"D2Coding",Consolas,monospace}
.lbl{font-size:11.5px;color:var(--muted);font-weight:700;letter-spacing:.02em}
del{background:var(--del);text-decoration:line-through}
ins{background:var(--ins);text-decoration:none}
details{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px}
summary{cursor:pointer;font-size:13px;color:var(--accent);font-weight:600}
ul{margin:6px 0;padding-left:19px}li{margin:3px 0;font-size:13.5px}
.ev{color:var(--muted);font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left}
th{font-size:12px;color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--card)}
td.c{text-align:center}
.dot{display:inline-block;min-width:44px;padding:2px 8px;border-radius:999px;font-size:11.5px}
.step{display:flex;gap:14px;align-items:flex-start;padding:12px 0;border-bottom:1px solid var(--line)}
.step:last-child{border-bottom:0}
.step .v{font-weight:700;font-size:13px;white-space:nowrap;color:var(--accent);min-width:92px}
.empty{color:var(--muted);padding:26px;text-align:center}
.legend{font-size:12px;color:var(--muted);display:flex;gap:12px;flex-wrap:wrap;margin-top:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
"""

_JS = """
(function(){
  var tabs = document.querySelectorAll('nav button');
  tabs.forEach(function(tab){
    tab.addEventListener('click', function(){
      tabs.forEach(function(t){
        var on = (t === tab);
        t.setAttribute('aria-selected', String(on));
        document.getElementById(t.dataset.tab).hidden = !on;
      });
    });
  });

  var state = {risk:'all', status:'all', party:'all', cat:'all', q:''};
  function refresh(){
    var shown = 0;
    document.querySelectorAll('#clause-list .clause').forEach(function(el){
      var ok = (state.risk === 'all' || el.dataset.risk === state.risk)
        && (state.status === 'all' || el.dataset.status === state.status)
        && (state.party === 'all' || (el.dataset.adverse||'').split('|').indexOf(state.party) >= 0)
        && (state.cat === 'all' || (el.dataset.cats||'').split('|').indexOf(state.cat) >= 0)
        && (state.q === '' || (el.dataset.search||'').indexOf(state.q) >= 0);
      el.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    document.getElementById('shown-count').textContent = shown;
  }
  document.querySelectorAll('.chip[data-kind]').forEach(function(chip){
    chip.addEventListener('click', function(){
      var kind = chip.dataset.kind;
      document.querySelectorAll('.chip[data-kind="'+kind+'"]').forEach(function(c){
        c.setAttribute('aria-pressed', String(c === chip));
      });
      state[kind] = chip.dataset.value;
      refresh();
    });
  });
  var search = document.getElementById('search');
  if (search) {
    search.addEventListener('input', function(){
      state.q = search.value.trim().toLowerCase();
      refresh();
    });
  }
  refresh();
})();
"""


def render_html(result: ReviewResult) -> str:
    changed = sorted(result.changed(), key=lambda c: (-c.effective_level.rank, c.sort_key))
    counts = result.counts()
    risks = result.risk_counts()

    version_note = ""
    if result.before_doc.version or result.after_doc.version:
        version_note = (
            f' <b>{_e(result.before_doc.version or "?")} → '
            f'{_e(result.after_doc.version or "?")}</b>'
        )

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>계약서 검토 대시보드 — {_e(result.after_doc.name)}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<header>
  <h1>계약서 비교 검토 대시보드</h1>
  <div class="meta">
    <b>{_e(result.before_doc.name)}</b> → <b>{_e(result.after_doc.name)}</b>{version_note}
    &nbsp;·&nbsp; {_e(result.generated_at)}
    &nbsp;·&nbsp; 코멘트 {_e(result.backend)}
    &nbsp;·&nbsp; 당사자 {len(result.parties)}인
  </div>
</header>
<div class="disclaimer">{_e(DISCLAIMER)}</div>

<nav>
  <button data-tab="tab-overview" aria-selected="true">개요</button>
  <button data-tab="tab-clauses" aria-selected="false">조문 비교</button>
  <button data-tab="tab-parties" aria-selected="false">당사자 영향</button>
  <button data-tab="tab-history" aria-selected="false">변경 이력</button>
</nav>

<section id="tab-overview">
{_overview(result, counts, risks)}
</section>

<section id="tab-clauses" hidden>
{_toolbar(result)}
<div id="clause-list">
{"".join(_clause_html(c) for c in changed) or '<div class="empty">변경된 조문이 없습니다.</div>'}
</div>
</section>

<section id="tab-parties" hidden>
{_party_tab(result, changed)}
</section>

<section id="tab-history" hidden>
{_history_tab(result)}
</section>

<script id="review-data" type="application/json">{_json(result)}</script>
<script>{_JS}</script>
</div></body></html>"""


# ---------------------------------------------------------------- 개요 탭


def _overview(result: ReviewResult, counts: dict[str, int], risks: dict[str, int]) -> str:
    kpis = [
        ("변경 조문", counts["modified"] + counts["added"] + counts["deleted"], None),
        ("수정", counts["modified"], None),
        ("신설", counts["added"], None),
        ("삭제", counts["deleted"], None),
        ("위험 높음", risks["high"], _RISK_COLOR["high"]),
        ("위험 중간", risks["medium"], _RISK_COLOR["medium"]),
    ]
    kpi_html = "".join(
        '<div class="card kpi"><div class="n"'
        + (f" style='color:{color}'" if color else "")
        + f">{value}</div>"
        + f'<div class="l">{_e(label)}</div></div>'
        for label, value, color in kpis
    )

    categories = result.category_counts()
    return f"""
<div class="grid kpis">{kpi_html}</div>
<div class="grid panels">
  <div class="card">
    <h2>위험도 분포</h2>
    {_donut(risks)}
  </div>
  <div class="card">
    <h2>쟁점 카테고리 (변경 조문 기준)</h2>
    {_bars(categories)}
  </div>
</div>
<div class="card" style="margin-top:12px">
  <h2>당사자별 영향 요약</h2>
  {_party_bars(result)}
  <div class="legend">
    <span><i style="background:{_VERDICT_COLOR['adverse']}"></i>불리</span>
    <span><i style="background:{_VERDICT_COLOR['neutral']}"></i>중립</span>
    <span><i style="background:{_VERDICT_COLOR['favorable']}"></i>유리</span>
    <span>· 문장 단위 권리/의무 표현 계수에 기반한 추정치입니다.</span>
  </div>
</div>"""


def _donut(risks: dict[str, int]) -> str:
    total = sum(risks.values())
    if total == 0:
        return '<div class="empty">변경 없음</div>'

    radius, stroke, cx, cy = 62, 26, 90, 90
    circumference = 2 * math.pi * radius
    offset = 0.0
    arcs = []
    for key in ("high", "medium", "low", "info"):
        value = risks[key]
        if not value:
            continue
        length = circumference * value / total
        arcs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" '
            f'stroke="{_RISK_COLOR[key]}" stroke-width="{stroke}" '
            f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"><title>'
            f"{key} {value}건</title></circle>"
        )
        offset += length

    labels = "".join(
        f'<span><i style="background:{_RISK_COLOR[k]}"></i>{lab} {risks[k]}</span>'
        for k, lab in (("high", "높음"), ("medium", "중간"), ("low", "낮음"), ("info", "참고"))
        if risks[k]
    )
    return f"""<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
<svg width="180" height="180" viewBox="0 0 180 180" role="img" aria-label="위험도 분포">
{"".join(arcs)}
<text x="90" y="86" text-anchor="middle" font-size="26" font-weight="700"
 fill="currentColor">{total}</text>
<text x="90" y="106" text-anchor="middle" font-size="11" fill="#8a919c">변경 조문</text>
</svg>
<div class="legend" style="flex-direction:column;gap:6px">{labels}</div></div>"""


def _bars(categories: dict[str, int]) -> str:
    if not categories:
        return '<div class="empty">탐지된 쟁점 없음</div>'

    items = list(categories.items())[:10]
    top = max(v for _, v in items)
    rows = []
    for i, (name, value) in enumerate(items):
        width = max(4, int(220 * value / top))
        y = 8 + i * 26
        rows.append(
            f'<text x="0" y="{y + 12}" font-size="12" fill="currentColor">{_e(name)}</text>'
            f'<rect x="96" y="{y}" width="{width}" height="16" rx="4" fill="#2b5cd9" opacity="0.8"/>'
            f'<text x="{96 + width + 6}" y="{y + 12}" font-size="11" fill="#8a919c">{value}</text>'
        )
    height = 16 + len(items) * 26
    return (
        f'<svg width="100%" height="{height}" viewBox="0 0 360 {height}" '
        f'preserveAspectRatio="xMinYMin meet" role="img" aria-label="쟁점 카테고리">'
        f'{"".join(rows)}</svg>'
    )


def _party_bars(result: ReviewResult) -> str:
    summary = [row for row in result.party_summary()]
    if not summary:
        return '<div class="empty">당사자를 인식하지 못했습니다.</div>'

    rows = []
    for row in summary:
        total = row["adverse"] + row["neutral"] + row["favorable"]
        label = row["alias"] + (f' · {row["role"]}' if row["role"] else "")
        if total == 0:
            rows.append(
                f'<tr><td>{_e(label)}</td><td colspan="2" class="ev">언급된 변경 조문 없음</td></tr>'
            )
            continue
        segments, x = [], 0.0
        for key in ("adverse", "neutral", "favorable"):
            width = 240 * row[key] / total
            if width > 0:
                segments.append(
                    f'<rect x="{x:.1f}" y="0" width="{width:.1f}" height="16" '
                    f'fill="{_VERDICT_COLOR[key]}"><title>{key} {row[key]}건</title></rect>'
                )
                x += width
        rows.append(
            f"<tr><td>{_e(label)}</td>"
            f'<td><svg width="240" height="16" viewBox="0 0 240 16">{"".join(segments)}</svg></td>'
            f'<td class="ev">불리 {row["adverse"]} · 중립 {row["neutral"]} · '
            f'유리 {row["favorable"]}'
            + (f' · <b style="color:{_RISK_COLOR["high"]}">고위험 불리 {row["high"]}</b>'
               if row["high"] else "")
            + "</td></tr>"
        )
    return f"<table>{''.join(rows)}</table>"


# ---------------------------------------------------------------- 조문 비교 탭


def _toolbar(result: ReviewResult) -> str:
    def chips(kind: str, options: list[tuple[str, str]]) -> str:
        out = [f'<span class="lb">{_LABEL[kind]}</span>']
        out.append(
            f'<button class="chip" data-kind="{kind}" data-value="all" '
            f'aria-pressed="true">전체</button>'
        )
        out += [
            f'<button class="chip" data-kind="{kind}" data-value="{_e(value)}" '
            f'aria-pressed="false">{_e(label)}</button>'
            for value, label in options
        ]
        return f'<div class="group">{"".join(out)}</div>'

    party_options = [(p.id, f"{p.alias} 불리") for p in result.parties]
    category_options = [(c, c) for c in result.category_counts()][:12]

    return f"""<div class="toolbar">
  <input id="search" type="search" placeholder="조문 본문·코멘트 검색">
  <span class="ev"><b id="shown-count">0</b>건 표시</span>
</div>
<div class="toolbar">
{chips("risk", [("high", "높음"), ("medium", "중간"), ("low", "낮음"), ("info", "참고")])}
{chips("status", [("modified", "수정"), ("added", "신설"), ("deleted", "삭제")])}
</div>
<div class="toolbar">
{chips("party", party_options)}
</div>
<div class="toolbar">
{chips("cat", category_options)}
</div>"""


_LABEL = {"risk": "위험도", "status": "구분", "party": "당사자", "cat": "쟁점"}


def _clause_html(comp: ClauseComparison) -> str:
    level = comp.effective_level
    adverse = [i for i in comp.impacts if i.verdict == "adverse" and i.mentioned]
    favorable = [i for i in comp.impacts if i.verdict == "favorable" and i.mentioned]

    search_blob = " ".join(
        filter(
            None,
            [
                comp.heading,
                comp.before.full_text if comp.before else "",
                comp.after.full_text if comp.after else "",
                " ".join(f.message for f in comp.flags),
                " ".join(c.summary for c in comp.comments),
            ],
        )
    ).lower()

    parts = [
        f'<div class="clause" data-risk="{level.value}" data-status="{comp.status.value}"'
        f' data-adverse="{_e("|".join(i.party_id for i in adverse))}"'
        f' data-cats="{_e("|".join(comp.categories))}"'
        f' data-search="{_e(search_blob)}">',
        '<div class="chead">',
        f"<h3>{_e(comp.heading)}</h3>",
        f'<span class="tag {level.value}">위험도 {_e(level.label)}</span>',
        f'<span class="tag">{_e(comp.status.label)}</span>',
        f'<span class="tag">유사도 {comp.similarity:.2f}</span>',
    ]
    parts += [f'<span class="tag adverse">{_e(i.alias)} 불리</span>' for i in adverse]
    parts += [f'<span class="tag favorable">{_e(i.alias)} 유리</span>' for i in favorable]
    parts.append("</div>")

    parts += [
        '<div class="cols">',
        f'<div><span class="lbl">변경 전</span><pre>{_diff_html(comp, "before")}</pre></div>',
        f'<div><span class="lbl">변경 후</span><pre>{_diff_html(comp, "after")}</pre></div>',
        "</div>",
    ]

    if comp.flags:
        items = "".join(
            f'<li><span class="tag {f.level.value}">{_e(f.level.label)}</span> '
            f"<b>{_e(f.category)}</b> {_e(f.message)}"
            + (f'<div class="ev">근거: {_e(f.evidence)}</div>' if f.evidence else "")
            + "</li>"
            for f in comp.flags
        )
        parts.append(
            f'<details open><summary>자동 탐지 위험 신호 {len(comp.flags)}건</summary>'
            f"<ul>{items}</ul></details>"
        )

    for comment in comp.comments:
        parts.append(_comment_html(comment))

    parts.append("</div>")
    return "\n".join(parts)


def _comment_html(comment) -> str:
    body = [
        f'<details open><summary>법무 코멘트 · {_e(comment.party_view or "중립")} '
        f'<span class="ev">({_e(comment.source)})</span></summary>'
    ]
    if comment.summary:
        body.append(f"<p>{_e(comment.summary)}</p>")
    if comment.issues:
        body.append(
            "<b>법적 쟁점</b><ul>" + "".join(f"<li>{_e(i)}</li>" for i in comment.issues) + "</ul>"
        )
    if comment.rationale:
        body.append(f'<p class="ev">판단 근거: {_e(comment.rationale)}</p>')
    if comment.negotiation_points:
        body.append(
            "<b>협상 포인트</b><ul>"
            + "".join(f"<li>{_e(p)}</li>" for p in comment.negotiation_points)
            + "</ul>"
        )
    if comment.suggested_text:
        body.append(f"<b>권장 수정 문안</b><pre>{_e(comment.suggested_text)}</pre>")
    body.append("</details>")
    return "".join(body)


def _diff_html(comp: ClauseComparison, side: str) -> str:
    clause = comp.before if side == "before" else comp.after
    if clause is None:
        return '<span class="ev">(해당 조문 없음)</span>'
    if not comp.segments:
        return _e(clause.full_text)

    out = []
    for seg in comp.segments:
        if seg.op == "equal":
            out.append(_e(seg.text))
        elif seg.op == "delete" and side == "before":
            out.append(f"<del>{_e(seg.text)}</del>")
        elif seg.op == "insert" and side == "after":
            out.append(f"<ins>{_e(seg.text)}</ins>")
    return "".join(out)


# ---------------------------------------------------------------- 당사자 영향 탭


def _party_tab(result: ReviewResult, changed: list[ClauseComparison]) -> str:
    if not result.parties:
        return '<div class="empty">당사자를 인식하지 못했습니다.</div>'
    if not changed:
        return '<div class="empty">변경된 조문이 없습니다.</div>'

    head = "".join(f'<th class="c">{_e(p.display())}</th>' for p in result.parties)
    rows = []
    for comp in changed:
        by_party = {i.party_id: i for i in comp.impacts}
        cells = []
        for party in result.parties:
            impact = by_party.get(party.id)
            if impact is None or not impact.mentioned:
                cells.append('<td class="c ev">–</td>')
                continue
            color = _VERDICT_COLOR[impact.verdict]
            sign = f"{impact.delta:+d}" if impact.delta else "0"
            cells.append(
                f'<td class="c"><span class="dot" style="background:{color}1f;color:{color}">'
                f"{_e(impact.verdict_label)} {sign}</span></td>"
            )
        rows.append(
            f'<tr><td><span class="tag {comp.effective_level.value}">'
            f"{_e(comp.effective_level.label)}</span> {_e(comp.heading)}</td>"
            f'<td class="c ev">{_e(comp.status.label)}</td>{"".join(cells)}</tr>'
        )

    return f"""<div class="card">
<h2>조문 × 당사자 영향 매트릭스</h2>
<div style="overflow-x:auto">
<table><thead><tr><th>조문</th><th class="c">구분</th>{head}</tr></thead>
<tbody>{"".join(rows)}</tbody></table>
</div>
<div class="legend">
  <span><i style="background:{_VERDICT_COLOR['adverse']}"></i>불리 — 권리 대비 의무가 늘어남</span>
  <span><i style="background:{_VERDICT_COLOR['favorable']}"></i>유리</span>
  <span>숫자는 (권리−의무) 점수의 변화량입니다. 법적 판단이 아닌 검토 우선순위 신호입니다.</span>
</div>
</div>"""


# ---------------------------------------------------------------- 변경 이력 탭


def _history_tab(result: ReviewResult) -> str:
    if not result.timeline:
        return (
            '<div class="empty">버전 이력이 없습니다.<br>'
            "<code>contract-review version add &lt;계약ID&gt; &lt;파일&gt;</code> 로 "
            "버전을 등록하면 이 탭에 변경 이력이 쌓입니다.</div>"
        )

    steps = []
    for step in result.timeline:
        chips = (
            f'<span class="tag">수정 {step.modified}</span>'
            f'<span class="tag">신설 {step.added}</span>'
            f'<span class="tag">삭제 {step.deleted}</span>'
            + (f'<span class="tag high">고위험 {step.high}</span>' if step.high else "")
            + (f'<span class="tag medium">중위험 {step.medium}</span>' if step.medium else "")
        )
        headings = (
            '<div class="ev" style="margin-top:5px">주요 변경: '
            + ", ".join(_e(h) for h in step.headings)
            + "</div>"
            if step.headings
            else ""
        )
        steps.append(
            f'<div class="step"><div class="v">{_e(step.from_version)} → '
            f'{_e(step.to_version)}</div><div style="flex:1">'
            f'<div class="chead">{chips}</div>{headings}</div></div>'
        )

    return f"""<div class="card">
<h2>{_e(result.contract_id or "계약")} 버전 타임라인 ({len(result.timeline) + 1}개 버전)</h2>
{"".join(steps)}
</div>"""


# ---------------------------------------------------------------- 유틸


def _json(result: ReviewResult) -> str:
    # </script> 로 문서가 조기 종료되지 않도록 이스케이프한다.
    return json.dumps(result.to_dict(), ensure_ascii=False).replace("</", "<\\/")


def _e(text: str) -> str:
    return html.escape(str(text or ""))
