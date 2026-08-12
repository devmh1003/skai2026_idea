"""문자 3-gram 코사인 유사도.

한국어는 공백 분리가 불규칙하고 조사가 붙어 변형되므로, 형태소 분석기 없이
부분 일치를 잡으려면 문자 n-gram이 가장 견고하다. 외부 의존성도 없다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

_CLEAN_RE = re.compile(r"\s+")
NGRAM_SIZE = 3


def _normalize(text: str) -> str:
    return _CLEAN_RE.sub("", text)


@lru_cache(maxsize=4096)
def _ngrams(text: str) -> tuple[tuple[str, int], ...]:
    cleaned = _normalize(text)
    if len(cleaned) < NGRAM_SIZE:
        return ((cleaned, 1),) if cleaned else ()
    counter = Counter(cleaned[i : i + NGRAM_SIZE] for i in range(len(cleaned) - NGRAM_SIZE + 1))
    return tuple(sorted(counter.items()))


def similarity(a: str, b: str) -> float:
    """0.0(무관) ~ 1.0(동일)."""
    if a == b:
        return 1.0
    va, vb = dict(_ngrams(a)), dict(_ngrams(b))
    if not va or not vb:
        return 0.0

    if len(va) > len(vb):
        va, vb = vb, va
    dot = sum(count * vb.get(gram, 0) for gram, count in va.items())
    if dot == 0:
        return 0.0

    norm_a = math.sqrt(sum(c * c for c in va.values()))
    norm_b = math.sqrt(sum(c * c for c in vb.values()))
    return dot / (norm_a * norm_b)
