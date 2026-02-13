"""Shared data contracts for the advanced consistency pipeline.

These models intentionally keep each stage bounded and auditable:
- extraction is evidence-first
- normalization preserves raw labels
- graph triples carry provenance
- findings carry evidence from both policies
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TextSpan:
    policy_id: str
    section_id: str
    section_path: str
    start_char: int
    end_char: int
    quote: str


@dataclass(frozen=True)
class SectionNode:
    section_id: str
    level: int
    title: str
    section_path: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ClauseNode:
    clause_id: str
    policy_id: str
    section_id: str
    section_path: str
    start_char: int
    end_char: int
    text: str


@dataclass(frozen=True)
class PolicyDocument:
    policy_id: str
    party_type: str  # "1P" or "3P"
    source_path: str | None
    raw_text: str
    cleaned_text: str
    sections: list[SectionNode]
    clauses: list[ClauseNode]
    definitions: dict[str, str]


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    policy_id: str
    party_type: str
    section_id: str
    section_path: str
    char_start: int
    char_end: int
    chunk_hash: str
    text: str
    clause_ids: list[str]


@dataclass(frozen=True)
class LabeledSpan:
    label: str
    evidence: str | None


@dataclass(frozen=True)
class OperationCandidate:
    op_id: str
    statement_id: str
    action: LabeledSpan | None
    subject: LabeledSpan | None
    view: LabeledSpan | None
    purposes: list[LabeledSpan]
    recipient: LabeledSpan | None = None
    source: LabeledSpan | None = None
    legal_basis: LabeledSpan | None = None
    manner: LabeledSpan | None = None
    temporal: LabeledSpan | None = None
    localisation: LabeledSpan | None = None
    evidence_spans: list[TextSpan] = field(default_factory=list)


@dataclass(frozen=True)
class StatementCandidate:
    statement_id: str
    text_span: TextSpan
    text: str
    operations: list[OperationCandidate]


@dataclass(frozen=True)
class ExtractionResult:
    statements: list[StatementCandidate]
    nonextractable_notes: list[str]
    validation_errors: list[str]


@dataclass(frozen=True)
class NormalizedField:
    raw_label: str | None
    normalized_uri: str | None
    confidence: float
    reason: str


@dataclass(frozen=True)
class NormalizedOperation:
    op_id: str
    statement_id: str
    policy_id: str
    action: NormalizedField
    subject: NormalizedField
    view: NormalizedField
    purposes: list[NormalizedField]
    recipient: NormalizedField | None
    source: NormalizedField | None
    legal_basis: NormalizedField | None
    manner: NormalizedField | None
    temporal: NormalizedField | None
    localisation: NormalizedField | None
    evidence_spans: list[TextSpan]
    original: OperationCandidate


@dataclass(frozen=True)
class GraphTriple:
    subject: str
    predicate: str
    obj: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class ValidationIssue:
    issue_id: str
    level: str  # error|warning
    message: str
    op_id: str
    policy_id: str


@dataclass(frozen=True)
class AlignedPair:
    fp_op_id: str
    tp_op_id: str
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class ComplianceFinding:
    finding_id: str
    finding_type: str
    status: str
    summary: str
    fp_op_id: str | None
    tp_op_id: str | None
    fp_evidence: list[TextSpan]
    tp_evidence: list[TextSpan]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class VerificationDecision:
    decision: str  # CONFIRMED|NOT_CONFIRMED|UNDER_SPECIFIED
    rationale: str
