"""설정에 따라 코멘트 백엔드를 고른다."""

from __future__ import annotations

import sys

from ..config import Settings
from .base import CommentBackend
from .offline import OfflineBackend


def create_backend(settings: Settings) -> CommentBackend:
    choice = settings.backend

    if choice == "offline":
        return OfflineBackend()
    if choice == "local":
        from .local_ax import LocalAXBackend

        return LocalAXBackend(settings)
    if choice == "hf_api":
        from .hf_api import HFApiBackend

        return HFApiBackend(settings)
    if choice != "auto":
        raise ValueError(f"알 수 없는 백엔드: {choice}")

    # auto — 사용할 수 있는 것 중 가장 좋은 것으로 내려간다.
    if _has_local_stack():
        try:
            from .local_ax import LocalAXBackend

            return LocalAXBackend(settings)
        except Exception as exc:
            _warn(f"로컬 백엔드 사용 불가 → {exc}")

    if settings.hf_token:
        try:
            from .hf_api import HFApiBackend

            return HFApiBackend(settings)
        except Exception as exc:
            _warn(f"HF API 백엔드 사용 불가 → {exc}")

    _warn(
        "LLM 백엔드가 없어 룰 기반 오프라인 코멘트로 실행합니다. "
        "A.X 코멘트를 쓰려면 .env에 HF_TOKEN을 설정하십시오."
    )
    return OfflineBackend()


def _has_local_stack() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _warn(message: str) -> None:
    print(f"[경고] {message}", file=sys.stderr)
