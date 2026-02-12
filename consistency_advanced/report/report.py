"""Reporting placeholder."""
from __future__ import annotations


def build_human_report(findings: list) -> str:
    """Return a human-readable report. Placeholder."""
    raise NotImplementedError("Implement human-readable reporting.")


def build_machine_report(findings: list) -> dict:
    """Return a machine-readable report (JSON). Placeholder."""
    raise NotImplementedError("Implement JSON reporting.")
