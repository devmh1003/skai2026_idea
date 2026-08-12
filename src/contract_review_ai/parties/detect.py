"""계약 당사자 자동 인식.

`주식회사 가나다(이하 "갑"이라 한다)` 형태의 정의 문언을 찾아 약칭과 정식 명칭을
연결한다. 2자 계약뿐 아니라 병·정… 이 등장하는 다자간 계약도 같은 방식으로 잡는다.
"""

from __future__ import annotations

import re

from ..models import Party

# (이하 "갑"이라 한다) / (이하 “수급인”이라고 한다) / (이하 '병'이라 칭한다)
_ALIAS_RE = re.compile(
    r"[(（]\s*이하\s*[\"'“”‘’]?\s*(?P<alias>[^\"'“”‘’)）\s]{1,16})\s*[\"'“”‘’]?\s*"
    r"(?:이?라(?:고)?)\s*(?:한다|칭한다|합니다)\s*[)）]"
)

_NAME_SPLIT_RE = re.compile(r"[\n,、·)）]|와\s|과\s|및\s")

_ROLE_HINTS: tuple[tuple[str, str], ...] = (
    ("발주", "발주자"),
    ("수급", "수급인"),
    ("위탁", "위탁자"),
    ("수탁", "수탁자"),
    ("공급", "공급자"),
    ("매도", "매도인"),
    ("매수", "매수인"),
    ("보증", "보증인"),
    ("임대", "임대인"),
    ("임차", "임차인"),
)

_DEFAULT_ALIASES = ("갑", "을", "병", "정", "무", "기")
_DEFAULT_ROLES = {"갑": "발주자", "을": "수급인", "병": "제3당사자", "정": "제4당사자"}


def detect_parties(text: str) -> list[Party]:
    """본문에서 당사자를 찾는다. 정의 문언이 없으면 갑/을/병… 등장 여부로 보완."""
    parties: list[Party] = []
    seen: set[str] = set()

    for match in _ALIAS_RE.finditer(text):
        alias = match.group("alias").strip()
        if not alias or alias in seen:
            continue
        seen.add(alias)
        parties.append(
            Party(
                id=alias,
                alias=alias,
                name=_name_before(text, match.start()),
                role=_guess_role(alias, _name_before(text, match.start())),
            )
        )

    for alias in _DEFAULT_ALIASES:
        if alias in seen:
            continue
        if re.search(rf"(?<![가-힣]){re.escape(alias)}(?=[은는이가을를에의와과도만]|\s|,|\.)", text):
            seen.add(alias)
            parties.append(
                Party(id=alias, alias=alias, name="", role=_DEFAULT_ROLES.get(alias, ""))
            )

    parties.sort(key=lambda p: _order(p.alias))
    return parties


def merge_parties(*groups: list[Party]) -> list[Party]:
    """원본·개정본에서 각각 인식한 당사자를 합친다(개정본 정보 우선)."""
    merged: dict[str, Party] = {}
    for group in groups:
        for party in group:
            existing = merged.get(party.id)
            if existing is None:
                merged[party.id] = Party(party.id, party.alias, party.name, party.role)
                continue
            existing.name = existing.name or party.name
            existing.role = existing.role or party.role
    return sorted(merged.values(), key=lambda p: _order(p.alias))


def parse_party_spec(spec: str) -> Party:
    """`약칭[=정식명칭][:역할]` 문자열을 Party로 바꾼다.

        "병"                              → 약칭만
        "병=주식회사 사아자"               → 상호까지
        "병=주식회사 사아자:연대보증인"     → 역할까지
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("당사자 표기가 비어 있습니다.")

    head, _, role = spec.partition(":")
    alias, _, name = head.partition("=")
    alias = alias.strip()
    if not alias:
        raise ValueError(f"약칭을 읽을 수 없습니다: {spec!r}")

    return Party(
        id=alias,
        alias=alias,
        name=name.strip(),
        role=role.strip() or _guess_role(alias, name.strip()),
    )


def apply_overrides(
    parties: list[Party],
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> list[Party]:
    """자동 인식 결과에 사용자의 추가·삭제 지시를 반영한다.

    자동 인식은 정의 문언이 없는 계약서(별지 합의서, 각서 등)에서 당사자를
    놓치거나, 반대로 예시 문구를 당사자로 잘못 잡을 수 있다. 최종 판단은
    사용자가 하도록 남긴다.
    """
    dropped = {name.strip() for name in (remove or []) if name.strip()}
    result = [p for p in parties if p.id not in dropped and p.alias not in dropped]

    for spec in add or []:
        party = parse_party_spec(spec)
        existing = next((p for p in result if p.id == party.id), None)
        if existing is None:
            result.append(party)
            continue
        # 이미 인식된 당사자면 사용자가 준 정보로 덮어쓴다.
        existing.name = party.name or existing.name
        existing.role = party.role or existing.role

    return sorted(result, key=lambda p: _order(p.alias))


def _name_before(text: str, position: int) -> str:
    """정의 문언 바로 앞의 상호를 잘라낸다."""
    head = text[max(0, position - 60) : position]
    chunks = _NAME_SPLIT_RE.split(head)
    name = chunks[-1].strip() if chunks else ""
    return re.sub(r'^["\'“”‘’(（\s]+', "", name).strip()


def _guess_role(alias: str, name: str) -> str:
    for keyword, role in _ROLE_HINTS:
        if keyword in alias or keyword in name:
            return role
    return _DEFAULT_ROLES.get(alias, "")


def _order(alias: str) -> tuple[int, str]:
    if alias in _DEFAULT_ALIASES:
        return (_DEFAULT_ALIASES.index(alias), alias)
    return (len(_DEFAULT_ALIASES), alias)
