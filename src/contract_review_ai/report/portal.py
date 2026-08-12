"""여러 계약·여러 비교본을 한 페이지에 담는 포털.

검토 결과를 바로 펼치지 않고 두 번 고르게 한다.

    1단계  어떤 계약인가        — 계약 카드 목록
    2단계  어떤 비교본인가       — v1→v2, v2→v3, v1→최신 …
    3단계  검토 결과            — 조문 대비 / 당사자 영향 / 개정 연혁

협상이 몇 차례 오간 계약이 여러 건 굴러가는 상황에서, 파일을 찾아 열지 않고
한 페이지에서 고르게 하려는 구조다. 결과 패널은 `html.render_result_panel`을
그대로 재사용하므로 단건 리포트와 화면이 완전히 같다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import DISCLAIMER
from ..models import ReviewResult
from .html import CSS, JS, render_result_panel

_PORTAL_JS = """
(function(){
  var screens = {
    contracts: document.querySelector('[data-screen="contracts"]'),
    samples: document.querySelector('[data-screen="samples"]'),
    result: document.querySelector('[data-screen="result"]')
  };
  var crumbContract = document.querySelector('.js-crumb-contract');
  var crumbSample = document.querySelector('.js-crumb-sample');

  function show(name){
    Object.keys(screens).forEach(function(key){
      if (screens[key]) screens[key].hidden = (key !== name);
    });
    window.scrollTo(0, 0);
  }

  function pickContract(id, title){
    document.querySelectorAll('[data-sample]').forEach(function(el){
      el.hidden = (el.dataset.contract !== id);
    });
    if (crumbContract) { crumbContract.textContent = title; crumbContract.hidden = false; }
    if (crumbSample) crumbSample.hidden = true;
    show('samples');
  }

  function pickSample(key, label){
    document.querySelectorAll('[data-result]').forEach(function(el){
      el.hidden = (el.dataset.result !== key);
    });
    if (crumbSample) { crumbSample.textContent = label; crumbSample.hidden = false; }
    show('result');
  }

  document.querySelectorAll('[data-contract-pick]').forEach(function(btn){
    btn.addEventListener('click', function(){
      pickContract(btn.dataset.contractPick, btn.dataset.title);
    });
  });
  document.querySelectorAll('[data-sample]').forEach(function(btn){
    btn.addEventListener('click', function(){
      pickSample(btn.dataset.sample, btn.dataset.label);
    });
  });
  document.querySelectorAll('.js-home').forEach(function(btn){
    btn.addEventListener('click', function(){
      if (crumbContract) crumbContract.hidden = true;
      if (crumbSample) crumbSample.hidden = true;
      show('contracts');
    });
  });
  document.querySelectorAll('.js-back-samples').forEach(function(btn){
    btn.addEventListener('click', function(){
      if (crumbSample) crumbSample.hidden = true;
      show('samples');
    });
  });
})();
"""

@dataclass
class PortalContract:
    """포털 한 칸 — 계약 하나와 그 비교본들."""

    contract_id: str
    title: str = ""
    results: list[ReviewResult] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.title or self.contract_id

    @property
    def high(self) -> int:
        return sum(r.risk_counts()["high"] for r in self.results)


def render_portal(contracts: list[PortalContract], heading: str = "계약 검토 리포트") -> str:
    cards, samples, panels = [], [], []

    for index, contract in enumerate(contracts):
        cards.append(
            f'<button class="pick" data-contract-pick="{_e(contract.contract_id)}" '
            f'data-title="{_e(contract.label)}">'
            '<span class="arrow">›</span>'
            f'<div class="eyebrow">{_e(contract.contract_id)}</div>'
            f"<h3>{_e(contract.label)}</h3>"
            f'<div class="desc">{_e(_version_span(contract))}</div>'
            '<div class="metrics">'
            + _metrics([("비교본", len(contract.results), ""), ("고위험", contract.high, "high")])
            + "</div></button>"
        )

        for order, result in enumerate(contract.results):
            key = f"{index}-{order}"
            risks = result.risk_counts()
            counts = result.counts()
            label = f"{result.before_doc.name} → {result.after_doc.name}"
            metrics = _metrics(
                [
                    ("수정", counts["modified"], ""),
                    ("신설", counts["added"], ""),
                    ("삭제", counts["deleted"], ""),
                    ("고위험", risks["high"], "high"),
                    ("중위험", risks["medium"], "medium"),
                ]
            )
            samples.append(
                f'<button class="pick" data-sample="{key}" '
                f'data-contract="{_e(contract.contract_id)}" data-label="{_e(label)}" hidden>'
                '<span class="arrow">›</span>'
                f'<div class="eyebrow">비교본 {order + 1}</div>'
                f"<h3>{_e(label)}</h3>"
                f'<div class="desc">{_e(result.generated_at)} · '
                f"당사자 {len(result.parties)}인 · {_e(result.backend)}</div>"
                f'<div class="metrics">{metrics}</div></button>'
            )
            panels.append(
                f'<div data-result="{key}" hidden>{render_result_panel(result)}</div>'
            )

    if not cards:
        cards.append('<div class="empty">등록된 계약이 없습니다.</div>')

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(heading)}</title>
<style>{CSS}</style></head>
<body>
<div class="masthead"><div class="inner">
  <div class="logo">CR</div>
  <div>
    <h1>{_e(heading)}</h1>
    <div class="sub">계약 선택 → 비교본 선택 → 검토 결과</div>
  </div>
  <div class="crumbs">
    <button class="js-home">전체 계약</button>
    <span>›</span><button class="js-crumb-contract js-back-samples" hidden></button>
    <span>›</span><button class="js-crumb-sample" hidden></button>
  </div>
</div></div>

<div class="wrap">
<div class="screen" data-screen="contracts">
  <h2 class="big">계약 선택</h2>
  <p class="lead">검토할 계약을 선택하십시오.</p>
  <div class="picker">{"".join(cards)}</div>
</div>

<div class="screen" data-screen="samples" hidden>
  <h2 class="big">비교본 선택</h2>
  <p class="lead">버전 조합을 선택하면 조문별 대비와 법무 코멘트를 확인할 수 있습니다.</p>
  <div class="picker">{"".join(samples)}</div>
</div>

<div class="screen" data-screen="result" hidden>
{"".join(panels)}
</div>

<div class="disclaimer">{_e(DISCLAIMER)}</div>
<script>{JS}</script>
<script>{_PORTAL_JS}</script>
</div></body></html>"""


def _metrics(items: list[tuple[str, int, str]]) -> str:
    """카드 하단의 수치 묶음. 0인 항목은 지운다."""
    return "".join(
        f'<div><div class="n {cls}">{value}</div><div class="k">{_e(label)}</div></div>'
        for label, value, cls in items
        if value
    )


def _version_span(contract: PortalContract) -> str:
    versions = [
        v
        for result in contract.results
        for v in (result.before_doc.version, result.after_doc.version)
        if v
    ]
    if not versions:
        return f"비교본 {len(contract.results)}건"
    unique = sorted(set(versions), key=lambda v: int("".join(c for c in v if c.isdigit()) or 0))
    return f"{unique[0]} ~ {unique[-1]} · 버전 {len(unique)}개"


def _e(text: str) -> str:
    import html as _html

    return _html.escape(str(text or ""))
