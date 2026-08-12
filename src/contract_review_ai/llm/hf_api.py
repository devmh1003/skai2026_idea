"""Hugging Face Inference(라우터) 백엔드.

GPU 없이 A.X 모델을 쓰는 기본 경로. HF_TOKEN이 필요하며, 해당 모델에
서버리스 추론 공급자가 붙어 있어야 한다.
"""

from __future__ import annotations

from ..config import Settings
from .openai_compat import OpenAICompatBackend


class HFApiBackend(OpenAICompatBackend):
    def __init__(self, settings: Settings) -> None:
        if not settings.hf_token:
            raise RuntimeError(
                "HF_TOKEN이 없습니다. .env에 HF_TOKEN을 넣거나 --backend offline을 쓰십시오."
            )
        super().__init__(
            base_url=settings.api_base,
            api_key=settings.hf_token,
            model=settings.model,
            name=f"hf_api:{settings.model}",
            max_new_tokens=settings.max_new_tokens,
            temperature=settings.temperature,
            timeout=settings.timeout,
        )
