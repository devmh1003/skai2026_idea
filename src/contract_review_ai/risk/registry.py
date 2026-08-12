"""룰셋 구성 — 내장 룰 + 사용자 룰 파일 + 비활성화 목록.

내장 룰은 어느 계약에나 걸리는 공통 쟁점(손해배상·해지·IP·관할…)만 담는다.
업종·회사마다 반드시 봐야 하는 항목은 다르므로(하도급법 준수, 개인정보 국외이전,
ESG 조항, 사내 표준 문안 위반 등) 사용자가 파일로 얹거나 필요 없는 룰을 끌 수 있게 한다.

룰 파일은 JSON 또는 TOML.

    {
      "rules": [
        {
          "code": "SUBCON-LAW",
          "category": "하도급",
          "level": "high",
          "mode": "introduced",
          "pattern": "대금\\\\s*직접\\\\s*지급|하도급대금",
          "message": "하도급법상 직접지급 사유에 해당하는지 확인하십시오."
        }
      ],
      "disable": ["MFN"]
    }

같은 `code`를 쓰면 내장 룰을 덮어쓴다 — 문구만 사내 표현으로 바꾸거나 위험도를
조정할 때 쓴다.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from ..models import RiskLevel
from .rules import RULES, Rule

_REQUIRED = ("code", "category", "level", "mode", "pattern", "message")
_MODES = ("introduced", "removed", "changed")
_LEVELS = {level.value: level for level in RiskLevel}


class RuleFileError(ValueError):
    """룰 파일이 잘못됐을 때. 어느 항목이 왜 틀렸는지까지 담는다."""


def load_rule_file(path: str | Path) -> tuple[list[Rule], list[str]]:
    """(룰 목록, 비활성화할 코드 목록)."""
    p = Path(path)
    if not p.is_file():
        raise RuleFileError(f"룰 파일을 찾을 수 없습니다: {p}")

    suffix = p.suffix.lower()
    try:
        if suffix == ".toml":
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        elif suffix in {".json", ".jsonc", ""}:
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            raise RuleFileError(f"룰 파일은 .json 또는 .toml이어야 합니다: {p}")
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RuleFileError(f"룰 파일을 읽을 수 없습니다 ({p}): {exc}") from exc

    if not isinstance(data, dict):
        raise RuleFileError(f"룰 파일 최상위는 객체여야 합니다: {p}")

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise RuleFileError(f"'rules'는 배열이어야 합니다: {p}")

    rules = [_parse_rule(item, p, index) for index, item in enumerate(raw_rules)]

    disable = data.get("disable", [])
    if not isinstance(disable, list):
        raise RuleFileError(f"'disable'은 배열이어야 합니다: {p}")

    return rules, [str(code).strip() for code in disable if str(code).strip()]


def _parse_rule(item: Any, path: Path, index: int) -> Rule:
    where = f"{path} rules[{index}]"
    if not isinstance(item, dict):
        raise RuleFileError(f"{where}: 객체가 아닙니다.")

    missing = [key for key in _REQUIRED if not str(item.get(key, "")).strip()]
    if missing:
        raise RuleFileError(f"{where}: 필수 항목 누락 — {', '.join(missing)}")

    level = str(item["level"]).strip().lower()
    if level not in _LEVELS:
        raise RuleFileError(
            f"{where}: level은 {', '.join(_LEVELS)} 중 하나여야 합니다 (받은 값: {level})"
        )

    mode = str(item["mode"]).strip().lower()
    if mode not in _MODES:
        raise RuleFileError(
            f"{where}: mode는 {', '.join(_MODES)} 중 하나여야 합니다 (받은 값: {mode})"
        )

    pattern = str(item["pattern"])
    try:
        re.compile(pattern)
    except re.error as exc:
        raise RuleFileError(f"{where}: 정규식이 잘못됐습니다 — {exc}") from exc

    return Rule(
        code=str(item["code"]).strip(),
        category=str(item["category"]).strip(),
        level=_LEVELS[level],
        mode=mode,
        pattern=pattern,
        message=str(item["message"]).strip(),
    )


def build_ruleset(
    rule_files: list[str] | None = None,
    disable: list[str] | None = None,
    include_builtin: bool = True,
) -> tuple[tuple[Rule, ...], set[str]]:
    """최종 룰 목록과 비활성화 코드 집합을 만든다.

    비활성화 집합을 따로 돌려주는 이유: 수치변경·조문삭제처럼 룰 표가 아니라
    코드로 붙는 합성 플래그도 같은 방식으로 끌 수 있어야 하기 때문이다.
    """
    by_code: dict[str, Rule] = {}
    if include_builtin:
        by_code = {rule.code: rule for rule in RULES}

    disabled = {code.strip() for code in (disable or []) if code.strip()}

    for path in rule_files or []:
        rules, file_disable = load_rule_file(path)
        for rule in rules:
            by_code[rule.code] = rule  # 같은 코드면 덮어쓴다
        disabled.update(file_disable)

    active = tuple(rule for rule in by_code.values() if rule.code not in disabled)
    return active, disabled


def export_rules(rules: tuple[Rule, ...], path: str | Path) -> Path:
    """현재 룰셋을 파일로 내보낸다. 사용자 룰 작성의 출발점."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "rules": [
            {
                "code": rule.code,
                "category": rule.category,
                "level": rule.level.value,
                "mode": rule.mode,
                "pattern": rule.pattern,
                "message": rule.message,
            }
            for rule in rules
        ],
        "disable": [],
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
