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
    "high": "#8c1d18",
    "medium": "#9a6b1c",
    "low": "#6f6a52",
    "info": "#8b8782",
}
_VERDICT_COLOR = {"adverse": "#8c1d18", "favorable": "#1f5136", "neutral": "#8b8782"}

_CSS = """
/* 대형 로펌 의견서 톤: 감청(navy) 바탕에 금박 포인트, 명조 계열 제목,
   둥근 모서리 없이 얇은 괘선과 여백으로만 위계를 만든다. */
:root{
  --paper:#f4f2ed;      /* 미색 종이 */
  --card:#ffffff;
  --navy:#0e2340;       /* 표제·강조 */
  --navy-soft:#1b3a5f;
  --gold:#a4854b;       /* 괘선 포인트 */
  --ink:#1c1c1a;
  --muted:#6f6a62;
  --line:#ddd8cf;
  --line-strong:#c6bfb2;
  --del:#f6e4e2;
  --ins:#e4ecdf;
  --chip:#f0ede6;
}
/* 서체: 본문은 명조(의견서 톤), 라벨·수치는 자간을 넓힌 산세리프. */
:root{
  --serif:"Nanum Myeongjo","Noto Serif KR","Source Han Serif K","Apple SD Gothic Neo",
          Batang,바탕,"EB Garamond",Garamond,Georgia,"Times New Roman",serif;
  --sans:"Pretendard","Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",
         "Segoe UI",system-ui,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);line-height:1.78;
font-family:var(--serif);font-size:15px;letter-spacing:-.003em;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}
.wrap{max-width:1140px;margin:0 auto;padding:0 24px 76px}
/* 라벨·수치·조작부는 산세리프로 — 본문 명조와 역할을 갈라 놓는다. */
nav button,.chip,.tag,.lbl,th,.group .lb,.toolbar input,.count,.legend,.difflegend,
.ev,.kpi .l,.dot,.mark,.sub{font-family:var(--sans)}

/* ── 표제부 ───────────────────────────────────────── */
.masthead{background:var(--navy);color:#f2efe8;padding:38px 24px 30px;
border-bottom:3px solid var(--gold)}
.masthead .inner{max-width:1092px;margin:0 auto;text-align:center}
.mark{font-family:var(--sans);font-size:10.5px;letter-spacing:.5em;text-transform:uppercase;
color:var(--gold);margin-bottom:16px;padding-left:.5em}
.masthead h1{font-size:31px;font-weight:400;letter-spacing:.14em;margin:0;
padding-left:.14em}
.masthead .rule{width:52px;height:1px;background:var(--gold);margin:16px auto 14px}
.masthead .sub{font-family:var(--sans);font-size:11px;letter-spacing:.2em;
color:rgba(242,239,232,.55)}

.disclaimer{border-left:2px solid var(--gold);background:#fbf9f4;color:#5c4a2a;
padding:11px 17px;font-size:13px;margin:24px 0 0}

/* ── 목차 탭 ───────────────────────────────────────── */
nav{display:flex;gap:0;border-bottom:1px solid var(--line-strong);margin:22px 0 26px;
flex-wrap:wrap}
nav button{font:inherit;font-size:13px;letter-spacing:.09em;padding:11px 22px 10px;border:0;
background:none;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;
margin-bottom:-1px}
nav button:hover{color:var(--navy)}
nav button[aria-selected="true"]{color:var(--navy);border-bottom-color:var(--gold);font-weight:700}
section[hidden]{display:none}

/* ── 카드·표제 ─────────────────────────────────────── */
.strip{display:flex;align-items:center;gap:26px;flex-wrap:wrap;margin-top:26px;
padding-bottom:22px;border-bottom:1px solid var(--line-strong)}
.strip .kpis{flex:1 1 460px}
.strip .donut{flex:0 0 auto}
.grid{display:grid;gap:1px;background:var(--line)}
.kpis{grid-template-columns:repeat(auto-fit,minmax(104px,1fr));border:1px solid var(--line)}
.card{background:var(--card);border:1px solid var(--line);padding:18px 22px}
.kpi{background:var(--card);padding:14px 16px;text-align:center}
.kpi .n{font-family:var(--serif);font-size:31px;font-weight:400;line-height:1.1;
color:var(--navy)}
.kpi .l{font-family:var(--sans);font-size:10.5px;letter-spacing:.14em;color:var(--muted);
margin-top:5px}
.difflegend{display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:12.5px;
margin:0 0 16px;padding-bottom:14px;border-bottom:1px solid var(--line)}
h2{font-family:var(--serif);font-size:16px;
font-weight:700;color:var(--navy);margin:0 0 14px;padding-bottom:8px;
border-bottom:1px solid var(--line)}

/* ── 검색·필터 ─────────────────────────────────────── */
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.toolbar input{font:inherit;font-size:13px;padding:9px 13px;border:1px solid var(--line-strong);
background:var(--card);color:var(--ink);min-width:200px;flex:1 1 240px}
.toolbar input:focus{outline:0;border-color:var(--gold)}
.chip{font:inherit;font-size:12.5px;padding:5px 13px;cursor:pointer;
border:1px solid var(--line-strong);background:var(--card);color:var(--muted)}
.chip:hover{color:var(--navy);border-color:var(--navy-soft)}
.chip[aria-pressed="true"]{background:var(--navy);color:#f2efe8;border-color:var(--navy)}
.group{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.group .lb{font-size:11px;letter-spacing:.12em;color:var(--muted);margin-right:6px;min-width:44px}

/* ── 조문 카드 ─────────────────────────────────────── */
.clause{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--line-strong);
padding:18px 22px;margin-bottom:14px}
.clause[data-risk="high"]{border-left-color:#8c1d18}
.clause[data-risk="medium"]{border-left-color:#9a6b1c}
.clause[data-risk="low"]{border-left-color:#6f6a52}
.chead{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px}
.chead h3{font-family:var(--serif);margin:0;
font-size:17px;font-weight:700;color:var(--navy);flex:1 1 auto}
.tag{font-size:11px;letter-spacing:.04em;padding:2px 9px;background:var(--chip);
color:var(--muted);white-space:nowrap;border:1px solid var(--line)}
.tag.high{background:#8c1d18;color:#fff;border-color:#8c1d18}
.tag.medium{background:#9a6b1c;color:#fff;border-color:#9a6b1c}
.tag.low{background:#efe9d6;color:#5c5326;border-color:#ddd2ad}
.tag.adverse{background:#f6e4e2;color:#7d1a15;border-color:#e6c6c2}
.tag.favorable{background:#e4ecdf;color:#1f5136;border-color:#c6d8c2}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}
@media(max-width:760px){.cols{grid-template-columns:1fr}}
pre{white-space:pre-wrap;word-break:break-word;background:#fbfaf7;border:1px solid var(--line);
padding:12px 14px;margin:6px 0 0;font-size:13px;line-height:1.85;
font-family:var(--serif);color:#7a766c}
.lbl{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold);
font-weight:700}
/* 변경분은 진하게, 그대로인 문맥은 흐리게 — 눈이 바뀐 곳으로 먼저 가도록. */
del{background:#f7d9d6;color:#7d1a15;font-weight:700;text-decoration:line-through;
text-decoration-thickness:2px;text-decoration-color:#b4534b;padding:0 2px;
box-shadow:inset 2px 0 0 #8c1d18}
ins{background:#d8e8d4;color:#17452c;font-weight:700;text-decoration:none;padding:0 2px;
box-shadow:inset 2px 0 0 #1f5136}

/* ── 변경 요지 (삭제 ↔ 추가 대응) ─────────────────── */
.digest{margin-top:13px;border:1px solid var(--line-strong);background:#fdfcf9}
.digest .dhead{display:flex;align-items:center;gap:10px;padding:7px 13px;
border-bottom:1px solid var(--line);background:var(--chip)}
.digest .dhead .lbl{color:var(--navy)}
.digest .count{font-size:11.5px;font-weight:700;letter-spacing:.02em}
.digest .count.del{color:#8c1d18}
.digest .count.ins{color:#1f5136}
.drow{display:grid;grid-template-columns:26px 1fr;gap:10px;padding:8px 13px;
border-bottom:1px dotted var(--line);font-size:13px;line-height:1.6}
.drow:last-child{border-bottom:0}
.drow .sign{font-weight:700;text-align:center;font-size:14px}
.drow.d .sign{color:#8c1d18}
.drow.i .sign{color:#1f5136}
.drow.d .txt{color:#7d1a15;text-decoration:line-through;text-decoration-color:#c08b86}
.drow.i .txt{color:#17452c;font-weight:600}

/* ── 대비 보기 / 통합 보기 ─────────────────────────── */
.unified{display:none;margin-top:14px}
#clause-list[data-view="unified"] .cols{display:none}
#clause-list[data-view="unified"] .unified{display:block}
#clause-list[data-view="unified"] .unified pre{color:#2a2a26}
details{margin-top:15px;border-top:1px solid var(--line);padding-top:11px}
summary{cursor:pointer;font-size:12.5px;color:var(--navy);font-weight:700;letter-spacing:.02em}
summary:hover{color:var(--gold)}
ul{margin:8px 0;padding-left:18px}
li{margin:4px 0;font-size:13.5px}
li::marker{color:var(--gold)}
p{margin:8px 0}
.ev{color:var(--muted);font-size:12px}
b{color:var(--navy)}

/* ── 표 ───────────────────────────────────────────── */
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:middle}
th{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
font-weight:700;background:var(--card);border-bottom:1px solid var(--line-strong)}
tbody tr:hover{background:#faf8f4}
td.c{text-align:center}
.dot{display:inline-block;min-width:52px;padding:2px 9px;font-size:11.5px;
border:1px solid currentColor}

/* ── 연혁 ─────────────────────────────────────────── */
.step{display:flex;gap:20px;align-items:flex-start;padding:15px 0;
border-bottom:1px solid var(--line)}
.step:last-child{border-bottom:0}
.step .v{font-family:var(--serif);font-weight:700;
font-size:14px;white-space:nowrap;color:var(--navy);min-width:104px}
.empty{color:var(--muted);padding:34px;text-align:center;font-size:13.5px}
.legend{font-size:11.5px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;
padding-top:10px;border-top:1px solid var(--line)}
.legend i{display:inline-block;width:9px;height:9px;margin-right:6px}

@media print{
  body{background:#fff}
  nav,.toolbar{display:none}
  section[hidden]{display:block !important}
  .clause,.card{break-inside:avoid;border-color:#bbb}
  .masthead{background:#fff;color:var(--ink);border-bottom:2px solid var(--navy)}
  .masthead h1,.docket span{color:var(--navy)}
}
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
  var list = document.getElementById('clause-list');
  document.querySelectorAll('.chip[data-view]').forEach(function(chip){
    chip.addEventListener('click', function(){
      document.querySelectorAll('.chip[data-view]').forEach(function(c){
        c.setAttribute('aria-pressed', String(c === chip));
      });
      if (list) list.dataset.view = chip.dataset.view;
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

    version_line = ""
    if result.before_doc.version or result.after_doc.version:
        version_line = (
            f'{_e(result.before_doc.version or "?")} → {_e(result.after_doc.version or "?")}'
        )

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>계약 검토 의견서 — {_e(result.after_doc.name)}</title>
<style>{_CSS}</style></head>
<body>
<div class="masthead"><div class="inner">
  <div class="mark">Contract Review</div>
  <h1>계약 개정안 검토 의견서</h1>
  <div class="rule"></div>
  <div class="sub">{_e(result.generated_at)}{f" · {version_line}" if version_line else ""}</div>
</div></div>

<div class="wrap">
{_summary_strip(result, counts, risks)}

<nav>
  <button data-tab="tab-clauses" aria-selected="true">조문 대비</button>
  <button data-tab="tab-parties" aria-selected="false">당사자 영향</button>
  <button data-tab="tab-history" aria-selected="false">개정 연혁</button>
</nav>

<section id="tab-clauses">
{_toolbar(result)}
<div id="clause-list" data-view="split">
{"".join(_clause_html(c) for c in changed) or '<div class="empty">변경된 조문이 없습니다.</div>'}
</div>
</section>

<section id="tab-parties" hidden>
{_party_tab(result, changed)}
</section>

<section id="tab-history" hidden>
{_history_tab(result)}
</section>

<div class="disclaimer">{_e(DISCLAIMER)}</div>

<script id="review-data" type="application/json">{_json(result)}</script>
<script>{_JS}</script>
</div></body></html>"""


# ---------------------------------------------------------------- 요약 스트립


def _summary_strip(result: ReviewResult, counts: dict[str, int], risks: dict[str, int]) -> str:
    """탭 위에 항상 떠 있는 요약. 탭을 옮겨도 총량 감각을 잃지 않게 한다."""
    kpis = [
        ("변경 조문", counts["modified"] + counts["added"] + counts["deleted"], None),
        ("수정", counts["modified"], None),
        ("신설", counts["added"], None),
        ("삭제", counts["deleted"], None),
        ("고위험", risks["high"], _RISK_COLOR["high"]),
        ("중위험", risks["medium"], _RISK_COLOR["medium"]),
    ]
    kpi_html = "".join(
        '<div class="kpi"><div class="n"'
        + (f" style='color:{color}'" if color else "")
        + f">{value}</div>"
        + f'<div class="l">{_e(label)}</div></div>'
        for label, value, color in kpis
    )
    return f"""<div class="strip">
  <div class="grid kpis">{kpi_html}</div>
  <div class="donut">{_donut(risks)}</div>
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
            f'<rect x="96" y="{y}" width="{width}" height="14" fill="#0e2340" opacity="0.82"/>'
            f'<text x="{96 + width + 7}" y="{y + 11}" font-size="11" fill="#6f6a62">{value}</text>'
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

    return f"""<div class="card" style="margin-bottom:18px">
  <h2>쟁점 분포</h2>
  {_bars(result.category_counts())}
</div>
<div class="toolbar">
  <input id="search" type="search" placeholder="조문 본문·코멘트 검색">
  <div class="group">
    <span class="lb">보기</span>
    <button class="chip" data-view="split" aria-pressed="true">좌우 대비</button>
    <button class="chip" data-view="unified" aria-pressed="false">통합 대조</button>
  </div>
  <span class="ev"><b id="shown-count">0</b>건 표시</span>
</div>
<div class="difflegend">
  <span><del>삭제된 문언</del></span><span><ins>추가된 문언</ins></span>
  <span class="ev">흐린 글씨는 변경 없는 문맥입니다.</span>
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

    parts.append(_digest_html(comp))
    parts += [
        '<div class="cols">',
        f'<div><span class="lbl">변경 전</span><pre>{_diff_html(comp, "before")}</pre></div>',
        f'<div><span class="lbl">변경 후</span><pre>{_diff_html(comp, "after")}</pre></div>',
        "</div>",
        '<div class="unified"><span class="lbl">통합 대조</span>'
        f"<pre>{_unified_html(comp)}</pre></div>",
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


def _digest_html(comp: ClauseComparison, limit: int = 8) -> str:
    """조문 카드 맨 위에 붙는 변경 요지.

    좌우 대조는 문맥을 보여주지만 '무엇이 바뀌었는지'를 찾으려면 눈이 두 번
    움직여야 한다. 삭제·추가된 문언만 뽑아 먼저 보여준다.
    """
    removed = [s.text.strip() for s in comp.segments if s.op == "delete" and s.text.strip()]
    added = [s.text.strip() for s in comp.segments if s.op == "insert" and s.text.strip()]
    if not removed and not added:
        return ""

    rows = []
    for text in removed[:limit]:
        rows.append(f'<div class="drow d"><div class="sign">−</div>'
                    f'<div class="txt">{_e(_clip(text))}</div></div>')
    if len(removed) > limit:
        rows.append(f'<div class="drow d"><div class="sign">−</div>'
                    f'<div class="ev">삭제 {len(removed) - limit}건 더</div></div>')
    for text in added[:limit]:
        rows.append(f'<div class="drow i"><div class="sign">+</div>'
                    f'<div class="txt">{_e(_clip(text))}</div></div>')
    if len(added) > limit:
        rows.append(f'<div class="drow i"><div class="sign">+</div>'
                    f'<div class="ev">추가 {len(added) - limit}건 더</div></div>')

    return (
        '<div class="digest"><div class="dhead"><span class="lbl">변경 요지</span>'
        f'<span class="count del">− 삭제 {len(removed)}</span>'
        f'<span class="count ins">+ 추가 {len(added)}</span></div>'
        f'{"".join(rows)}</div>'
    )


def _unified_html(comp: ClauseComparison) -> str:
    """삭제·추가를 한 흐름에 겹쳐 보여주는 통합 대조."""
    if not comp.segments:
        clause = comp.after or comp.before
        return _e(clause.full_text) if clause else ""

    out = []
    for seg in comp.segments:
        if seg.op == "equal":
            out.append(_e(seg.text))
        elif seg.op == "delete":
            out.append(f"<del>{_e(seg.text)}</del>")
        else:
            out.append(f"<ins>{_e(seg.text)}</ins>")
    return "".join(out)


def _clip(text: str, width: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width] + " …"


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

    return f"""<div class="card" style="margin-bottom:18px">
<h2>당사자별 영향 요약</h2>
{_party_bars(result)}
<div class="legend">
  <span><i style="background:{_VERDICT_COLOR['adverse']}"></i>불리</span>
  <span><i style="background:{_VERDICT_COLOR['neutral']}"></i>중립</span>
  <span><i style="background:{_VERDICT_COLOR['favorable']}"></i>유리</span>
</div>
</div>
<div class="card">
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
