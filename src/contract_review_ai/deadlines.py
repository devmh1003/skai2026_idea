"""계약 기한을 조문에서 뽑아낸다.

법무팀이 계약을 놓치는 가장 흔한 경로는 검토 실수가 아니라 **날짜**다.
자동 갱신 계약의 갱신 거절 통지 기한을 넘기면 조건이 그대로 1년 더 굴러간다.
계약기간 조문에 이미 적혀 있는 정보이므로, 읽어서 앞으로 당겨 보여 준다.

    종료일        "2026년 12월 31일까지" → 2026-12-31
    통지 기한     "만료 1개월 전까지 …통지"  → 종료일 − 1개월
    자동 갱신     "자동으로 갱신된다" 문구 유무

날짜 표기가 별첨에 있거나 "체결일부터 2년"처럼 기산점이 문서 밖에 있는 계약은
뽑히지 않는다. 그 경우 값을 지어내지 않고 비워 둔다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from .models import Clause

_TERM_TITLES = ("계약기간", "기간", "임대차 기간", "계약 기간", "존속")
_DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_NOTICE_RE = re.compile(
    r"(?:만료|종료)[^.。\n]{0,20}?(\d{1,2})\s*(개월|일|주)\s*전(?:까지)?"
)
_AUTO_RE = re.compile(r"자동(?:으로)?\s*(?:갱신|연장)")


@dataclass
class Deadline:
    """계약 하나에서 읽어 낸 기한."""

    ends_on: date | None = None
    notify_by: date | None = None
    auto_renew: bool = False
    source: str = ""
    """근거 조문 제목."""

    @property
    def known(self) -> bool:
        return self.ends_on is not None

    def days_left(self, today: date | None = None) -> int | None:
        if self.ends_on is None:
            return None
        return (self.ends_on - (today or date.today())).days

    def notice_days_left(self, today: date | None = None) -> int | None:
        if self.notify_by is None:
            return None
        return (self.notify_by - (today or date.today())).days

    def urgency(self, today: date | None = None) -> str:
        """지남 / 임박(30일 이내) / 여유 / 알 수 없음."""
        target = self.notify_by or self.ends_on
        if target is None:
            return "unknown"
        left = (target - (today or date.today())).days
        if left < 0:
            return "passed"
        return "soon" if left <= 30 else "ok"


def extract(clauses: list[Clause]) -> Deadline:
    """계약기간 조문에서 종료일·통지 기한·자동갱신 여부를 읽는다."""
    for clause in clauses:
        if not any(hint in clause.title for hint in _TERM_TITLES):
            continue

        text = clause.full_text
        dates = [_to_date(m) for m in _DATE_RE.finditer(text)]
        dates = [d for d in dates if d]
        if not dates:
            continue

        deadline = Deadline(ends_on=max(dates), source=clause.heading)
        deadline.auto_renew = bool(_AUTO_RE.search(text))

        notice = _NOTICE_RE.search(text)
        if notice:
            amount, unit = int(notice.group(1)), notice.group(2)
            days = {"개월": 30, "주": 7, "일": 1}[unit] * amount
            deadline.notify_by = deadline.ends_on - timedelta(days=days)
        return deadline

    return Deadline()


def _to_date(match: re.Match[str]) -> date | None:
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
