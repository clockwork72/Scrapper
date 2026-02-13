"""OpenAI-backed bounded verifier for findings."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from consistency_advanced.core.models import ComplianceFinding, VerificationDecision
from consistency_advanced.llm import OpenAIJSONClient

_ALLOWED = {"CONFIRMED", "NOT_CONFIRMED", "UNDER_SPECIFIED"}


@dataclass
class OpenAIFindingVerifier:
    client: OpenAIJSONClient

    @classmethod
    def from_defaults(cls, *, model: str = "gpt-4.1-mini", api_key: str | None = None, timeout_s: int = 90) -> "OpenAIFindingVerifier":
        return cls(client=OpenAIJSONClient(model=model, api_key=api_key, timeout_s=timeout_s))

    def __call__(self, finding: ComplianceFinding) -> VerificationDecision:
        system_prompt = (
            "You are a strict legal evidence verifier. "
            "Given structured finding data and direct quotes, decide whether the claim is entailed. "
            "Do not speculate. Return JSON only."
        )
        payload = {
            "task": "Verify whether finding is supported by evidence quotes only.",
            "allowed_decisions": ["CONFIRMED", "NOT_CONFIRMED", "UNDER_SPECIFIED"],
            "finding": {
                "type": finding.finding_type,
                "summary": finding.summary,
                "metadata": finding.metadata,
                "fp_op_id": finding.fp_op_id,
                "tp_op_id": finding.tp_op_id,
                "fp_quotes": [span.quote for span in finding.fp_evidence],
                "tp_quotes": [span.quote for span in finding.tp_evidence],
            },
            "rules": [
                "If either side lacks concrete evidence text, return UNDER_SPECIFIED.",
                "If quotes do not support the mismatch claim, return NOT_CONFIRMED.",
                "Only return CONFIRMED when mismatch/consistency is directly entailed.",
            ],
            "response_schema": {"decision": "one_of_allowed_decisions", "rationale": "short string"},
        }

        raw = self.client.complete_json(system_prompt=system_prompt, user_prompt=json.dumps(payload, ensure_ascii=False), temperature=0.0)
        return self._parse(raw)

    def _parse(self, raw: dict[str, Any]) -> VerificationDecision:
        decision = raw.get("decision")
        rationale = raw.get("rationale")
        if isinstance(decision, str):
            decision = decision.strip().upper()
        else:
            decision = "UNDER_SPECIFIED"
        if decision not in _ALLOWED:
            decision = "UNDER_SPECIFIED"
        if not isinstance(rationale, str) or not rationale.strip():
            rationale = "verifier_no_rationale"
        return VerificationDecision(decision=decision, rationale=rationale.strip())
