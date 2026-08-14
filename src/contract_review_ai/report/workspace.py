"""CLAUSA 워크스페이스 — 계약·버전·검토를 한 페이지에서 다루는 콘솔.

화면 구성

    대시보드     포트폴리오 지표, 분류별 분포, 최근 개정 활동
    계약         분류 필터 + 계약 목록 표 → 행 선택
    계약 상세     버전 관리 표(등록일·해시·메모), 개정 타임라인, 비교본 목록
    검토 결과     조문 대비 / 당사자 영향 / 개정 연혁 (html.render_result_panel 재사용)

서버가 없는 단일 HTML이지만 화면 전환·필터·검색은 실제 콘솔처럼 동작한다.
데이터는 생성 시점에 전부 인라인되므로 폐쇄망에서도 그대로 열린다.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass, field

from .. import DISCLAIMER, relations
from ..deadlines import Deadline
from ..models import ReviewResult, TimelineStep, VersionRecord
from .checky import CSS as CHECKY_CSS
from .checky import JS as CHECKY_JS
from .checky import brand_markup, buddy_markup
from .html import CSS as BASE_CSS
from .html import JS as PANEL_JS
from .html import render_result_panel

BRAND = "체키"

CATEGORY_ORDER = ("물품구매", "용역", "자문", "연구개발", "라이선스")
"""계약 분류. 필터는 이 순서로 고정하고, 그 밖의 분류는 뒤에 붙인다."""

STATUS_ORDER = ("started", "ongoing", "done")
STATUS_LABEL = {"started": "개시", "ongoing": "진행중", "done": "완료"}
STATUS_COLOR = {"started": "#7c8698", "ongoing": "#1849a9", "done": "#087443"}
_FINAL_HINTS = ("최종", "날인", "서명", "확정", "체결")
USER_NAME = "김민형"
TAGLINE = "계약 검토 도우미"

_CSS = """
/* ── 앱 셸 ────────────────────────────────────────── */
/* 좌측 고정 사이드바는 폭이 좁아지면 자리를 잃는다. 상단 한 줄 탭은 어느 폭에서도
   가로 스크롤로 흡수되므로 레이아웃이 무너지지 않는다. */
.app{min-height:100vh}
.appbar{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.88);
backdrop-filter:saturate(180%) blur(14px);-webkit-backdrop-filter:saturate(180%) blur(14px);
border-bottom:1px solid var(--line)}
.appbar::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;
background:var(--chain);opacity:.5}
.appbar-inner{max-width:1320px;margin:0 auto;padding:0 24px;display:flex;align-items:center;
gap:22px;min-height:62px}
.brand{display:flex;align-items:center;gap:10px;flex:0 0 auto;border:0;background:none;
padding:0;cursor:pointer;font:inherit;text-align:left;border-radius:10px}
.brand:hover .name{filter:brightness(1.15)}
.brand:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.brand .name{font-size:15px;font-weight:700;letter-spacing:.06em;line-height:1.15;
background:var(--chain);-webkit-background-clip:text;background-clip:text;color:transparent}
.brand .tag{font-size:10px;color:var(--muted);letter-spacing:.08em}
.brand .ck-face{flex:0 0 auto}

.tabs{display:flex;align-items:center;gap:2px;overflow-x:auto;scrollbar-width:none;
flex:1 1 auto;min-width:0}
.tabs::-webkit-scrollbar{display:none}
.tabs button{position:relative;font:inherit;font-size:13.5px;font-weight:500;white-space:nowrap;
padding:19px 14px;border:0;background:none;color:var(--muted);cursor:pointer;
display:inline-flex;align-items:center;gap:7px}
.tabs button:hover{color:var(--ink)}
.tabs button::after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;
border-radius:2px;background:var(--chain);opacity:0;transition:opacity .16s}
.tabs button[aria-current="true"]{color:var(--accent);font-weight:600}
.tabs button[aria-current="true"]::after{opacity:1}
.tabs .cnt{font-size:11px;font-weight:600;color:var(--muted);background:var(--raise,#f2f4f7);
border-radius:999px;padding:1px 7px;font-variant-numeric:tabular-nums}
.tabs button[aria-current="true"] .cnt{background:var(--accent-soft);color:var(--accent)}

.appbar-right{display:flex;align-items:center;gap:12px;flex:0 0 auto}
.appbar-right .who{display:flex;align-items:center;gap:9px;font-size:12.5px;color:var(--muted)}
.appbar-right .who .av{width:26px;height:26px;border-radius:50%;background:var(--chain);
color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}

.main{min-width:0}
.topbar{max-width:1320px;margin:0 auto;padding:12px 24px 0;display:flex;align-items:center;
gap:14px;flex-wrap:wrap}
.topbar .path{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:7px;
flex-wrap:wrap}
.topbar .path button{font:inherit;border:0;background:none;color:var(--accent);cursor:pointer;
padding:0;font-weight:500}
.topbar .path button:hover{text-decoration:underline}
.topbar .path .sep{color:var(--line-2)}
.topbar .path b{font-weight:600;color:var(--ink)}
.shellinfo{margin-left:auto;font-size:11.5px;color:var(--muted)}

.view{max-width:1320px;margin:0 auto;padding:18px 24px 120px}
.view[hidden]{display:none}
.vhead{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap;margin-bottom:20px}
.vhead h2{font-size:20px;font-weight:600;margin:0;letter-spacing:-.02em}
.vhead p{margin:2px 0 0;font-size:13px;color:var(--muted)}
.vhead .right{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}

@media(max-width:900px){
  .appbar-inner{gap:12px;padding:0 14px;flex-wrap:wrap;min-height:0;padding-top:10px}
  .brand .tag{display:none}
  .tabs{order:3;width:100%;flex-basis:100%;border-top:1px solid var(--line)}
  .tabs button{padding:12px 11px}
  .appbar-right{margin-left:auto}
  .topbar,.view{padding-left:14px;padding-right:14px}
  .ck-buddy{display:none}
}

/* ── 진행 단계 보드 ────────────────────────────────── */
.statboard{margin-bottom:18px}
.statcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.statcard{position:relative;overflow:hidden;text-align:left;font:inherit;cursor:pointer;
background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px 14px;
box-shadow:var(--shadow);transition:transform .16s,box-shadow .16s,border-color .16s}
.statcard:hover{transform:translateY(-2px);border-color:var(--sc);
box-shadow:0 12px 28px rgba(16,24,40,.10)}
.statcard::before{content:"";position:absolute;inset:0 0 auto;height:3px;background:var(--sc)}
.statcard .dotmark{position:absolute;top:16px;right:16px;width:8px;height:8px;border-radius:50%;
background:var(--sc);box-shadow:0 0 0 4px color-mix(in srgb,var(--sc) 18%,transparent)}
.sc-k{font-size:12px;color:var(--muted);font-weight:600;letter-spacing:.04em}
.sc-n{font-size:32px;font-weight:600;line-height:1.1;margin-top:6px;color:var(--sc);
font-variant-numeric:tabular-nums}
.sc-d{font-size:11.5px;color:var(--muted);margin-top:2px}
.sc-bar{height:4px;border-radius:3px;background:#eef1f5;margin-top:12px;overflow:hidden}
.sc-bar i{display:block;height:100%;border-radius:3px;background:var(--sc);
animation:grow .8s cubic-bezier(.22,1,.36,1) both}
.flowbar{display:flex;gap:3px;height:8px;margin-top:12px}
.flowbar .seg{border-radius:4px;animation:fade .6s ease both}
@keyframes fade{from{opacity:0}}

.tracks{display:flex;flex-direction:column;gap:4px}
.track{display:grid;grid-template-columns:210px 1fr 150px;gap:16px;align-items:center;
padding:11px 10px;border-radius:8px;cursor:pointer;transition:background .14s}
.track:hover{background:#f8fafc}
@media(max-width:820px){.track{grid-template-columns:1fr}}
.tk-name b{display:block;font-size:13.5px;font-weight:600}
.tk-name .ev{display:block;font-size:11.5px;margin-top:1px}
.tk-track{position:relative;height:8px;border-radius:5px;background:#eef1f5}
.tk-fill{height:100%;border-radius:5px;animation:grow .8s cubic-bezier(.22,1,.36,1) both}
.tk-dots{position:absolute;inset:0;display:flex;align-items:center;gap:0;
justify-content:space-between;padding:0 2px}
.vdot{width:6px;height:6px;border-radius:50%;background:#fff;
box-shadow:0 0 0 1.5px rgba(16,24,40,.18)}
.vdot.done{background:var(--accent);box-shadow:0 0 0 1.5px var(--accent),0 0 10px rgba(67,56,202,.55)}
.tk-meta{display:flex;align-items:center;gap:10px;justify-content:flex-end}
.pill-status{font-size:11.5px;font-weight:600;color:var(--sc);background:
color-mix(in srgb,var(--sc) 12%,transparent);padding:3px 10px;border-radius:999px}

/* ── 지표 ─────────────────────────────────────────── */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;
margin-bottom:20px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 18px;
box-shadow:var(--shadow)}
.kpi .k{font-size:11.5px;color:var(--muted)}
.kpi .n{font-size:26px;font-weight:600;line-height:1.2;margin-top:4px;
font-variant-numeric:tabular-nums}
.kpi .n.high{color:var(--high)}
.kpi .d{font-size:11.5px;color:var(--muted);margin-top:2px}
.panels{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}
@media(max-width:900px){.panels{grid-template-columns:1fr}}

/* ── 표 ───────────────────────────────────────────── */
.tbl{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;
box-shadow:var(--shadow)}
.tbl table{width:100%;border-collapse:collapse;font-size:13.5px}
.tbl th{background:#fbfbfc;font-size:11px;font-weight:600;letter-spacing:.06em;
text-transform:uppercase;color:var(--muted);padding:10px 14px;text-align:left;
border-bottom:1px solid var(--line)}
.tbl td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:middle}
.tbl tr:last-child td{border-bottom:0}
.tbl tbody tr[data-open]{cursor:pointer}
.tbl tbody tr[data-open]:hover{background:#f8fafc}
.tbl .name{font-weight:600}
.tbl .sub{font-size:12px;color:var(--muted);margin-top:1px}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;
color:var(--muted)}
.badge{display:inline-block;font-size:11.5px;padding:2px 9px;border-radius:5px;
background:#eef2f7;color:var(--ink-2);white-space:nowrap}
.badge.cat{background:#eef4ff;color:#1849a9}
.badge.high{background:var(--del);color:var(--high)}
.badge.medium{background:#fdf3e7;color:var(--medium)}
.badge.ok{background:var(--ins);color:var(--ok)}
.badge.latest{background:#101828;color:#fff}
.num{font-variant-numeric:tabular-nums;text-align:right}

/* ── 분포 막대 ─────────────────────────────────────── */
.dist{display:flex;flex-direction:column;gap:11px}
.dist .row{display:grid;grid-template-columns:110px 1fr 34px;align-items:center;gap:10px;
font-size:13px}
.dist .bar{height:8px;border-radius:4px;background:#eef1f5;overflow:hidden}
.dist .bar i{display:block;height:100%;background:#2563eb;border-radius:4px}
.dist .v{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}

/* ── 활동 ─────────────────────────────────────────── */
.feed{display:flex;flex-direction:column}
.feed .it{display:grid;grid-template-columns:88px 1fr;gap:12px;padding:11px 0;
border-bottom:1px solid var(--line);font-size:13px}
.feed .it:last-child{border-bottom:0}
.feed .when{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.feed .what b{font-weight:600}
.feed .meta{color:var(--muted);font-size:12px;margin-top:2px}

/* ── 계약 상세 ─────────────────────────────────────── */
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
@media(max-width:900px){.detail-grid{grid-template-columns:1fr}}
.sec{margin-bottom:22px}
.sec h3{font-size:14px;font-weight:600;margin:0 0 10px}
.sec .hint{font-size:12.5px;color:var(--muted);margin:0 0 10px}
.filters{display:flex;gap:6px;flex-wrap:wrap}
.tpl-grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(268px,1fr))}
.tpl{display:flex;flex-direction:column;gap:12px;background:var(--surface);
border:1px solid var(--line);border-radius:10px;padding:16px 18px;box-shadow:var(--shadow);
transition:border-color .14s,box-shadow .14s}
.tpl:hover{border-color:var(--accent);box-shadow:var(--glow)}
.tpl h4{margin:6px 0 4px;font-size:14.5px;font-weight:600}
.tpl p{margin:0;font-size:12.5px;color:var(--muted);line-height:1.6}
.tpl button{align-self:flex-start;margin-top:auto}
textarea{font:inherit;font-size:13.5px;width:100%;padding:10px 12px;border-radius:8px;
border:1px solid var(--line-2);background:var(--surface);color:var(--ink);resize:vertical;
margin-top:5px;line-height:1.7}
textarea:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
select{font:inherit;font-size:13.5px;padding:8px 12px;border-radius:8px;
border:1px solid var(--line-2);background:var(--surface);color:var(--ink);margin-top:5px}
.mtstate{font-size:12.5px;color:var(--muted)}
.mtstate.err{color:var(--high)}
.mtstate.ok{color:var(--ok)}
.proposals{display:flex;flex-direction:column;gap:10px;margin-top:14px}
.prop{border:1px solid var(--line);border-radius:10px;overflow:hidden}
.prop-head{display:flex;align-items:center;gap:10px;padding:10px 14px;background:#fbfbfc;
border-bottom:1px solid var(--line)}
.prop-head b{font-size:13.5px}
.prop-head label{margin-left:auto;display:flex;align-items:center;gap:6px;font-size:12.5px;
color:var(--muted);cursor:pointer}
.prop-body{padding:12px 14px}
.prop .basis{font-size:12.5px;color:var(--accent);background:var(--accent-soft);
border-radius:6px;padding:8px 11px;margin-bottom:10px}
.prop .cols2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:820px){.prop .cols2{grid-template-columns:1fr}}
.prop .note{font-size:12px;color:var(--muted);margin-top:8px}
.dl-list{display:flex;flex-direction:column}
.dl-row{display:flex;align-items:center;gap:12px;padding:11px 0;
border-bottom:1px solid var(--line);cursor:pointer}
.dl-row:last-child{border-bottom:0}
.dl-row:hover{background:#f8fafc}
.dl-row b{font-size:13.5px;font-weight:600}
.dl-row .ev{margin-top:2px}
.dl-tag{margin-left:auto;font-size:11.5px;font-weight:600;padding:3px 11px;border-radius:999px;
white-space:nowrap}
.dl-tag.passed{background:var(--del);color:var(--high)}
.dl-tag.soon{background:#fdf3e7;color:var(--medium)}
.dl-tag.ok{background:#eef2f7;color:var(--muted)}

.hits{display:flex;flex-direction:column;gap:10px}
.hit{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 18px;
box-shadow:var(--shadow);cursor:pointer}
.hit:hover{border-color:var(--accent);box-shadow:var(--glow)}
.hit-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.hit-head b{font-size:14px;font-weight:600}
.hit-head .ev{margin-left:auto}
.hit p{margin:8px 0 0;font-size:13px;line-height:1.7;color:var(--ink-2);white-space:pre-wrap}
.hit mark{background:#fff3c4;border-radius:3px;padding:0 2px}
/* ── 체인 표현 ─────────────────────────────────────── */
.chainpill{display:flex;align-items:center;gap:7px;margin-left:auto;font:inherit;font-size:12px;
padding:5px 12px;border-radius:999px;border:1px solid var(--line-2);background:var(--surface);
cursor:pointer;color:var(--ink-2)}
.chainpill:hover{border-color:var(--accent)}
.chainpill b{font-weight:600}
.chainpill .node{width:7px;height:7px;border-radius:50%;background:var(--ok);
box-shadow:0 0 8px rgba(8,116,67,.55)}
.chainpill .link{width:10px;height:2px;background:var(--ok);opacity:.6;border-radius:2px}
.chainpill.bad .node,.chainpill.bad .link{background:var(--high)}
.chainpill .tip{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--muted)}
.chainpill .lock{font-size:11px;color:var(--accent);background:var(--accent-soft);
padding:1px 7px;border-radius:999px}
.topbar .who{margin-left:14px}

.step-link[data-result-open]{cursor:pointer;border-radius:8px;padding-left:8px;
margin-left:-8px;transition:background .14s}
.step-link[data-result-open]:hover{background:var(--accent-soft)}
.step-link[data-result-open] .when{color:var(--accent);font-weight:600}
.chain{display:flex;align-items:stretch;gap:0;overflow-x:auto;padding:4px 0 2px}
.cnode{position:relative;flex:0 0 auto;min-width:78px;padding:9px 11px;margin-right:18px;
border:1px solid var(--line);border-radius:9px;text-align:center;
background:linear-gradient(180deg,#fff,#FBFCFE);box-shadow:0 1px 2px rgba(16,24,40,.06)}
.cnode:last-child{border-color:rgba(67,56,202,.45);box-shadow:var(--glow)}
.cnode:last-child{margin-right:0}
.cnode::after{content:"";position:absolute;right:-18px;top:50%;width:18px;height:2px;
background:var(--chain);transform:translateY(-50%);border-radius:2px}
.cnode:last-child::after{display:none}
.cnode.more{display:flex;align-items:center;color:var(--muted);min-width:34px}
.cidx{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.cver{font-size:12.5px;font-weight:600;margin:1px 0 2px}
.chash{font-family:ui-monospace,Consolas,monospace;font-size:10.5px;color:var(--accent)}

.ledger-card{border-left:3px solid var(--ok);
background:linear-gradient(120deg,rgba(8,116,67,.045),transparent 42%),var(--surface)}
.ledger-card.bad{border-left-color:var(--high)}
.ledger-grid{display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start}
.ledger-grid .k{font-size:11.5px;color:var(--muted)}
.ledger-grid .n{font-size:26px;font-weight:600;line-height:1.2;
font-variant-numeric:tabular-nums;background:var(--chain);-webkit-background-clip:text;background-clip:text;color:transparent}
.ledger-grid .d{font-size:11.5px;color:var(--muted);margin-top:2px}
.tipline{font-size:13px;margin-top:6px;color:var(--accent)}
.badge.ok{background:var(--ins);color:var(--ok)}
.linkcell .arrow2{margin:0 6px;color:var(--accent)}
.tbl tbody tr[data-open]{cursor:pointer}
/* ── 계약 관계망 ───────────────────────────────────── */
.rel-body{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}
.relmap{flex:1 1 520px;min-width:320px;height:auto;overflow:visible}
.rel-side{flex:0 0 232px;min-width:200px}
.rel-side .k{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
color:var(--muted);margin-bottom:8px}
.rel-row{display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:8px;
cursor:pointer;font-size:13px;transition:background .14s}
.rel-row:hover{background:var(--accent-soft)}
.rel-row b{font-weight:600;flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
.rel-row .ev{flex:0 0 auto;font-size:11.5px}
.dotmini{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
.rel-legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;padding-top:10px;
border-top:1px solid var(--line);font-size:11.5px;color:var(--muted)}
.rl{display:flex;align-items:center;gap:6px}
.rl i{width:9px;height:9px;border-radius:3px;display:inline-block}
.rl i.line{width:18px;height:0;border-top:2px solid var(--accent);border-radius:0}
.rl i.line.dashed{border-top-style:dashed}

.rel-edge{transition:opacity .18s,stroke-width .18s}
.rel-node{cursor:pointer}
.rel-node .dot{transition:r .18s,filter .18s}
.rel-node .deg{font-size:11px;font-weight:700;fill:#fff;
font-family:var(--sans);pointer-events:none}
.rel-node .lab{font-size:11.5px;font-weight:600;fill:var(--ink-2);font-family:var(--sans);
pointer-events:none;paint-order:stroke;stroke:#fff;stroke-width:3.5px;stroke-linejoin:round}
.rel-node:hover .dot{filter:drop-shadow(0 4px 12px rgba(67,56,202,.45))}
.relmap.focused .rel-edge{opacity:.12}
.relmap.focused .rel-edge.on{opacity:1;stroke-width:3.4}
.relmap.focused .rel-node{opacity:.28}
.relmap.focused .rel-node.on{opacity:1}
/* A.Biz 회의록 — 실제 호출은 하지 않는다(화면 흐름 시연용) */
.abiz{margin:14px 0 4px;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.abiz-head{display:flex;align-items:center;gap:9px;padding:10px 14px;
background:linear-gradient(90deg,rgba(67,56,202,.06),rgba(14,165,233,.05))}
.abiz-head b{font-size:13.5px}
.abiz-mark{width:22px;height:22px;border-radius:7px;background:var(--chain);color:#fff;
display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}
.abiz-head .mini{margin-left:auto}
.abiz-list{border-top:1px solid var(--line)}
.abiz-item{display:flex;align-items:flex-start;gap:12px;padding:12px 14px;cursor:pointer;
border-bottom:1px solid var(--line);transition:background .14s}
.abiz-item:last-child{border-bottom:0}
.abiz-item:hover{background:var(--accent-soft)}
.abiz-item .who{flex:1 1 auto;min-width:0}
.abiz-item b{display:block;font-size:13.5px;font-weight:600}
.abiz-item .meta{font-size:11.5px;color:var(--muted);margin-top:2px}
.abiz-item .go{flex:0 0 auto;font-size:12px;font-weight:600;color:var(--accent)}

/* 접히는 구획 */
.sec h3 .toggle{margin-left:10px;vertical-align:middle}
.sec-body[hidden]{display:none}
.vrow{cursor:pointer}
.vrow:hover{background:#f8fafc}
.vrow[aria-expanded="true"]{background:var(--accent-soft)}
.vdoc{margin-top:12px;border:1px solid var(--line);border-radius:10px;background:var(--surface);
box-shadow:var(--shadow);overflow:hidden}
.vdoc-head{display:flex;align-items:center;gap:12px;padding:11px 16px;background:#fbfbfc;
border-bottom:1px solid var(--line);font-size:13.5px}
.vdoc-head .ev{margin-left:auto}
.edit-tools{display:flex;gap:6px;align-items:center}
.edit-tools input{font:inherit;font-size:12.5px;padding:5px 10px;border-radius:6px;
border:1px solid var(--line-2);width:150px}
.vdoc[data-editing="1"] .vclause{background:#fbfcff;border-radius:8px;padding:12px}
.vclause [contenteditable="true"]{outline:0;border:1px solid var(--line-2);border-radius:6px;
padding:7px 10px;background:var(--surface)}
.vclause [contenteditable="true"]:focus{border-color:var(--accent);
box-shadow:0 0 0 3px var(--accent-soft)}
.vclause h4[contenteditable="true"]{margin-bottom:7px}
.editstate{display:none;padding:10px 16px;font-size:12.5px;border-bottom:1px solid var(--line)}
.editstate[data-on="1"]{display:block}
.editstate.ok{color:var(--ok)}
.editstate.err{color:var(--high)}
.vdoc-body{max-height:520px;overflow:auto;padding:6px 16px 14px}
.vclause{padding:12px 0;border-bottom:1px solid var(--line)}
.vclause:last-child{border-bottom:0}
.vclause h4{margin:0 0 5px;font-size:13.5px;font-weight:600;color:var(--accent)}
.vclause p{margin:0;font-size:13px;line-height:1.75;color:var(--ink-2);white-space:pre-wrap}
.upload-card .card{padding:18px 20px}
.frow{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.frow label{display:flex;flex-direction:column;gap:5px;flex:1 1 220px;font-size:12px;
font-weight:600;color:var(--muted)}
.frow input{font:inherit;font-size:13.5px;font-weight:400;color:var(--ink);padding:8px 12px;
border-radius:8px;border:1px solid var(--line-2);background:var(--surface)}
.frow input:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.fhint{font-size:11.5px;font-weight:400;color:var(--muted);line-height:1.5}
.fhint code{background:#f2f4f7;padding:1px 5px;border-radius:4px}
.upload-card input[type="file"]{color:var(--muted)}
.upstate{font-size:12.5px;margin-top:10px;display:none}
.upstate[data-on="1"]{display:block}
.upstate.ok{color:var(--ok)}
.upstate.err{color:var(--high)}
.upstate code{display:block;margin-top:6px;font-family:ui-monospace,Consolas,monospace;
font-size:11.5px;background:#f7f8fa;border:1px solid var(--line);border-radius:6px;
padding:7px 10px;color:var(--ink-2);white-space:pre-wrap;word-break:break-all}
.filters .chip{padding:5px 12px}

/* ── 당사자 관리 ───────────────────────────────────── */
.party-tbl input{font:inherit;font-size:13px;padding:6px 9px;border-radius:6px;
border:1px solid var(--line-2);background:var(--surface);color:var(--ink);width:100%}
.party-tbl input:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.party-tbl tr[data-hidden="1"]{display:none}
.removed{display:none;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px;padding-top:12px;
border-top:1px dashed var(--line-2)}
.removed[data-on="1"]{display:flex}
.removed .lb{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
color:var(--muted)}
.removed button{font:inherit;font-size:12px;padding:4px 10px;border-radius:999px;
border:1px dashed var(--line-2);background:var(--surface);color:var(--muted);cursor:pointer}
.removed button:hover{border-style:solid;border-color:var(--accent);color:var(--accent)}
.party-tbl td{padding:9px 12px}
.mini{font:inherit;font-size:12px;font-weight:600;padding:5px 11px;border-radius:6px;
border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);cursor:pointer;
white-space:nowrap;transition:all .14s}
.mini:hover{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.mini.danger:hover{border-color:var(--high);color:var(--high);background:var(--del)}
.mini.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.mini.primary:hover{background:#123c8f;color:#fff}
.addrow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px;
padding-top:12px;border-top:1px dashed var(--line-2)}
.addrow input{font:inherit;font-size:13px;padding:7px 11px;border-radius:7px;
border:1px solid var(--line-2);background:var(--surface);min-width:120px;flex:1 1 130px}
.notice{display:none;align-items:flex-start;gap:10px;margin-top:12px;padding:11px 14px;
border-radius:8px;background:#fff8ec;border:1px solid #f0dcb8;color:#7c5514;font-size:12.5px}
.notice[data-on="1"]{display:flex}
.notice code{display:block;margin-top:6px;font-family:ui-monospace,Consolas,monospace;
font-size:11.5px;color:#5a3d0c;background:#fdf1dc;padding:6px 9px;border-radius:5px;
white-space:pre-wrap;word-break:break-all}

/* ── 시각 효과 ─────────────────────────────────────── */


.brand .mark{background:var(--chain);box-shadow:0 6px 18px rgba(67,56,202,.45)}



.topbar{background:rgba(255,255,255,.82);backdrop-filter:saturate(180%) blur(12px);
-webkit-backdrop-filter:saturate(180%) blur(12px)}
.kpi{position:relative;overflow:hidden;transition:transform .16s,box-shadow .16s}
.kpi::before{content:"";position:absolute;inset:0 0 auto;height:2px;
background:var(--chain)}
.kpi:nth-child(4)::before{background:linear-gradient(90deg,#b42318,#f97066)}
.kpi:hover{transform:translateY(-2px);box-shadow:var(--glow)}
.card,.tbl{transition:box-shadow .18s}
.card:hover,.tbl:hover{box-shadow:0 6px 20px rgba(16,24,40,.07)}
.tbl tbody tr[data-open],.tbl tbody tr[data-result-open]{position:relative;
transition:background .14s}
.tbl tbody tr[data-open]:hover,.tbl tbody tr[data-result-open]:hover{
box-shadow:inset 3px 0 0 var(--accent)}
.dist .bar i{background:var(--chain);
animation:grow .7s cubic-bezier(.22,1,.36,1) both}
@keyframes grow{from{width:0 !important}}
.view:not([hidden]){animation:enter .28s cubic-bezier(.22,1,.36,1) both}
@keyframes enter{from{opacity:0;transform:translateY(6px)}}
.feed .it{transition:background .14s;border-radius:6px}
.feed .it:hover{background:#f8fafc}
.badge.high{box-shadow:0 0 0 1px rgba(180,35,24,.14)}
.badge.latest{background:var(--chain);color:#fff}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:#d5dae2;border-radius:6px;border:3px solid var(--canvas)}
::-webkit-scrollbar-thumb:hover{background:#b9c0cc}
"""

_APP_JS = r"""
(function(){
  // data-view는 결과 패널의 보기 전환 칩도 쓰므로, 앱 화면은 전용 속성을 쓴다.
  var views = {};
  document.querySelectorAll('[data-app-view]').forEach(function(v){
    views[v.dataset.appView] = v;
  });
  var navButtons = document.querySelectorAll('.tabs button[data-goto]');
  var path = document.querySelector('.js-path');
  var switchedAt = 0;

  function settling(){ return Date.now() - switchedAt < 350; }

  function crumbs(items){
    if (!path) return;
    path.innerHTML = '';
    items.forEach(function(item, i){
      if (i) {
        var sep = document.createElement('span');
        sep.className = 'sep'; sep.textContent = '/';
        path.appendChild(sep);
      }
      var node;
      if (item.go) {
        node = document.createElement('button');
        node.textContent = item.label;
        node.addEventListener('click', function(){ item.go(); });
      } else {
        node = document.createElement('b');
        node.textContent = item.label;
      }
      path.appendChild(node);
    });
  }

  function show(name){
    Object.keys(views).forEach(function(key){ views[key].hidden = (key !== name); });
    navButtons.forEach(function(b){
      b.setAttribute('aria-current', String(b.dataset.goto === name));
    });
    switchedAt = Date.now();
    window.scrollTo(0, 0);
  }

  function tell(view){ if (window.checkyView) window.checkyView(view); }
  function goDashboard(){ show('dashboard'); crumbs([{label:'현황관리'}]); tell('dashboard'); }
  function goContracts(){ show('contracts'); crumbs([{label:'계약상세'}]); tell('contracts'); }
  function goCreate(){ show('create'); crumbs([{label:'계약생성'}]); tell('create'); }
  function goCustomers(){ show('customers'); crumbs([{label:'고객관리'}]); tell('customers'); }
  function goSearch(){ show('search'); crumbs([{label:'조항검색'}]); tell('search'); }
  function goLedger(){ show('ledger'); crumbs([{label:'원장'}]); tell('ledger'); }

  function goDetail(id, title){
    document.querySelectorAll('[data-detail]').forEach(function(el){
      el.hidden = (el.dataset.detail !== id);
    });
    show('detail');
    crumbs([{label:'계약상세', go:goContracts}, {label:title}]);
    tell('detail');
  }

  function goResult(key, contractId, contractTitle, label){
    document.querySelectorAll('[data-result]').forEach(function(el){
      el.hidden = (el.dataset.result !== key);
    });
    show('result');
    tell('result');
    crumbs([
      {label:'계약상세', go:goContracts},
      {label:contractTitle, go:function(){ goDetail(contractId, contractTitle); }},
      {label:label}
    ]);
  }

  var routes = {
    dashboard: goDashboard,
    contracts: goContracts,
    create: goCreate,
    customers: goCustomers,
    search: goSearch,
    ledger: goLedger
  };
  navButtons.forEach(function(btn){
    btn.addEventListener('click', function(){
      (routes[btn.dataset.goto] || goDashboard)();
    });
  });

  document.querySelectorAll('[data-goto-view]').forEach(function(el){
    el.addEventListener('click', function(){
      (routes[el.dataset.gotoView] || goDashboard)();
    });
  });

  // 관계망 — 노드에 올리면 그 계약과 이어진 것만 남긴다.
  document.querySelectorAll('.relmap').forEach(function(map){
    var nodes = map.querySelectorAll('.rel-node');
    var edges = map.querySelectorAll('.rel-edge');

    function focus(index){
      map.classList.add('focused');
      var neighbours = {};
      neighbours[index] = true;
      edges.forEach(function(edge){
        var a = edge.dataset.a, b = edge.dataset.b;
        var touches = (a === index || b === index);
        edge.classList.toggle('on', touches);
        if (touches) { neighbours[a] = true; neighbours[b] = true; }
      });
      nodes.forEach(function(node){
        node.classList.toggle('on', !!neighbours[node.dataset.node]);
      });
    }
    function clear(){
      map.classList.remove('focused');
      edges.forEach(function(e){ e.classList.remove('on'); });
      nodes.forEach(function(n){ n.classList.remove('on'); });
    }

    nodes.forEach(function(node){
      node.addEventListener('mouseenter', function(){ focus(node.dataset.node); });
      node.addEventListener('mouseleave', clear);
    });
  });

  document.querySelectorAll('[data-open]').forEach(function(row){
    row.addEventListener('click', function(){
      if (settling()) return;
      goDetail(row.dataset.open, row.dataset.title);
    });
  });

  document.querySelectorAll('[data-result-open]').forEach(function(row){
    row.addEventListener('click', function(){
      if (settling()) return;
      goResult(row.dataset.resultOpen, row.dataset.contract, row.dataset.contractTitle,
               row.dataset.label);
      var panel = document.querySelector('[data-result="' + row.dataset.resultOpen + '"]');
      var flagged = panel ? panel.querySelectorAll('.clause[data-flagged="1"]').length : 0;
      if (window.checky) {
        if (flagged) {
          window.checky.say('<b>' + flagged + '개 조항</b>을 짚어 뒀어요. 위에서부터 보시면 돼요.',
                            'alert', 9000);
        } else {
          window.checky.say('걸리는 조항은 없었어요.', 'ok', 9000);
        }
      }
    });
  });

  // 계약 목록의 분류 필터 + 검색
  var rows = document.querySelectorAll('.js-contract-row');
  var state = {cat:'all', status:'all', q:''};
  function refresh(){
    var n = 0;
    rows.forEach(function(row){
      var ok = (state.cat === 'all' || row.dataset.category === state.cat)
        && (state.status === 'all' || row.dataset.status === state.status)
        && (state.q === '' || (row.dataset.search||'').indexOf(state.q) >= 0);
      row.style.display = ok ? '' : 'none';
      if (ok) n++;
    });
    var count = document.querySelector('.js-contract-count');
    if (count) count.textContent = n;
  }
  document.querySelectorAll('.js-cat').forEach(function(chip){
    chip.addEventListener('click', function(){
      document.querySelectorAll('.js-cat').forEach(function(c){
        c.setAttribute('aria-pressed', String(c === chip));
      });
      state.cat = chip.dataset.value;
      refresh();
    });
  });
  document.querySelectorAll('.js-status').forEach(function(chip){
    chip.addEventListener('click', function(){
      document.querySelectorAll('.js-status').forEach(function(c){
        c.setAttribute('aria-pressed', String(c === chip));
      });
      state.status = chip.dataset.value;
      refresh();
    });
  });

  // 현황 카드를 누르면 그 단계만 걸러 계약 목록으로 넘어간다.
  document.querySelectorAll('[data-status-filter]').forEach(function(card){
    card.addEventListener('click', function(){
      var value = card.dataset.statusFilter;
      document.querySelectorAll('.js-status').forEach(function(c){
        c.setAttribute('aria-pressed', String(c.dataset.value === value));
      });
      state.status = value;
      refresh();
      goContracts();
    });
  });

  var search = document.querySelector('.js-contract-search');
  if (search) {
    search.addEventListener('input', function(){
      state.q = search.value.trim().toLowerCase();
      refresh();
    });
  }
  refresh();

  // ── 버전 원문 펼치기 ──────────────────────────────
  document.querySelectorAll('.vrow').forEach(function(row){
    row.addEventListener('click', function(){
      var detail = row.closest('[data-detail]');
      var target = detail.querySelector('[data-version-doc="' + row.dataset.version + '"]');
      if (!target) return;
      if (target.dataset.editing === '1') return;
      var opening = target.hidden;
      detail.querySelectorAll('[data-version-doc]').forEach(function(el){ el.hidden = true; });
      detail.querySelectorAll('.vrow').forEach(function(r){ r.setAttribute('aria-expanded','false'); });
      target.hidden = !opening;
      row.setAttribute('aria-expanded', String(opening));
      if (opening) target.scrollIntoView({block:'nearest', behavior:'smooth'});
    });
  });
  // 조문 편집 — 저장하면 다음 버전으로 쌓인다(원본은 건드리지 않는다).
  document.querySelectorAll('.vdoc').forEach(function(doc){
    var tools = doc.querySelector('.edit-tools');
    var label = doc.querySelector('[data-edit="label"]');
    var state = doc.querySelector('[data-editstate]');
    var btnEdit = tools.querySelector('[data-act="edit"]');
    var btnSave = tools.querySelector('[data-act="save-edit"]');
    var btnCancel = tools.querySelector('[data-act="cancel-edit"]');
    var original = null;

    function setMode(on){
      doc.dataset.editing = on ? '1' : '0';
      doc.querySelectorAll('[data-field]').forEach(function(el){
        el.setAttribute('contenteditable', String(on));
      });
      [label, btnSave, btnCancel].forEach(function(el){ el.hidden = !on; });
      btnEdit.hidden = on;
    }
    function say(kind, message){
      state.className = 'editstate ' + kind;
      state.dataset.on = '1';
      state.textContent = message;
    }

    btnEdit.addEventListener('click', function(ev){
      ev.stopPropagation();
      original = doc.querySelector('.vdoc-body').innerHTML;
      setMode(true);
      say('', '조문을 고친 뒤 새 버전으로 저장하십시오. 등록된 원본은 그대로 보존됩니다.');
    });

    btnCancel.addEventListener('click', function(ev){
      ev.stopPropagation();
      if (original !== null) doc.querySelector('.vdoc-body').innerHTML = original;
      setMode(false);
      state.dataset.on = '0';
    });

    btnSave.addEventListener('click', function(ev){
      ev.stopPropagation();
      if (!live) {
        say('err', '저장은 서버 모드에서 동작합니다. 터미널에서 contract-review serve 를 실행하십시오.');
        return;
      }
      var clauses = Array.prototype.map.call(doc.querySelectorAll('[data-clause]'), function(el){
        return {
          heading: el.querySelector('[data-field="heading"]').innerText.trim(),
          body: el.querySelector('[data-field="body"]').innerText.trim()
        };
      });
      say('', '저장 중…');
      fetch('/api/edit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          contract_id: doc.dataset.contract,
          base_version: doc.dataset.versionDoc,
          label: label.value.trim(),
          clauses: clauses
        })
      }).then(function(r){ return r.json(); }).then(function(res){
        if (!res.ok) { say('err', res.error || '저장에 실패했습니다.'); return; }
        say('ok', res.version + ' ' + res.label + ' 으로 저장했습니다. 검토를 다시 계산합니다…');
        setTimeout(function(){ location.reload(); }, 700);
      }).catch(function(err){ say('err', String(err)); });
    });
  });

  document.querySelectorAll('[data-act="close-doc"]').forEach(function(btn){
    btn.addEventListener('click', function(ev){
      ev.stopPropagation();
      btn.closest('[data-version-doc]').hidden = true;
    });
  });

  // 회의 반영 — 회의록을 조문 수정안으로 옮기고, 채택분만 새 버전으로 저장한다.
  document.querySelectorAll('[data-meeting]').forEach(function(box){
    var contractId = box.dataset.meeting;
    var state = box.querySelector('[data-mtstate]');
    var list = box.querySelector('[data-proposals]');
    var btnApply = box.querySelector('[data-act="apply-meeting"]');
    var clauses = null;

    function get(name){ return box.querySelector('[data-mt="' + name + '"]').value.trim(); }
    function say(kind, message){
      state.className = 'mtstate ' + kind;
      state.textContent = message;
    }

    box.querySelector('[data-act="analyze"]').addEventListener('click', function(){
      var minutes = get('minutes');
      if (!minutes) { say('err', '회의 내용을 입력하십시오.'); return; }
      if (!live) {
        say('err', '회의 반영은 서버 모드에서 동작합니다.');
        return;
      }
      say('', '조문을 찾는 중…');
      if (window.checky) window.checky.say('회의 내용을 조문에 맞춰 보고 있어요…', 'scanning', 20000);
      list.innerHTML = '';
      btnApply.hidden = true;

      fetch('/api/meeting', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          contract_id: contractId, version: get('version'), minutes: minutes
        })
      }).then(function(r){ return r.json(); }).then(function(res){
        if (!res.ok) { say('err', res.error || '분석에 실패했습니다.'); return; }
        clauses = res.clauses;
        if (!res.proposals.length) {
          say('err', '회의 내용과 연결되는 조문을 찾지 못했습니다. 조 번호를 함께 적어 보십시오.');
          return;
        }
        res.proposals.forEach(function(p){
          var el = document.createElement('div');
          el.className = 'prop';
          el.dataset.heading = p.heading;
          el.innerHTML =
            '<div class="prop-head"><b></b>' +
            '<span class="badge">' + (p.changed ? '수정 제안' : '검토 필요') + '</span>' +
            '<label><input type="checkbox" data-adopt' + (p.changed ? ' checked' : '') +
            '> 채택</label></div>' +
            '<div class="prop-body"><div class="basis"></div>' +
            '<div class="cols2"><div><span class="lbl">현재 문안</span>' +
            '<textarea rows="5" readonly></textarea></div>' +
            '<div><span class="lbl">수정안</span>' +
            '<textarea rows="5" data-revised></textarea></div></div>' +
            '<div class="note"></div></div>';
          el.querySelector('b').textContent = p.heading;
          el.querySelector('.basis').innerHTML = p.items.map(function(i){
            var d = document.createElement('div');
            d.textContent = '· ' + i;
            return d.outerHTML;
          }).join('');
          el.querySelectorAll('textarea')[0].value = p.current;
          el.querySelector('[data-revised]').value = p.proposed || p.current;
          el.querySelector('.note').textContent =
            (p.note || '') + (p.source ? '  (' + p.source + ')' : '');
          list.appendChild(el);
        });
        var extra = res.unmatched.length
          ? ' · 연결하지 못한 항목 ' + res.unmatched.length + '건' : '';
        say('ok', res.proposals.length + '개 조문에 반영안을 만들었습니다.' + extra);
        if (window.checky) {
          window.checky.say('<b>' + res.proposals.length + '개 조문</b>에 반영안을 만들었어요.'
            + (res.unmatched.length ? ' ' + res.unmatched.length + '건은 조문을 못 찾았어요.' : ''),
            res.unmatched.length ? 'alert' : 'ok', 12000);
        }
        btnApply.hidden = false;
      }).catch(function(err){ say('err', String(err)); });
    });

    btnApply.addEventListener('click', function(){
      if (!clauses) return;
      var adopted = {};
      list.querySelectorAll('.prop').forEach(function(el){
        if (el.querySelector('[data-adopt]').checked) {
          adopted[el.dataset.heading] = el.querySelector('[data-revised]').value.trim();
        }
      });
      if (!Object.keys(adopted).length) { say('err', '채택할 조문을 선택하십시오.'); return; }

      var merged = clauses.map(function(c){
        var body = adopted[c.heading] !== undefined ? adopted[c.heading] : c.body;
        return {heading: c.heading, body: body};
      });
      say('', '저장 중…');
      if (window.checky) window.checky.say('새 버전으로 저장하고 있어요…', 'scanning', 20000);
      fetch('/api/edit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          contract_id: contractId,
          base_version: get('version'),
          label: get('label') || '회의 반영본',
          note: '회의 반영 · ' + Object.keys(adopted).length + '개 조문',
          clauses: merged
        })
      }).then(function(r){ return r.json(); }).then(function(res){
        if (!res.ok) { say('err', res.error || '저장에 실패했습니다.'); return; }
        say('ok', res.version + ' ' + res.label + ' 으로 저장했습니다. 검토를 다시 계산합니다…');
        setTimeout(function(){ location.reload(); }, 700);
      }).catch(function(err){ say('err', String(err)); });
    });
  });

  // 조항검색 — 계약을 가로질러 조문을 찾는다.
  var hits = document.querySelectorAll('.hit');
  var hitCount = document.querySelector('.js-hit-count');
  var searchEmpty = document.querySelector('.js-search-empty');
  var clauseSearch = document.querySelector('.js-clause-search');
  var scope = 'latest';

  if (clauseSearch) {
    // 원문을 보관해 두고 강조할 때마다 여기서 다시 그린다.
    hits.forEach(function(el){
      var body = el.querySelector('p');
      body.dataset.plain = body.textContent;
    });

    function highlight(el, terms){
      var body = el.querySelector('p');
      var text = body.dataset.plain;
      if (!terms.length) { body.textContent = text; return; }
      var pattern = terms.map(function(term){
        return term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      }).join('|');
      body.innerHTML = '';
      var re = new RegExp(pattern, 'gi');
      var last = 0, match;
      while ((match = re.exec(text)) !== null) {
        body.appendChild(document.createTextNode(text.slice(last, match.index)));
        var mark = document.createElement('mark');
        mark.textContent = match[0];
        body.appendChild(mark);
        last = match.index + match[0].length;
        if (match[0] === '') re.lastIndex++;
      }
      body.appendChild(document.createTextNode(text.slice(last)));
    }

    function runSearch(){
      // 띄어 쓴 단어는 모두 포함(AND)으로 본다. '국외 이전'이 '국외로 이전한'을
      // 놓치던 문제를 없앤다.
      var terms = clauseSearch.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      var enough = terms.join('').length >= 2;
      var shown = 0, hiddenByScope = 0;

      hits.forEach(function(el){
        var blob = el.dataset.search || '';
        var matched = enough && terms.every(function(term){ return blob.indexOf(term) >= 0; });
        var inScope = scope === 'all' || el.dataset.latest === '1';
        var ok = matched && inScope;
        el.hidden = !ok;
        if (ok) { shown++; highlight(el, terms); }
        else if (matched && !inScope) hiddenByScope++;
      });

      hitCount.textContent = shown;
      if (!enough) {
        searchEmpty.textContent =
          '찾을 문구를 입력하십시오. 여러 단어를 띄어 쓰면 모두 포함된 조문을 찾습니다.';
      } else if (shown) {
        searchEmpty.textContent = '';
      } else if (hiddenByScope) {
        searchEmpty.textContent =
          '최신 버전에는 없습니다. 이전 버전 포함으로 보면 ' + hiddenByScope + '건이 있습니다.';
      } else {
        searchEmpty.textContent = '일치하는 조문이 없습니다.';
      }
      searchEmpty.style.display = searchEmpty.textContent ? '' : 'none';
    }

    clauseSearch.addEventListener('input', runSearch);
    document.querySelectorAll('.js-scope').forEach(function(chip){
      chip.addEventListener('click', function(){
        document.querySelectorAll('.js-scope').forEach(function(c){
          c.setAttribute('aria-pressed', String(c === chip));
        });
        scope = chip.dataset.scope;
        runSearch();
      });
    });
  }

  // 접히는 구획 — 등록 원장처럼 늘 볼 필요는 없는 것들
  document.querySelectorAll('[data-collapsible]').forEach(function(sec){
    var button = sec.querySelector('[data-act="toggle-sec"]');
    var body = sec.querySelector('.sec-body');
    if (!button || !body) return;
    button.addEventListener('click', function(){
      var opening = body.hidden;
      body.hidden = !opening;
      button.textContent = opening ? '접기' : '펼치기';
      button.setAttribute('aria-expanded', String(opening));
    });
  });

  // A.Biz 회의록 — 목록을 받아 고르면 회의 내용이 채워지고 바로 분석까지 간다.
  document.querySelectorAll('[data-meeting]').forEach(function(box){
    var loadBtn = box.querySelector('[data-act="load-meetings"]');
    var list = box.querySelector('[data-abiz-list]');
    if (!loadBtn || !list) return;
    var contractId = box.dataset.meeting;

    loadBtn.addEventListener('click', function(){
      if (!live) {
        list.hidden = false;
        list.innerHTML = '<div class="abiz-item"><div class="who">' +
          '<b>서버 모드에서 동작합니다</b><div class="meta">' +
          'contract-review serve 를 실행하십시오.</div></div></div>';
        return;
      }
      loadBtn.textContent = '불러오는 중…';
      var version = box.querySelector('[data-mt="version"]').value;
      fetch('/api/meetings?contract=' + encodeURIComponent(contractId) +
            '&version=' + encodeURIComponent(version))
        .then(function(r){ return r.json(); })
        .then(function(res){
          loadBtn.textContent = '다시 불러오기';
          list.hidden = false;
          if (!res.ok || !res.meetings.length) {
            list.innerHTML = '<div class="abiz-item"><div class="who"><b>회의록이 없습니다</b>' +
              '<div class="meta">' + (res.error || '연결된 회의가 없습니다.') +
              '</div></div></div>';
            return;
          }
          list.innerHTML = '';
          res.meetings.forEach(function(meeting){
            var row = document.createElement('div');
            row.className = 'abiz-item';
            row.innerHTML = '<div class="who"><b></b><div class="meta"></div></div>' +
              '<span class="go">반영하기 →</span>';
            row.querySelector('b').textContent = meeting.title;
            row.querySelector('.meta').textContent =
              meeting.at + ' · ' + meeting.attendees;
            row.addEventListener('click', function(){
              box.querySelector('[data-mt="minutes"]').value = meeting.minutes;
              var label = box.querySelector('[data-mt="label"]');
              if (!label.value) label.value = meeting.title + ' 반영';
              list.hidden = true;
              if (window.checky) {
                window.checky.say('회의록을 가져왔어요. 조문을 찾아볼게요.', 'scanning', 12000);
              }
              box.querySelector('[data-act="analyze"]').click();
            });
            list.appendChild(row);
          });
        })
        .catch(function(err){
          loadBtn.textContent = '회의록 불러오기';
          list.hidden = false;
          list.innerHTML = '<div class="abiz-item"><div class="who"><b>불러오지 못했습니다</b>' +
            '<div class="meta">' + String(err) + '</div></div></div>';
        });
    });
  });

  // ── 업로드 / 내려받기 ─────────────────────────────
  var live = location.protocol === 'http:' || location.protocol === 'https:';

  function q(params){
    return Object.keys(params)
      .filter(function(k){ return params[k]; })
      .map(function(k){ return k + '=' + encodeURIComponent(params[k]); })
      .join('&');
  }

  document.querySelectorAll('[data-dl]').forEach(function(btn){
    btn.addEventListener('click', function(ev){
      ev.stopPropagation();
      var params = {
        contract: btn.dataset.contract,
        from: btn.dataset.from || 'first',
        to: btn.dataset.to || 'latest',
        format: btn.dataset.dl
      };
      if (live) { window.location = '/api/download?' + q(params); return; }
      alert('내려받기는 서버 모드에서 동작합니다. 터미널에서 contract-review serve 를 실행하십시오. '
            + '또는 contract-review review --contract ' + params.contract
            + ' --from ' + params.from + ' --to ' + params.to
            + ' --format ' + params.format);
    });
  });

  document.querySelectorAll('[data-template]').forEach(function(btn){
    btn.addEventListener('click', function(){
      if (live) { window.location = '/api/template?id=' + btn.dataset.template; return; }
      alert('양식 내려받기는 서버 모드에서 동작합니다. '
            + 'data/templates 폴더의 원본을 직접 열 수도 있습니다.');
    });
  });

  document.querySelectorAll('[data-export]').forEach(function(btn){
    btn.addEventListener('click', function(){
      if (live) { window.location = '/api/export?kind=' + btn.dataset.export; return; }
      alert('대장 내려받기는 서버 모드에서 동작합니다. '
            + '터미널에서 contract-review workspace --export csv 를 실행하십시오.');
    });
  });

  document.querySelectorAll('[data-uploader]').forEach(function(box){
    var state = box.querySelector('[data-upstate]');
    function say(kind, message, command){
      state.className = 'upstate ' + kind;
      state.dataset.on = '1';
      state.textContent = message;
      if (command) {
        var code = document.createElement('code');
        code.textContent = command;
        state.appendChild(code);
      }
    }

    box.querySelector('[data-act="upload"]').addEventListener('click', function(){
      var get = function(name){
        var el = box.querySelector('[data-up="' + name + '"]');
        return el ? el.value.trim() : '';
      };
      var input = box.querySelector('[data-up="files"]');
      var contractId = get('contract_id');
      if (!contractId) { say('err', '계약 ID를 입력하십시오.'); return; }
      if (!input.files.length) { say('err', '올릴 파일을 선택하십시오.'); return; }
      var wrong = Array.prototype.filter.call(input.files, function(f){
        return !/\.(hwp|hwpx|docx|pdf)$/i.test(f.name);
      });
      if (wrong.length) {
        say('err', '한글(.hwp/.hwpx), Word(.docx), PDF만 올릴 수 있습니다: ' +
            wrong.map(function(f){ return f.name; }).join(', '));
        return;
      }

      var names = Array.prototype.map.call(input.files, function(f){ return f.name; });
      if (!live) {
        say('err', '업로드는 서버 모드에서 동작합니다. 아래 명령으로 같은 작업을 할 수 있습니다.',
            'contract-review attach ' + contractId + ' ' + names.join(' '));
        return;
      }

      var form = new FormData();
      form.append('contract_id', contractId);
      ['title','category','labels','parties','note'].forEach(function(f){
        if (get(f)) form.append(f, get(f));
      });
      Array.prototype.forEach.call(input.files, function(f){ form.append('files', f); });

      say('', '업로드 중…');
      if (window.checky) window.checky.say('파일을 읽고 있어요…', 'scanning', 20000);
      fetch('/api/upload', {method:'POST', body: form})
        .then(function(r){ return r.json(); })
        .then(function(res){
          if (!res.ok) { say('err', res.error || '업로드에 실패했습니다.'); return; }
          var added = res.added.map(function(a){ return a.version + ' ' + a.label; }).join(', ');
          say('ok', added + ' 등록됨. 검토를 다시 계산합니다…');
          if (window.checky) window.checky.say(added + ' 등록했어요. 바로 검토할게요!', 'ok', 9000);
          setTimeout(function(){ location.reload(); }, 700);
        })
        .catch(function(err){ say('err', String(err)); });
    });
  });

  goDashboard();
})();
"""


@dataclass
class ContractEntry:
    """워크스페이스가 다루는 계약 하나."""

    contract_id: str
    title: str = ""
    category: str = "미분류"
    versions: list[VersionRecord] = field(default_factory=list)
    timeline: list[TimelineStep] = field(default_factory=list)
    results: list[ReviewResult] = field(default_factory=list)
    deadline: Deadline = field(default_factory=Deadline)
    chain: list = field(default_factory=list)
    """이 계약의 원장 블록."""

    encrypted: bool = False
    """원본이 암호화돼 보관되는지."""
    texts: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    """버전별 조문 원문 — {버전: [(조문 제목, 본문), …]}."""

    @property
    def label(self) -> str:
        return self.title or self.contract_id

    @property
    def flagged(self) -> int:
        """쟁점 신호가 붙은 조문 수(비교본 전체 합계)."""
        return sum(1 for r in self.results for c in r.changed() if c.flags)

    @property
    def issues(self) -> int:
        return sum(len(c.flags) for r in self.results for c in r.changed())

    # 이전 이름 — 호출부 정리 전까지 유지
    @property
    def high(self) -> int:
        return self.flagged

    status_override: str = ""
    """수동 지정 상태(started/ongoing/done). 비어 있으면 버전 이력에서 추론한다."""

    @property
    def status(self) -> str:
        """개시 → 진행중 → 완료.

        초안만 올라온 계약은 '개시', 상대방과 주고받는 중이면 '진행중',
        마지막 버전 라벨이 최종본·날인본이면 '완료'로 본다. 라벨만으로 판단이
        어려운 계약은 manifest의 status로 직접 지정할 수 있다.
        """
        if self.status_override in STATUS_ORDER:
            return self.status_override
        if len(self.versions) <= 1:
            return "started"
        label = self.versions[-1].label
        return "done" if any(hint in label for hint in _FINAL_HINTS) else "ongoing"

    @property
    def status_label(self) -> str:
        return STATUS_LABEL[self.status]

    @property
    def rounds(self) -> int:
        """협상 왕복 횟수 = 버전 수 - 1."""
        return max(len(self.versions) - 1, 0)

    @property
    def latest(self) -> str:
        return self.versions[-1].version if self.versions else "-"

    @property
    def updated_at(self) -> str:
        return self.versions[-1].imported_at if self.versions else ""

    @property
    def parties(self) -> list[str]:
        for result in self.results:
            if result.parties:
                return [p.alias for p in result.parties]
        return []


def render_workspace(entries: list[ContractEntry], integrity=None, blocks=None) -> str:
    """integrity: ledger.Verification, blocks: 원장 블록 전체(원장 화면용)."""
    blocks = blocks or []
    present = {e.category for e in entries}
    categories = [c for c in CATEGORY_ORDER if c in present]
    categories += sorted(present - set(CATEGORY_ORDER))
    total_versions = sum(len(e.versions) for e in entries)
    total_high = sum(e.flagged for e in entries)
    total_changes = sum(step.total for e in entries for step in e.timeline)

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{BRAND} · {TAGLINE}</title>
<style>{BASE_CSS}{_CSS}{CHECKY_CSS}</style></head>
<body>
<div class="app">
<header class="appbar">
  <div class="appbar-inner">
    <button class="brand" data-goto-view="dashboard" title="현황관리로">
      {brand_markup(30)}
      <div>
        <div class="name">{BRAND}</div>
        <div class="tag">{TAGLINE}</div>
      </div>
    </button>
    <nav class="tabs">
      <button data-goto="dashboard" aria-current="true">현황관리</button>
      <button data-goto="contracts">계약상세<span class="cnt">{len(entries)}</span></button>
      <button data-goto="create">계약생성</button>
      <button data-goto="customers">고객관리<span class="cnt">{_party_total(entries)}</span></button>
      <button data-goto="search">조항검색</button>
      <button data-goto="ledger">원장<span class="cnt">{len(blocks)}</span></button>
    </nav>
    <div class="appbar-right">
      {_integrity_pill(integrity, entries)}
      <div class="who"><span>{_e(USER_NAME)}</span><div class="av">{_e(USER_NAME[:1])}</div></div>
    </div>
  </div>
</header>

<div class="main">
<div class="topbar">
  <div class="path js-path"></div>
  <div class="shellinfo">계약 {len(entries)}건 · 버전 {total_versions}개
    {_vault_badge(entries, integrity)}</div>
</div>

<div class="view" data-app-view="dashboard">
{_dashboard(entries, total_versions, total_high, total_changes, blocks, integrity)}
</div>

<div class="view" data-app-view="contracts" hidden>
{_contracts_view(entries, categories)}
</div>

<div class="view" data-app-view="create" hidden>
{_create_view()}
</div>

<div class="view" data-app-view="customers" hidden>
{_customers_view(entries)}
</div>

<div class="view" data-app-view="search" hidden>
{_search_view(entries)}
</div>

<div class="view" data-app-view="ledger" hidden>
{_ledger_view(blocks, integrity, entries)}
</div>

<div class="view" data-app-view="detail" hidden>
{"".join(_detail_view(e, i) for i, e in enumerate(entries))}
</div>

<div class="view" data-app-view="result" hidden>
{"".join(_result_panels(entries))}
</div>

<div class="view-foot" style="padding:0 28px 40px">
  <div class="disclaimer">{_e(DISCLAIMER)}</div>
</div>
</div></div>
{buddy_markup()}
<script>{PANEL_JS}</script>
<script>{CHECKY_JS}</script>
<script>{_APP_JS}</script>
</body></html>"""


# ---------------------------------------------------------------- 대시보드


def _dashboard(
    entries,
    total_versions: int,
    total_high: int,
    total_changes: int,
    blocks=None,
    integrity=None,
) -> str:
    negotiating = sum(1 for e in entries if len(e.versions) > 1)
    kpis = [
        ("관리 계약", len(entries), f"분류 {len({e.category for e in entries})}종", ""),
        ("등록 버전", total_versions, f"협상 진행 {negotiating}건", ""),
        ("누적 변경 조문", total_changes, "버전 간 합계", ""),
        ("검토 대상 조문", total_high, "쟁점 신호 탐지", "high"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="k">{_e(k)}</div>'
        f'<div class="n {cls}">{v}</div><div class="d">{_e(d)}</div></div>'
        for k, v, d, cls in kpis
    )

    by_category: dict[str, int] = {}
    for entry in entries:
        by_category[entry.category] = by_category.get(entry.category, 0) + 1
    top = max(by_category.values(), default=1)
    dist = "".join(
        f'<div class="row"><span>{_e(name)}</span>'
        f'<span class="bar"><i style="width:{int(100 * count / top)}%"></i></span>'
        f'<span class="v">{count}</span></div>'
        for name, count in sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))
    ) or '<div class="ev">등록된 계약이 없습니다.</div>'

    activity = []
    for entry in entries:
        for record, step in zip(entry.versions[1:], entry.timeline, strict=False):
            activity.append((record.imported_at, entry, record, step))
    activity.sort(key=lambda item: item[0], reverse=True)

    feed = "".join(
        f'<div class="it"><div class="when">{_e(when[:10])}</div>'
        f'<div class="what"><b>{_e(entry.label)}</b> · {_e(record.version)} {_e(record.label)}'
        f'<div class="meta">수정 {step.modified} · 신설 {step.added} · 삭제 {step.deleted}'
        + (f" · 쟁점 {step.flagged}" if step.flagged else "")
        + (f" — {_e(record.note)}" if record.note else "")
        + "</div></div></div>"
        for when, entry, record, step in activity[:8]
    ) or '<div class="ev">기록된 개정 활동이 없습니다.</div>'

    return f"""<div class="vhead">
  <div><h2>현황관리</h2><p>계약 진행 단계와 최근 개정 활동을 한눈에 확인합니다.</p></div>
  <div class="right">
    <button class="mini" data-export="contracts">계약대장</button>
    <button class="mini" data-export="versions">버전대장</button>
  </div>
</div>
{_status_board(entries)}
<div class="kpis">{kpi_html}</div>
{_relation_map(entries)}
{_ledger_card(blocks, integrity, entries)}
{_deadline_panel(entries)}
<div class="panels">
  <div class="card"><h2>최근 개정 활동</h2><div class="feed">{feed}</div></div>
  <div class="card"><h2>분류별 계약 수</h2><div class="dist">{dist}</div></div>
</div>"""


# ---------------------------------------------------------------- 계약 목록


def _status_board(entries: list[ContractEntry]) -> str:
    """계약 진행 단계 현황.

    법무팀이 아침에 가장 먼저 보는 것은 "지금 몇 건이 협상 중이고, 몇 건이 닫혔나"다.
    단계별 건수와 함께 계약별 진행 막대를 붙여, 어디서 오래 머물러 있는지 보이게 한다.
    """
    if not entries:
        return '<div class="card"><div class="empty">등록된 계약이 없습니다.</div></div>'

    buckets = {key: [e for e in entries if e.status == key] for key in STATUS_ORDER}
    total = len(entries)

    cards = "".join(
        f'<button class="statcard" data-status-filter="{key}" '
        f'style="--sc:{STATUS_COLOR[key]}">'
        f'<span class="dotmark"></span>'
        f'<div class="sc-k">{STATUS_LABEL[key]}</div>'
        f'<div class="sc-n">{len(rows)}</div>'
        f'<div class="sc-d">전체의 {round(100 * len(rows) / total)}%</div>'
        f'<div class="sc-bar"><i style="width:{round(100 * len(rows) / total)}%"></i></div>'
        "</button>"
        for key, rows in buckets.items()
    )

    flow = "".join(
        f'<div class="seg" style="flex:{max(len(rows), 0.001)};background:{STATUS_COLOR[key]}" '
        f'title="{STATUS_LABEL[key]} {len(rows)}건"></div>'
        for key, rows in buckets.items()
        if rows
    )

    # 진행중 계약을 오래된 순으로 — 멈춰 있는 협상이 위로 온다.
    watch = sorted(
        (e for e in entries if e.status != "done"),
        key=lambda e: (e.status == "started", e.updated_at),
    )[:6]
    rows = "".join(
        f'<div class="track" data-open="{_e(e.contract_id)}" data-title="{_e(e.label)}">'
        f'<div class="tk-name"><b>{_e(e.label)}</b>'
        f'<span class="ev">{_e(e.category)} · {e.rounds}회 왕복</span></div>'
        f"{_progress(e)}"
        f'<div class="tk-meta"><span class="pill-status" style="--sc:{STATUS_COLOR[e.status]}">'
        f"{_e(e.status_label)}</span>"
        f'<span class="ev">{_e(e.updated_at[:10])}</span></div></div>'
        for e in watch
    ) or '<div class="ev">진행 중인 계약이 없습니다.</div>'

    return f"""<div class="statboard">
  <div class="statcards">{cards}</div>
  <div class="flowbar">{flow}</div>
</div>
<div class="card" style="margin-bottom:20px">
  <h2>진행 중인 계약</h2>
  <div class="tracks">{rows}</div>
</div>"""


def _progress(entry: ContractEntry) -> str:
    """버전 진행 막대. 점 하나가 버전 하나."""
    total = max(len(entry.versions), 1)
    dots = "".join(
        f'<span class="vdot{" done" if index == total - 1 else ""}" '
        f'title="{_e(record.version)} {_e(record.label)}"></span>'
        for index, record in enumerate(entry.versions)
    )
    ratio = 100 if entry.status == "done" else min(round(100 * entry.rounds / 6), 92)
    return (
        f'<div class="tk-track"><div class="tk-fill" '
        f'style="width:{ratio}%;background:{STATUS_COLOR[entry.status]}"></div>'
        f'<div class="tk-dots">{dots}</div></div>'
    )


def _contracts_view(entries, categories: list[str]) -> str:
    status_chips = "".join(
        f'<button class="chip js-status" data-value="{key}" aria-pressed="false">'
        f"{STATUS_LABEL[key]}</button>"
        for key in STATUS_ORDER
    )
    chips = '<button class="chip js-cat" data-value="all" aria-pressed="true">전체</button>'
    chips += "".join(
        f'<button class="chip js-cat" data-value="{_e(c)}" aria-pressed="false">{_e(c)}</button>'
        for c in categories
    )

    rows = "".join(
        f'<tr class="js-contract-row" data-open="{_e(e.contract_id)}" '
        f'data-title="{_e(e.label)}" data-category="{_e(e.category)}" '
        f'data-status="{_e(e.status)}" '
        f'data-search="{_e((e.label + " " + e.contract_id + " " + e.category).lower())}">'
        f'<td><div class="name">{_e(e.label)}</div>'
        f'<div class="sub">{_e(e.contract_id)}'
        + (f" · 당사자 {' / '.join(_e(p) for p in e.parties)}" if e.parties else "")
        + "</div></td>"
        f'<td><span class="badge cat">{_e(e.category)}</span></td>'
        f'<td><span class="pill-status" style="--sc:{STATUS_COLOR[e.status]}">'
        f"{_e(e.status_label)}</span></td>"
        f'<td class="num">{len(e.versions)}</td>'
        f'<td><span class="badge latest">{_e(e.latest)}</span></td>'
        f'<td class="num">'
        + (f'<span class="badge">{e.flagged}</span>' if e.flagged else '<span class="ev">–</span>')
        + "</td>"
        f'<td class="mono">{_e(e.updated_at[:16])}</td></tr>'
        for e in entries
    ) or '<tr><td colspan="7" class="ev">등록된 계약이 없습니다.</td></tr>'

    return f"""<div class="vhead">
  <div><h2>계약</h2>
    <p><b class="js-contract-count">0</b>건 표시 중 · 행을 선택하면 버전과 검토 결과를 봅니다.</p>
  </div>
  <div class="right">
    <input class="js-contract-search" type="search" placeholder="계약명·분류 검색"
      style="font:inherit;font-size:13.5px;padding:8px 13px;border-radius:8px;
      border:1px solid var(--line-2);background:var(--surface);min-width:220px">
  </div>
</div>
<div class="filters" style="margin-bottom:10px">{chips}</div>
<div class="filters" style="margin-bottom:14px">
  <button class="chip js-status" data-value="all" aria-pressed="true">진행 전체</button>
  {status_chips}
</div>
<div class="tbl"><table>
<thead><tr><th>계약</th><th>분류</th><th>진행</th><th style="text-align:right">버전</th><th>최신</th>
<th style="text-align:right">쟁점</th><th>최종 등록</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""


# ---------------------------------------------------------------- 계약 상세


def _detail_view(entry: ContractEntry, index: int) -> str:
    changes = {step.to_version: step for step in entry.timeline}
    version_rows = "".join(
        f'<tr data-version="{_e(record.version)}" class="vrow">'
        "<td><span class='badge"
        + (" latest" if record.version == entry.latest else "")
        + f"'>{_e(record.version)}</span></td>"
        f'<td><div class="name">{_e(record.label)}</div>'
        + (f'<div class="sub">{_e(record.note)}</div>' if record.note else "")
        + "</td>"
        f'<td>{_change_note(changes.get(record.version))}</td>'
        f'<td class="mono">{_e(record.imported_at[:16])}</td>'
        f'<td class="mono">{_e(record.sha256[:12])}…</td></tr>'
        for record in entry.versions
    ) or '<tr><td colspan="5" class="ev">등록된 버전이 없습니다.</td></tr>'

    # 타임라인 한 줄은 곧 하나의 비교본이다. 눌렀을 때 그 비교로 바로 가게 한다.
    by_pair = {
        (r.before_doc.version, r.after_doc.version): f"{index}-{order}"
        for order, r in enumerate(entry.results)
    }
    steps = "".join(
        '<div class="it step-link"'
        + (
            f' data-result-open="{by_pair[(step.from_version, step.to_version)]}"'
            f' data-contract="{_e(entry.contract_id)}"'
            f' data-contract-title="{_e(entry.label)}"'
            f' data-label="{_e(step.from_version)} → {_e(step.to_version)}"'
            if (step.from_version, step.to_version) in by_pair
            else ""
        )
        + f'><div class="when">{_e(step.from_version)} → {_e(step.to_version)}</div>'
        f'<div class="what"><b>수정 {step.modified} · 신설 {step.added} · '
        f"삭제 {step.deleted}</b>"
        + (f' <span class="badge">쟁점 {step.flagged}</span>' if step.flagged else "")
        + (
            f'<div class="meta">{", ".join(_e(h) for h in step.headings)}</div>'
            if step.headings
            else ""
        )
        + "</div></div>"
        for step in entry.timeline
    ) or '<div class="ev">비교할 버전이 2개 미만입니다.</div>'

    comparison_rows = "".join(
        f'<tr data-result-open="{index}-{order}" data-contract="{_e(entry.contract_id)}" '
        f'data-contract-title="{_e(entry.label)}" '
        f'data-label="{_e(result.before_doc.name)} → {_e(result.after_doc.name)}" '
        f'data-open-row="1" style="cursor:pointer">'
        f'<td><div class="name">{_e(result.before_doc.name)} → '
        f"{_e(result.after_doc.name)}</div>"
        f'<div class="sub">당사자 {len(result.parties)}인</div></td>'
        f'<td class="num">{result.counts()["modified"]}</td>'
        f'<td class="num">{result.counts()["added"]}</td>'
        f'<td class="num">{result.counts()["deleted"]}</td>'
        f'<td class="num">'
        + (
            f'<span class="badge">{sum(1 for c in result.changed() if c.flags)}</span>'
            if any(c.flags for c in result.changed())
            else '<span class="ev">–</span>'
        )
        + "</td>"
        + '<td style="text-align:right;white-space:nowrap">'
        + f'<button class="mini" data-dl="docx" data-contract="{_e(entry.contract_id)}" '
        f'data-from="{_e(result.before_doc.version)}" data-to="{_e(result.after_doc.version)}">'
        "Word</button> "
        f'<button class="mini" data-dl="pdf" data-contract="{_e(entry.contract_id)}" '
        f'data-from="{_e(result.before_doc.version)}" data-to="{_e(result.after_doc.version)}">'
        "PDF</button></td></tr>"
        for order, result in enumerate(entry.results)
    ) or '<tr><td colspan="5" class="ev">검토된 비교본이 없습니다.</td></tr>'

    parties = " / ".join(_e(p) for p in entry.parties) or "인식된 당사자 없음"

    return f"""<div data-detail="{_e(entry.contract_id)}" hidden>
<div class="vhead">
  <div>
    <h2>{_e(entry.label)}</h2>
    <p><span class="badge cat">{_e(entry.category)}</span> &nbsp;{_e(entry.contract_id)}
    · 당사자 {parties}</p>
  </div>
  <div class="right">
    <button class="mini" data-dl="docx" data-contract="{_e(entry.contract_id)}">Word</button>
    <button class="mini" data-dl="pdf" data-contract="{_e(entry.contract_id)}">PDF</button>
    <span class="badge">버전 {len(entry.versions)}</span>
    {f'<span class="badge">검토 대상 {entry.flagged}</span>' if entry.flagged else ""}
    {f'<span class="badge">쟁점 {entry.issues}</span>' if entry.issues else ""}
  </div>
</div>

<div class="sec">
  <h3>버전 관리</h3>
  <p class="hint">등록된 원본은 SHA-256으로 고정됩니다. 버전을 선택하면 그 시점의 조문 전문을 봅니다.</p>
  <div class="tbl"><table>
  <thead><tr><th>버전</th><th>라벨</th><th>주요 변경</th><th>등록 일시</th>
  <th>해시</th></tr></thead>
  <tbody>{version_rows}</tbody></table></div>
  {_version_docs(entry)}
</div>

{_chain_panel(entry)}

{_meeting_panel(entry)}

<div class="detail-grid">
  <div class="card"><h2>개정 타임라인</h2><div class="feed">{steps}</div></div>
  <div class="card"><h2>검토 요약</h2>{_detail_summary(entry)}</div>
</div>

<div class="sec">
  <h3>비교본</h3>
  <p class="hint">행을 선택하면 조문별 대비와 법무 코멘트를 확인합니다.</p>
  <div class="tbl"><table>
  <thead><tr><th>비교 구간</th><th style="text-align:right">수정</th>
  <th style="text-align:right">신설</th><th style="text-align:right">삭제</th>
  <th style="text-align:right">쟁점</th><th style="text-align:right">내려받기</th></tr></thead>
  <tbody>{comparison_rows}</tbody></table></div>
</div>
</div>"""


def _uploader(entry: ContractEntry | None = None) -> str:
    """계약 등록 카드.

    서버 모드(`contract-review serve`)에서는 실제로 파일이 저장되고 버전이 등록된다.
    파일을 그냥 열었을 때는 저장할 곳이 없으므로, 같은 입력으로 실행할 CLI 명령을
    만들어 준다 — 되는 척하지 않는다.
    """
    return """<div class="sec upload-card" data-uploader>
  <div class="card">
    <div class="frow">
      <label>계약 ID<input data-up="contract_id" placeholder="예: 2026-용역-007"></label>
      <label>계약명<input data-up="title" placeholder="예: AI 플랫폼 구축 용역"></label>
      <label>분류<input data-up="category" placeholder="예: 용역·도급"></label>
    </div>
    <div class="frow">
      <label style="flex:2 1 420px">당사자
        <input data-up="parties"
          placeholder="갑=주식회사 가나다:발주자, 을=주식회사 라마바:수급인, 병=...">
        <span class="fhint">약칭=상호:역할 형식으로 쉼표 구분. 비워 두면 계약서에서 자동 인식합니다.
        자동 인식된 당사자를 빼려면 <code>-병</code> 처럼 앞에 -를 붙입니다.</span>
      </label>
      <label>버전 라벨<input data-up="labels" placeholder="예: 당사 초안|상대방 1차"></label>
    </div>
    <div class="frow">
      <label style="flex:2 1 380px">계약서 파일
        <input type="file" data-up="files" multiple accept=".hwp,.hwpx,.docx,.pdf">
        <span class="fhint">한글(.hwp/.hwpx), Word(.docx), PDF를 올릴 수 있습니다.
        여러 개를 올리면 v1, v2… 순서로 등록됩니다.</span>
      </label>
      <button class="mini primary" data-act="upload" style="align-self:flex-end">등록하기</button>
    </div>
    <div class="upstate" data-upstate></div>
  </div>
</div>"""


def _meeting_panel(entry: ContractEntry) -> str:
    """회의 합의 사항을 조문 수정안으로 옮기는 패널.

    회의록을 붙여 넣으면 어느 조문에 걸리는지 찾아 수정 문안을 제안하고,
    채택한 것만 모아 다음 버전으로 저장한다.
    """
    options = "".join(
        f'<option value="{_e(r.version)}">{_e(r.version)} {_e(r.label)}</option>'
        for r in reversed(entry.versions)
    )
    placeholder = (
        "- 3조 대금 지급기일을 45일로 단축하기로 함&#10;"
        "- 손해배상 한도는 계약금액 100%로 하되 고의·중과실은 제외&#10;"
        "- 준거법은 대한민국 법으로 환원"
    )
    return f"""<div class="sec" data-meeting="{_e(entry.contract_id)}">
  <h3>회의 반영</h3>
  <p class="hint">협상 회의에서 합의된 내용을 붙여 넣으면 해당 조문을 찾아 수정 문안을 제안합니다.
  채택한 조문만 모아 새 버전으로 저장합니다.</p>
  <div class="card">
    <div class="frow">
      <label style="flex:0 0 220px">기준 버전
        <select data-mt="version">{options}</select>
      </label>
      <label style="flex:1 1 260px">회의 정보
        <input data-mt="label" placeholder="예: 2026-08-12 3차 협상 회의 반영">
      </label>
    </div>
    <div class="abiz">
      <div class="abiz-head">
        <span class="abiz-mark">A.</span>
        <b>A.Biz 회의록</b>
        <span class="badge">데모 데이터</span>
        <button class="mini" data-act="load-meetings">회의록 불러오기</button>
      </div>
      <div class="abiz-list" data-abiz-list hidden></div>
    </div>
    <label style="display:block;font-size:12px;font-weight:600;color:var(--muted)">회의 내용
      <textarea data-mt="minutes" rows="5" placeholder="{placeholder}"></textarea>
    </label>
    <div class="frow" style="margin:12px 0 0;align-items:center">
      <button class="mini primary" data-act="analyze">조문 수정안 만들기</button>
      <button class="mini" data-act="apply-meeting" hidden>채택본 저장</button>
      <span class="mtstate" data-mtstate></span>
    </div>
    <div class="proposals" data-proposals></div>
  </div>
</div>"""


def _integrity_pill(integrity, entries: list[ContractEntry]) -> str:
    """상단바 무결성 표시 — 체인이 성립하는지 한눈에."""
    if integrity is None:
        return ""
    sealed = any(e.encrypted for e in entries)
    state = "ok" if integrity.ok else "bad"
    label = f"체인 {integrity.length}블록" if integrity.ok else "체인 불일치"
    return (
        f'<button class="chainpill {state}" data-goto-view="ledger" title="원장 보기">'
        f'<span class="node"></span><span class="link"></span><span class="node"></span>'
        f"<b>{_e(label)}</b>"
        + (f'<span class="tip">{_e(integrity.tip[:10])}…</span>' if integrity.ok else "")
        + ("<span class='lock'>암호화</span>" if sealed else "")
        + "</button>"
    )


def _chain_strip(blocks, limit: int = 12) -> str:
    """블록을 이어 붙인 띠. 각 칸이 앞 칸의 해시를 물고 있다는 것을 보이게 한다."""
    if not blocks:
        return ""

    shown = blocks[-limit:]
    cells = []
    if len(blocks) > limit:
        cells.append('<div class="cnode more">…</div>')
    for block in shown:
        cells.append(
            f'<div class="cnode" title="{_e(block.hash)}">'
            f'<div class="cidx">#{block.index}</div>'
            f'<div class="cver">{_e(block.version or block.kind)}</div>'
            f'<div class="chash">{_e(block.hash[:8])}</div></div>'
        )
    return f'<div class="chain">{"".join(cells)}</div>'


CATEGORY_COLOR = {
    "물품구매": "#4338CA",
    "용역": "#0EA5E9",
    "자문": "#7C3AED",
    "연구개발": "#0891B2",
    "라이선스": "#DB2777",
}
_FALLBACK_COLOR = "#64748B"


def _relation_map(entries: list[ContractEntry]) -> str:
    """계약 관계망.

    계약은 한 건씩 떨어져 있는 것처럼 보이지만, 같은 상대방과 여러 건을 맺고 있거나
    같은 쟁점이 여러 계약에 흩어져 있는 경우가 많다. 그런 계약은 함께 대응하는 편이
    낫다는 것을 한눈에 보이게 한다.

    좌표는 서버에서 스프링 모형으로 계산해 박아 넣는다. 브라우저에서 물리를 돌리지
    않으므로 열 때마다 그림이 흔들리지 않는다.
    """
    graph = relations.build(entries)
    if len(graph.nodes) < 2:
        return ""

    width, height = 780, 470
    points = relations.layout(graph, width, height)
    by_id = {e.contract_id: e for e in entries}

    # 간선 — 조직 공유는 굵고 이어진 선, 쟁점 공유는 가늘고 점선
    edges = []
    for index, link in enumerate(graph.links):
        (x1, y1), (x2, y2) = points[link.source], points[link.target]
        # 살짝 휘어야 여러 간선이 겹쳐도 구분된다
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        cx, cy = mx - dy * 0.09, my + dx * 0.09
        strong = link.kind == "org"
        thickness = 1.1 + link.weight * (0.9 if strong else 0.4)
        dash = "" if strong else ' stroke-dasharray="5 5"'
        tip = (
            f"{graph.nodes[link.source].label} ↔ {graph.nodes[link.target].label}"
            f" · {link.label}"
        )
        edges.append(
            f'<path class="rel-edge {link.kind}" d="M{x1},{y1} Q{cx},{cy} {x2},{y2}" '
            f'data-edge="{index}" data-a="{link.source}" data-b="{link.target}" '
            f'stroke="url(#relGrad)" stroke-width="{thickness:.1f}" fill="none"{dash}>'
            f"<title>{_e(tip)}</title></path>"
        )

    # 노드 — 크기는 연결 수, 색은 분류
    nodes = []
    for index, node in enumerate(graph.nodes):
        x, y = points[index]
        degree = graph.degree(index)
        radius = 13 + min(degree, 6) * 2.4
        color = CATEGORY_COLOR.get(node.category, _FALLBACK_COLOR)
        entry = by_id.get(node.contract_id)
        versions = len(entry.versions) if entry else 0
        label = node.label if len(node.label) <= 12 else node.label[:11] + "…"

        nodes.append(
            f'<g class="rel-node" data-node="{index}" data-open="{_e(node.contract_id)}" '
            f'data-title="{_e(node.label)}" transform="translate({x},{y})">'
            f'<circle class="halo" r="{radius + 9}" fill="{color}" opacity="0.10"/>'
            f'<circle class="dot" r="{radius}" fill="{color}" />'
            f'<circle class="ring" r="{radius}" fill="none" stroke="#fff" stroke-width="2.5"/>'
            f'<text class="deg" text-anchor="middle" dy="4">{versions}</text>'
            f'<text class="lab" y="{radius + 17}" text-anchor="middle">{_e(label)}</text>'
            f"<title>{_e(node.label)} · {_e(node.category)} · 버전 {versions} · "
            f"연결 {degree}</title></g>"
        )

    legend = "".join(
        f'<span class="rl"><i style="background:{color}"></i>{_e(name)}</span>'
        for name, color in CATEGORY_COLOR.items()
        if any(n.category == name for n in graph.nodes)
    )

    # 가장 많이 얽힌 계약 — 그래프만으로는 순위가 눈에 안 들어온다
    ranked = sorted(
        ((graph.degree(i), n) for i, n in enumerate(graph.nodes)),
        key=lambda pair: (-pair[0], pair[1].label),
    )[:4]
    top = "".join(
        f'<div class="rel-row" data-open="{_e(node.contract_id)}" data-title="{_e(node.label)}">'
        f'<span class="dotmini" style="background:'
        f'{CATEGORY_COLOR.get(node.category, _FALLBACK_COLOR)}"></span>'
        f"<b>{_e(node.label)}</b><span class=\"ev\">{degree}개 계약과 연결</span></div>"
        for degree, node in ranked
        if degree
    ) or '<div class="ev">겹치는 계약이 없습니다.</div>'

    return f"""<div class="card rel-card" style="margin-bottom:20px">
  <h2>계약 관계망
    <span class="badge">조직 공유 {len(graph.org_links)}</span>
    <span class="badge">쟁점 공유 {len(graph.issue_links)}</span>
  </h2>
  <p class="hint" style="margin:-6px 0 10px">같은 조직이 당사자로 얽혔거나 같은 쟁점이
  함께 잡힌 계약을 잇습니다. 원 크기는 버전 수, 색은 분류입니다.</p>
  <div class="rel-body">
    <svg class="relmap" viewBox="0 0 {width} {height}" role="img"
      aria-label="계약 관계망">
      <defs>
        <linearGradient id="relGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#4338CA" stop-opacity=".55"/>
          <stop offset="100%" stop-color="#0EA5E9" stop-opacity=".55"/>
        </linearGradient>
      </defs>
      <g class="rel-edges">{"".join(edges)}</g>
      <g class="rel-nodes">{"".join(nodes)}</g>
    </svg>
    <div class="rel-side">
      <div class="k">가장 많이 얽힌 계약</div>
      {top}
      <div class="rel-legend">{legend}</div>
      <div class="rel-legend">
        <span class="rl"><i class="line solid"></i>조직 공유</span>
        <span class="rl"><i class="line dashed"></i>쟁점 공유</span>
      </div>
    </div>
  </div>
</div>"""


def _ledger_card(blocks, integrity, entries: list[ContractEntry]) -> str:
    """현황관리 상단의 원장 요약."""
    if integrity is None:
        return ""

    sealed = sum(1 for e in entries if e.encrypted)
    state_class = "ok" if integrity.ok else "bad"
    state_text = "무결성 확인" if integrity.ok else f"블록 {integrity.broken_at} 불일치"
    return f"""<div class="card ledger-card {state_class}" style="margin-bottom:20px">
  <h2>문서 원장
    <span class="badge {"ok" if integrity.ok else "high"}">{_e(state_text)}</span>
    {f'<span class="badge">암호화 보관 {sealed}건</span>' if sealed else ""}
  </h2>
  <div class="ledger-grid">
    <div>
      <div class="k">블록</div><div class="n">{integrity.length}</div>
      <div class="d">등록·편집마다 1개</div>
    </div>
    <div>
      <div class="k">체인 팁</div>
      <div class="mono tipline">{_e(integrity.tip[:24])}…</div>
      <div class="d">가장 최근 블록의 해시</div>
    </div>
    <div style="flex:1;min-width:220px">
      <div class="k">최근 블록</div>
      {_chain_strip(blocks, limit=8)}
    </div>
  </div>
</div>"""


def _ledger_view(blocks, integrity, entries: list[ContractEntry]) -> str:
    """원장 전체 화면."""
    if not blocks:
        return """<div class="vhead"><div><h2>원장</h2>
        <p>아직 기록된 블록이 없습니다.</p></div></div>"""

    titles = {e.contract_id: e.label for e in entries}
    rows = "".join(
        f'<tr data-open="{_e(block.contract_id)}" '
        f'data-title="{_e(titles.get(block.contract_id, block.contract_id))}">'
        f'<td class="num mono">#{block.index}</td>'
        f'<td class="mono">{_e(block.at[:16])}</td>'
        f'<td><span class="badge">{_e(block.kind)}</span></td>'
        f'<td><div class="name">{_e(titles.get(block.contract_id, block.contract_id))}</div>'
        f'<div class="sub">{_e(block.contract_id)} · {_e(block.version)} {_e(block.label)}</div></td>'
        f'<td class="mono">{_e(block.sha256[:12])}…</td>'
        f'<td class="mono linkcell">{_e(block.prev[:8])}…<span class="arrow2">→</span>'
        f"{_e(block.hash[:8])}…</td></tr>"
        for block in reversed(blocks)
    )

    state = "무결성 확인" if integrity and integrity.ok else "불일치"
    return f"""<div class="vhead">
  <div><h2>원장</h2>
    <p>등록·편집이 일어날 때마다 블록이 쌓입니다. 각 블록은 앞 블록의 해시를 품고 있어,
    중간 기록을 고치면 뒤가 전부 어긋납니다.</p>
  </div>
  <div class="right">
    <span class="badge {"ok" if integrity and integrity.ok else "high"}">{_e(state)}</span>
    <span class="badge">블록 {len(blocks)}</span>
  </div>
</div>
{_chain_strip(blocks, limit=14)}
<div class="tbl" style="margin-top:14px"><table>
<thead><tr><th>블록</th><th>기록 시각</th><th>종류</th><th>대상</th>
<th>문서 해시</th><th>연결 (앞 → 이 블록)</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""


def _vault_badge(entries: list[ContractEntry], integrity) -> str:
    """사이드바 하단 보관 상태 — 암호화 여부와 원장 무결성."""
    sealed = any(e.encrypted for e in entries)
    lines = [
        "<br>보관 " + ("암호화" if sealed else "평문"),
    ]
    if integrity is not None:
        state = "무결성 확인" if integrity.ok else "불일치"
        lines.append(f" · 원장 {integrity.length}블록 {state}")
    return "".join(lines)


def _chain_panel(entry: ContractEntry) -> str:
    """계약별 등록 원장.

    버전 표가 '무엇이 등록됐는지'를 보여준다면, 원장은 '그 기록 자체가 손대지
    않았음'을 보여준다. 각 블록은 앞 블록의 해시를 품고 있어 중간을 고치면
    뒤가 전부 어긋난다.
    """
    if not entry.chain:
        return ""

    rows = "".join(
        f"<tr><td class='num'>#{block.index}</td>"
        f'<td><span class="badge">{_e(block.version)}</span> {_e(block.label)}</td>'
        f'<td class="mono">{_e(block.at[:16])}</td>'
        f'<td class="mono">{_e(block.sha256[:12])}…</td>'
        f'<td class="mono">{_e(block.prev[:8])}… → {_e(block.hash[:8])}…</td></tr>'
        for block in entry.chain
    )
    seal = (
        '<span class="badge ok">암호화 보관</span>'
        if entry.encrypted
        else '<span class="badge">평문 보관</span>'
    )
    return f"""<div class="sec" data-collapsible>
  <h3>등록 원장 {seal}
    <button class="mini toggle" data-act="toggle-sec" aria-expanded="false">펼치기</button>
  </h3>
  <div class="sec-body" hidden>
  <p class="hint">등록·편집이 일어날 때마다 블록이 하나 붙고, 각 블록은 앞 블록의 해시를
  품습니다. 중간 기록을 고치면 뒤 블록의 해시가 전부 어긋나 바로 드러납니다.</p>
  {_chain_strip(entry.chain)}
  <div class="tbl"><table>
  <thead><tr><th>블록</th><th>버전</th><th>기록 시각</th><th>문서 해시</th>
  <th>연결</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
  </div>
</div>"""


def _version_docs(entry: ContractEntry) -> str:
    """버전 행을 눌렀을 때 펼쳐지는 조문 전문.

    비교 결과만 보다 보면 "이 버전 원문이 실제로 어땠더라"를 확인할 데가 없다.
    등록된 파일을 파싱한 그대로를 붙여, 인용할 때 원본을 다시 열지 않아도 되게 한다.
    """
    if not entry.texts:
        return ""

    panels = []
    for record in entry.versions:
        clauses = entry.texts.get(record.version)
        if not clauses:
            continue
        body = "".join(
            f'<div class="vclause" data-clause>'
            f'<h4 data-field="heading" contenteditable="false">{_e(heading)}</h4>'
            f'<p data-field="body" contenteditable="false">{_e(text)}</p></div>'
            for heading, text in clauses
        )
        panels.append(
            f'<div class="vdoc" data-version-doc="{_e(record.version)}" '
            f'data-contract="{_e(entry.contract_id)}" hidden>'
            f'<div class="vdoc-head"><b>{_e(record.version)} {_e(record.label)}</b>'
            f'<span class="ev">조문 {len(clauses)}건 · {_e(record.imported_at[:16])}</span>'
            f'<span class="edit-tools">'
            f'<input data-edit="label" placeholder="새 버전 라벨" hidden>'
            f'<button class="mini" data-act="edit">조문 편집</button>'
            f'<button class="mini primary" data-act="save-edit" hidden>새 버전으로 저장</button>'
            f'<button class="mini" data-act="cancel-edit" hidden>취소</button>'
            f'<button class="mini" data-act="close-doc">닫기</button></span></div>'
            f'<div class="editstate" data-editstate></div>'
            f'<div class="vdoc-body">{body}</div></div>'
        )
    return "".join(panels)


def _deadline_panel(entries: list[ContractEntry]) -> str:
    """다가오는 기한.

    자동 갱신 계약은 갱신 거절 통지 기한을 넘기면 조건이 그대로 한 해 더 간다.
    계약기간 조문에 이미 적혀 있는 날짜를 앞으로 당겨 보여 준다.
    """
    dated = [e for e in entries if e.deadline.known]
    if not dated:
        return ""

    def key(entry: ContractEntry):
        target = entry.deadline.notify_by or entry.deadline.ends_on
        return target

    rows = []
    for entry in sorted(dated, key=key)[:6]:
        d = entry.deadline
        urgency = d.urgency()
        left = d.notice_days_left() if d.notify_by else d.days_left()
        when = "통지 기한" if d.notify_by else "계약 만료"
        label = {
            "passed": f"{abs(left)}일 지남",
            "soon": f"{left}일 남음",
            "ok": f"{left}일 남음",
        }.get(urgency, "-")
        rows.append(
            f'<div class="dl-row" data-open="{_e(entry.contract_id)}" '
            f'data-title="{_e(entry.label)}">'
            f'<div><b>{_e(entry.label)}</b>'
            f'<div class="ev">{_e(when)} {_e(str(d.notify_by or d.ends_on))}'
            + (" · 자동 갱신" if d.auto_renew else "")
            + f" · 근거 {_e(d.source)}</div></div>"
            f'<span class="dl-tag {urgency}">{_e(label)}</span></div>'
        )

    counts = {"passed": 0, "soon": 0, "ok": 0}
    for entry in dated:
        counts[entry.deadline.urgency()] = counts.get(entry.deadline.urgency(), 0) + 1

    return f"""<div class="card" style="margin-bottom:20px">
  <h2>다가오는 기한
    <span class="badge">기한 확인 {len(dated)}건</span>
    {f'<span class="badge high">지남 {counts["passed"]}</span>' if counts["passed"] else ""}
    {f'<span class="badge medium">30일 이내 {counts["soon"]}</span>' if counts["soon"] else ""}
  </h2>
  <div class="dl-list">{"".join(rows)}</div>
</div>"""


def _search_view(entries: list[ContractEntry]) -> str:
    """계약을 가로질러 조문을 찾는다.

    "지체상금이 들어간 계약이 어디였더라"를 계약을 하나씩 열어 확인하던 일을
    한 번에 끝낸다. 조문 원문은 이미 페이지에 들어 있어 서버를 다시 부르지 않는다.

    협상 과정에서 빠진 문언(위약벌처럼 상대방이 넣었다가 합의로 삭제된 조항)도
    찾을 수 있어야 하므로 전 버전을 색인하되, 같은 문안이 여러 버전에 걸쳐 있으면
    한 건으로 묶고 등장 구간만 표시한다.
    """
    cards = []
    for entry in entries:
        latest = entry.latest
        seen: dict[tuple[str, str], list[str]] = {}
        for record in entry.versions:
            for heading, body in entry.texts.get(record.version, []):
                seen.setdefault((heading, body), []).append(record.version)

        for (heading, body), versions in seen.items():
            in_latest = latest in versions
            span = versions[0] if len(versions) == 1 else f"{versions[0]}–{versions[-1]}"
            blob = f"{entry.label} {entry.category} {heading} {body}".lower()
            cards.append(
                f'<div class="hit" data-search="{_e(blob)}" data-latest="{"1" if in_latest else "0"}"'
                f' data-open="{_e(entry.contract_id)}" data-title="{_e(entry.label)}" hidden>'
                f'<div class="hit-head"><b>{_e(heading)}</b>'
                f'<span class="badge cat">{_e(entry.category)}</span>'
                + ("" if in_latest else '<span class="badge medium">이전 버전</span>')
                + f'<span class="ev">{_e(entry.label)} · {_e(span)}</span></div>'
                f'<p>{_e(body)}</p></div>'
            )

    latest_count = sum(1 for c in cards if 'data-latest="1"' in c)
    return f"""<div class="vhead">
  <div><h2>조항검색</h2>
    <p>모든 계약의 조문에서 찾습니다. 최신 {latest_count}개 · 전체 {len(cards)}개 문안.</p>
  </div>
</div>
<div class="toolbar">
  <input class="js-clause-search" type="search"
    placeholder="예: 지체상금, 연대보증, 국외 이전, 위약벌">
  <button class="chip js-scope" data-scope="latest" aria-pressed="true">최신 버전</button>
  <button class="chip js-scope" data-scope="all" aria-pressed="false">이전 버전 포함</button>
  <span class="ev"><b class="js-hit-count">0</b>건</span>
</div>
<div class="hits">{"".join(cards)}</div>
<div class="empty js-search-empty">찾을 문구를 입력하십시오.
여러 단어를 띄어 쓰면 모두 포함된 조문을 찾습니다.</div>"""


def _party_total(entries: list[ContractEntry]) -> int:
    return sum(len(e.parties) for e in entries)


def _change_note(step) -> str:
    """버전 한 줄 요약 — 이 버전에서 무엇이 바뀌었는지."""
    if step is None:
        return '<span class="ev">최초 등록본</span>'

    counts = []
    if step.modified:
        counts.append(f"수정 {step.modified}")
    if step.added:
        counts.append(f"신설 {step.added}")
    if step.deleted:
        counts.append(f"삭제 {step.deleted}")
    head = " · ".join(counts) or "변경 없음"

    detail = ""
    if step.headings:
        names = [h.split("(")[-1].rstrip(")") for h in step.headings[:3]]
        more = f" 외 {len(step.headings) - 3}건" if len(step.headings) > 3 else ""
        detail = f'<div class="sub">{_e(", ".join(names))}{more}</div>'
    return f"<div>{_e(head)}</div>{detail}"


def _create_view() -> str:
    from ..templates import TEMPLATES

    cards = "".join(
        f'<div class="tpl">'
        f'<div class="tpl-body"><div class="eyebrow">{_e(t.category)}</div>'
        f"<h4>{_e(t.title)}</h4><p>{_e(t.summary)}</p></div>"
        f'<button class="mini" data-template="{_e(t.id)}">양식 받기</button></div>'
        for t in TEMPLATES
    )

    return f"""<div class="vhead">
  <div><h2>계약생성</h2>
    <p>계약을 등록하고 당사자를 지정합니다. 등록한 당사자는 이후 모든 비교본에 적용됩니다.</p>
  </div>
</div>
{_uploader()}

<div class="sec">
  <h3>표준 계약서 양식</h3>
  <p class="hint">초안이 없다면 표준 양식을 Word로 받아 수정한 뒤 그대로 올리십시오.</p>
  <div class="tpl-grid">{cards}</div>
</div>"""


def _customers_view(entries: list[ContractEntry]) -> str:
    rows = []
    for entry in entries:
        roster = _roster(entry)
        if roster:
            people = "".join(
                f'<div><b>{_e(p["alias"])}</b> {_e(p["name"] or "-")}'
                + (f' <span class="badge">{_e(p["role"])}</span>' if p["role"] else "")
                + "</div>"
                for p in roster
            )
        else:
            people = '<span class="ev">인식된 당사자가 없습니다.</span>'
        rows.append(
            f'<tr data-open="{_e(entry.contract_id)}" data-title="{_e(entry.label)}">'
            f'<td><div class="name">{_e(entry.label)}</div>'
            f'<div class="sub">{_e(entry.contract_id)}</div></td>'
            f'<td><span class="badge cat">{_e(entry.category)}</span></td>'
            f"<td>{people}</td>"
            f'<td class="num">{len(roster)}</td></tr>'
        )

    body = "".join(rows) or '<tr><td colspan="4" class="ev">등록된 계약이 없습니다.</td></tr>'
    return f"""<div class="vhead">
  <div><h2>고객관리</h2>
    <p>계약별 당사자 명부입니다. 당사자 지정은 계약생성 화면에서 합니다.</p>
  </div>
</div>
<div class="tbl"><table>
<thead><tr><th>계약</th><th>분류</th><th>당사자</th>
<th style="text-align:right">인원</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def _roster(entry: ContractEntry) -> list[dict[str, str]]:
    for result in entry.results:
        if result.parties:
            return [
                {"id": p.id, "alias": p.alias, "name": p.name, "role": p.role}
                for p in result.parties
            ]
    return []


def _detail_summary(entry: ContractEntry) -> str:
    categories: dict[str, int] = {}
    for result in entry.results:
        for name, count in result.category_counts().items():
            categories[name] = categories.get(name, 0) + count
    if not categories:
        return '<div class="ev">검토 결과가 없습니다.</div>'

    top = max(categories.values())
    rows = "".join(
        f'<div class="row"><span>{_e(name)}</span>'
        f'<span class="bar"><i style="width:{int(100 * count / top)}%"></i></span>'
        f'<span class="v">{count}</span></div>'
        for name, count in sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    )
    return f'<div class="dist">{rows}</div>'


def _result_panels(entries: list[ContractEntry]) -> list[str]:
    panels = []
    for index, entry in enumerate(entries):
        for order, result in enumerate(entry.results):
            panels.append(
                f'<div data-result="{index}-{order}" hidden>{render_result_panel(result)}</div>'
            )
    return panels


def _last_run(entries: list[ContractEntry]) -> str:
    stamps = [r.generated_at for e in entries for r in e.results if r.generated_at]
    return max(stamps)[:16] if stamps else "-"


def _e(text: str) -> str:
    return _html.escape(str(text or ""))
