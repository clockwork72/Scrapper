"""Stage 3: build provenance-rich RDF-like triples from normalized operations."""
from __future__ import annotations

import json
from pathlib import Path

from consistency_advanced.core.models import GraphTriple, NormalizedOperation


def _op_node(op_id: str) -> str:
    return f"op:{op_id}"


def _policy_node(policy_id: str) -> str:
    return f"policy:{policy_id}"


def _provenance(op: NormalizedOperation) -> dict[str, object]:
    spans = []
    for span in op.evidence_spans:
        spans.append(
            {
                "policy_id": span.policy_id,
                "section_id": span.section_id,
                "section_path": span.section_path,
                "start_char": span.start_char,
                "end_char": span.end_char,
                "quote": span.quote,
            }
        )
    return {"statement_id": op.statement_id, "spans": spans}


def build_triples(normalized_ops: list[NormalizedOperation]) -> list[GraphTriple]:
    """Convert normalized operations into triples (RDF-ready shape)."""
    triples: list[GraphTriple] = []
    for op in normalized_ops:
        subj = _op_node(op.op_id)
        prov = _provenance(op)

        triples.append(GraphTriple(subj, "rdf:type", "ppv:Operation", prov))
        triples.append(GraphTriple(subj, "ppv:declaredByPolicy", _policy_node(op.policy_id), prov))

        if op.action.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasAction", op.action.normalized_uri, prov))
        if op.subject.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasSubject", op.subject.normalized_uri, prov))
        if op.view.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasView", op.view.normalized_uri, prov))

        for purpose in op.purposes:
            if purpose.normalized_uri:
                triples.append(GraphTriple(subj, "ppv:hasPurpose", purpose.normalized_uri, prov))

        if op.recipient and op.recipient.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasRecipient", op.recipient.normalized_uri, prov))
        if op.source and op.source.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasSource", op.source.normalized_uri, prov))
        if op.legal_basis and op.legal_basis.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasLegalBasis", op.legal_basis.normalized_uri, prov))
        if op.manner and op.manner.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasManner", op.manner.normalized_uri, prov))
        if op.temporal and op.temporal.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasTemporal", op.temporal.normalized_uri, prov))
        if op.localisation and op.localisation.normalized_uri:
            triples.append(GraphTriple(subj, "ppv:hasLocalisation", op.localisation.normalized_uri, prov))

    return triples


def write_graph(triples: list[GraphTriple], output_path: str) -> None:
    """Write triples to JSONL for inspection/loading into a graph DB."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for t in triples:
            payload = {
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.obj,
                "provenance": t.provenance,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
