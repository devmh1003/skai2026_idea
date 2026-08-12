"""OpenAI 호환 `/chat/completions` 게이트웨이 공통 클라이언트.

Hugging Face Router, SKT A.Biz 사내 게이트웨이, 사설 vLLM 서버가 모두 같은
스키마를 쓴다. 엔드포인트와 인증 헤더만 갈아 끼우면 되도록 여기 모아 둔다.
표준 라이브러리(urllib)만 쓰므로 폐쇄망 반입 시 추가 패키지가 필요 없다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ChatBackend


class OpenAICompatBackend(ChatBackend):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        name: str,
        max_new_tokens: int = 900,
        temperature: float = 0.2,
        timeout: int = 120,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = name
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}

    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            **self.extra_body,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"{self.name} HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.name} 연결 실패: {exc.reason}") from exc

        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.name} 응답에 choices가 없습니다: {str(body)[:300]}")
        return choices[0].get("message", {}).get("content", "")
