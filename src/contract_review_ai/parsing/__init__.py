from .loader import SUPPORTED_SUFFIXES, load_document, read_hwpx, read_text
from .segmenter import segment_clauses

__all__ = [
    "SUPPORTED_SUFFIXES",
    "load_document",
    "read_hwpx",
    "read_text",
    "segment_clauses",
]
