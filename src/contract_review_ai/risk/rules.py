"""룰 기반 위험 탐지.

LLM에 판단을 통째로 맡기지 않고, 먼저 결정론적 룰로 "무엇을 봐야 하는지"를
좁힌다. 이 플래그는 (1) LLM 프롬프트의 근거로 들어가고 (2) 모델이 놓치더라도
리포트에 남아 검토자가 확인할 수 있게 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import ChangeStatus, ClauseComparison, RiskFlag, RiskLevel

# mode:
#   introduced — 개정본에서 새로 등장 (위험이 추가됨)
#   removed    — 원본에 있었으나 사라짐 (보호장치가 빠짐)
#   changed    — 양쪽 중 하나라도 걸리고 문언이 바뀜 (내용 확인 필요)


@dataclass(frozen=True)
class Rule:
    code: str
    category: str
    level: RiskLevel
    mode: str
    pattern: str
    message: str

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


RULES: tuple[Rule, ...] = (
    Rule(
        "LIAB-UNLIMITED",
        "손해배상",
        RiskLevel.HIGH,
        "introduced",
        r"(일체의|모든|전부의)\s*(손해|책임)|제한\s*없이\s*배상|무한\s*책임",
        "손해배상 범위를 무제한으로 확장하는 문언이 추가되었습니다. 책임 상한(계약금액 100% 등)과 "
        "간접·특별·결과적 손해 제외 문언을 요구하십시오.",
    ),
    Rule(
        "LIAB-CAP-REMOVED",
        "손해배상",
        RiskLevel.HIGH,
        "removed",
        r"(책임|배상)(의)?\s*(한도|상한)|(초과하지|넘지)\s*(아니한다|않는다)|한도로\s*한다",
        "책임 한도(cap) 조항이 삭제되었습니다. 삭제 경위를 확인하고 상한 복원을 요구하십시오.",
    ),
    Rule(
        "LIAB-INDIRECT-REMOVED",
        "손해배상",
        RiskLevel.MEDIUM,
        "removed",
        r"(간접|특별|결과적|파생적)\s*손해|일실\s*이익",
        "간접·특별·결과적 손해 배제 문언이 사라졌습니다. 배상 범위가 실질적으로 확대될 수 있습니다.",
    ),
    Rule(
        "PENALTY-BREACH",
        "위약벌",
        RiskLevel.HIGH,
        "introduced",
        r"위약벌|손해배상액의\s*예정|배상액을\s*예정",
        "위약벌 또는 손해배상액 예정 조항이 추가되었습니다. 위약벌은 감액이 어려우므로 "
        "'손해배상액의 예정'으로 성질을 명시하고 금액 적정성을 다투십시오.",
    ),
    Rule(
        "TERM-UNILATERAL",
        "계약해지",
        RiskLevel.HIGH,
        "introduced",
        r"(언제든지|사전\s*(통지|통보)\s*없이|일방적으로)[^.。\n]{0,40}(해지|해제)"
        r"|(해지|해제)[^.。\n]{0,30}(언제든지|사전\s*(통지|통보)\s*없이)",
        "상대방의 일방적·즉시 해지권이 추가되었습니다. 최고(催告) 절차와 시정 기간(예: 30일), "
        "해지 사유의 한정을 요구하십시오.",
    ),
    Rule(
        "TERM-CURE-REMOVED",
        "계약해지",
        RiskLevel.MEDIUM,
        "removed",
        r"(시정|치유)\s*(기간|기회)|최고|상당한\s*기간을\s*정하여",
        "해지 전 시정 기회(cure period) 문언이 삭제되었습니다.",
    ),
    Rule(
        "IP-ASSIGN",
        "지식재산권",
        RiskLevel.HIGH,
        "changed",
        r"(지식재산권|지적재산권|저작권|특허)[^.。\n]{0,40}(귀속|양도|이전)",
        "지식재산권 귀속 조항이 변경되었습니다. 기존 보유 IP(background IP)와 산출물 IP를 "
        "분리하고, 최소한 자사 업무용 실시권(license-back)을 확보하십시오.",
    ),
    Rule(
        "IP-MORAL",
        "지식재산권",
        RiskLevel.MEDIUM,
        "introduced",
        r"저작인격권[^.。\n]{0,30}(행사하지|포기)",
        "저작인격권 불행사·포기 문언이 추가되었습니다. 실무상 유효성 논란이 있으므로 범위를 한정하십시오.",
    ),
    Rule(
        "INDEMNITY",
        "면책·보상",
        RiskLevel.HIGH,
        "introduced",
        r"면책(하고|시키고|하여야)|방어[^.。\n]{0,20}배상|일체의\s*책임을\s*진다",
        "면책·방어(indemnify & defend) 의무가 추가되었습니다. 대상 청구의 범위, 통지 절차, "
        "방어 주도권, 상한 적용 여부를 확인하십시오.",
    ),
    Rule(
        "DISCLAIM",
        "면책·보상",
        RiskLevel.MEDIUM,
        "introduced",
        r"책임을\s*(지지|부담하지)\s*(아니한다|않는다)|어떠한\s*책임도\s*없다",
        "상대방의 면책(책임 부인) 문언이 추가되었습니다. 자사에 불리한 일방적 면책인지 확인하십시오.",
    ),
    Rule(
        "LATE-FEE",
        "지체상금",
        RiskLevel.MEDIUM,
        "changed",
        r"지체상금|지연배상|지연손해금",
        "지체상금·지연손해금 조항이 변경되었습니다. 요율, 산정 기준금액, 상한(총액의 10% 등)을 "
        "함께 확인하십시오.",
    ),
    Rule(
        "PAYMENT-TERM",
        "대금지급",
        RiskLevel.MEDIUM,
        "changed",
        r"(대금|보수|용역료|계약금액)[^.。\n]{0,40}(지급|지불)|(지급|검수)\s*(기일|기한)|익월",
        "대금 지급 조건이 변경되었습니다. 지급 기일 연장은 현금흐름에 직접 영향을 주며, "
        "하도급거래 시 법정 지급기일(60일) 제한을 검토해야 합니다.",
    ),
    Rule(
        "PAYMENT-DEDUCT",
        "대금지급",
        RiskLevel.MEDIUM,
        "introduced",
        r"(감액|차감|공제|상계)(할\s*수\s*있다|한다)",
        "일방적 감액·상계 권한이 추가되었습니다. 사유를 한정하고 사전 협의 절차를 요구하십시오.",
    ),
    Rule(
        "CONF-SCOPE",
        "비밀유지",
        RiskLevel.MEDIUM,
        "changed",
        r"비밀\s*유지|기밀|비밀정보",
        "비밀유지 조항이 변경되었습니다. 비밀정보의 정의, 예외 사유, 존속 기간의 대칭성을 확인하십시오.",
    ),
    Rule(
        "LAW-JURIS",
        "준거법·분쟁해결",
        RiskLevel.HIGH,
        "changed",
        r"준거법|관할\s*법원|중재|분쟁의\s*해결",
        "준거법 또는 분쟁해결 조항이 변경되었습니다. 외국 준거법·해외 중재지는 분쟁 비용을 "
        "크게 높이므로 관할 변경 여부를 반드시 확인하십시오.",
    ),
    Rule(
        "AUTO-RENEW",
        "계약기간",
        RiskLevel.MEDIUM,
        "introduced",
        r"자동(으로)?\s*(갱신|연장)",
        "자동 갱신 조항이 추가되었습니다. 갱신 거절 통지 기한과 갱신 시 조건 변경 가능성을 확인하십시오.",
    ),
    Rule(
        "SUB-CONTRACT",
        "재위탁",
        RiskLevel.MEDIUM,
        "changed",
        r"재위탁|하도급|제3자에게\s*(위탁|양도)",
        "재위탁·하도급 조항이 변경되었습니다. 사전 동의 요건과 수급인 책임 범위를 확인하십시오.",
    ),
    Rule(
        "ASSIGN-BAN",
        "권리양도",
        RiskLevel.LOW,
        "introduced",
        r"(양도|이전)(하지|할\s*수)\s*(못한다|없다)|사전\s*(서면)?\s*동의\s*없이[^.。\n]{0,20}양도",
        "권리·의무 양도 제한이 추가되었습니다. 계열사 간 이전, M&A 시 승계 예외를 확보하십시오.",
    ),
    Rule(
        "NON-COMPETE",
        "경업금지",
        RiskLevel.MEDIUM,
        "introduced",
        r"경업|동종\s*(업종|영업)|경쟁\s*(업체|사업)[^.。\n]{0,20}(금지|하지)",
        "경업금지 의무가 추가되었습니다. 기간·지역·대상의 합리적 범위 여부가 유효성을 좌우합니다.",
    ),
    Rule(
        "PRIVACY",
        "개인정보",
        RiskLevel.MEDIUM,
        "changed",
        r"개인정보|가명정보|정보주체",
        "개인정보 관련 조항이 변경되었습니다. 개인정보보호법상 위탁·제3자 제공 구분과 "
        "수탁자 관리·감독 책임을 확인하십시오.",
    ),
    Rule(
        "FORCE-MAJEURE",
        "불가항력",
        RiskLevel.MEDIUM,
        "removed",
        r"불가항력|천재지변",
        "불가항력 면책 조항이 삭제되었습니다. 통제 불가 사유로 인한 불이행까지 책임을 지게 될 수 있습니다.",
    ),
    Rule(
        "WARRANTY",
        "하자담보",
        RiskLevel.MEDIUM,
        "changed",
        r"하자\s*(보수|담보)|보증\s*기간|무상\s*보수",
        "하자담보·보증 조항이 변경되었습니다. 보증 기간과 무상 보수 범위를 확인하십시오.",
    ),
    Rule(
        "GUARANTY",
        "연대보증",
        RiskLevel.HIGH,
        "changed",
        r"연대보증|연대하여\s*(책임|변제)|최고[^.。\n]{0,20}없이[^.。\n]{0,20}청구",
        "연대보증 조항이 변경되었습니다. 보증 한도·기간·대상 채무의 특정 여부와 "
        "민법상 보증인 보호 규정(서면 요건, 최고·검색의 항변) 적용 여부를 확인하십시오.",
    ),
    Rule(
        "GUARANTY-UNLIMITED",
        "연대보증",
        RiskLevel.HIGH,
        "introduced",
        r"(한도\s*없이|일체의\s*채무)[^.。\n]{0,30}보증|보증[^.。\n]{0,30}(한도\s*없이|무제한)",
        "보증 한도가 없는 포괄근보증 형태입니다. 보증 한도액과 보증 기간을 서면으로 특정하지 "
        "않으면 보증인이 예측할 수 없는 채무까지 부담하게 됩니다.",
    ),
    Rule(
        "MFN",
        "최혜대우",
        RiskLevel.MEDIUM,
        "introduced",
        r"최혜|가장\s*유리한\s*조건|동등\s*이상의\s*조건",
        "최혜대우(MFN) 조항이 추가되었습니다. 다른 거래처와의 계약 조건까지 구속될 수 있습니다.",
    ),
)

# 조문 안의 수치(기간·요율·금액)는 문언이 같아도 실질을 바꾼다.
_NUMBER_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(%|퍼센트|일|영업일|개월|년|원|천분의|분의|배|회)"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.。])\s*|\n")


def analyze_comparison(
    comp: ClauseComparison,
    rules: tuple[Rule, ...] | None = None,
    disabled: set[str] | None = None,
) -> list[RiskFlag]:
    """비교 결과 하나에 대해 위험 플래그 목록을 만든다.

    rules를 주지 않으면 내장 룰 전체를 쓴다. disabled에는 룰 코드뿐 아니라
    NUMERIC-CHANGE·CLAUSE-DELETED 같은 합성 플래그 코드도 넣을 수 있다.
    """
    if comp.status is ChangeStatus.UNCHANGED:
        return []

    rules = RULES if rules is None else rules
    disabled = disabled or set()

    before = comp.before.full_text if comp.before else ""
    after = comp.after.full_text if comp.after else ""

    flags: list[RiskFlag] = []
    for rule in rules:
        flag = _apply_rule(rule, before, after, comp.status)
        if flag:
            flags.append(flag)

    flags.extend(_numeric_flags(before, after))

    if comp.status is ChangeStatus.DELETED and not any(
        f.level is RiskLevel.HIGH for f in flags
    ):
        flags.append(
            RiskFlag(
                code="CLAUSE-DELETED",
                category="조문삭제",
                level=RiskLevel.MEDIUM,
                message=(
                    "조문 전체가 삭제되었습니다. 삭제된 권리·의무가 다른 조문으로 "
                    "이관되었는지 확인하십시오."
                ),
                side="before",
            )
        )
    if comp.status is ChangeStatus.ADDED and not flags:
        flags.append(
            RiskFlag(
                code="CLAUSE-ADDED",
                category="조문신설",
                level=RiskLevel.LOW,
                message="조문이 신설되었습니다. 기존 조문과의 충돌 여부를 확인하십시오.",
                side="after",
            )
        )

    flags = [flag for flag in flags if flag.code not in disabled]
    flags.sort(key=lambda f: (-f.level.rank, f.code))
    return flags


def _apply_rule(rule: Rule, before: str, after: str, status: ChangeStatus) -> RiskFlag | None:
    regex = rule.regex
    hit_before = regex.search(before)
    hit_after = regex.search(after)

    if rule.mode == "introduced" and hit_after and not hit_before:
        return _flag(rule, hit_after, after, "after")
    if rule.mode == "removed" and hit_before and not hit_after:
        return _flag(rule, hit_before, before, "before")
    if rule.mode == "changed" and status is not ChangeStatus.UNCHANGED:
        if hit_after:
            return _flag(rule, hit_after, after, "after" if not hit_before else "both")
        if hit_before:
            return _flag(rule, hit_before, before, "before")
    return None


def _flag(rule: Rule, match: re.Match[str], text: str, side: str) -> RiskFlag:
    return RiskFlag(
        code=rule.code,
        category=rule.category,
        level=rule.level,
        message=rule.message,
        evidence=_sentence_around(text, match.start()),
        side=side,
    )


def _sentence_around(text: str, position: int, width: int = 160) -> str:
    start = max(0, position - width // 2)
    end = min(len(text), position + width)
    snippet = " ".join(text[start:end].split())
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def _numeric_flags(before: str, after: str) -> list[RiskFlag]:
    if not before or not after:
        return []

    before_nums = {f"{v}{u}" for v, u in _NUMBER_RE.findall(before)}
    after_nums = {f"{v}{u}" for v, u in _NUMBER_RE.findall(after)}
    removed = sorted(before_nums - after_nums)
    added = sorted(after_nums - before_nums)
    if not removed and not added:
        return []

    return [
        RiskFlag(
            code="NUMERIC-CHANGE",
            category="수치변경",
            level=RiskLevel.MEDIUM,
            message="기간·요율·금액 등 수치가 변경되었습니다. 문언이 비슷해도 실질적 부담이 달라집니다.",
            evidence=f"변경 전: {', '.join(removed) or '-'} → 변경 후: {', '.join(added) or '-'}",
            side="both",
        )
    ]
