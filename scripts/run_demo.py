"""샘플 계약서로 전체 파이프라인을 한 번 돌린다.

    python scripts/run_demo.py            # 오프라인(룰) 코멘트, 네트워크 0회
    python scripts/run_demo.py --backend hf_api   # A.X 모델 코멘트

버전 저장소에 v1·v2를 등록해 변경 이력 탭까지 채운 뒤 대시보드를 만든다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contract_review_ai.config import Settings  # noqa: E402
from contract_review_ai.report import render_html, render_markdown  # noqa: E402
from contract_review_ai.review import review_versions  # noqa: E402
from contract_review_ai.versioning import VersionStore  # noqa: E402

CONTRACT_ID = "샘플_용역계약"
SAMPLES = ROOT / "data" / "samples"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="offline")
    parser.add_argument("--party", default="all")
    args = parser.parse_args()

    store = VersionStore(ROOT / "data" / "versions")
    for path, label in ((SAMPLES / "용역계약서_v1.txt", "당사 초안"),
                        (SAMPLES / "용역계약서_v2.txt", "상대방 수정본")):
        try:
            record = store.add(CONTRACT_ID, path, label=label, title="소프트웨어 개발 용역계약")
            print(f"버전 등록: {record.version} {record.label}")
        except ValueError as exc:
            print(f"버전 건너뜀: {exc}")

    settings = Settings.from_env()
    settings.backend = args.backend

    result = review_versions(
        CONTRACT_ID,
        "first",
        "latest",
        store=store,
        settings=settings,
        views=[v for v in args.party.split(",") if v],
    )

    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    html_path = out_dir / "dashboard.html"
    md_path = out_dir / "report.md"
    html_path.write_text(render_html(result), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")

    risks = result.risk_counts()
    print(
        f"\n변경 {len(result.changed())}건 · 높음 {risks['high']} / 중간 {risks['medium']} "
        f"/ 낮음 {risks['low']}"
    )
    print(f"대시보드: {html_path}")
    print(f"마크다운: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
