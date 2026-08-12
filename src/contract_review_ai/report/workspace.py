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
from .html import CSS as BASE_CSS
from .html import JS as PANEL_JS
from .html import render_result_panel

BRAND = "CLAUSA"
USER_NAME = "김민형"
TAGLINE = "Contract Intelligence"

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
.upload-card .card{padding:14px 16px}
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

_APP_JS = """
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

  function goDashboard(){ show('dashboard'); crumbs([{label:'대시보드'}]); }
  function goContracts(){ show('contracts'); crumbs([{label:'계약'}]); }

  function goDetail(id, title){
    document.querySelectorAll('[data-detail]').forEach(function(el){
      el.hidden = (el.dataset.detail !== id);
    });
    show('detail');
    crumbs([{label:'계약', go:goContracts}, {label:title}]);
  }

  function goResult(key, contractId, contractTitle, label){
    document.querySelectorAll('[data-result]').forEach(function(el){
      el.hidden = (el.dataset.result !== key);
    });
    show('result');
    crumbs([
      {label:'계약', go:goContracts},
      {label:contractTitle, go:function(){ goDetail(contractId, contractTitle); }},
      {label:label}
    ]);
  }

  navButtons.forEach(function(btn){
    btn.addEventListener('click', function(){
      if (btn.dataset.goto === 'contracts') goContracts(); else goDashboard();
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
    });
  });

  // 계약 목록의 분류 필터 + 검색
  var rows = document.querySelectorAll('.js-contract-row');
  var state = {cat:'all', q:''};
  function refresh(){
    var n = 0;
    rows.forEach(function(row){
      var ok = (state.cat === 'all' || row.dataset.category === state.cat)
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
  var search = document.querySelector('.js-contract-search');
  if (search) {
    search.addEventListener('input', function(){
      state.q = search.value.trim().toLowerCase();
      refresh();
    });
  }
  refresh();

  // ── 당사자 관리 ───────────────────────────────────
  // 편집 결과는 브라우저에 저장돼 다시 열어도 유지된다. 서버가 없는 파일이므로
  // localStorage가 유일한 저장소다.
  document.querySelectorAll('[data-party-manager]').forEach(function(box){
    var contractId = box.dataset.partyManager;
    var key = 'clausa:parties:' + contractId;
    var state = {};
    try { state = JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) { state = {}; }
    state.edits = state.edits || {};
    state.hidden = state.hidden || [];
    state.added = state.added || [];

    var tbody = box.querySelector('tbody');
    var notice = box.querySelector('[data-notice]');
    var cmdBox = box.querySelector('[data-cmd]');

    function save(){ localStorage.setItem(key, JSON.stringify(state)); }

    function labelOf(row){
      var alias = row.querySelector('[data-field="alias"]').value.trim();
      var name = row.querySelector('[data-field="name"]').value.trim();
      var role = row.querySelector('[data-field="role"]').value.trim();
      var out = alias;
      if (name && name !== alias) out += ' (' + name + ')';
      if (role) out += ' · ' + role;
      return {alias: alias, name: name, role: role, label: out};
    }

    function applyRow(row){
      var id = row.dataset.partyRow;
      var v = labelOf(row);
      var hidden = row.dataset.hidden === '1';
      document.querySelectorAll('[data-party="' + id + '"]').forEach(function(el){
        el.style.display = hidden ? 'none' : '';
        if (el.hasAttribute('data-party-label')) el.textContent = v.label;
        if (el.hasAttribute('data-party-alias')) {
          el.textContent = v.alias + (el.classList.contains('adverse') ? ' 불리' : ' 유리');
        }
      });
      document.querySelectorAll('tr[data-party="' + id + '"]').forEach(function(tr){
        tr.style.display = hidden ? 'none' : '';
      });
    }

    function applyAll(){ tbody.querySelectorAll('[data-party-row]').forEach(applyRow); }

    function renderRemoved(){
      var box2 = box.querySelector('[data-removed]');
      var list = box.querySelector('[data-removed-list]');
      if (!box2 || !list) return;
      list.innerHTML = '';
      state.hidden.forEach(function(id){
        var btn = document.createElement('button');
        btn.dataset.act = 'restore';
        btn.dataset.restore = id;
        btn.textContent = id + ' 되돌리기';
        list.appendChild(btn);
      });
      box2.hidden = state.hidden.length === 0;
      box2.dataset.on = state.hidden.length ? '1' : '0';
    }

    function refreshNotice(){
      if (!state.added.length) { notice.dataset.on = '0'; return; }
      notice.dataset.on = '1';
      var flags = state.added.map(function(p){
        var spec = p.alias + (p.name ? '=' + p.name : '') + (p.role ? ':' + p.role : '');
        return '--add-party "' + spec + '"';
      }).join(' ');
      cmdBox.textContent = 'contract-review workspace ' + contractId + ' ' + flags;
    }

    // 저장된 편집 복원
    tbody.querySelectorAll('[data-party-row]').forEach(function(row){
      var id = row.dataset.partyRow;
      var saved = state.edits[id];
      if (saved) {
        ['alias','name','role'].forEach(function(f){
          if (saved[f] !== undefined) row.querySelector('[data-field="'+f+'"]').value = saved[f];
        });
      }
      if (state.hidden.indexOf(id) >= 0) row.dataset.hidden = '1';
    });
    state.added.forEach(function(p){ addRow(p, false); });
    applyAll();
    renderRemoved();
    refreshNotice();

    function addRow(party, persist){
      var tr = document.createElement('tr');
      tr.dataset.partyRow = party.id;
      tr.dataset.hidden = '0';
      tr.dataset.addedRow = '1';
      tr.innerHTML =
        '<td><input data-field="alias" value="' + party.alias + '"></td>' +
        '<td><input data-field="name" value="' + (party.name || '') + '"></td>' +
        '<td><input data-field="role" value="' + (party.role || '') + '"></td>' +
        '<td style="text-align:right"><span class="badge medium">재실행 필요</span> ' +
        '<button class="mini danger" data-act="remove">삭제</button></td>';
      tbody.appendChild(tr);
      if (persist) { state.added.push(party); save(); refreshNotice(); }
    }

    box.addEventListener('input', function(ev){
      var row = ev.target.closest('[data-party-row]');
      if (!row || !ev.target.dataset.field) return;
      var v = labelOf(row);
      state.edits[row.dataset.partyRow] = {alias:v.alias, name:v.name, role:v.role};
      save();
      applyRow(row);
    });

    box.addEventListener('click', function(ev){
      var act = ev.target.dataset.act;
      if (!act) return;
      var row = ev.target.closest('[data-party-row]');

      if (act === 'toggle') {
        var id = row.dataset.partyRow;
        row.dataset.hidden = '1';
        if (state.hidden.indexOf(id) < 0) state.hidden.push(id);
        save();
        applyRow(row);
        renderRemoved();
      } else if (act === 'restore') {
        var rid2 = ev.target.dataset.restore;
        state.hidden = state.hidden.filter(function(x){ return x !== rid2; });
        save();
        var target = tbody.querySelector('[data-party-row="' + rid2 + '"]');
        if (target) { target.dataset.hidden = '0'; applyRow(target); }
        renderRemoved();
      } else if (act === 'reset') {
        delete state.edits[row.dataset.partyRow];
        save();
        location.reload();
      } else if (act === 'remove') {
        var rid = row.dataset.partyRow;
        state.added = state.added.filter(function(p){ return p.id !== rid; });
        save();
        row.remove();
        refreshNotice();
      } else if (act === 'add') {
        var alias = box.querySelector('[data-new="alias"]').value.trim();
        if (!alias) return;
        var party = {
          id: alias,
          alias: alias,
          name: box.querySelector('[data-new="name"]').value.trim(),
          role: box.querySelector('[data-new="role"]').value.trim()
        };
        addRow(party, true);
        ['alias','name','role'].forEach(function(f){
          box.querySelector('[data-new="'+f+'"]').value = '';
        });
      }
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

      var names = Array.prototype.map.call(input.files, function(f){ return f.name; });
      if (!live) {
        say('err', '업로드는 서버 모드에서 동작합니다. 아래 명령으로 같은 작업을 할 수 있습니다.',
            'contract-review attach ' + contractId + ' ' + names.join(' '));
        return;
      }

      var form = new FormData();
      form.append('contract_id', contractId);
      ['title','category','labels','note'].forEach(function(f){
        if (get(f)) form.append(f, get(f));
      });
      Array.prototype.forEach.call(input.files, function(f){ form.append('files', f); });

      say('', '업로드 중…');
      fetch('/api/upload', {method:'POST', body: form})
        .then(function(r){ return r.json(); })
        .then(function(res){
          if (!res.ok) { say('err', res.error || '업로드에 실패했습니다.'); return; }
          var added = res.added.map(function(a){ return a.version + ' ' + a.label; }).join(', ');
          say('ok', added + ' 등록됨. 검토를 다시 계산합니다…');
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
<style>{BASE_CSS}{_CSS}</style></head>
<body>
<div class="app">
<aside class="side">
  <div class="brand">
    <div class="mark">CA</div>
    <div>
      <div class="name">{BRAND}</div>
      <div class="tag">{TAGLINE}</div>
    </div>
  </div>
  <div class="grp">워크스페이스</div>
  <button data-goto="dashboard" aria-current="true"><span>대시보드</span></button>
  <button data-goto="contracts"><span>계약</span><span class="cnt">{len(entries)}</span></button>
  <div class="grp">현황</div>
  <button disabled style="opacity:.45;cursor:default">
    <span>검토 대상 조문</span><span class="cnt">{total_high}</span></button>
  <button disabled style="opacity:.45;cursor:default">
    <span>등록 버전</span><span class="cnt">{total_versions}</span></button>
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
<script>{PANEL_JS}</script>
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
  <div><h2>대시보드</h2><p>계약 포트폴리오와 최근 개정 활동을 한눈에 확인합니다.</p></div>
  <div class="right">
    <button class="mini" data-export="contracts">계약대장 CSV</button>
    <button class="mini" data-export="versions">버전대장 CSV</button>
  </div>
</div>
<div class="kpis">{kpi_html}</div>
<div class="panels">
  <div class="card"><h2>최근 개정 활동</h2><div class="feed">{feed}</div></div>
  <div class="card"><h2>분류별 계약 수</h2><div class="dist">{dist}</div></div>
</div>"""


# ---------------------------------------------------------------- 계약 목록


def _contracts_view(entries, categories: list[str]) -> str:
    chips = '<button class="chip js-cat" data-value="all" aria-pressed="true">전체</button>'
    chips += "".join(
        f'<button class="chip js-cat" data-value="{_e(c)}" aria-pressed="false">{_e(c)}</button>'
        for c in categories
    )

    rows = "".join(
        f'<tr class="js-contract-row" data-open="{_e(e.contract_id)}" '
        f'data-title="{_e(e.label)}" data-category="{_e(e.category)}" '
        f'data-search="{_e((e.label + " " + e.contract_id + " " + e.category).lower())}">'
        f'<td><div class="name">{_e(e.label)}</div>'
        f'<div class="sub">{_e(e.contract_id)}'
        + (f" · 당사자 {' / '.join(_e(p) for p in e.parties)}" if e.parties else "")
        + "</div></td>"
        f'<td><span class="badge cat">{_e(e.category)}</span></td>'
        f'<td class="num">{len(e.versions)}</td>'
        f'<td><span class="badge latest">{_e(e.latest)}</span></td>'
        f'<td class="num">'
        + (f'<span class="badge">{e.flagged}</span>' if e.flagged else '<span class="ev">–</span>')
        + "</td>"
        f'<td class="mono">{_e(e.updated_at[:16])}</td></tr>'
        for e in entries
    ) or '<tr><td colspan="6" class="ev">등록된 계약이 없습니다.</td></tr>'

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
<div class="filters" style="margin-bottom:14px">{chips}</div>
{_uploader()}
<div class="tbl"><table>
<thead><tr><th>계약</th><th>분류</th><th style="text-align:right">버전</th><th>최신</th>
<th style="text-align:right">쟁점</th><th>최종 등록</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""


# ---------------------------------------------------------------- 계약 상세


def _detail_view(entry: ContractEntry, index: int) -> str:
    version_rows = "".join(
        "<tr><td><span class='badge"
        + (" latest" if record.version == entry.latest else "")
        + f"'>{_e(record.version)}</span></td>"
        f'<td><div class="name">{_e(record.label)}</div>'
        + (f'<div class="sub">{_e(record.note)}</div>' if record.note else "")
        + "</td>"
        f'<td class="mono">{_e(record.imported_at[:16])}</td>'
        f'<td class="mono">{_e(record.sha256[:12])}…</td></tr>'
        for record in entry.versions
    ) or '<tr><td colspan="4" class="ev">등록된 버전이 없습니다.</td></tr>'

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
        + f'<td style="text-align:right;white-space:nowrap">'
        f'<button class="mini" data-dl="csv" data-contract="{_e(entry.contract_id)}" '
        f'data-from="{_e(result.before_doc.version)}" data-to="{_e(result.after_doc.version)}">'
        "CSV</button> "
        f'<button class="mini" data-dl="md" data-contract="{_e(entry.contract_id)}" '
        f'data-from="{_e(result.before_doc.version)}" data-to="{_e(result.after_doc.version)}">'
        "MD</button></td></tr>"
        for order, result in enumerate(entry.results)
    ) or '<tr><td colspan="5" class="ev">검토된 비교본이 없습니다.</td></tr>'

    parties = " / ".join(_e(p) for p in entry.parties) or "인식된 당사자 없음"
    roster = _party_manager(entry)

    return f"""<div data-detail="{_e(entry.contract_id)}" hidden>
<div class="vhead">
  <div>
    <h2>{_e(entry.label)}</h2>
    <p><span class="badge cat">{_e(entry.category)}</span> &nbsp;{_e(entry.contract_id)}
    · 당사자 {parties}</p>
  </div>
  <div class="right">
    <button class="mini" data-dl="csv" data-contract="{_e(entry.contract_id)}">CSV</button>
    <button class="mini" data-dl="md" data-contract="{_e(entry.contract_id)}">Markdown</button>
    <button class="mini" data-dl="html" data-contract="{_e(entry.contract_id)}">HTML</button>
    <button class="mini" data-dl="json" data-contract="{_e(entry.contract_id)}">JSON</button>
    <span class="badge">버전 {len(entry.versions)}</span>
    {f'<span class="badge">검토 대상 {entry.flagged}</span>' if entry.flagged else ""}
    {f'<span class="badge">쟁점 {entry.issues}</span>' if entry.issues else ""}
  </div>
</div>

<div class="sec">
  <h3>버전 관리</h3>
  <p class="hint">등록된 원본은 SHA-256으로 고정됩니다. 협상 기록으로 그대로 인용할 수 있습니다.</p>
  <div class="tbl"><table>
  <thead><tr><th>버전</th><th>라벨</th><th>등록 일시</th><th>해시</th></tr></thead>
  <tbody>{version_rows}</tbody></table></div>
</div>

{_uploader(entry)}

{roster}

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
    """계약서 업로드 카드.

    서버 모드(`contract-review serve`)에서는 실제로 파일이 저장되고 버전이 등록된다.
    파일을 그냥 열었을 때는 저장할 곳이 없으므로, 같은 입력으로 실행할 CLI 명령을
    만들어 준다 — 되는 척하지 않는다.
    """
    if entry is None:
        head = "계약 등록"
        hint = "새 계약을 만들거나 기존 계약에 원본을 올립니다. hwpx·hwp·docx·pdf·txt 지원."
        id_field = '<input data-up="contract_id" placeholder="계약 ID (예: 2026-용역-007)">'
        meta = (
            '<input data-up="title" placeholder="계약명">'
            '<input data-up="category" placeholder="분류 (예: 용역·도급)">'
        )
    else:
        head = "버전 추가"
        hint = "협상 회차마다 받은 수정본을 올리면 다음 버전으로 등록됩니다."
        id_field = (
            f'<input data-up="contract_id" value="{_e(entry.contract_id)}" readonly '
            'style="background:#f7f8fa">'
        )
        meta = '<input data-up="labels" placeholder="버전 라벨 (예: 상대방 2차)">'

    return f"""<div class="sec upload-card" data-uploader>
  <h3>{head}</h3>
  <p class="hint">{hint}</p>
  <div class="card">
    <div class="addrow" style="border:0;margin:0;padding:0">
      {id_field}
      {meta}
      <input type="file" data-up="files" multiple
        style="flex:2 1 240px;font-size:12.5px;padding:6px 0">
      <button class="mini primary" data-act="upload">올리기</button>
    </div>
    <div class="upstate" data-upstate></div>
  </div>
</div>"""


def _party_manager(entry: ContractEntry) -> str:
    """당사자 명부 편집기.

    표기(약칭·상호·역할) 수정과 제외는 이 페이지에서 즉시 반영된다 — 검토 결과의
    영향 매트릭스 열과 조문 배지까지 함께 바뀐다. 반면 당사자를 새로 추가하면
    권리·의무 점수를 다시 계산해야 하므로, 재실행 명령을 함께 띄운다.
    """
    parties = _roster(entry)
    rows = "".join(
        f'<tr data-party-row="{_e(p["id"])}" data-hidden="0">'
        f'<td style="width:110px"><input data-field="alias" value="{_e(p["alias"])}"></td>'
        f'<td><input data-field="name" value="{_e(p["name"])}" placeholder="상호"></td>'
        f'<td style="width:150px"><input data-field="role" value="{_e(p["role"])}" '
        f'placeholder="역할"></td>'
        f'<td style="width:150px;text-align:right;white-space:nowrap">'
        f'<button class="mini" data-act="reset">되돌리기</button> '
        f'<button class="mini danger" data-act="toggle">삭제</button></td></tr>'
        for p in parties
    ) or '<tr><td colspan="4" class="ev">인식된 당사자가 없습니다.</td></tr>'

    return f"""<div class="sec" data-party-manager="{_e(entry.contract_id)}">
  <h3>당사자 관리</h3>
  <p class="hint">약칭·상호·역할을 고치면 검토 결과의 영향 매트릭스와 조문 배지에 즉시 반영됩니다.
  삭제한 당사자는 목록과 검토 결과에서 모두 사라지며, 아래에서 되돌릴 수 있습니다.</p>
  <div class="tbl party-tbl"><table>
  <thead><tr><th>약칭</th><th>상호</th><th>역할</th><th style="text-align:right">동작</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div style="padding:0 14px 14px">
    <div class="addrow">
      <input data-new="alias" placeholder="약칭 (예: 정)">
      <input data-new="name" placeholder="상호 (예: 주식회사 한울)">
      <input data-new="role" placeholder="역할 (예: 연대보증인)">
      <button class="mini primary" data-act="add">당사자 추가</button>
    </div>
    <div class="removed" data-removed hidden>
      <span class="lb">삭제된 당사자</span>
      <span data-removed-list></span>
    </div>
    <div class="notice" data-notice>
      <div>
        <b>추가한 당사자는 재실행이 필요합니다.</b>
        권리·의무 점수는 조문 원문을 다시 읽어야 계산됩니다. 아래 명령으로 재생성하십시오.
        <code data-cmd></code>
      </div>
    </div>
  </div></div>
</div>"""


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
