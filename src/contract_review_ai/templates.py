"""표준 계약서 양식.

계약을 새로 만들 때 빈 화면에서 시작하지 않도록 기본 양식을 함께 제공한다.
`data/templates/*.txt`가 원본이며, 내려받을 때 Word로 변환한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TEMPLATE_DIR = Path("data/templates")


@dataclass(frozen=True)
class Template:
    id: str
    title: str
    category: str
    file: str
    summary: str


TEMPLATES: tuple[Template, ...] = (
    Template(
        "service",
        "구축 용역계약서",
        "용역·도급",
        "용역_구축.txt",
        "공정 관리·검수·지식재산권·안전보건·연대보증을 포함한 3자 도급 표준안",
    ),
    Template(
        "supply",
        "장비 공급계약서",
        "구매·공급",
        "공급_장비.txt",
        "발주·납품·검사·품질보증·인허가를 담은 계속적 공급거래 표준안",
    ),
    Template(
        "lease",
        "사무실 임대차계약서",
        "부동산",
        "임대차_사무실.txt",
        "보증금·차임 증감·원상회복·전대 제한·연대보증 조항 포함",
    ),
    Template(
        "nda",
        "상호 비밀유지계약서",
        "비밀유지",
        "비밀유지.txt",
        "비밀정보 정의·예외·사용 제한·반환/파기·존속기간을 갖춘 상호(NDA) 표준안",
    ),
    Template(
        "privacy",
        "개인정보 처리위탁 계약서",
        "개인정보",
        "개인정보_처리위탁.txt",
        "위탁 범위·재위탁 제한·안전성 확보조치·유출 통지 의무 포함",
    ),
)


def find(template_id: str) -> Template | None:
    return next((t for t in TEMPLATES if t.id == template_id), None)


def read(template: Template, root: Path | None = None) -> str:
    path = (root or TEMPLATE_DIR) / template.file
    if not path.is_file():
        raise FileNotFoundError(f"양식 파일이 없습니다: {path}")
    return path.read_text(encoding="utf-8")
