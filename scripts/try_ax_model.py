"""A.X 모델 연결만 단독으로 확인하는 스크립트.

계약서 파이프라인을 거치지 않고, 모델이 실제로 로드·생성되는지만 본다.
GPU가 있는 장비에서 먼저 이걸 통과시킨 뒤 contract-review를 돌리는 편이 빠르다.

    python scripts/try_ax_model.py                      # 로컬 transformers
    python scripts/try_ax_model.py --backend pipeline   # transformers.pipeline
    python scripts/try_ax_model.py --backend hf_api     # HF Inference (GPU 불필요)
    python scripts/try_ax_model.py --model skt/A.X-3.1  # 34B

메모리(bfloat16): A.X-3.1-Light 7B ≈ 16GB · A.X-3.1 34B ≈ 70GB · A.X-4.0 72B ≈ 145GB
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contract_review_ai.config import DEFAULT_MODEL, Settings  # noqa: E402
from contract_review_ai.console import force_utf8  # noqa: E402
from contract_review_ai.llm.base import ClauseContext  # noqa: E402
from contract_review_ai.llm.factory import create_backend  # noqa: E402
from contract_review_ai.models import ChangeStatus, RiskFlag, RiskLevel  # noqa: E402

BEFORE = "제7조(손해배상)\n배상 총액은 본 계약의 총 계약금액을 한도로 한다."
AFTER = "제7조(손해배상)\n당사자는 그로 인하여 발생한 일체의 손해를 제한 없이 배상하여야 한다."


def main() -> int:
    force_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--backend", default="local")
    args = parser.parse_args()

    settings = Settings.from_env()
    settings.model = args.model
    settings.backend = args.backend
    settings.max_new_tokens = 600

    print(f"모델 {settings.model} / 백엔드 {settings.backend} 로드 중…")
    try:
        backend = create_backend(settings)
    except (RuntimeError, ValueError) as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 1
    print(f"백엔드 준비 완료: {backend.name}\n")

    ctx = ClauseContext(
        heading="제7조(손해배상)",
        status=ChangeStatus.MODIFIED,
        before_text=BEFORE,
        after_text=AFTER,
        diff_summary=(
            "- 삭제: 배상 총액은 총 계약금액을 한도로 한다\n"
            "- 추가: 일체의 손해를 제한 없이 배상하여야 한다"
        ),
        flags=[
            RiskFlag(
                code="LIAB-CAP-REMOVED",
                category="손해배상",
                level=RiskLevel.HIGH,
                message="책임 한도 조항이 삭제되었습니다.",
            )
        ],
    )

    comment = backend.comment(ctx)
    print(f"요약     : {comment.summary}")
    print(f"위험도   : {comment.risk_level.label}")
    for issue in comment.issues:
        print(f"쟁점     : {issue}")
    for point in comment.negotiation_points:
        print(f"협상포인트: {point}")
    if comment.suggested_text:
        print(f"수정문안 : {comment.suggested_text}")
    print(f"\n출처     : {comment.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
