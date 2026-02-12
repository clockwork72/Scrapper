# Ontology (Operational)

This folder freezes the ontology profile, vocabularies, normalization rules, alignment semantics, and mismatch predicates used in the advanced consistency pipeline.

## Key Files

- `ontology_profile.md`: frozen meaning of statement → operation → fields
- `vocab/`: versioned canonical vocabularies (actions, purposes, data categories, recipients, legal bases, views)
- `normalization_rules.yml`: regex/synonym normalization spec
- `alignment_spec.yml`: cross‑policy alignment semantics
- `mismatch_predicates.md`: deterministic rule definitions
- `finding_mapping.md`: which mismatch emits which ComplianceFinding

## JSON Utilities

- `vocab.json` and `compatibility_rules.json` remain available as legacy aggregates for programmatic loading.
- `loader.py` can now load the canonical `vocab/` directory directly.
- `loader.py` and `compatibility.py` provide helper methods for subsumption and context compatibility.
