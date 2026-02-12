"""Normalization layer placeholder."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class NormalizedField:
    raw_label: str
    normalized_uri: str
    confidence: float
    reason: str


def normalize_label(label: str, vocab: dict) -> NormalizedField:
    """Normalize a free-text label to a canonical URI. Placeholder."""
    raise NotImplementedError("Implement deterministic mapping + fallback LLM.")


def normalize_operation(op: dict, vocab: dict) -> dict:
    """Normalize an extracted operation. Placeholder."""
    raise NotImplementedError("Implement full operation normalization.")
