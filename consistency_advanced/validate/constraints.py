"""Stage 4: graph/operation validation before reasoning.

This is a lightweight SHACL-like validator that can be upgraded to real SHACL/SPARQL ASK.
"""
from __future__ import annotations

from consistency_advanced.core.models import NormalizedOperation, ValidationIssue


_ALLOWED_PREFIXES = {
    "action",
    "subject",
    "data",
    "purpose",
    "view",
    "recipient",
    "basis",
    "context",
}


def _prefix(uri: str | None) -> str | None:
    if uri is None or ":" not in uri:
        return None
    return uri.split(":", 1)[0]


def validate_operations(ops: list[NormalizedOperation]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for op in ops:
        idx = len(issues) + 1
        if op.action.normalized_uri is None:
            issues.append(
                ValidationIssue(
                    issue_id=f"issue_{idx}",
                    level="error",
                    message="Operation missing canonical action",
                    op_id=op.op_id,
                    policy_id=op.policy_id,
                )
            )
            idx += 1

        if op.subject.normalized_uri is None:
            issues.append(
                ValidationIssue(
                    issue_id=f"issue_{idx}",
                    level="error",
                    message="Operation missing canonical subject",
                    op_id=op.op_id,
                    policy_id=op.policy_id,
                )
            )
            idx += 1

        if op.view.normalized_uri is None:
            issues.append(
                ValidationIssue(
                    issue_id=f"issue_{idx}",
                    level="warning",
                    message="Operation missing modality/view",
                    op_id=op.op_id,
                    policy_id=op.policy_id,
                )
            )
            idx += 1

        action_uri = op.action.normalized_uri or ""
        if any(action_uri.endswith(s) for s in ("share", "disclose")):
            if op.recipient is None or op.recipient.normalized_uri is None:
                issues.append(
                    ValidationIssue(
                        issue_id=f"issue_{idx}",
                        level="warning",
                        message="Share/disclose operation missing recipient; treat as under-specified",
                        op_id=op.op_id,
                        policy_id=op.policy_id,
                    )
                )
                idx += 1

        # Prefix sanity checks (allowed ontology spaces).
        fields = [
            op.action.normalized_uri,
            op.subject.normalized_uri,
            op.view.normalized_uri,
            *(p.normalized_uri for p in op.purposes),
            op.recipient.normalized_uri if op.recipient else None,
            op.legal_basis.normalized_uri if op.legal_basis else None,
            op.manner.normalized_uri if op.manner else None,
            op.temporal.normalized_uri if op.temporal else None,
            op.localisation.normalized_uri if op.localisation else None,
            op.source.normalized_uri if op.source else None,
        ]

        for uri in fields:
            pf = _prefix(uri)
            if uri is None:
                continue
            if pf not in _ALLOWED_PREFIXES:
                issues.append(
                    ValidationIssue(
                        issue_id=f"issue_{idx}",
                        level="warning",
                        message=f"URI prefix `{pf}` not in allowed set",
                        op_id=op.op_id,
                        policy_id=op.policy_id,
                    )
                )
                idx += 1

    return issues


def has_blocking_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.level == "error" for issue in issues)
