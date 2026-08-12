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
