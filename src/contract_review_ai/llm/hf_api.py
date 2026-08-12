"""Hugging Face Inference(라우터) 백엔드 — OpenAI 호환 chat/completions.

GPU 없이 A.X 모델을 쓰는 기본 경로. HF_TOKEN이 필요하며, 해당 모델에
서버리스 추론 공급자가 붙어 있어야 한다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import Settings
from .base import ChatBackend


class HFApiBackend(ChatBackend):
    def __init__(self, settings: Settings) -> None:
        if not settings.hf_token:
            raise RuntimeError(
                "HF_TOKEN이 없습니다. .env에 HF_TOKEN을 넣거나 --backend offline을 쓰십시오."
            )
        self.settings = settings
        self.name = f"hf_api:{settings.model}"

    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.settings.max_new_tokens,
            "temperature": self.settings.temperature,
        }
        request = urllib.request.Request(
            f"{self.settings.api_base.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.hf_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"HF API {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"HF API 연결 실패: {exc.reason}") from exc

        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError(f"HF API 응답에 choices가 없습니다: {str(body)[:300]}")
        return choices[0].get("message", {}).get("content", "")
