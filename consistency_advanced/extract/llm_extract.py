"""Stage 1: bounded extraction of Statement/Operation candidates with evidence spans.

This module keeps extraction checkable:
- accepts either backend-produced JSON or deterministic fallback extraction
- validates payload shape
- enforces evidence spans for produced operations
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any, Callable, Protocol

from consistency_advanced.core.models import (
    ExtractionResult,
    LabeledSpan,
    OperationCandidate,
    PolicyChunk,
    StatementCandidate,
    TextSpan,
)


class ExtractBackend(Protocol):
    """Backend contract for LLM extraction."""

    def __call__(self, *, chunk: PolicyChunk, definitions: dict[str, str], schema: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class SlotPattern:
    label: str
    pattern: re.Pattern[str]


_ACTION_PATTERNS = [
    SlotPattern("collect", re.compile(r"\b(collect|gather|obtain|receive)\b", re.I)),
    SlotPattern("use", re.compile(r"\b(use|process|analyze|analyse|utili[sz]e)\b", re.I)),
    SlotPattern("share", re.compile(r"\b(share|disclose|provide to|transfer to)\b", re.I)),
    SlotPattern("retain", re.compile(r"\b(retain|store|keep)\b", re.I)),
    SlotPattern("delete", re.compile(r"\b(delete|erase|remove)\b", re.I)),
    SlotPattern("sell", re.compile(r"\b(sell)\b", re.I)),
    SlotPattern("transfer", re.compile(r"\b(transfer)\b", re.I)),
]

_VIEW_PATTERNS = [
    SlotPattern("do_not", re.compile(r"\b(do not|don't|never|will not)\b", re.I)),
    SlotPattern("only_if", re.compile(r"\b(only if|provided that|subject to)\b", re.I)),
    SlotPattern("required", re.compile(r"\b(required|must|shall)\b", re.I)),
    SlotPattern("may", re.compile(r"\b(may|might|can)\b", re.I)),
    SlotPattern("do", re.compile(r"\b(we (?:collect|use|share|retain|disclose|process))\b", re.I)),
]

_PURPOSE_PATTERNS = [
    SlotPattern("analytics", re.compile(r"\b(analytics?|measurement|metrics?)\b", re.I)),
    SlotPattern("advertising", re.compile(r"\b(advertis(?:e|ing)|marketing|targeted ads?)\b", re.I)),
    SlotPattern("security", re.compile(r"\b(security|fraud|abuse|integrity)\b", re.I)),
    SlotPattern("service_provision", re.compile(r"\b(provide|service|operate|deliver)\b", re.I)),
    SlotPattern("personalization", re.compile(r"\b(personali[sz]ation|recommendation)\b", re.I)),
    SlotPattern("legal", re.compile(r"\b(legal|law|compliance|obligation)\b", re.I)),
]

_SUBJECT_PATTERNS = [
    SlotPattern("email", re.compile(r"\b(email|e-mail address)\b", re.I)),
    SlotPattern("device_id", re.compile(r"\b(device id|device identifier|advertising id|cookie id)\b", re.I)),
    SlotPattern("ip_address", re.compile(r"\b(ip address|internet protocol)\b", re.I)),
    SlotPattern("precise_location", re.compile(r"\b(precise location|gps location)\b", re.I)),
    SlotPattern("location", re.compile(r"\b(location data|location information|geolocation)\b", re.I)),
    SlotPattern("payment", re.compile(r"\b(payment|credit card|billing)\b", re.I)),
    SlotPattern("usage_data", re.compile(r"\b(usage data|activity data|interaction data)\b", re.I)),
]

_RECIPIENT_PATTERNS = [
    SlotPattern("service_provider", re.compile(r"\b(service providers?|processors?|vendors?)\b", re.I)),
    SlotPattern("partner", re.compile(r"\b(partners?|third parties)\b", re.I)),
    SlotPattern("advertiser", re.compile(r"\b(advertisers?|ad partners?)\b", re.I)),
    SlotPattern("affiliate", re.compile(r"\b(affiliates?)\b", re.I)),
    SlotPattern("authority", re.compile(r"\b(authorities?|law enforcement|regulators?)\b", re.I)),
]

_SOURCE_PATTERNS = [
    SlotPattern("from_partners", re.compile(r"\b(from partners?|from third parties?)\b", re.I)),
    SlotPattern("from_users", re.compile(r"\b(from you|you provide|user provide)\b", re.I)),
]

_LEGAL_BASIS_PATTERNS = [
    SlotPattern("consent", re.compile(r"\b(consent|with your permission)\b", re.I)),
    SlotPattern("legitimate_interest", re.compile(r"\b(legitimate interest)\b", re.I)),
    SlotPattern("contract", re.compile(r"\b(contract|performance of a contract)\b", re.I)),
    SlotPattern("legal_obligation", re.compile(r"\b(legal obligation|required by law)\b", re.I)),
]

_TEMPORAL_PATTERNS = [
    SlotPattern("fixed_period", re.compile(r"\b\d+\s*(day|days|month|months|year|years)\b", re.I)),
    SlotPattern("until_deletion", re.compile(r"\b(until (?:you )?delete|account deletion)\b", re.I)),
    SlotPattern("as_needed", re.compile(r"\b(as long as necessary|as needed)\b", re.I)),
]

_LOCALISATION_PATTERNS = [
    SlotPattern("eea", re.compile(r"\b(eea|eu|european economic area)\b", re.I)),
    SlotPattern("us", re.compile(r"\b(united states|u\.s\.|usa)\b", re.I)),
    SlotPattern("global", re.compile(r"\b(global|worldwide|international)\b", re.I)),
]

_MANNER_PATTERNS = [
    SlotPattern("aggregated", re.compile(r"\b(aggregated|aggregate)\b", re.I)),
    SlotPattern("anonymized", re.compile(r"\b(anonymi[sz]ed|de-identified)\b", re.I)),
    SlotPattern("automated", re.compile(r"\b(automated|automatically)\b", re.I)),
    SlotPattern("opt_out", re.compile(r"\b(opt out|opt-out)\b", re.I)),
]


def _load_schema(schema_path: str) -> dict[str, Any]:
    path = Path(schema_path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _field_from_patterns(text: str, patterns: list[SlotPattern]) -> LabeledSpan | None:
    for item in patterns:
        match = item.pattern.search(text)
        if not match:
            continue
        return LabeledSpan(label=item.label, evidence=match.group(0))
    return None


def _fields_from_patterns(text: str, patterns: list[SlotPattern]) -> list[LabeledSpan]:
    out: list[LabeledSpan] = []
    seen: set[str] = set()
    for item in patterns:
        match = item.pattern.search(text)
        if not match:
            continue
        if item.label in seen:
            continue
        seen.add(item.label)
        out.append(LabeledSpan(label=item.label, evidence=match.group(0)))
    return out


def _validate_payload_shape(payload: dict[str, Any]) -> list[str]:
    """Small local validator (JSON schema equivalent for bounded extraction)."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload is not an object"]
    statements = payload.get("statements")
    if not isinstance(statements, list):
        errors.append("statements must be a list")
        return errors
    for i, stmt in enumerate(statements):
        if not isinstance(stmt, dict):
            errors.append(f"statements[{i}] must be object")
            continue
        if not isinstance(stmt.get("statement_id"), str):
            errors.append(f"statements[{i}].statement_id must be string")
        if not isinstance(stmt.get("text"), str):
            errors.append(f"statements[{i}].text must be string")
        ops = stmt.get("operations")
        if not isinstance(ops, list):
            errors.append(f"statements[{i}].operations must be list")
            continue
        for j, op in enumerate(ops):
            if not isinstance(op, dict):
                errors.append(f"statements[{i}].operations[{j}] must be object")
                continue
            if not isinstance(op.get("op_id"), str):
                errors.append(f"statements[{i}].operations[{j}].op_id must be string")
            spans = op.get("evidence_spans")
            if not isinstance(spans, list) or not spans:
                errors.append(f"statements[{i}].operations[{j}] must have evidence_spans")
    return errors


def _deterministic_extract(chunk: PolicyChunk) -> dict[str, Any]:
    """Fallback bounded extractor used when no LLM backend is configured."""
    statements: list[dict[str, Any]] = []
    cursor = chunk.char_start
    for idx, raw_line in enumerate(chunk.text.splitlines()):
        text = raw_line.strip()
        line_start = cursor
        cursor += len(raw_line) + 1
        if not text or len(text) < 8:
            continue

        action = _field_from_patterns(text, _ACTION_PATTERNS)
        subject = _field_from_patterns(text, _SUBJECT_PATTERNS)
        purposes = _fields_from_patterns(text, _PURPOSE_PATTERNS)
        view = _field_from_patterns(text, _VIEW_PATTERNS) or LabeledSpan(label="may", evidence=None)

        if action is None and subject is None and not purposes:
            continue

        statement_id = f"{chunk.chunk_id}.stmt_{idx + 1}"
        op_id = f"{statement_id}.op_1"

        span = {
            "policy_id": chunk.policy_id,
            "section_id": chunk.section_id,
            "section_path": chunk.section_path,
            "start_char": line_start,
            "end_char": line_start + len(text),
            "quote": text,
        }

        op: dict[str, Any] = {
            "op_id": op_id,
            "action": None if action is None else {"label": action.label, "evidence": action.evidence},
            "subject": None if subject is None else {"label": subject.label, "evidence": subject.evidence},
            "view": None if view is None else {"label": view.label, "evidence": view.evidence},
            "purposes": [{"label": p.label, "evidence": p.evidence} for p in purposes],
            "recipient": None,
            "source": None,
            "legal_basis": None,
            "manner": None,
            "temporal": None,
            "localisation": None,
            "evidence_spans": [span],
        }

        recipient = _field_from_patterns(text, _RECIPIENT_PATTERNS)
        source = _field_from_patterns(text, _SOURCE_PATTERNS)
        legal_basis = _field_from_patterns(text, _LEGAL_BASIS_PATTERNS)
        temporal = _field_from_patterns(text, _TEMPORAL_PATTERNS)
        localisation = _field_from_patterns(text, _LOCALISATION_PATTERNS)
        manner = _field_from_patterns(text, _MANNER_PATTERNS)

        if recipient is not None:
            op["recipient"] = {"label": recipient.label, "evidence": recipient.evidence}
        if source is not None:
            op["source"] = {"label": source.label, "evidence": source.evidence}
        if legal_basis is not None:
            op["legal_basis"] = {"label": legal_basis.label, "evidence": legal_basis.evidence}
        if temporal is not None:
            op["temporal"] = {"label": temporal.label, "evidence": temporal.evidence}
        if localisation is not None:
            op["localisation"] = {"label": localisation.label, "evidence": localisation.evidence}
        if manner is not None:
            op["manner"] = {"label": manner.label, "evidence": manner.evidence}

        statements.append(
            {
                "statement_id": statement_id,
                "text": text,
                "text_span": span,
                "operations": [op],
            }
        )

    return {"statements": statements, "nonextractable_notes": []}


def _to_labeled(value: dict[str, Any] | None) -> LabeledSpan | None:
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    if not isinstance(label, str) or not label.strip():
        return None
    evidence = value.get("evidence")
    return LabeledSpan(label=label.strip(), evidence=evidence if isinstance(evidence, str) else None)


def _build_result(payload: dict[str, Any]) -> ExtractionResult:
    validation_errors = _validate_payload_shape(payload)
    nonextractable = payload.get("nonextractable_notes")
    if not isinstance(nonextractable, list):
        nonextractable = []

    statements_out: list[StatementCandidate] = []
    for stmt in payload.get("statements", []):
        if not isinstance(stmt, dict):
            continue

        stmt_id = stmt.get("statement_id")
        text = stmt.get("text")
        span_raw = stmt.get("text_span")
        if not isinstance(stmt_id, str) or not isinstance(text, str) or not isinstance(span_raw, dict):
            continue

        text_span = TextSpan(
            policy_id=str(span_raw.get("policy_id", "")),
            section_id=str(span_raw.get("section_id", "")),
            section_path=str(span_raw.get("section_path", "")),
            start_char=int(span_raw.get("start_char", 0)),
            end_char=int(span_raw.get("end_char", 0)),
            quote=str(span_raw.get("quote", text)),
        )

        ops: list[OperationCandidate] = []
        for op in stmt.get("operations", []):
            if not isinstance(op, dict):
                continue
            op_id = op.get("op_id")
            if not isinstance(op_id, str):
                continue

            evidence_spans: list[TextSpan] = []
            for raw in op.get("evidence_spans", []):
                if not isinstance(raw, dict):
                    continue
                evidence_spans.append(
                    TextSpan(
                        policy_id=str(raw.get("policy_id", text_span.policy_id)),
                        section_id=str(raw.get("section_id", text_span.section_id)),
                        section_path=str(raw.get("section_path", text_span.section_path)),
                        start_char=int(raw.get("start_char", text_span.start_char)),
                        end_char=int(raw.get("end_char", text_span.end_char)),
                        quote=str(raw.get("quote", text_span.quote)),
                    )
                )

            if not evidence_spans:
                continue

            purposes = []
            for p in op.get("purposes", []):
                lp = _to_labeled(p)
                if lp is not None:
                    purposes.append(lp)

            ops.append(
                OperationCandidate(
                    op_id=op_id,
                    statement_id=stmt_id,
                    action=_to_labeled(op.get("action")),
                    subject=_to_labeled(op.get("subject")),
                    view=_to_labeled(op.get("view")),
                    purposes=purposes,
                    recipient=_to_labeled(op.get("recipient")),
                    source=_to_labeled(op.get("source")),
                    legal_basis=_to_labeled(op.get("legal_basis")),
                    manner=_to_labeled(op.get("manner")),
                    temporal=_to_labeled(op.get("temporal")),
                    localisation=_to_labeled(op.get("localisation")),
                    evidence_spans=evidence_spans,
                )
            )

        statements_out.append(
            StatementCandidate(
                statement_id=stmt_id,
                text_span=text_span,
                text=text,
                operations=ops,
            )
        )

    return ExtractionResult(
        statements=statements_out,
        nonextractable_notes=[str(x) for x in nonextractable],
        validation_errors=validation_errors,
    )


def verify_evidence(result: ExtractionResult, chunk_text: str) -> bool:
    """Check that quoted evidence still exists in the input chunk text."""
    hay = chunk_text or ""
    for statement in result.statements:
        for op in statement.operations:
            for span in op.evidence_spans:
                quote = span.quote.strip()
                if not quote:
                    return False
                if quote not in hay:
                    return False
    return True


def extract_operations(
    chunk: PolicyChunk,
    schema_path: str,
    *,
    definitions: dict[str, str] | None = None,
    backend: ExtractBackend | None = None,
) -> ExtractionResult:
    """Extract operations from one chunk using backend or deterministic fallback."""
    schema = _load_schema(schema_path)
    payload = backend(chunk=chunk, definitions=definitions or {}, schema=schema) if backend else _deterministic_extract(chunk)
    result = _build_result(payload)

    if not verify_evidence(result, chunk.text):
        return ExtractionResult(
            statements=[],
            nonextractable_notes=result.nonextractable_notes + ["evidence_verification_failed"],
            validation_errors=result.validation_errors + ["evidence_quotes_not_found_in_chunk"],
        )

    return result


def extract_operations_legacy(chunk_text: str, schema_path: str) -> ExtractionResult:
    """Backward-compatible helper for simple string-only callers."""
    chunk = PolicyChunk(
        chunk_id="legacy.chunk_1",
        policy_id="legacy",
        party_type="1P",
        section_id="section_1",
        section_path="Document",
        char_start=0,
        char_end=len(chunk_text or ""),
        chunk_hash="",
        text=chunk_text or "",
        clause_ids=[],
    )
    return extract_operations(chunk, schema_path)
