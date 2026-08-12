"""당사자별 유·불리 영향 추정.

조문을 문장으로 쪼갠 뒤, 각 문장에서 **누가 주체인지**를 조사로 판별한다.
계약 문장은 대부분 "A는 B에게 …하여야 한다" 꼴이라, 주체와 객체를 구분하지
않고 세면 한 문장에 등장하는 모든 당사자가 같은 방향으로 계산되어 버린다.

    주체(은/는/이/가)  — 권리 표현이면 유리, 의무 표현이면 불리
    객체(에게/을/를/의) — 반대로 계산. 상대가 권리를 얻으면 나는 부담을 지고,
                          상대의 의무가 나를 향하면 나는 이익을 얻는다.

예) "갑은 을에 대한 최고 없이 병에게 직접 이행을 청구할 수 있다."
    → 갑 유리(+1), 병 불리(-1)

점수 = 권리 수 − 의무 수. 변경 전후 점수 차이가 그 당사자의 영향 방향이다.
법적 판단이 아니라 검토 우선순위를 정하는 신호이며, 리포트에도 그렇게 표기한다.
"""

from __future__ import annotations

import re

from ..models import Clause, ClauseComparison, Party, PartyImpact

_SENTENCE_RE = re.compile(r"[^\n.。]+[.。]?")

_OBLIGATION_RE = re.compile(
    r"하여야\s*한다|해야\s*한다|하여야\s*하며|아니\s*된다|아니한다|않는다|말아야"
    r"|부담한다|부담하며|지급한다|지급하여야|배상하여야|배상한다|보증한다|담보한다"
    r"|책임을\s*진다|의무를\s*진다|면책하여야|귀속한다|귀속하며|준수하여야|허락한다"
)
_RIGHT_RE = re.compile(
    r"할\s*수\s*있다|청구할\s*수\s*있다|요구할\s*수\s*있다|해지할\s*수\s*있다"
    r"|감액할\s*수\s*있다|권리를\s*가진다|보유한다|책임을\s*지지\s*아니한다"
    r"|책임을\s*부담하지\s*아니한다|면책된다"
)

_SUBJECT_JOSA = {"은": 2, "는": 2, "이": 1, "가": 1}
_JOSA_RE = "은|는|이|가|에게|에|을|를|의|과|와|도|만|으로부터|로부터"


def _mention_re(term: str) -> re.Pattern[str]:
    # 조사가 붙어도 잡되, 다른 낱말의 일부로 걸리지 않도록 앞자리를 막는다.
    return re.compile(rf"(?<![가-힣]){re.escape(term)}({_JOSA_RE})?")


def _mentions(sentence: str, party: Party) -> list[tuple[int, str]]:
    """(위치, 조사) 목록. 약칭과 정식 명칭을 모두 본다."""
    found = [(m.start(), m.group(1) or "") for m in _mention_re(party.alias).finditer(sentence)]
    if len(party.name) >= 2:
        found += [(m.start(), m.group(1) or "") for m in _mention_re(party.name).finditer(sentence)]
    return found


def _subject_of(sentence: str, parties: list[Party]) -> str | None:
    """주절 주어로 볼 당사자.

    주제 조사(은/는)를 주격 조사(이/가)보다 우선한다. 한국어 계약 문장에서
    "을이 위반한 경우 갑은 …할 수 있다"처럼 종속절 주어가 이/가를 취하고
    주절 주어가 은/는을 취하는 형태가 지배적이기 때문이다. 같은 등급이면
    뒤에 나온 쪽을 택한다.
    """
    best: tuple[int, int, str] | None = None
    for party in parties:
        for position, josa in _mentions(sentence, party):
            rank = _SUBJECT_JOSA.get(josa)
            if rank is None:
                continue
            candidate = (rank, position, party.id)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    return best[2] if best else None


def score_text(text: str, party: Party, parties: list[Party] | None = None) -> tuple[int, int]:
    """(의무 수, 권리 수)."""
    if not text:
        return (0, 0)

    others = parties if parties is not None else [party]
    obligations = rights = 0

    for sentence in _SENTENCE_RE.findall(text):
        if not _mentions(sentence, party):
            continue

        has_right = bool(_RIGHT_RE.search(sentence))
        has_obligation = bool(_OBLIGATION_RE.search(sentence))
        if not (has_right or has_obligation):
            continue

        if _subject_of(sentence, others) == party.id:
            rights += has_right
            obligations += has_obligation
        else:
            # 객체 위치 — 상대의 권리는 내 부담, 상대의 의무는 내 이익.
            obligations += has_right
            rights += has_obligation

    return (obligations, rights)


def analyze_impacts(comp: ClauseComparison, parties: list[Party]) -> list[PartyImpact]:
    before = _text(comp.before)
    after = _text(comp.after)

    impacts: list[PartyImpact] = []
    for party in parties:
        b_obl, b_rig = score_text(before, party, parties)
        a_obl, a_rig = score_text(after, party, parties)
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
