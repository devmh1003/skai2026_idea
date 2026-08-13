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
        "supply",
        "물품 공급계약서",
        "물품구매",
        "물품구매_장비.txt",
        "발주·납품·검사·품질보증·인허가를 담은 계속적 공급거래 표준안",
    ),
    Template(
        "service",
        "구축 용역계약서",
        "용역",
        "용역_구축.txt",
        "공정 관리·검수·지식재산권·안전보건·연대보증을 포함한 3자 도급 표준안",
    ),
    Template(
        "advisory",
        "기술자문 계약서",
        "자문",
        "자문_기술.txt",
        "자문 범위·자문 의견의 성격·이해상충·비밀유지를 정리한 자문 표준안",
    ),
    Template(
        "codev",
        "공동개발 계약서",
        "연구개발",
        "연구개발_공동.txt",
        "역할 분담·개발 비용·배경 IP와 공동 성과물의 귀속·실시 조건 포함",
    ),
    Template(
        "license",
        "AI 모델 사용권 계약서",
        "라이선스",
        "라이선스_AI.txt",
        "사용 범위·입력 데이터 취급·산출물 권리·서비스 수준·책임 한도 포함",
    ),
)


def find(template_id: str) -> Template | None:
    return next((t for t in TEMPLATES if t.id == template_id), None)


def read(template: Template, root: Path | None = None) -> str:
    path = (root or TEMPLATE_DIR) / template.file
    if not path.is_file():
        raise FileNotFoundError(f"양식 파일이 없습니다: {path}")
    return path.read_text(encoding="utf-8")
