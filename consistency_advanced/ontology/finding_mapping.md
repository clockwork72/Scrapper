# Finding Mapping

This file maps mismatch predicates to ComplianceFinding subclasses.

- **Contradiction** → `InconsistentRequirement`
- **Scope mismatch (PurposeMismatch)** → `InconsistentRequirement`
- **Condition mismatch (Legal basis/consent)** → `InconsistentRequirement`
- **Context mismatch** → `InconsistentRequirement`
- **Omission** → `UnderSpecifiedRequirement` (or `InconsistentRequirement` if strict compliance mode)
- **Granularity mismatch** → `UnderSpecifiedRequirement` (or `InconsistentRequirement` if strict)

If a GDPR‑required field is missing in 1P (e.g., retention), emit `ViolatedRequirement` in strict mode.
