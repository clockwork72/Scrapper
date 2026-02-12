# Advanced Consistency Analysis (Placeholder)

This folder is a **placeholder scaffold** for the next-phase “advanced consistency analysis” system. It mirrors the target architecture and keeps each module **separate and testable**. The goal is to build a robust, scalable pipeline that extracts privacy-policy operations, normalizes them into a canonical ontology, writes an RDF graph with provenance, and produces deterministic compliance findings backed by citations from both policies.

## Target System Architecture

Modules (separate, testable):

1. Ingest & segment: PDF/HTML → clean text → section tree → chunks
2. Extract (LLM): chunk → Operation objects + evidence spans
3. Normalize: map free-text labels → canonical Action/Subject/Purpose/Context/View URIs
4. Graph build: write RDF triples + provenance into a graph store
5. Reason & compare: SPARQL/rules to produce ComplianceFinding + PurposeMismatch
6. Report: human-readable + machine-readable output with citations

Rule: **No finding without citations from both policies.**

## Step 0 — Ontology, Made Operational

Before any LLM calls, define the controlled vocabulary and hierarchy:

- Action URIs: collect, use, share/disclose, retain, delete, transfer, sell, etc.
- Subject URIs: device_id, precise_location, email, payment, etc. (with subclasses)
- Purpose URIs: analytics, security, service_provision, advertising, personalization, legal, etc.
- View URIs: do, may, do_not, only_if, opt_out, required, etc.
- Context facets: temporal, localization, cause, manner (with value sets)

Compatibility rules define the deterministic baseline:

- Purpose subsumption (e.g., personalization ⊄ service_provision)
- Subject/Data category subsumption (device_identifier ⊇ advertising_id)
- Context compatibility (EU-only vs global, optional strictness)

Step 0 outputs are frozen in `consistency_advanced/ontology/`:

- `ontology_profile.md`: unit of analysis + field semantics
- `vocab/`: versioned vocabularies (actions, purposes, data categories, recipients, legal bases, views)
- `normalization_rules.yml`: deterministic regex/synonym mappings
- `alignment_spec.yml`: cross-policy alignment semantics
- `mismatch_predicates.md`: deterministic mismatch definitions
- `finding_mapping.md`: mismatch → ComplianceFinding mapping

## Long Policy Handling — Structure-First Chunking

1. Parse to a section tree (H1/H2/H3 → paragraphs → bullets → tables).
2. Chunk per section node; if too long, split within the same section.
3. Target ~800–1200 tokens per chunk, 10–15% overlap.
4. Store stable IDs for provenance.

Every chunk should track:

- policy_id, party_type (1P/3P), section_path, char_start/end, chunk_hash

## Extraction Schema (LLM)

LLM output should be **strict JSON**, validated by code:

```json
{
  "operations": [
    {
      "op_id": "p1_s3_c2_op7",
      "action": {"label": "share", "evidence": "share"},
      "subject": {"label": "device identifiers", "evidence": "device identifiers"},
      "purposes": [{"label": "analytics", "evidence": "analytics"}],
      "context": {
        "localisation": {"label": "EU", "evidence": "in the EU"},
        "temporal": {"label": "30 days", "evidence": "for 30 days"}
      },
      "view": {"label": "may", "evidence": "may"},
      "evidence_spans": [
        {
          "quote": "We may share device identifiers with analytics partners...",
          "char_start": 1234,
          "char_end": 1320
        }
      ]
    }
  ],
  "nonextractable_notes": []
}
```

Critical rules:

- Evidence spans are mandatory (verbatim quote + offsets).
- If evidence is missing, output nothing (or add a note).

## Normalization

- Deterministic dictionary + synonym maps first
- If ambiguous, LLM chooses from a controlled URI list
- Store raw_label, normalized_uri, confidence, reason

## RDF + Provenance

Example triples:

```
:op123 a :Operation
:op123 :declaredBy :FirstPartyAcme
:op123 :hasAction :Share
:op123 :hasSubject :DeviceIdentifier
:op123 :hasPurpose :Analytics
:op123 :hasContext :ctx456

:op123 :sourcePolicy :policy1
:op123 :sourceSectionPath "Sharing > Partners > Analytics"
:op123 :sourceQuote "We may share device identifiers..."
:op123 :sourceCharStart 1234
:op123 :sourceCharEnd 1320
```

## Reasoning Rules

- Align operations by subject/action/context compatibility
- PurposeMismatch if 3P purposes are not in 1P purpose closure
- Within-policy contradictions: “do not share” vs “may share”

## Reporting

Each finding includes:

- mismatch type, parties, aligned subject/action/context
- exact quotes from 1P and 3P with section paths
- extra/missing purposes
- confidence and rationale

## MVP Order

1. Ingestion + chunking + provenance IDs
2. Extraction schema + validator + evidence enforcement
3. Normalization to URIs
4. RDF graph build
5. One mismatch type end-to-end (PurposeMismatch)
6. Report generation

## Directory Layout

- `ontology/`: canonical vocab + normalization/alignment + mismatch specs
- `schemas/`: JSON schemas for LLM outputs
- `ingest/`: policy ingestion + segmentation
- `extract/`: LLM extraction stubs
- `normalize/`: normalization layer stubs
- `graph/`: RDF graph construction stubs
- `reason/`: SPARQL/rules stubs
- `report/`: report output stubs
- `configs/`: pipeline configuration templates
- `tests/`: test scaffolds
- `examples/`: sample inputs/outputs
- `data/`: scratch data for experiments

All modules are placeholders. Implementations will be added incrementally.
