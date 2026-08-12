"""로컬 transformers 백엔드 — skt/A.X 계열을 직접 로드해 추론한다.

7B(A.X-3.1-Light / A.X-4.0-Light) 기준 bfloat16으로 약 16GB VRAM이 필요하다.
CPU만 있는 경우에도 동작은 하지만 조문당 수 분이 걸리므로 권장하지 않는다.
"""

from __future__ import annotations

from ..config import Settings
from .base import ChatBackend


class LocalAXBackend(ChatBackend):
    def __init__(self, settings: Settings) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "로컬 백엔드에는 `pip install torch transformers accelerate`가 필요합니다."
            ) from exc

        self.settings = settings
        self.name = f"local:{settings.model}"
        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(settings.model)
        self.model = AutoModelForCausalLM.from_pretrained(
            settings.model,
            dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        self.model.eval()

    def chat(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        input_ids = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to(self.model.device)

        with self._torch.no_grad():
            output = self.model.generate(
                input_ids,
                max_new_tokens=self.settings.max_new_tokens,
                do_sample=self.settings.temperature > 0,
                temperature=max(self.settings.temperature, 1e-5),
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated = output[0][len(input_ids[0]) :]
        return self.tokenizer.decode(generated, skip_special_tokens=True)
