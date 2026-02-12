"""LLM extraction placeholder."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class EvidenceSpan:
    quote: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class LabeledField:
    label: str
    evidence: str


@dataclass(frozen=True)
class Operation:
    op_id: str
    action: LabeledField
    subject: LabeledField
    purposes: List[LabeledField]
    context: dict
    view: LabeledField
    evidence_spans: List[EvidenceSpan]


@dataclass(frozen=True)
class ExtractionResult:
    operations: List[Operation]
    nonextractable_notes: List[str]


def extract_operations(chunk_text: str, schema_path: str) -> ExtractionResult:
    """Call the LLM to extract operations. Placeholder."""
    raise NotImplementedError("Implement model call + JSON schema validation.")


def verify_evidence(op: Operation, chunk_text: str) -> bool:
    """Verify that evidence spans actually exist in the chunk text."""
    raise NotImplementedError("Implement evidence verification.")
