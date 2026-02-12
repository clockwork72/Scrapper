# Ontology Profile (Operational)

This profile freezes how the pipeline interprets each extracted statement and how it is mapped into the ontology.

## Unit of Analysis

- **Input unit**: a *statement* = a sentence or bullet item after structural segmentation (headings retained as context).
- **Output unit**: one or more **Operation** instances per statement.
- **Conjunction policy**: split multi‑purpose statements into **one Operation with multiple purposes** (default). If required later, you can split into multiple operations, but this profile assumes a multi‑purpose set per operation.
- **Provenance**: every Operation must include `statement_id` and an exact evidence span (quote + char offsets).

## Core Classes and Properties

### Policy & Statement

- `ppv:PrivacyPolicy`
  - subclasses: `ppv:FirstPartyPolicy`, `ppv:ThirdPartyPolicy`
- `ppv:Statement`
  - linked to policies via `ppv:hasFirstPartyPolicy` / `ppv:hasThirdPartyPolicy`

### Data Processing (Extraction Output)

- `ppv:Operation`
  - `ppv:hasAction` → **Action** (canonical)
  - `ppv:hasSubject` → **DataCategory** (canonical)
  - `ppv:hasView` → **View/Modality** (canonical)
  - `ppv:hasContext` → **Context** (canonical facets)
  - `ppv:hasRecipient` → **Recipient** (canonical)
  - `ppv:hasLegalBasis` → **LegalBasis** (canonical)
  - `ppv:hasPurpose` → **Purpose** (canonical; 0..n)

Note: `hasSubject` is used for **personal data categories**. We do not use `hasObject` in this profile.

### Context Facets

- **Purpose**
- **Temporal** (retention windows)
- **Manner** (encrypted, automatic)
- **Localisation** (EU/US/global)
- **LegalBasis** (consent, legitimate interest, contract, legal obligation)
- **Recipient** (partners, service providers, named third party)

## Minimum Extractable Fields per Operation

- action
- data category
- purposes (0..n)
- recipients (0..n)
- legal basis (0..n)
- retention/temporal (0..1 structured + raw text)
- localisation (0..n)
- view/modality (must/may/do_not/conditional)

Missing required fields emit **UnderSpecifiedRequirement** (or **ViolatedRequirement** if strict).
