"""로컬 transformers 백엔드 — skt/A.X 계열을 직접 로드해 추론한다.

Hugging Face 모델 카드의 권장 사용법을 그대로 따른다.

    tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                  tokenize=True, return_dict=True,
                                  return_tensors="pt")
    model.generate(**inputs, max_new_tokens=...)

`return_dict=True`로 받아 `attention_mask`까지 함께 넘기는 것이 중요하다.
input_ids만 넘기면 패딩 토큰이 섞였을 때 경고와 함께 품질이 떨어진다.

메모리 기준(bfloat16): 7B ≈ 16GB, 34B ≈ 70GB, 72B ≈ 145GB.
GPU가 없으면 CPU로도 돌지만 조문당 수 분이 걸리므로 hf_api 백엔드를 쓰는 편이 낫다.
"""

from __future__ import annotations

from ..config import Settings
from .base import ChatBackend


def _import_transformers():
    try:
        import torch
        import transformers
    except ImportError as exc:  # pragma: no cover - 선택 의존성
        raise RuntimeError(
            "로컬 백엔드에는 `pip install torch transformers accelerate`가 필요합니다."
        ) from exc
    return torch, transformers


class LocalAXBackend(ChatBackend):
    """AutoModelForCausalLM을 직접 들고 생성한다."""

    def __init__(self, settings: Settings) -> None:
        torch, transformers = _import_transformers()

        self.settings = settings
        self.name = f"local:{settings.model}"
        self._torch = torch

        self.tokenizer = transformers.AutoTokenizer.from_pretrained(settings.model)
        self.model = _load_model(transformers, torch, settings.model)
        self.model.eval()

    def chat(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)

        with self._torch.no_grad():
            outputs = self.model.generate(**inputs, **self._generation_kwargs())

        prompt_length = inputs["input_ids"].shape[-1]
        return self.tokenizer.decode(outputs[0][prompt_length:], skip_special_tokens=True)

    def _generation_kwargs(self) -> dict:
        sample = self.settings.temperature > 0
        # pad_token_id는 0이 유효한 값이라 truthy 검사로 대체하면 안 된다.
        pad_token_id = self.tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = self.tokenizer.eos_token_id

        kwargs = {
            "max_new_tokens": self.settings.max_new_tokens,
            "do_sample": sample,
            "pad_token_id": pad_token_id,
        }
        if sample:
            kwargs["temperature"] = self.settings.temperature
        return kwargs


class PipelineAXBackend(ChatBackend):
    """`transformers.pipeline("text-generation", ...)`을 쓰는 간편 경로.

    모델 카드 예제와 가장 가까운 형태다. 채팅 메시지를 그대로 넣으면 파이프라인이
    chat template 적용부터 디코딩까지 처리한다.
    """

    def __init__(self, settings: Settings) -> None:
        _, transformers = _import_transformers()

        self.settings = settings
        self.name = f"pipeline:{settings.model}"
        self.pipe = transformers.pipeline(
            "text-generation", model=settings.model, device_map="auto"
        )

    def chat(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        sample = self.settings.temperature > 0
        kwargs = {"max_new_tokens": self.settings.max_new_tokens, "do_sample": sample}
        if sample:
            kwargs["temperature"] = self.settings.temperature

        outputs = self.pipe(messages, return_full_text=False, **kwargs)
        return _extract_pipeline_text(outputs)


def _load_model(transformers, torch, model_id: str):
    """transformers 버전에 따라 dtype 인자 이름이 다른 것을 흡수한다."""
    cuda = torch.cuda.is_available()
    dtype = torch.bfloat16 if cuda else torch.float32
    common = {"device_map": "auto"} if cuda else {}

    try:  # transformers 4.56+
        return transformers.AutoModelForCausalLM.from_pretrained(
            model_id, dtype=dtype, **common
        )
    except TypeError:  # 구버전은 torch_dtype
        return transformers.AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype, **common
        )


def _extract_pipeline_text(outputs) -> str:
    """파이프라인 반환 형태(문자열 / 메시지 리스트)를 모두 받아낸다."""
    if not outputs:
        return ""
    generated = outputs[0].get("generated_text", "")
    if isinstance(generated, str):
        return generated
    if isinstance(generated, list) and generated:
        last = generated[-1]
        return last.get("content", "") if isinstance(last, dict) else str(last)
    return str(generated)
