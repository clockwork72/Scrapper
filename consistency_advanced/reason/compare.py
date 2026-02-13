"""Stage 5-7: alignment, mismatch detection, and bounded verification."""
from __future__ import annotations

from typing import Callable, Iterable

from consistency_advanced.core.models import (
    AlignedPair,
    ComplianceFinding,
    NormalizedOperation,
    TextSpan,
    VerificationDecision,
)
from consistency_advanced.ontology.compatibility import HierarchyIndex, is_subsumed, purpose_in_closure


_ACTION_FAMILY = {
    "action:share": "share_receive",
    "action:disclose": "share_receive",
    "action:collect": "share_receive",
    "action:receive": "share_receive",
    "action:use": "process",
    "action:process": "process",
    "action:retain": "retain",
    "action:delete": "delete",
    "action:transfer": "transfer",
    "action:sell": "sell",
}


def _family(uri: str | None) -> str | None:
    if uri is None:
        return None
    return _ACTION_FAMILY.get(uri, uri)


def _subject_score(a: str | None, b: str | None, index: HierarchyIndex | None) -> float:
    if a is None or b is None:
        return 0.0
    if a == b:
        return 1.0
    if index is None:
        return 0.0
    if is_subsumed(a, b, index) or is_subsumed(b, a, index):
        return 0.8
    return 0.0


def _purpose_overlap(a: list[str], b: list[str], index: HierarchyIndex | None) -> float:
    if not a or not b:
        return 0.0
    if index is None:
        inter = len(set(a).intersection(set(b)))
        return inter / max(1, len(set(a).union(set(b))))

    hits = 0
    for left in a:
        for right in b:
            if is_subsumed(left, right, index) or is_subsumed(right, left, index):
                hits += 1
                break
    return hits / max(1, min(len(a), len(b)))


def align_operations(
    fp_ops: list[NormalizedOperation],
    tp_ops: list[NormalizedOperation],
    rules: dict | None = None,
    *,
    index: HierarchyIndex | None = None,
    strict_context_compat: bool = False,
    min_score: float = 1.25,
) -> list[AlignedPair]:
    """Create deterministic operation alignments (1P ↔ 3P)."""
    pairs: list[AlignedPair] = []
    used_tp: set[str] = set()

    for fp in fp_ops:
        best: tuple[float, NormalizedOperation | None, list[str]] = (0.0, None, [])
        for tp in tp_ops:
            if tp.op_id in used_tp:
                continue

            reasons: list[str] = []
            score = 0.0

            subj = _subject_score(fp.subject.normalized_uri, tp.subject.normalized_uri, index)
            if subj > 0:
                score += 1.0 * subj
                reasons.append("subject_compatible")

            fam_fp = _family(fp.action.normalized_uri)
            fam_tp = _family(tp.action.normalized_uri)
            if fam_fp and fam_tp and fam_fp == fam_tp:
                score += 1.0
                reasons.append("action_family_compatible")

            purp = _purpose_overlap(
                [p.normalized_uri for p in fp.purposes if p.normalized_uri],
                [p.normalized_uri for p in tp.purposes if p.normalized_uri],
                index,
            )
            if purp > 0:
                score += 0.6 * purp
                reasons.append("purpose_overlap")

            if fp.recipient and tp.source and fp.recipient.normalized_uri and tp.source.normalized_uri:
                if fp.recipient.normalized_uri == tp.source.normalized_uri:
                    score += 0.4
                    reasons.append("recipient_source_alignment")

            if strict_context_compat:
                if fp.localisation and tp.localisation and fp.localisation.normalized_uri and tp.localisation.normalized_uri:
                    if fp.localisation.normalized_uri == tp.localisation.normalized_uri:
                        score += 0.2
                    else:
                        score -= 0.3
                if fp.temporal and tp.temporal and fp.temporal.normalized_uri and tp.temporal.normalized_uri:
                    if fp.temporal.normalized_uri == tp.temporal.normalized_uri:
                        score += 0.2
                    else:
                        score -= 0.3

            if score > best[0]:
                best = (score, tp, reasons)

        if best[1] is not None and best[0] >= min_score:
            tp_best = best[1]
            used_tp.add(tp_best.op_id)
            pairs.append(
                AlignedPair(
                    fp_op_id=fp.op_id,
                    tp_op_id=tp_best.op_id,
                    score=best[0],
                    reasons=best[2],
                )
            )

    return pairs


def _quotes(spans: Iterable[TextSpan]) -> list[str]:
    out: list[str] = []
    for span in spans:
        q = span.quote.strip()
        if q:
            out.append(q)
    return out


def _verifier_decision(finding: ComplianceFinding) -> VerificationDecision:
    """Bounded verifier pass: validates entailment preconditions, not free-form judging."""
    if not finding.fp_evidence or not finding.tp_evidence:
        return VerificationDecision(decision="UNDER_SPECIFIED", rationale="missing_evidence_in_one_side")
    if not _quotes(finding.fp_evidence) or not _quotes(finding.tp_evidence):
        return VerificationDecision(decision="UNDER_SPECIFIED", rationale="empty_quotes")
    if finding.finding_type == "UnderSpecifiedRequirement":
        return VerificationDecision(decision="UNDER_SPECIFIED", rationale="incomplete_slots")
    return VerificationDecision(decision="CONFIRMED", rationale="structured_evidence_present")


def find_mismatches(
    aligned_ops: list[AlignedPair],
    fp_ops: list[NormalizedOperation],
    tp_ops: list[NormalizedOperation],
    rules: dict | None = None,
    *,
    index: HierarchyIndex | None = None,
    verifier: Callable[[ComplianceFinding], VerificationDecision] | None = None,
) -> list[ComplianceFinding]:
    """Apply deterministic mismatch predicates and return findings with dual citations."""
    fp_by_id = {op.op_id: op for op in fp_ops}
    tp_by_id = {op.op_id: op for op in tp_ops}

    findings: list[ComplianceFinding] = []

    for pair in aligned_ops:
        fp = fp_by_id.get(pair.fp_op_id)
        tp = tp_by_id.get(pair.tp_op_id)
        if fp is None or tp is None:
            continue

        # No finding without citations from both policies.
        if not fp.evidence_spans or not tp.evidence_spans:
            continue

        fp_purposes = [p.normalized_uri for p in fp.purposes if p.normalized_uri]
        tp_purposes = [p.normalized_uri for p in tp.purposes if p.normalized_uri]

        # Under-specified gate
        required_missing = (
            fp.action.normalized_uri is None
            or fp.subject.normalized_uri is None
            or tp.action.normalized_uri is None
            or tp.subject.normalized_uri is None
        )
        if required_missing:
            finding = ComplianceFinding(
                finding_id=f"finding_{len(findings)+1}",
                finding_type="UnderSpecifiedRequirement",
                status="PotentiallyNonCompliant",
                summary="Aligned operations are missing required canonical slots.",
                fp_op_id=fp.op_id,
                tp_op_id=tp.op_id,
                fp_evidence=list(fp.evidence_spans),
                tp_evidence=list(tp.evidence_spans),
                metadata={"alignment_score": pair.score, "reasons": pair.reasons},
            )
            decision = (verifier or _verifier_decision)(finding)
            if decision.decision != "NOT_CONFIRMED":
                findings.append(finding)
            continue

        # Contradiction: 1P do_not vs 3P positive operation.
        fp_view = fp.view.normalized_uri or ""
        tp_view = tp.view.normalized_uri or ""
        if fp_view.endswith("do_not") and not tp_view.endswith("do_not"):
            finding = ComplianceFinding(
                finding_id=f"finding_{len(findings)+1}",
                finding_type="InconsistentRequirement",
                status="PotentiallyNonCompliant",
                summary="Contradiction: first-party denies processing while third-party indicates processing.",
                fp_op_id=fp.op_id,
                tp_op_id=tp.op_id,
                fp_evidence=list(fp.evidence_spans),
                tp_evidence=list(tp.evidence_spans),
                metadata={"subtype": "Contradiction", "alignment_score": pair.score},
            )
            if (verifier or _verifier_decision)(finding).decision == "CONFIRMED":
                findings.append(finding)
            continue

        # Purpose mismatch: P_tp not subset of closure(P_fp)
        extra_tp = []
        for p in tp_purposes:
            if index is not None:
                in_scope = purpose_in_closure(p, fp_purposes, index)
            else:
                in_scope = p in fp_purposes
            if not in_scope:
                extra_tp.append(p)

        if extra_tp:
            finding = ComplianceFinding(
                finding_id=f"finding_{len(findings)+1}",
                finding_type="PurposeMismatch",
                status="PotentiallyNonCompliant",
                summary="Third-party purposes exceed first-party disclosed/allowed purposes.",
                fp_op_id=fp.op_id,
                tp_op_id=tp.op_id,
                fp_evidence=list(fp.evidence_spans),
                tp_evidence=list(tp.evidence_spans),
                metadata={
                    "extra_tp_purposes": extra_tp,
                    "fp_purposes": fp_purposes,
                    "tp_purposes": tp_purposes,
                    "alignment_score": pair.score,
                },
            )
            if (verifier or _verifier_decision)(finding).decision == "CONFIRMED":
                findings.append(finding)
            continue

        # Condition mismatch: legal basis differs and both explicit.
        fp_basis = fp.legal_basis.normalized_uri if fp.legal_basis else None
        tp_basis = tp.legal_basis.normalized_uri if tp.legal_basis else None
        if fp_basis and tp_basis and fp_basis != tp_basis:
            finding = ComplianceFinding(
                finding_id=f"finding_{len(findings)+1}",
                finding_type="ConditionMismatch",
                status="PotentiallyNonCompliant",
                summary="Legal basis/condition differs across aligned operations.",
                fp_op_id=fp.op_id,
                tp_op_id=tp.op_id,
                fp_evidence=list(fp.evidence_spans),
                tp_evidence=list(tp.evidence_spans),
                metadata={"fp_legal_basis": fp_basis, "tp_legal_basis": tp_basis, "alignment_score": pair.score},
            )
            if (verifier or _verifier_decision)(finding).decision == "CONFIRMED":
                findings.append(finding)
            continue

        # Satisfied requirement fallback.
        finding = ComplianceFinding(
            finding_id=f"finding_{len(findings)+1}",
            finding_type="SatisfiedRequirement",
            status="Consistent",
            summary="Aligned operations are consistent on checked dimensions.",
            fp_op_id=fp.op_id,
            tp_op_id=tp.op_id,
            fp_evidence=list(fp.evidence_spans),
            tp_evidence=list(tp.evidence_spans),
            metadata={"alignment_score": pair.score, "reasons": pair.reasons},
        )
        if (verifier or _verifier_decision)(finding).decision == "CONFIRMED":
            findings.append(finding)

    return findings
