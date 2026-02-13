"""Stage 8: render machine + human reports from findings with citations."""
from __future__ import annotations

from datetime import datetime

from consistency_advanced.core.models import ComplianceFinding


def _span_to_dict(span) -> dict:
    return {
        "policy_id": span.policy_id,
        "section_id": span.section_id,
        "section_path": span.section_path,
        "start_char": span.start_char,
        "end_char": span.end_char,
        "quote": span.quote,
    }


def build_machine_report(
    findings: list[ComplianceFinding],
    *,
    report_id: str = "report_1",
    first_party_policy_id: str | None = None,
    third_party_policy_id: str | None = None,
) -> dict:
    """Return a machine-readable report payload with full evidence."""
    status = "Consistent"
    if any(f.status == "PotentiallyNonCompliant" for f in findings):
        status = "PotentiallyNonCompliant"

    return {
        "report_id": report_id,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "first_party_policy_id": first_party_policy_id,
        "third_party_policy_id": third_party_policy_id,
        "compliance_status": status,
        "finding_count": len(findings),
        "findings": [
            {
                "finding_id": f.finding_id,
                "type": f.finding_type,
                "status": f.status,
                "summary": f.summary,
                "fp_operation_id": f.fp_op_id,
                "tp_operation_id": f.tp_op_id,
                "fp_evidence": [_span_to_dict(span) for span in f.fp_evidence],
                "tp_evidence": [_span_to_dict(span) for span in f.tp_evidence],
                "metadata": f.metadata,
            }
            for f in findings
        ],
    }


def build_human_report(findings: list[ComplianceFinding]) -> str:
    """Return a concise, citation-rich text report for reviewers."""
    if not findings:
        return "No findings."

    lines: list[str] = []
    for idx, finding in enumerate(findings, start=1):
        lines.append(f"{idx}. [{finding.finding_type}] {finding.summary}")
        lines.append(f"   - Status: {finding.status}")
        if finding.fp_op_id:
            lines.append(f"   - First-party op: {finding.fp_op_id}")
        if finding.tp_op_id:
            lines.append(f"   - Third-party op: {finding.tp_op_id}")

        if finding.fp_evidence:
            first = finding.fp_evidence[0]
            lines.append(
                "   - 1P evidence: "
                f"\"{first.quote[:180]}\" "
                f"({first.section_path}, chars {first.start_char}-{first.end_char})"
            )
        if finding.tp_evidence:
            first = finding.tp_evidence[0]
            lines.append(
                "   - 3P evidence: "
                f"\"{first.quote[:180]}\" "
                f"({first.section_path}, chars {first.start_char}-{first.end_char})"
            )

    return "\n".join(lines)
