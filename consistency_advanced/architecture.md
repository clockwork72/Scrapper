# Advanced Consistency Pipeline Architecture

This folder now follows a strict staged pipeline:

1. `ingest.segment`:
   - load and clean policy text
   - build section tree
   - split into clause-addressable units
   - produce section-first chunks with overlap
2. `extract.llm_extract`:
   - bounded operation extraction with evidence spans
   - schema-shape validation
   - evidence verification against chunk text
3. `normalize.normalize`:
   - map free-text labels to canonical URIs from ontology vocab
   - keep raw label + confidence + reason
4. `graph.build_graph`:
   - generate RDF-like triples
   - attach provenance for every statement/operation triple
5. `validate.constraints`:
   - SHACL-like deterministic checks before reasoning
   - block malformed operations from downstream judgments
6. `reason.compare`:
   - align 1P and 3P operations
   - apply mismatch predicates (purpose/condition/contradiction/under-specified)
   - bounded verifier decision gate
7. `report.report`:
   - machine-readable JSON report
   - human-readable report with citations
8. `pipeline.run`:
   - orchestrates all stages end-to-end

## Evidence Contract

No `ComplianceFinding` is emitted without evidence spans from both policies.

Each span includes:

- `policy_id`
- `section_id`
- `section_path`
- `start_char`, `end_char`
- `quote`

## Key Contracts

- Stage outputs are typed in `core/models.py`.
- Extractor output shape is defined in `schemas/operation.schema.json`.
- Vocabulary and compatibility rules stay in `ontology/`.

## Extension Points

- Replace deterministic extractor with a real LLM backend by passing `extractor_backend` into `pipeline.run_pipeline`.
- Add LLM-assisted normalization by passing `normalize_chooser`.
- Replace lightweight validation with SHACL/SPARQL while keeping `ValidationIssue` output contract.
