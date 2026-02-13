"""Stage 2: normalize extracted labels into canonical ontology URIs."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from consistency_advanced.core.models import (
    ExtractionResult,
    NormalizedField,
    NormalizedOperation,
    OperationCandidate,
)
from consistency_advanced.ontology.loader import Vocabulary


NormalizeChooser = Callable[[str, list[str]], str | None]


def _canon(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9_\-\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _build_index(vocab: Vocabulary) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for label, uri in vocab.label_to_uri().items():
        mapping[_canon(label)] = uri
    # Add URI-derived lexical fallbacks.
    all_terms = (
        vocab.actions
        + vocab.data_categories
        + vocab.purposes
        + vocab.views
        + vocab.recipients
        + vocab.legal_bases
    )
    for term in all_terms:
        tail = term.uri.split(":", 1)[-1]
        mapping.setdefault(_canon(tail.replace("_", " ")), term.uri)
    return mapping


def normalize_label(
    label: str | None,
    vocab: Vocabulary,
    *,
    fallback_choices: list[str] | None = None,
    chooser: NormalizeChooser | None = None,
) -> NormalizedField:
    """Map one free-text label to canonical URI with deterministic fallback."""
    if label is None or not str(label).strip():
        return NormalizedField(raw_label=label, normalized_uri=None, confidence=0.0, reason="missing")

    label_raw = str(label)
    label_key = _canon(label_raw)
    index = _build_index(vocab)

    exact = index.get(label_key)
    if exact is not None:
        return NormalizedField(raw_label=label_raw, normalized_uri=exact, confidence=1.0, reason="exact_label")

    # deterministic containment pass
    for known, uri in index.items():
        if known in label_key or label_key in known:
            return NormalizedField(raw_label=label_raw, normalized_uri=uri, confidence=0.82, reason="substring_match")

    # Optional bounded chooser (LLM/matcher) over enumerated URI candidates.
    if chooser is not None and fallback_choices:
        picked = chooser(label_raw, fallback_choices)
        if picked in fallback_choices:
            return NormalizedField(raw_label=label_raw, normalized_uri=picked, confidence=0.7, reason="chooser")

    return NormalizedField(raw_label=label_raw, normalized_uri=None, confidence=0.0, reason="unknown")


def _norm_slot(
    slot_label: str | None,
    *,
    vocab: Vocabulary,
    allowed_prefix: str,
    chooser: NormalizeChooser | None,
) -> NormalizedField:
    candidates = []
    for uri in _build_index(vocab).values():
        if uri.startswith(f"{allowed_prefix}:"):
            candidates.append(uri)
    return normalize_label(slot_label, vocab, fallback_choices=sorted(set(candidates)), chooser=chooser)


def normalize_operation(
    op: OperationCandidate,
    vocab: Vocabulary,
    *,
    chooser: NormalizeChooser | None = None,
) -> NormalizedOperation:
    """Normalize one operation into canonical URI-backed fields."""
    action_label = op.action.label if op.action else None
    subject_label = op.subject.label if op.subject else None
    view_label = op.view.label if op.view else None

    action = _norm_slot(action_label, vocab=vocab, allowed_prefix="action", chooser=chooser)
    subject = _norm_slot(subject_label, vocab=vocab, allowed_prefix="subject", chooser=chooser)
    view = _norm_slot(view_label, vocab=vocab, allowed_prefix="view", chooser=chooser)

    purposes = [
        _norm_slot(p.label, vocab=vocab, allowed_prefix="purpose", chooser=chooser)
        for p in op.purposes
    ]

    def ctx(label: str | None, prefix: str) -> NormalizedField | None:
        if label is None:
            return None
        return _norm_slot(label, vocab=vocab, allowed_prefix=prefix, chooser=chooser)

    recipient = ctx(op.recipient.label if op.recipient else None, "recipient")
    source = ctx(op.source.label if op.source else None, "context")
    legal_basis = ctx(op.legal_basis.label if op.legal_basis else None, "basis")
    manner = ctx(op.manner.label if op.manner else None, "context")
    temporal = ctx(op.temporal.label if op.temporal else None, "context")
    localisation = ctx(op.localisation.label if op.localisation else None, "context")

    policy_id = op.evidence_spans[0].policy_id if op.evidence_spans else "unknown"

    return NormalizedOperation(
        op_id=op.op_id,
        statement_id=op.statement_id,
        policy_id=policy_id,
        action=action,
        subject=subject,
        view=view,
        purposes=purposes,
        recipient=recipient,
        source=source,
        legal_basis=legal_basis,
        manner=manner,
        temporal=temporal,
        localisation=localisation,
        evidence_spans=list(op.evidence_spans),
        original=op,
    )


def normalize_extraction(
    extraction: ExtractionResult,
    vocab: Vocabulary,
    *,
    chooser: NormalizeChooser | None = None,
) -> list[NormalizedOperation]:
    """Normalize all operations from extraction output."""
    out: list[NormalizedOperation] = []
    for statement in extraction.statements:
        for op in statement.operations:
            out.append(normalize_operation(op, vocab, chooser=chooser))
    return out
