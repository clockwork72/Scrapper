# Advanced Consistency Analysis

This module is structured as a provenance-first, ontology-driven pipeline for cross-policy consistency checking.

## Workflow

The implementation follows this strict stage order:

1. **Ingest & segment** (`ingest/segment.py`)
2. **Extract** (`extract/llm_extract.py`)
3. **Normalize** (`normalize/normalize.py`)
4. **Graph build** (`graph/build_graph.py`)
5. **Validate** (`validate/constraints.py`)
6. **Reason & compare** (`reason/compare.py`)
7. **Verifier gate** (inside reasoning stage)
8. **Report** (`report/report.py`)

Orchestration entrypoint:

- `pipeline/run.py` -> `run_pipeline(...)`

## Safety / Anti-hallucination Rules

- Extraction is bounded JSON, not free-form prose.
- Every operation must carry evidence spans.
- Missing explicit slots are left `null` (not guessed).
- Validation runs before mismatch logic.
- No finding is emitted without citations from both policies.

## Data Contracts

Shared models: `core/models.py`

Important objects:

- `PolicyDocument`, `PolicyChunk`
- `StatementCandidate`, `OperationCandidate`
- `NormalizedOperation`
- `GraphTriple`
- `ComplianceFinding`

Extractor schema:

- `schemas/operation.schema.json`

## Ontology Assets

`ontology/` contains the operational ontology profile:

- canonical vocabularies (`vocab/`)
- compatibility rules
- alignment spec
- mismatch definitions
- finding-class mapping

## Minimal Usage

```python
from consistency_advanced.pipeline import run_pipeline

result = run_pipeline(
    first_party_policy_path="outputs/example/first_party.txt",
    third_party_policy_path="outputs/example/third_party.txt",
    output_dir="outputs/consistency_run_001",
)

print(result["summary"])
print(result["human_report"])
```

OpenAI-backed extraction + verifier:

```python
from consistency_advanced.pipeline import run_pipeline_openai

result = run_pipeline_openai(
    first_party_policy_path="outputs/example/first_party.txt",
    third_party_policy_path="outputs/example/third_party.txt",
    output_dir="outputs/consistency_openai_run",
    extract_model="gpt-4.1",
    verifier_model="gpt-4.1-mini",
)
```

The OpenAI key is read from `OPENAI_API_KEY` (or `api_key=` argument).

Outputs written to `output_dir`:

- `graph.triples.jsonl`
- `report.machine.json`
- `report.human.txt`
- `summary.json`

## Current Scope

Implemented now:

- deterministic ingestion/segmentation/chunking
- bounded extraction fallback (plus LLM backend hook)
- deterministic normalization
- provenance-rich graph construction
- validation checks
- deterministic alignment + mismatch detection
- report generation

Planned next:

- production LLM extractor + verifier prompts
- SHACL/SPARQL-native validation and reasoning
- richer mismatch families (granularity, omission, localisation/temporal variants)
