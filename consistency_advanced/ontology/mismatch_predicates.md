# Mismatch Predicates (Operational)

Each predicate assumes aligned operations (see `alignment_spec.yml`).

## 1) Granularity Mismatch

**Predicate**: 1P recipient term is a higher‑level category (e.g., `recipient:partner`) while 3P uses a more specific category or explicit named recipient, and the 1P policy lacks that specific disclosure.

**Implementation hook**: compute a **specificity score** based on taxonomy depth; mismatch if `depth(tp_recipient) > depth(fp_recipient)` and no fp recipient at or below tp depth.

## 2) Contradiction

**Predicate**: aligned operations where 1P view = `do_not` and 3P asserts a positive view (`do`/`may`) for same subject/action/context.

## 3) Omission

**Predicate**: a 3P operation exists for a subject/action/context that has **no aligned 1P disclosure**.

## 4) Scope Mismatch (PurposeMismatch)

**Predicate**: purposes_3p ⊄ closure(purposes_1p) for aligned operations.

## 5) Condition Mismatch (Legal basis / consent)

**Predicate**: aligned operations where legal basis or consent conditions differ (e.g., 1P `basis:consent` vs 3P `basis:legitimate_interest`).

## 6) Context Mismatch (Localisation/Temporal)

**Predicate**: aligned operations whose context facets are incompatible under `compatibility_rules` (e.g., EU‑only vs global under strict mode).
