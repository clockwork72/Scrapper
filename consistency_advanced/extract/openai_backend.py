"""OpenAI-backed extractor for Stage 1.

Output contract remains bounded and evidence-first.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from consistency_advanced.core.models import PolicyChunk
from consistency_advanced.llm import OpenAIJSONClient


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _find_quote_span(haystack: str, quote: str, base_offset: int) -> tuple[int, int] | None:
    q = quote.strip()
    if not q:
        return None
    idx = haystack.find(q)
    if idx >= 0:
        return base_offset + idx, base_offset + idx + len(q)

    # Whitespace-tolerant fallback
    q2 = _collapse_ws(q)
    if not q2:
        return None
    # Build normalization map from collapsed to original offsets.
    mapping: list[int] = []
    collapsed_chars: list[str] = []
    prev_space = False
    for i, ch in enumerate(haystack):
        if ch.isspace():
            if prev_space:
                continue
            prev_space = True
            collapsed_chars.append(" ")
            mapping.append(i)
        else:
            prev_space = False
            collapsed_chars.append(ch)
            mapping.append(i)
    collapsed = "".join(collapsed_chars)
    idx2 = collapsed.find(q2)
    if idx2 < 0:
        return None

    start_orig = mapping[idx2]
    end_idx = idx2 + len(q2) - 1
    end_orig = mapping[end_idx] + 1
    return base_offset + start_orig, base_offset + end_orig


def _norm_labeled(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        val = value.strip()
        if not val:
            return None
        return {"label": val, "evidence": None}
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    if not isinstance(label, str) or not label.strip():
        return None
    evidence = value.get("evidence")
    if evidence is not None and not isinstance(evidence, str):
        evidence = None
    return {"label": label.strip(), "evidence": evidence}


@dataclass
class OpenAIExtractorBackend:
    client: OpenAIJSONClient

    @classmethod
    def from_defaults(cls, *, model: str = "gpt-4.1", api_key: str | None = None, timeout_s: int = 120) -> "OpenAIExtractorBackend":
        return cls(client=OpenAIJSONClient(model=model, api_key=api_key, timeout_s=timeout_s))

    def __call__(self, *, chunk: PolicyChunk, definitions: dict[str, str], schema: dict[str, Any]) -> dict[str, Any]:
        # Keep backend independent of schema internals; schema is included for model grounding.
        schema_hint = {
            "required_root_keys": ["statements", "nonextractable_notes"],
            "statement_shape": {
                "statement_id": "string",
                "text": "string",
                "operations": "array",
            },
            "operation_shape": {
                "op_id": "string",
                "action": "{label,evidence}|null",
                "subject": "{label,evidence}|null",
                "view": "{label,evidence}|null",
                "purposes": "array[{label,evidence}]",
                "recipient": "{label,evidence}|null",
                "source": "{label,evidence}|null",
                "legal_basis": "{label,evidence}|null",
                "manner": "{label,evidence}|null",
                "temporal": "{label,evidence}|null",
                "localisation": "{label,evidence}|null",
                "evidence_quotes": "array[string]"
            },
        }

        defs = [{"term": k, "definition": v} for k, v in sorted(definitions.items())][:80]

        system_prompt = (
            "You are an information extraction engine for privacy policies. "
            "Only extract facts explicitly supported by the text chunk. "
            "Never infer missing slots. Use null for unknown slots. "
            "Return JSON only."
        )

        user_prompt = json.dumps(
            {
                "task": "Extract statement-level operations with evidence from one policy chunk.",
                "rules": [
                    "Do not hallucinate: only explicit text evidence.",
                    "If a slot is not explicit, set it to null.",
                    "Every operation must include at least one exact evidence quote copied from chunk.",
                    "Keep quotes short and exact.",
                    "No prose outside JSON.",
                ],
                "chunk": {
                    "chunk_id": chunk.chunk_id,
                    "policy_id": chunk.policy_id,
                    "party_type": chunk.party_type,
                    "section_id": chunk.section_id,
                    "section_path": chunk.section_path,
                    "chunk_text": chunk.text,
                },
                "definitions": defs,
                "output_contract": schema_hint,
                "target_json_example": {
                    "statements": [
                        {
                            "statement_id": f"{chunk.chunk_id}.stmt_1",
                            "text": "...",
                            "operations": [
                                {
                                    "op_id": f"{chunk.chunk_id}.stmt_1.op_1",
                                    "action": {"label": "share", "evidence": "share"},
                                    "subject": {"label": "device identifiers", "evidence": "device identifiers"},
                                    "view": {"label": "may", "evidence": "may"},
                                    "purposes": [{"label": "analytics", "evidence": "analytics"}],
                                    "recipient": None,
                                    "source": None,
                                    "legal_basis": None,
                                    "manner": None,
                                    "temporal": None,
                                    "localisation": None,
                                    "evidence_quotes": ["We may share device identifiers with analytics partners"]
                                }
                            ]
                        }
                    ],
                    "nonextractable_notes": []
                },
            },
            ensure_ascii=False,
        )

        raw = self.client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0)
        return self._postprocess(raw, chunk)

    def _postprocess(self, raw: dict[str, Any], chunk: PolicyChunk) -> dict[str, Any]:
        out: dict[str, Any] = {"statements": [], "nonextractable_notes": []}

        notes = raw.get("nonextractable_notes")
        if isinstance(notes, list):
            out["nonextractable_notes"] = [str(n) for n in notes]

        statements = raw.get("statements")
        if not isinstance(statements, list):
            out["nonextractable_notes"].append("backend_missing_statements_array")
            return out

        for s_idx, stmt in enumerate(statements, start=1):
            if not isinstance(stmt, dict):
                continue
            stmt_text = stmt.get("text")
            if not isinstance(stmt_text, str) or not stmt_text.strip():
                continue
            statement_id = stmt.get("statement_id")
            if not isinstance(statement_id, str) or not statement_id.strip():
                statement_id = f"{chunk.chunk_id}.stmt_{s_idx}"

            stmt_span = _find_quote_span(chunk.text, stmt_text, chunk.char_start)
            if stmt_span is None:
                # Use full chunk fallback if statement text cannot be located reliably.
                stmt_start, stmt_end = chunk.char_start, chunk.char_end
                stmt_quote = stmt_text
            else:
                stmt_start, stmt_end = stmt_span
                stmt_quote = stmt_text

            statement_payload: dict[str, Any] = {
                "statement_id": statement_id,
                "text": stmt_text,
                "text_span": {
                    "policy_id": chunk.policy_id,
                    "section_id": chunk.section_id,
                    "section_path": chunk.section_path,
                    "start_char": stmt_start,
                    "end_char": stmt_end,
                    "quote": stmt_quote,
                },
                "operations": [],
            }

            ops = stmt.get("operations")
            if not isinstance(ops, list):
                continue

            for o_idx, op in enumerate(ops, start=1):
                if not isinstance(op, dict):
                    continue
                op_id = op.get("op_id")
                if not isinstance(op_id, str) or not op_id.strip():
                    op_id = f"{statement_id}.op_{o_idx}"

                evidence_quotes = op.get("evidence_quotes")
                if not isinstance(evidence_quotes, list):
                    evidence_quotes = []

                evidence_spans: list[dict[str, Any]] = []
                for q in evidence_quotes:
                    if not isinstance(q, str) or not q.strip():
                        continue
                    span = _find_quote_span(chunk.text, q, chunk.char_start)
                    if span is None:
                        continue
                    s_char, e_char = span
                    evidence_spans.append(
                        {
                            "policy_id": chunk.policy_id,
                            "section_id": chunk.section_id,
                            "section_path": chunk.section_path,
                            "start_char": s_char,
                            "end_char": e_char,
                            "quote": q.strip(),
                        }
                    )

                if not evidence_spans:
                    # fallback to statement span to keep provenance strict.
                    evidence_spans.append(
                        {
                            "policy_id": chunk.policy_id,
                            "section_id": chunk.section_id,
                            "section_path": chunk.section_path,
                            "start_char": stmt_start,
                            "end_char": stmt_end,
                            "quote": stmt_quote,
                        }
                    )

                statement_payload["operations"].append(
                    {
                        "op_id": op_id,
                        "action": _norm_labeled(op.get("action")),
                        "subject": _norm_labeled(op.get("subject")),
                        "view": _norm_labeled(op.get("view")),
                        "purposes": [
                            p_norm
                            for p_norm in ([_norm_labeled(v) for v in (op.get("purposes") or [])])
                            if p_norm is not None
                        ],
                        "recipient": _norm_labeled(op.get("recipient")),
                        "source": _norm_labeled(op.get("source")),
                        "legal_basis": _norm_labeled(op.get("legal_basis")),
                        "manner": _norm_labeled(op.get("manner")),
                        "temporal": _norm_labeled(op.get("temporal")),
                        "localisation": _norm_labeled(op.get("localisation")),
                        "evidence_spans": evidence_spans,
                    }
                )

            if statement_payload["operations"]:
                out["statements"].append(statement_payload)

        return out
