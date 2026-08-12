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

from .. import DISCLAIMER
from ..models import ReviewResult, TimelineStep, VersionRecord
from .checky import CSS as CHECKY_CSS
from .checky import JS as CHECKY_JS
from .checky import brand_markup, buddy_markup
from .html import CSS as BASE_CSS
from .html import JS as PANEL_JS
from .html import render_result_panel

BRAND = "체키"

STATUS_ORDER = ("started", "ongoing", "done")
STATUS_LABEL = {"started": "개시", "ongoing": "진행중", "done": "완료"}
STATUS_COLOR = {"started": "#7c8698", "ongoing": "#1849a9", "done": "#087443"}
_FINAL_HINTS = ("최종", "날인", "서명", "확정", "체결")
USER_NAME = "김민형"
TAGLINE = "계약 검토 도우미"

_CSS = """
/* ── 앱 셸 ────────────────────────────────────────── */
body{background:var(--canvas)}
.app{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
@media(max-width:900px){.app{grid-template-columns:1fr}.side{display:none}}
.side{background:#0d1526;color:#c3cbd9;padding:20px 14px;border-right:1px solid #0a1120}
.brand{display:flex;align-items:center;gap:10px;padding:4px 10px 22px}
.brand .mark{width:30px;height:30px;border-radius:8px;background:#2563eb;color:#fff;
display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.brand .name{font-size:15px;font-weight:700;color:#fff;letter-spacing:.06em;line-height:1.15}
.brand .tag{font-size:10px;color:#6b7a91;letter-spacing:.1em;text-transform:uppercase}
.side .grp{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#5c6b82;
padding:14px 10px 6px}
.side button{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;
font:inherit;font-size:13.5px;text-align:left;padding:8px 10px;border:0;border-radius:7px;
background:none;color:#c3cbd9;cursor:pointer;margin-bottom:2px}
.side button:hover{background:#16203473;color:#fff}
.side button[aria-current="true"]{background:#1c2a44;color:#fff;font-weight:600}
.side .cnt{font-size:11px;color:#6b7a91;font-variant-numeric:tabular-nums}
.side .foot{margin-top:22px;padding:12px 10px 0;border-top:1px solid #1a2438;font-size:11px;
color:#5c6b82;line-height:1.6}

.main{min-width:0}
.topbar{background:var(--surface);border-bottom:1px solid var(--line);padding:0 28px;
display:flex;align-items:center;gap:14px;min-height:58px;position:sticky;top:0;z-index:5}
.topbar .path{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:7px;
flex-wrap:wrap}
.topbar .path button{font:inherit;border:0;background:none;color:var(--accent);cursor:pointer;
padding:0;font-weight:500}
.topbar .path button:hover{text-decoration:underline}
.topbar .path .sep{color:var(--line-2)}
.topbar .path b{font-weight:600;color:var(--ink)}
.topbar .who{margin-left:auto;display:flex;align-items:center;gap:9px;font-size:12.5px;
color:var(--muted)}
.topbar .who .av{width:26px;height:26px;border-radius:50%;background:#e8edf7;color:#1849a9;
display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
.view{padding:26px 28px 72px;max-width:1180px}
.view[hidden]{display:none}
.vhead{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap;margin-bottom:20px}
.vhead h2{font-size:20px;font-weight:600;margin:0;letter-spacing:-.02em}
.vhead p{margin:2px 0 0;font-size:13px;color:var(--muted)}
.vhead .right{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}

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
.vdot.done{box-shadow:0 0 0 1.5px var(--ink)}
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
.tpl:hover{border-color:var(--accent);box-shadow:0 6px 18px rgba(16,24,40,.08)}
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
.side{background:linear-gradient(180deg,#101a2e 0%,#0b1220 100%);position:relative}
.side::after{content:"";position:absolute;inset:0 0 auto;height:1px;
background:linear-gradient(90deg,transparent,rgba(96,150,255,.5),transparent)}
.brand .mark{background:linear-gradient(135deg,#3b82f6,#1d4ed8);
box-shadow:0 4px 14px rgba(37,99,235,.45)}
.brand .name{background:linear-gradient(90deg,#fff,#9dc0ff);-webkit-background-clip:text;
background-clip:text;color:transparent}
.side button{transition:background .16s,color .16s,transform .16s}
.side button[aria-current="true"]{box-shadow:inset 2px 0 0 #60a5fa}
.topbar{background:rgba(255,255,255,.82);backdrop-filter:saturate(180%) blur(12px);
-webkit-backdrop-filter:saturate(180%) blur(12px)}
.kpi{position:relative;overflow:hidden;transition:transform .16s,box-shadow .16s}
.kpi::before{content:"";position:absolute;inset:0 0 auto;height:2px;
background:linear-gradient(90deg,#2563eb,#7dd3fc)}
.kpi:nth-child(4)::before{background:linear-gradient(90deg,#b42318,#f97066)}
.kpi:hover{transform:translateY(-2px);box-shadow:0 10px 26px rgba(16,24,40,.09)}
.card,.tbl{transition:box-shadow .18s}
.card:hover,.tbl:hover{box-shadow:0 6px 20px rgba(16,24,40,.07)}
.tbl tbody tr[data-open],.tbl tbody tr[data-result-open]{position:relative;
transition:background .14s}
.tbl tbody tr[data-open]:hover,.tbl tbody tr[data-result-open]:hover{
box-shadow:inset 3px 0 0 var(--accent)}
.dist .bar i{background:linear-gradient(90deg,#1d4ed8,#60a5fa);
animation:grow .7s cubic-bezier(.22,1,.36,1) both}
@keyframes grow{from{width:0 !important}}
.view:not([hidden]){animation:enter .28s cubic-bezier(.22,1,.36,1) both}
@keyframes enter{from{opacity:0;transform:translateY(6px)}}
.feed .it{transition:background .14s;border-radius:6px}
.feed .it:hover{background:#f8fafc}
.badge.high{box-shadow:0 0 0 1px rgba(180,35,24,.14)}
.badge.latest{background:linear-gradient(135deg,#1f2937,#0f172a)}
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
  var navButtons = document.querySelectorAll('.side button[data-goto]');
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
    customers: goCustomers
  };
  navButtons.forEach(function(btn){
    btn.addEventListener('click', function(){
      (routes[btn.dataset.goto] || goDashboard)();
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


def render_workspace(entries: list[ContractEntry]) -> str:
    categories = sorted({e.category for e in entries})
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
<aside class="side">
  <div class="brand">
    {brand_markup()}
    <div>
      <div class="name">{BRAND}</div>
      <div class="tag">{TAGLINE}</div>
    </div>
  </div>
  <div class="grp">메뉴</div>
  <button data-goto="dashboard" aria-current="true"><span>현황관리</span></button>
  <button data-goto="contracts"><span>계약상세</span>
    <span class="cnt">{len(entries)}</span></button>
  <button data-goto="create"><span>계약생성</span></button>
  <button data-goto="customers"><span>고객관리</span>
    <span class="cnt">{_party_total(entries)}</span></button>
  <div class="foot">
    계약 {len(entries)}건 · 버전 {total_versions}개<br>마지막 분석 {_e(_last_run(entries))}
  </div>
</aside>

<div class="main">
<div class="topbar">
  <div class="path js-path"></div>
  <div class="who"><span>{_e(USER_NAME)}</span><div class="av">{_e(USER_NAME[:1])}</div></div>
</div>

<div class="view" data-app-view="dashboard">
{_dashboard(entries, total_versions, total_high, total_changes)}
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


def _dashboard(entries, total_versions: int, total_high: int, total_changes: int) -> str:
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

    steps = "".join(
        f'<div class="it"><div class="when">{_e(step.from_version)} → {_e(step.to_version)}</div>'
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
