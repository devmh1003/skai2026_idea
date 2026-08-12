"""실행 설정. 환경변수 → CLI 인자 순으로 덮어쓴다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "skt/A.X-3.1-Light"
"""SKT A.X 계열 기본 모델. 7B / 32K 컨텍스트 / Apache-2.0.

교체 후보:
  skt/A.X-3.1        (34B, 32K · YaRN 적용 시 131K)
  skt/A.X-4.0-Light  (7B, 16K)
  skt/A.X-4.0        (72B)
  skt/A.X-K2         (692B, MoE — API 전용)
"""

BACKENDS = ("auto", "local", "pipeline", "hf_api", "adot_biz", "offline")


def load_dotenv(path: str | Path = ".env") -> None:
    """의존성 없이 .env를 읽어 os.environ에 채운다(이미 있는 값은 유지)."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    backend: str = "auto"
    hf_token: str = ""
    api_base: str = "https://router.huggingface.co/v1"
    max_new_tokens: int = 900
    temperature: float = 0.2
    """법무 코멘트는 재현성이 중요하므로 낮게 고정한다."""

    timeout: int = 120
    max_clause_chars: int = 4000
    """조문이 이보다 길면 프롬프트에서 잘라낸다(컨텍스트 보호)."""

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        return cls(
            model=os.getenv("CONTRACT_REVIEW_MODEL", DEFAULT_MODEL),
            backend=os.getenv("CONTRACT_REVIEW_BACKEND", "auto"),
            hf_token=os.getenv("HF_TOKEN", "") or os.getenv("HUGGINGFACEHUB_API_TOKEN", ""),
        )
