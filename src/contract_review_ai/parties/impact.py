"""당사자별 유·불리 영향 추정.

조문을 문장으로 쪼개고, 각 문장에서 당사자 약칭이 등장할 때 그 문장이
'의무'를 지우는 문장인지 '권리'를 주는 문장인지를 어미·서술어로 판정한다.
점수 = 권리 수 − 의무 수, 변경 전후 점수 차이가 그 당사자의 영향 방향이다.

법적 판단이 아니라 검토 우선순위를 정하는 신호다. 리포트에도 그렇게 표기한다.
"""

from __future__ import annotations

import re

from ..models import Clause, ClauseComparison, Party, PartyImpact

_SENTENCE_RE = re.compile(r"[^\n.。]+[.。]?")

_OBLIGATION_RE = re.compile(
    r"하여야\s*한다|해야\s*한다|하여야\s*하며|아니\s*된다|않는다|말아야|부담한다|부담하며"
    r"|지급한다|지급하여야|배상하여야|배상한다|책임을\s*진다|의무를\s*진다|면책하여야"
    r"|제공하지\s*아니한다|귀속한다|지급하여야\s*한다|준수하여야"
)
_RIGHT_RE = re.compile(
    r"할\s*수\s*있다|청구할\s*수\s*있다|요구할\s*수\s*있다|해지할\s*수\s*있다"
    r"|감액할\s*수\s*있다|권리를\s*가진다|보유한다|책임을\s*지지\s*아니한다"
    r"|책임을\s*부담하지\s*아니한다|면책된다"
)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    # 조사가 붙어도 잡되, 다른 낱말의 일부로 걸리지 않도록 앞자리를 막는다.
    return re.compile(rf"(?<![가-힣]){re.escape(alias)}")


def score_text(text: str, party: Party) -> tuple[int, int]:
    """(의무 수, 권리 수)."""
    if not text:
        return (0, 0)

    pattern = _alias_pattern(party.alias)
    name_pattern = _alias_pattern(party.name) if len(party.name) >= 2 else None

    obligations = rights = 0
    for sentence in _SENTENCE_RE.findall(text):
        hit = pattern.search(sentence) or (name_pattern and name_pattern.search(sentence))
        if not hit:
            continue
        if _RIGHT_RE.search(sentence):
            rights += 1
        if _OBLIGATION_RE.search(sentence):
            obligations += 1
    return (obligations, rights)


def analyze_impacts(comp: ClauseComparison, parties: list[Party]) -> list[PartyImpact]:
    impacts: list[PartyImpact] = []
    before = _text(comp.before)
    after = _text(comp.after)

    for party in parties:
        b_obl, b_rig = score_text(before, party)
        a_obl, a_rig = score_text(after, party)
        impacts.append(
            PartyImpact(
                party_id=party.id,
                alias=party.alias,
                before_obligations=b_obl,
                before_rights=b_rig,
                after_obligations=a_obl,
                after_rights=a_rig,
            )
        )
    return impacts


def _text(clause: Clause | None) -> str:
    return clause.full_text if clause else ""
