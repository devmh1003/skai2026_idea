"""로컬 transformers 백엔드의 호출 방식 검증.

실제 가중치를 내려받지 않고, 모델 카드 스니펫과 같은 인자로 호출하는지만 본다.
apply_chat_template(return_dict=True) → generate(**inputs) → 프롬프트 길이만큼
잘라서 decode, 이 세 단계가 어긋나면 출력에 프롬프트가 섞여 나온다.
"""

from __future__ import annotations

import pytest

from contract_review_ai.config import Settings
from contract_review_ai.llm.local_ax import (
    LocalAXBackend,
    PipelineAXBackend,
    _extract_pipeline_text,
)


class FakeTensor(list):
    """outputs[0][n:] 슬라이싱과 .shape[-1]만 흉내 낸다."""

    @property
    def shape(self):
        return (len(self),)

    def __getitem__(self, key):
        result = list.__getitem__(self, key)
        return FakeTensor(result) if isinstance(key, slice) else result


class FakeInputs(dict):
    def to(self, _device):
        return self


class FakeTokenizer:
    pad_token_id = 0
    eos_token_id = 2

    def __init__(self):
        self.template_kwargs = None

    def apply_chat_template(self, messages, **kwargs):
        self.template_kwargs = kwargs
        self.messages = messages
        return FakeInputs(
            input_ids=FakeTensor([[1, 2, 3, 4]]),
            attention_mask=FakeTensor([[1, 1, 1, 1]]),
        )

    def decode(self, tokens, skip_special_tokens=False):
        return "".join({9: '{"summary":"요약","risk_level":"high"}'}.get(t, "") for t in tokens)


class FakeModel:
    device = "cpu"

    def __init__(self):
        self.generate_kwargs = None

    def eval(self):
        return self

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        # 프롬프트 4토큰 + 생성 1토큰
        return [FakeTensor([1, 2, 3, 4, 9])]


class FakeNoGrad:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


class FakeTorch:
    @staticmethod
    def no_grad():
        return FakeNoGrad()


@pytest.fixture
def backend():
    instance = object.__new__(LocalAXBackend)
    instance.settings = Settings(max_new_tokens=128, temperature=0.2)
    instance.name = "local:test"
    instance._torch = FakeTorch()
    instance.tokenizer = FakeTokenizer()
    instance.model = FakeModel()
    return instance


def test_chat_uses_model_card_template_arguments(backend):
    backend.chat("시스템", "사용자")
    assert backend.tokenizer.template_kwargs == {
        "add_generation_prompt": True,
        "tokenize": True,
        "return_dict": True,
        "return_tensors": "pt",
    }


def test_chat_passes_attention_mask_to_generate(backend):
    backend.chat("시스템", "사용자")
    assert "attention_mask" in backend.model.generate_kwargs
    assert backend.model.generate_kwargs["max_new_tokens"] == 128
    assert backend.model.generate_kwargs["pad_token_id"] == 0


def test_chat_strips_prompt_tokens(backend):
    """프롬프트 길이만큼 잘라내야 생성분만 남는다."""
    assert backend.chat("시스템", "사용자") == '{"summary":"요약","risk_level":"high"}'


def test_greedy_decoding_omits_temperature():
    instance = object.__new__(LocalAXBackend)
    instance.settings = Settings(temperature=0.0)
    instance.tokenizer = FakeTokenizer()
    kwargs = instance._generation_kwargs()
    assert kwargs["do_sample"] is False
    assert "temperature" not in kwargs


def test_comment_parses_model_json(backend):
    from contract_review_ai.llm.base import ClauseContext
    from contract_review_ai.models import ChangeStatus, RiskLevel

    ctx = ClauseContext(
        heading="제7조(손해배상)",
        status=ChangeStatus.MODIFIED,
        before_text="한도로 한다.",
        after_text="제한 없이 배상한다.",
    )
    comment = backend.comment(ctx)
    assert comment.summary == "요약"
    assert comment.risk_level is RiskLevel.HIGH
    assert comment.source == "local:test"


def test_pipeline_output_shapes():
    assert _extract_pipeline_text([{"generated_text": "문자열 응답"}]) == "문자열 응답"
    assert (
        _extract_pipeline_text(
            [{"generated_text": [{"role": "user", "content": "질문"},
                                 {"role": "assistant", "content": "답변"}]}]
        )
        == "답변"
    )
    assert _extract_pipeline_text([]) == ""


def test_pipeline_backend_sends_messages():
    instance = object.__new__(PipelineAXBackend)
    instance.settings = Settings(max_new_tokens=64, temperature=0.0)
    instance.name = "pipeline:test"
    captured = {}

    def fake_pipe(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return [{"generated_text": [{"role": "assistant", "content": "응답"}]}]

    instance.pipe = fake_pipe
    assert instance.chat("시스템", "사용자") == "응답"
    assert [m["role"] for m in captured["messages"]] == ["system", "user"]
    assert captured["kwargs"]["max_new_tokens"] == 64
    assert captured["kwargs"]["return_full_text"] is False
