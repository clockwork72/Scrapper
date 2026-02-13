"""Orchestrates the advanced consistency workflow end-to-end.

Stages:
0 ingest+segment -> 1 extract -> 2 normalize -> 3 graph build
4 validate -> 5 align -> 6 mismatch detect -> 7 verifier (inside reason)
8 report
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from consistency_advanced.core.models import ComplianceFinding, ExtractionResult, NormalizedOperation, VerificationDecision
from consistency_advanced.extract.llm_extract import ExtractBackend, extract_operations
from consistency_advanced.graph.build_graph import build_triples, write_graph
from consistency_advanced.ingest.segment import chunk_policy, load_policy
from consistency_advanced.normalize.normalize import NormalizeChooser, normalize_extraction
from consistency_advanced.ontology.compatibility import build_hierarchy_index
from consistency_advanced.ontology.loader import load_rules, load_vocab
from consistency_advanced.reason.compare import align_operations, find_mismatches
from consistency_advanced.reason.openai_verifier import OpenAIFindingVerifier
from consistency_advanced.report.report import build_human_report, build_machine_report
from consistency_advanced.validate.constraints import has_blocking_errors, validate_operations
from consistency_advanced.extract.openai_backend import OpenAIExtractorBackend


def _load_yaml_like(path: str | Path) -> dict[str, Any]:
    """Load config with optional PyYAML; fallback to defaults when unavailable."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        import yaml  # type: ignore

        with p.open("r", encoding="utf-8") as handle:
            obj = yaml.safe_load(handle) or {}
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {}


def _collect_extractions(
    *,
    chunks,
    schema_path: str,
    backend: ExtractBackend | None,
    definitions: dict[str, str],
) -> tuple[list[ExtractionResult], dict[str, int]]:
    results: list[ExtractionResult] = []
    stats = {"chunks": 0, "statements": 0, "operations": 0, "validation_errors": 0}
    for chunk in chunks:
        out = extract_operations(chunk, schema_path, definitions=definitions, backend=backend)
        results.append(out)
        stats["chunks"] += 1
        stats["statements"] += len(out.statements)
        stats["operations"] += sum(len(s.operations) for s in out.statements)
        stats["validation_errors"] += len(out.validation_errors)
    return results, stats


def _flatten_normalized(results: list[ExtractionResult], vocab, chooser: NormalizeChooser | None) -> list[NormalizedOperation]:
    all_ops: list[NormalizedOperation] = []
    for res in results:
        all_ops.extend(normalize_extraction(res, vocab, chooser=chooser))
    return all_ops


def run_pipeline(
    *,
    first_party_policy_path: str,
    third_party_policy_path: str,
    config_path: str = "consistency_advanced/configs/pipeline.yaml",
    vocab_path: str = "consistency_advanced/ontology/vocab",
    rules_path: str = "consistency_advanced/ontology/compatibility_rules.json",
    schema_path: str = "consistency_advanced/schemas/operation.schema.json",
    output_dir: str | None = None,
    extractor_backend: ExtractBackend | None = None,
    normalize_chooser: NormalizeChooser | None = None,
    finding_verifier: Callable[[ComplianceFinding], VerificationDecision] | None = None,
) -> dict[str, Any]:
    cfg = _load_yaml_like(config_path)

    chunk_cfg = cfg.get("chunking", {}) if isinstance(cfg, dict) else {}
    target_tokens = int(chunk_cfg.get("target_tokens", 1000))
    overlap_percent = float(chunk_cfg.get("overlap_percent", 0.12))

    reason_cfg = cfg.get("reasoning", {}) if isinstance(cfg, dict) else {}
    strict_context_compat = bool(reason_cfg.get("strict_context_compat", False))

    fp_doc = load_policy(first_party_policy_path, policy_id="fp_policy", party_type="1P")
    tp_doc = load_policy(third_party_policy_path, policy_id="tp_policy", party_type="3P")

    fp_chunks = list(chunk_policy(fp_doc, target_tokens=target_tokens, overlap_percent=overlap_percent))
    tp_chunks = list(chunk_policy(tp_doc, target_tokens=target_tokens, overlap_percent=overlap_percent))

    fp_extracts, fp_stats = _collect_extractions(
        chunks=fp_chunks,
        schema_path=schema_path,
        backend=extractor_backend,
        definitions=fp_doc.definitions,
    )
    tp_extracts, tp_stats = _collect_extractions(
        chunks=tp_chunks,
        schema_path=schema_path,
        backend=extractor_backend,
        definitions=tp_doc.definitions,
    )

    vocab = load_vocab(vocab_path)
    rules = load_rules(rules_path)
    index = build_hierarchy_index(vocab, rules)

    fp_norm = _flatten_normalized(fp_extracts, vocab, normalize_chooser)
    tp_norm = _flatten_normalized(tp_extracts, vocab, normalize_chooser)

    issues = validate_operations(fp_norm + tp_norm)
    blocking = has_blocking_errors(issues)

    triples = build_triples(fp_norm + tp_norm)

    aligned = align_operations(
        fp_norm,
        tp_norm,
        {"strict_context_compat": strict_context_compat},
        index=index,
        strict_context_compat=strict_context_compat,
    )

    findings = [] if blocking else find_mismatches(
        aligned,
        fp_norm,
        tp_norm,
        index=index,
        verifier=finding_verifier,
    )

    machine_report = build_machine_report(
        findings,
        report_id="report_fp_vs_tp",
        first_party_policy_id=fp_doc.policy_id,
        third_party_policy_id=tp_doc.policy_id,
    )
    human_report = build_human_report(findings)

    summary = {
        "config": {
            "target_tokens": target_tokens,
            "overlap_percent": overlap_percent,
            "strict_context_compat": strict_context_compat,
        },
        "input": {
            "first_party_policy_path": first_party_policy_path,
            "third_party_policy_path": third_party_policy_path,
        },
        "documents": {
            "fp_sections": len(fp_doc.sections),
            "fp_clauses": len(fp_doc.clauses),
            "tp_sections": len(tp_doc.sections),
            "tp_clauses": len(tp_doc.clauses),
        },
        "extract": {
            "fp": fp_stats,
            "tp": tp_stats,
        },
        "normalize": {
            "fp_operations": len(fp_norm),
            "tp_operations": len(tp_norm),
        },
        "validate": {
            "issues": [
                {
                    "issue_id": i.issue_id,
                    "level": i.level,
                    "message": i.message,
                    "op_id": i.op_id,
                    "policy_id": i.policy_id,
                }
                for i in issues
            ],
            "blocking_errors": blocking,
        },
        "reason": {
            "aligned_pairs": len(aligned),
            "findings": len(findings),
        },
    }

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_graph(triples, str(out / "graph.triples.jsonl"))
        (out / "report.machine.json").write_text(json.dumps(machine_report, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "report.human.txt").write_text(human_report, encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "summary": summary,
        "machine_report": machine_report,
        "human_report": human_report,
        "triples": triples,
        "aligned": aligned,
        "findings": findings,
    }


def run_pipeline_openai(
    *,
    first_party_policy_path: str,
    third_party_policy_path: str,
    output_dir: str | None = None,
    config_path: str = "consistency_advanced/configs/pipeline.yaml",
    vocab_path: str = "consistency_advanced/ontology/vocab",
    rules_path: str = "consistency_advanced/ontology/compatibility_rules.json",
    schema_path: str = "consistency_advanced/schemas/operation.schema.json",
    extract_model: str = "gpt-4.1",
    verifier_model: str = "gpt-4.1-mini",
    api_key: str | None = None,
) -> dict[str, Any]:
    extractor_backend = OpenAIExtractorBackend.from_defaults(model=extract_model, api_key=api_key)
    verifier_backend = OpenAIFindingVerifier.from_defaults(model=verifier_model, api_key=api_key)
    return run_pipeline(
        first_party_policy_path=first_party_policy_path,
        third_party_policy_path=third_party_policy_path,
        config_path=config_path,
        vocab_path=vocab_path,
        rules_path=rules_path,
        schema_path=schema_path,
        output_dir=output_dir,
        extractor_backend=extractor_backend,
        finding_verifier=verifier_backend,
    )
