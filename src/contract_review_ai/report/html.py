"""단일 HTML 리포트 생성.

CDN·외부 폰트·외부 스크립트 의존이 전혀 없다(폐쇄망 반입 가능). 차트는 파이썬이
SVG로 직접 그리고, 상호작용(탭·필터·검색)만 바닐라 JS로 처리한다.

한 페이지에 검토 결과를 여러 개 담을 수 있도록, 결과 한 건은 `.result-panel`
안에서 자기 완결적으로 동작한다(전역 id를 쓰지 않고 패널 내부에서만 요소를 찾는다).
포털 화면은 이 패널들을 골라 보여주는 껍데기다 — `portal.py` 참고.
"""

from __future__ import annotations

import html
import json
import re

from .. import DISCLAIMER
from ..diffing import sentence_changes
from ..models import ClauseComparison, DiffSegment, ReviewResult

_VERDICT_COLOR = {"adverse": "#b42318", "favorable": "#087443", "neutral": "#98a2b3"}

_SENTENCE_SPLIT = re.compile(r"[^.。]*[.。]?")

CSS = """
/* 엔터프라이즈 톤: 중립 무채색 표면에 액센트 하나, 얇은 보더, 낮은 라운드.
   장식 대신 정렬과 여백으로 위계를 만든다. */
:root{
  --canvas:#f7f8fa;
  --surface:#ffffff;
  --ink:#101828;
  --ink-2:#344054;
  --muted:#667085;
  --line:#e4e7ec;
  --line-2:#d0d5dd;
  --accent:#4338CA;
  --accent-2:#0EA5E9;
  --accent-soft:#EEF2FF;
  --chain:linear-gradient(90deg,#4338CA,#0EA5E9);
  --glow:0 0 0 1px rgba(67,56,202,.16), 0 10px 28px rgba(67,56,202,.12);
  --high:#b42318;
  --medium:#b54708;
  --ok:#087443;
  --del:#fdecea;
  --ins:#e9f5ef;
  --shadow:0 1px 2px rgba(16,24,40,.05);
  --sans:"Pretendard","Inter","Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",
         "Segoe UI",system-ui,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font-family:var(--sans);
font-size:14px;line-height:1.62;letter-spacing:-.006em;-webkit-font-smoothing:antialiased;
background:
  radial-gradient(1100px 520px at 8% -8%, rgba(67,56,202,.055), transparent 62%),
  radial-gradient(900px 460px at 100% 0%, rgba(14,165,233,.05), transparent 58%),
  linear-gradient(rgba(16,24,40,.028) 1px, transparent 1px) 0 0/72px 72px,
  linear-gradient(90deg, rgba(16,24,40,.028) 1px, transparent 1px) 0 0/72px 72px,
  var(--canvas)}
.wrap{max-width:1160px;margin:0 auto;padding:0 28px 72px}
b,strong{font-weight:600}

/* 상단 바 */
.masthead{background:var(--surface);border-bottom:1px solid var(--line);padding:0 28px}
.masthead .inner{max-width:1104px;margin:0 auto;display:flex;align-items:center;gap:12px;
min-height:62px;flex-wrap:wrap}
.logo{width:28px;height:28px;border-radius:7px;background:var(--accent);color:#fff;
display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;
flex:0 0 auto}
.masthead h1{font-size:15px;font-weight:600;margin:0;letter-spacing:-.01em}
.masthead .sub{font-size:12.5px;color:var(--muted)}
.crumbs{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:13px;
color:var(--muted);flex-wrap:wrap}
.crumbs button{font:inherit;border:0;background:none;color:var(--accent);cursor:pointer;
font-weight:500;padding:0}
.crumbs button:hover{text-decoration:underline}
.crumbs span{color:var(--line-2)}

/* 선택 화면 */
.screen[hidden]{display:none}
.screen h2.big{font-size:19px;font-weight:600;margin:32px 0 4px;letter-spacing:-.02em}
.screen p.lead{color:var(--muted);font-size:13.5px;margin:0 0 20px}
.picker{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.pick{background:var(--surface);border:1px solid var(--line);border-radius:10px;
padding:18px 20px;cursor:pointer;text-align:left;font:inherit;color:inherit;display:block;
width:100%;box-shadow:var(--shadow);transition:border-color .12s,box-shadow .12s}
.pick:hover{border-color:var(--accent);box-shadow:0 4px 12px rgba(16,24,40,.08)}
.pick .eyebrow{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted)}
.pick h3{font-size:15.5px;font-weight:600;margin:6px 0 3px;letter-spacing:-.01em}
.pick .desc{font-size:12.5px;color:var(--muted);margin-bottom:14px}
.metrics{display:flex;gap:20px;flex-wrap:wrap;padding-top:12px;border-top:1px solid var(--line)}
.metrics div{font-variant-numeric:tabular-nums}
.metrics .n{font-size:17px;font-weight:600;line-height:1.2}
.metrics .k{font-size:11px;color:var(--muted)}
.metrics .n.high{color:var(--high)}
.metrics .n.medium{color:var(--medium)}
.pill{display:inline-block;font-size:11.5px;font-weight:500;padding:2px 9px;border-radius:5px;
background:var(--accent-soft);color:var(--accent);margin:0 5px 5px 0}
.pill.high{background:var(--del);color:var(--high)}
.pill.medium{background:#fdf3e7;color:var(--medium)}
.arrow{float:right;color:var(--muted);font-size:15px}

/* 요약 지표 */
.summary{display:flex;align-items:center;gap:26px;flex-wrap:wrap;background:var(--surface);
border:1px solid var(--line);border-radius:10px;padding:14px 20px;margin:22px 0 18px;
box-shadow:var(--shadow)}
.stat{font-variant-numeric:tabular-nums;line-height:1.25}
.stat b{display:block;font-size:19px;font-weight:600}
.stat span{font-size:11.5px;color:var(--muted)}
.stat.high b{color:var(--high)}
.stat.medium b{color:var(--medium)}
.summary .spark{margin-left:auto}

/* 카드 */
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;
padding:18px 20px;box-shadow:var(--shadow)}
h2{font-size:14px;font-weight:600;margin:0 0 14px;letter-spacing:-.01em}

/* 조작부 */
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.toolbar input{font:inherit;font-size:13.5px;padding:8px 13px;border-radius:8px;
border:1px solid var(--line-2);background:var(--surface);color:var(--ink);flex:1 1 260px}
.toolbar input:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.chip{font:inherit;font-size:12.5px;padding:5px 12px;border-radius:7px;cursor:pointer;
border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2)}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip[aria-pressed="true"]{background:var(--chain);color:#fff;border-color:transparent;
font-weight:600;box-shadow:0 2px 10px rgba(67,56,202,.28)}
.group{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.group .lb{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
color:var(--muted);margin-right:4px}

/* 탭 */
nav{display:flex;gap:26px;margin:0 0 20px;border-bottom:1px solid var(--line);flex-wrap:wrap}
nav button{font:inherit;font-size:13.5px;font-weight:500;padding:0 0 11px;border:0;
background:none;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;
margin-bottom:-1px}
nav button:hover{color:var(--ink)}
nav button[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent);
font-weight:600}
section[hidden]{display:none}

/* 조문 */
.clause{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--line-2);
border-radius:10px;padding:18px 22px;margin-bottom:10px;box-shadow:var(--shadow)}
.clause[data-flagged="1"]{border-left-color:var(--accent)}
.chead{display:flex;flex-wrap:wrap;align-items:center;gap:7px}
.chead h3{margin:0;font-size:15px;font-weight:600;flex:1 1 auto;letter-spacing:-.01em}
.tag{font-size:11.5px;font-weight:500;padding:2px 9px;border-radius:5px;background:#f2f4f7;
color:var(--ink-2);white-space:nowrap}
.tag.high{background:var(--del);color:var(--high)}
.tag.medium{background:#fdf3e7;color:var(--medium)}
.tag.low{background:#f2f4f7;color:var(--muted)}
.tag.adverse{background:var(--del);color:var(--high)}
.tag.favorable{background:var(--ins);color:var(--ok)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
@media(max-width:760px){.cols{grid-template-columns:1fr}}
pre{white-space:pre-wrap;word-break:break-word;background:#fcfcfd;border:1px solid var(--line);
border-radius:8px;padding:12px 14px;margin:6px 0 0;font-size:13px;line-height:1.75;
font-family:var(--sans);color:#98a2b3}
.lbl{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
color:var(--muted)}
del{background:var(--del);color:var(--high);font-weight:500;text-decoration:line-through;
text-decoration-thickness:1.5px;border-radius:3px;padding:0 2px}
ins{background:var(--ins);color:var(--ok);font-weight:500;text-decoration:none;border-radius:3px;
padding:0 2px}

/* 변경 요지 */
.digest{margin-top:14px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.digest .dhead{display:flex;align-items:center;gap:12px;padding:7px 14px;background:#fcfcfd;
border-bottom:1px solid var(--line)}
.digest .count{font-size:11.5px;font-weight:600;font-variant-numeric:tabular-nums}
.digest .count.del{color:var(--high)}
.digest .count.ins{color:var(--ok)}
.drow{display:grid;grid-template-columns:18px 1fr;gap:10px;padding:7px 14px;font-size:13px;
line-height:1.6}
.drow+.drow{border-top:1px solid var(--line)}
.drow .sign{font-weight:600;text-align:center;color:var(--muted)}
.drow.d .sign{color:var(--high)}
.drow.i .sign{color:var(--ok)}
.drow.d .txt{color:var(--high);text-decoration:line-through;text-decoration-color:#e6a49e}
.drow.i .txt{color:var(--ok)}

.g{display:none}
.clause-list[data-grain="sentence"] .g.s{display:inline}
.clause-list[data-grain="word"] .g.w{display:inline}
.clause-list:not([data-grain]) .g.s{display:inline}
.unified{display:none;margin-top:14px}
.clause-list[data-view="unified"] .cols{display:none}
.clause-list[data-view="unified"] .unified{display:block}
.clause-list[data-view="unified"] .unified pre{color:var(--ink-2)}
.difflegend{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:12.5px;
margin-bottom:14px;color:var(--muted)}

details{margin-top:14px;border-top:1px solid var(--line);padding-top:11px}
summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--ink-2)}
summary:hover{color:var(--accent)}
ul{margin:8px 0;padding-left:18px}
li{margin:4px 0;font-size:13.5px}
li::marker{color:var(--line-2)}
p{margin:8px 0}
.ev{color:var(--muted);font-size:12.5px}

/* 표 */
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{border-bottom:1px solid var(--line);padding:9px 12px;text-align:left}
th{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
color:var(--muted)}
tbody tr:hover{background:#fcfcfd}
td.c{text-align:center}
.dot{display:inline-block;min-width:56px;padding:2px 9px;border-radius:5px;font-size:11.5px;
font-weight:500;font-variant-numeric:tabular-nums}

.step{display:flex;gap:18px;align-items:flex-start;padding:13px 0;
border-bottom:1px solid var(--line)}
.step:last-child{border-bottom:0}
.step .v{font-weight:600;font-size:13px;white-space:nowrap;color:var(--accent);min-width:92px;
font-variant-numeric:tabular-nums}
.empty{color:var(--muted);padding:36px;text-align:center;font-size:13.5px}
.legend{font-size:12px;color:var(--muted);display:flex;gap:14px;flex-wrap:wrap;margin-top:12px}
.legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
.disclaimer{color:var(--muted);font-size:12px;margin-top:32px;padding-top:14px;
border-top:1px solid var(--line)}

@media print{
  body{background:#fff}
  nav,.toolbar,.crumbs{display:none}
  section[hidden],.screen[hidden]{display:block !important}
  .clause,.card{break-inside:avoid;box-shadow:none}
}
"""

JS = """
(function(){
  // 결과 패널은 각자 독립적으로 동작한다 — 한 페이지에 여러 개가 놓일 수 있다.
  document.querySelectorAll('.result-panel').forEach(function(panel){
    var tabs = panel.querySelectorAll('nav button');
    tabs.forEach(function(tab){
      tab.addEventListener('click', function(){
        tabs.forEach(function(t){
          var on = (t === tab);
          t.setAttribute('aria-selected', String(on));
          var sec = panel.querySelector('section[data-panel="'+t.dataset.tab+'"]');
          if (sec) sec.hidden = !on;
        });
      });
    });

    var list = panel.querySelector('.clause-list');
    if (!list) return;
    var state = {flagged:'all', status:'all', party:'all', cat:'all', q:''};
    var shown = panel.querySelector('.js-shown');

    function refresh(){
      var n = 0;
      list.querySelectorAll('.clause').forEach(function(el){
        var ok = (state.flagged === 'all' || el.dataset.flagged === state.flagged)
          && (state.status === 'all' || el.dataset.status === state.status)
          && (state.party === 'all' || (el.dataset.adverse||'').split('|').indexOf(state.party) >= 0)
          && (state.cat === 'all' || (el.dataset.cats||'').split('|').indexOf(state.cat) >= 0)
          && (state.q === '' || (el.dataset.search||'').indexOf(state.q) >= 0);
        el.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (shown) shown.textContent = n;
    }

    panel.querySelectorAll('.chip[data-kind]').forEach(function(chip){
      chip.addEventListener('click', function(){
        var kind = chip.dataset.kind;
        panel.querySelectorAll('.chip[data-kind="'+kind+'"]').forEach(function(c){
          c.setAttribute('aria-pressed', String(c === chip));
        });
        state[kind] = chip.dataset.value;
        refresh();
      });
    });

    panel.querySelectorAll('.chip[data-grain]').forEach(function(chip){
      chip.addEventListener('click', function(){
        panel.querySelectorAll('.chip[data-grain]').forEach(function(c){
          c.setAttribute('aria-pressed', String(c === chip));
        });
        list.dataset.grain = chip.dataset.grain;
      });
    });

    panel.querySelectorAll('.chip[data-view]').forEach(function(chip){
      chip.addEventListener('click', function(){
        panel.querySelectorAll('.chip[data-view]').forEach(function(c){
          c.setAttribute('aria-pressed', String(c === chip));
        });
        list.dataset.view = chip.dataset.view;
      });
    });

    var search = panel.querySelector('.js-search');
    if (search) {
      search.addEventListener('input', function(){
        state.q = search.value.trim().toLowerCase();
        refresh();
      });
    }
    refresh();
  });
})();
"""


def render_html(result: ReviewResult) -> str:
    """검토 결과 한 건짜리 페이지."""
    subtitle = f"{result.before_doc.name} → {result.after_doc.name}"
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>계약 검토 리포트 — {_e(result.after_doc.name)}</title>
<style>{CSS}</style></head>
<body>
<div class="masthead"><div class="inner">
  <div class="logo">CR</div>
  <div>
    <h1>계약 검토 리포트</h1>
    <div class="sub">{_e(subtitle)} · {_e(result.generated_at)}</div>
  </div>
</div></div>

<div class="wrap">
{render_result_panel(result)}
<div class="disclaimer">{_e(DISCLAIMER)}</div>
<script type="application/json" class="review-data">{_json(result)}</script>
<script>{JS}</script>
</div></body></html>"""


def render_result_panel(result: ReviewResult) -> str:
    """검토 결과 한 건의 본문. 포털에서도 그대로 재사용한다."""
    changed = sorted(result.changed(), key=lambda c: (-len(c.flags), c.sort_key))
    clauses = "".join(_clause_html(c) for c in changed) or (
        '<div class="empty">변경된 조문이 없습니다.</div>'
    )

    return f"""<div class="result-panel">
{_summary(result)}
<nav>
  <button data-tab="clauses" aria-selected="true">조문 대비</button>
  <button data-tab="parties" aria-selected="false">당사자 영향</button>
  <button data-tab="history" aria-selected="false">개정 연혁</button>
</nav>

<section data-panel="clauses">
{_toolbar(result)}
<div class="clause-list" data-view="split" data-grain="sentence">{clauses}</div>
</section>

<section data-panel="parties" hidden>
{_party_tab(result, changed)}
</section>

<section data-panel="history" hidden>
{_history_tab(result)}
</section>
</div>"""


# ---------------------------------------------------------------- 요약 배지


def _summary(result: ReviewResult) -> str:
    counts = result.counts()
    total = counts["modified"] + counts["added"] + counts["deleted"]

    flagged = sum(1 for c in result.changed() if c.flags)
    issues = sum(len(c.flags) for c in result.changed())
    stats = [
        ("변경 조문", total),
        ("수정", counts["modified"]),
        ("신설", counts["added"]),
        ("삭제", counts["deleted"]),
        ("검토 필요", flagged),
        ("쟁점 신호", issues),
    ]
    chips = "".join(
        f"<span class='stat'><b>{value}</b>{_e(label)}</span>" for label, value in stats
    )
    return f'<div class="summary">{chips}</div>'


# ---------------------------------------------------------------- 조문 대비 탭


_LABEL = {"flagged": "검토", "status": "구분", "party": "당사자", "cat": "쟁점"}


def _toolbar(result: ReviewResult) -> str:
    def chips(kind: str, options: list[tuple[str, str]]) -> str:
        if not options:
            return ""
        out = [f'<span class="lb">{_LABEL[kind]}</span>',
               f'<button class="chip" data-kind="{kind}" data-value="all" '
               f'aria-pressed="true">전체</button>']
        out += [
            f'<button class="chip" data-kind="{kind}" data-value="{_e(value)}" '
            f'aria-pressed="false">{_e(label)}</button>'
            for value, label in options
        ]
        return f'<div class="group">{"".join(out)}</div>'

    # 이 비교본에서 실제로 불리 판정이 난 당사자만 칩으로 남긴다.
    adverse_ids = {
        impact.party_id
        for comp in result.changed()
        for impact in comp.impacts
        if impact.verdict == "adverse" and impact.mentioned
    }
    party_options = [(p.id, f"{p.alias} 불리") for p in result.parties if p.id in adverse_ids]
    category_options = [(c, c) for c in result.category_counts()][:12]

    return f"""<div class="toolbar">
  <input class="js-search" type="search" placeholder="조문 본문·코멘트 검색">
  <div class="group">
    <span class="lb">보기</span>
    <button class="chip" data-view="split" aria-pressed="true">좌우 대비</button>
    <button class="chip" data-view="unified" aria-pressed="false">통합 대조</button>
  </div>
  <div class="group">
    <span class="lb">비교 단위</span>
    <button class="chip" data-grain="sentence" aria-pressed="true">문장</button>
    <button class="chip" data-grain="word" aria-pressed="false">단어</button>
  </div>
  <span class="ev"><b class="js-shown">0</b>건</span>
</div>
<div class="difflegend">
  <span><del>삭제된 문언</del></span><span><ins>추가된 문언</ins></span>
  <span class="ev">흐린 글씨는 변경되지 않은 부분입니다.</span>
</div>
<div class="toolbar">
{chips("flagged", [("1", "쟁점 있음"), ("0", "쟁점 없음")])}
{chips("status", [("modified", "수정"), ("added", "신설"), ("deleted", "삭제")])}
</div>
<div class="toolbar">{chips("party", party_options)}</div>
<div class="toolbar">{chips("cat", category_options)}</div>"""


def _clause_html(comp: ClauseComparison) -> str:
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
        f'<div class="clause" data-flagged="{"1" if comp.flags else "0"}"'
        f' data-status="{comp.status.value}"'
        f' data-adverse="{_e("|".join(i.party_id for i in adverse))}"'
        f' data-cats="{_e("|".join(comp.categories))}"'
        f' data-search="{_e(search_blob)}">',
        '<div class="chead">',
        f"<h3>{_e(comp.heading)}</h3>",
        f'<span class="tag">{_e(comp.status.label)}</span>',
    ]
    parts += [
        f'<span class="tag adverse" data-party="{_e(i.party_id)}" data-party-alias>'
        f"{_e(i.alias)} 불리</span>"
        for i in adverse
    ]
    parts += [
        f'<span class="tag favorable" data-party="{_e(i.party_id)}" data-party-alias>'
        f"{_e(i.alias)} 유리</span>"
        for i in favorable
    ]
    parts.append("</div>")

    parts.append(_digest_html(comp))
    parts += [
        '<div class="cols">',
        f'<div><span class="lbl">변경 전</span><pre>{_grain_html(comp, "before")}</pre></div>',
        f'<div><span class="lbl">변경 후</span><pre>{_grain_html(comp, "after")}</pre></div>',
        "</div>",
        '<div class="unified"><span class="lbl">통합 대조</span>'
        f"<pre>{_unified_html(comp)}</pre></div>",
    ]

    if comp.flags:
        items = "".join(
            f"<li><b>{_e(f.category)}</b> {_e(f.message)}"
            + (f'<div class="ev">근거: {_e(f.evidence)}</div>' if f.evidence else "")
            + "</li>"
            for f in comp.flags
        )
        parts.append(
            f"<details open><summary>자동 탐지 위험 신호 {len(comp.flags)}건</summary>"
            f"<ul>{items}</ul></details>"
        )

    for comment in comp.comments:
        parts.append(_comment_html(comment))

    parts.append("</div>")
    return "\n".join(parts)


def _digest_html(comp: ClauseComparison, limit: int = 8) -> str:
    """조문 카드 맨 위에 붙는 변경 요지.

    좌우 대조는 문맥을 보여주지만 '무엇이 바뀌었는지'를 찾으려면 눈이 두 번
    움직여야 한다. 삭제·추가된 문언만 뽑아 먼저 보여준다.
    """
    before = comp.before.full_text if comp.before else ""
    after = comp.after.full_text if comp.after else ""
    removed, added = sentence_changes(before, after)
    if not removed and not added:
        return ""

    rows = []
    for text in removed[:limit]:
        rows.append('<div class="drow d"><div class="sign">−</div>'
                    f'<div class="txt">{_e(_clip(text))}</div></div>')
    if len(removed) > limit:
        rows.append('<div class="drow d"><div class="sign">−</div>'
                    f'<div class="ev">삭제 {len(removed) - limit}건 더</div></div>')
    for text in added[:limit]:
        rows.append('<div class="drow i"><div class="sign">+</div>'
                    f'<div class="txt">{_e(_clip(text))}</div></div>')
    if len(added) > limit:
        rows.append('<div class="drow i"><div class="sign">+</div>'
                    f'<div class="ev">추가 {len(added) - limit}건 더</div></div>')

    return (
        '<div class="digest"><div class="dhead"><span class="lbl">변경 요지</span>'
        f'<span class="count del">− 삭제 {len(removed)}</span>'
        f'<span class="count ins">+ 추가 {len(added)}</span></div>'
        f'{"".join(rows)}</div>'
    )


def _unified_html(comp: ClauseComparison) -> str:
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


def _sentence_segments(comp: ClauseComparison) -> list[DiffSegment]:
    """문장 단위 대비용 세그먼트.

    단어 단위 diff는 조문을 통째로 다시 쓴 개정에서 수십 개 조각으로 부서진다.
    실무에서는 "이 문장이 이 문장으로 바뀌었다"가 훨씬 빨리 읽히므로 이쪽을
    기본값으로 둔다.
    """
    before = comp.before.full_text if comp.before else ""
    after = comp.after.full_text if comp.after else ""
    removed, added = sentence_changes(before, after)
    removed_set, added_set = set(removed), set(added)

    segments: list[DiffSegment] = []
    for text, changed in _split_sentences(before, removed_set):
        segments.append(DiffSegment("delete" if changed else "equal", text))
    for text, changed in _split_sentences(after, added_set):
        if changed:
            segments.append(DiffSegment("insert", text))
    return segments


def _split_sentences(text: str, changed: set[str]) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for line in text.splitlines(keepends=True):
        for piece in _SENTENCE_SPLIT.findall(line):
            if piece:
                out.append((piece, piece.strip() in changed))
    return out


def _grain_html(comp: ClauseComparison, side: str) -> str:
    """문장/단어 두 벌을 함께 넣고, 보기 설정에 따라 CSS로 하나만 보인다."""
    sentence = _diff_html(comp, side, _sentence_segments(comp))
    word = _diff_html(comp, side, comp.segments)
    return f'<span class="g s">{sentence}</span><span class="g w">{word}</span>'


def _diff_html(
    comp: ClauseComparison, side: str, segments: list[DiffSegment] | None = None
) -> str:
    clause = comp.before if side == "before" else comp.after
    if clause is None:
        return '<span class="ev">(해당 조문 없음)</span>'
    segments = comp.segments if segments is None else segments
    if not segments:
        return _e(clause.full_text)

    out = []
    for seg in segments:
        if seg.op == "equal":
            out.append(_e(seg.text))
        elif seg.op == "delete" and side == "before":
            out.append(f"<del>{_e(seg.text)}</del>")
        elif seg.op == "insert" and side == "after":
            out.append(f"<ins>{_e(seg.text)}</ins>")
    return "".join(out)


def _comment_html(comment) -> str:
    body = [
        f'<details open><summary>법무 코멘트 · {_e(comment.party_view or "중립")}'
        "</summary>"
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


# ---------------------------------------------------------------- 당사자 영향 탭


def _party_tab(result: ReviewResult, changed: list[ClauseComparison]) -> str:
    if not result.parties:
        return '<div class="empty">당사자를 인식하지 못했습니다.</div>'
    if not changed:
        return '<div class="empty">변경된 조문이 없습니다.</div>'

    # data-party가 붙어 있어야 워크스페이스에서 당사자를 숨기거나 표기를 바꿀 때
    # 이 표의 열까지 함께 반영할 수 있다.
    head = "".join(
        f'<th class="c" data-party="{_e(p.id)}" data-party-label>{_e(p.display())}</th>'
        for p in result.parties
    )
    rows = []
    for comp in changed:
        by_party = {i.party_id: i for i in comp.impacts}
        cells = []
        for party in result.parties:
            impact = by_party.get(party.id)
            if impact is None or not impact.mentioned:
                cells.append(f'<td class="c ev" data-party="{_e(party.id)}">–</td>')
                continue
            color = _VERDICT_COLOR[impact.verdict]
            sign = f"{impact.delta:+d}" if impact.delta else "0"
            cells.append(
                f'<td class="c" data-party="{_e(party.id)}">'
                f'<span class="dot" style="background:{color}22;color:{color}">'
                f"{_e(impact.verdict_label)} {sign}</span></td>"
            )
        rows.append(
            f"<tr><td>{_e(comp.heading)}</td>"
            f'<td class="c ev">{_e(comp.status.label)}</td>{"".join(cells)}</tr>'
        )

    return f"""<div class="card" style="margin-bottom:16px">
<h2>당사자별 영향 요약</h2>
{_party_bars(result)}
<div class="legend">
  <span><i style="background:{_VERDICT_COLOR['adverse']}"></i>불리</span>
  <span><i style="background:{_VERDICT_COLOR['neutral']}"></i>중립</span>
  <span><i style="background:{_VERDICT_COLOR['favorable']}"></i>유리</span>
  <span>문장 단위 권리·의무 표현을 센 추정치입니다.</span>
</div>
</div>
<div class="card">
<h2>조문 × 당사자 매트릭스</h2>
<div style="overflow-x:auto">
<table><thead><tr><th>조문</th><th class="c">구분</th>{head}</tr></thead>
<tbody>{"".join(rows)}</tbody></table>
</div>
</div>"""


def _party_bars(result: ReviewResult) -> str:
    summary = result.party_summary()
    if not summary:
        return '<div class="empty">당사자를 인식하지 못했습니다.</div>'

    rows = []
    for row in summary:
        total = row["adverse"] + row["neutral"] + row["favorable"]
        label = row["alias"] + (f' · {row["role"]}' if row["role"] else "")
        if total == 0:
            rows.append(
                f'<tr data-party="{_e(row["party_id"])}"><td data-party-label>{_e(label)}</td>'
                f'<td colspan="2" class="ev">언급된 변경 조문 없음</td></tr>'
            )
            continue
        segments, x = [], 0.0
        for key in ("adverse", "neutral", "favorable"):
            width = 240 * row[key] / total
            if width > 0:
                segments.append(
                    f'<rect x="{x:.1f}" y="0" width="{width:.1f}" height="14" '
                    f'fill="{_VERDICT_COLOR[key]}"><title>{key} {row[key]}건</title></rect>'
                )
                x += width
        rows.append(
            f'<tr data-party="{_e(row["party_id"])}"><td data-party-label>{_e(label)}</td>'
            f'<td><svg width="240" height="14" viewBox="0 0 240 14">{"".join(segments)}</svg></td>'
            f'<td class="ev">불리 {row["adverse"]} · 중립 {row["neutral"]} · '
            f'유리 {row["favorable"]}'
            + (f" · <b>중점 검토 {row['high']}</b>" if row["high"] else "")
            + "</td></tr>"
        )
    return f"<table>{''.join(rows)}</table>"


# ---------------------------------------------------------------- 개정 연혁 탭


def _history_tab(result: ReviewResult) -> str:
    if not result.timeline:
        return (
            '<div class="empty">등록된 버전 이력이 없습니다.<br>'
            "<code>contract-review version add &lt;계약ID&gt; &lt;파일&gt;</code> 로 "
            "버전을 등록하면 이력이 쌓입니다.</div>"
        )

    steps = []
    for step in result.timeline:
        chips = (
            f'<span class="tag">수정 {step.modified}</span>'
            f'<span class="tag">신설 {step.added}</span>'
            f'<span class="tag">삭제 {step.deleted}</span>'
            + (f'<span class="tag">쟁점 {step.flagged}</span>' if step.flagged else "")
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
<h2>{_e(result.contract_id or "계약")} 버전 타임라인
({len(result.timeline) + 1}개 버전)</h2>
{"".join(steps)}
</div>"""


# ---------------------------------------------------------------- 유틸


def _clip(text: str, width: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width] + " …"


def _json(result: ReviewResult) -> str:
    # </script> 로 문서가 조기 종료되지 않도록 이스케이프한다.
    return json.dumps(result.to_dict(), ensure_ascii=False).replace("</", "<\\/")


def _e(text: str) -> str:
    return html.escape(str(text or ""))
