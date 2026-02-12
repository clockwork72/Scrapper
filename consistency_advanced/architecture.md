# Architecture Sketch (Placeholder)

```
Ingest/Segment
    ↓
Extract (LLM JSON + evidence)
    ↓
Normalize (URIs + confidence)
    ↓
Graph Build (RDF + provenance)
    ↓
Reason/Compare (SPARQL/rules)
    ↓
Report (human + machine)
```

Hard rule: no finding without citations from **both** policies.
