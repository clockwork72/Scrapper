# Privacy Research Dataset + Dashboard

This repository builds a **Step‑1 privacy research dataset** and ships an **Electron dashboard** to run and inspect crawls.

## What this project does

**Scraper (Python)**
- Website → first‑party privacy policy URL + extracted text
- Website → observed third‑party domains (from network requests)
- Third‑party domain → entity/category/policy URL (DuckDuckGo Tracker Radar)
- Third‑party policy URL → extracted policy text (best‑effort)

**Dashboard (Electron + Vite)**
- Launch the scraper with live progress + logs
- Inspect results, entities, categories, and prevalence
- Browse sites + policies via the Explorer
- Clear results/artifacts from the database view

**No LLMs / DeepSeek.** The pipeline is deterministic + heuristic filtering.

---

## Repository layout

- `privacy_research_dataset/` — core scraper package
- `scripts/` — helper scripts (Tracker Radar index, Tranco fetch)
- `tracker-radar/` — DuckDuckGo Tracker Radar repo (clone here)
- `dashboard/` — Electron + Vite UI
- `outputs/` — results JSONL, summary, explorer, artifacts

---

## Quick start (scraper only)

### 1) Python setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Crawl4AI uses Playwright
python -m playwright install chromium
```

### 2) Tracker Radar index

```bash
git clone https://github.com/duckduckgo/tracker-radar.git tracker-radar
python scripts/build_tracker_radar_index.py --tracker-radar-dir tracker-radar --out tracker_radar_index.json
```

### 3) Run a crawl

```bash
privacy-dataset --tranco-top 100 --tranco-date 2026-01-01 \
  --tracker-radar-index tracker_radar_index.json \
  --out outputs/results.jsonl \
  --artifacts-dir outputs/artifacts
```

---

## Dashboard setup (Electron + Vite)

### Requirements
- Node.js 18+ (recommended)
- Python + scraper dependencies installed

### Install & run

```bash
cd dashboard
npm install
npm run dev
```

The dashboard can **start the scraper directly** via IPC. If your Python is not `python` on PATH, set:

```bash
export PRIVACY_DATASET_PYTHON=/path/to/python
```

---

## Dashboard → Scraper integration

The dashboard launches the scraper using these outputs:

- `outputs/results.jsonl` — raw results
- `outputs/results.summary.json` — aggregated summary
- `outputs/run_state.json` — live run counters
- `outputs/explorer.jsonl` — explorer data

These are produced when you run with:

```bash
privacy-dataset \
  --emit-events \
  --state-file outputs/run_state.json \
  --summary-out outputs/results.summary.json \
  --explorer-out outputs/explorer.jsonl \
  --out outputs/results.jsonl \
  --artifacts-dir outputs/artifacts
```

The Electron app uses these files to power:
- **Results tab** (summary + categories + entities)
- **Explorer tab** (sites + policy links)
- **Analytics tab** (run state)

---

## Scraper CLI options (important)

- `--tranco-top N` / `--tranco-date YYYY-MM-DD` — reproducible Tranco list
- `--tracker-radar-index` — enables entity/category mapping
- `--third-party-engine crawl4ai|openwpm` — network collection
- `--no-third-party-policy-fetch` — disable third‑party policy fetch

**Integration / telemetry**
- `--emit-events` — JSON events to stdout
- `--state-file` — run state JSON
- `--summary-out` — aggregated summary JSON
- `--explorer-out` — explorer JSON/JSONL
- `--run-id` — set a fixed run id

**CrUX filter (browsable origins)**
- `--crux-filter` — keep only sites present in Chrome UX Report
- `--crux-api-key` or `CRUX_API_KEY` env var
- `--crux-concurrency`, `--crux-timeout-ms`

**Entity filtering**
- `--exclude-same-entity` — exclude third‑party domains owned by same entity as first‑party (requires Tracker Radar)

**Browsable-only (optional)**
- `--prefilter-websites` — lightweight HTML check before crawl
- `--skip-home-fetch-failed` — do not write results when home fetch fails

---

## Output schema (high‑level)

Each line in `results.jsonl` contains:
- `status`: `ok`, `policy_not_found`, `non_browsable`, `home_fetch_failed`, `exception`
- `first_party_policy`: URL + score + length
- `third_parties`: eTLD+1 + entity + categories + prevalence + policy_url
- timing fields: `home_fetch_ms`, `policy_fetch_ms`, `third_party_extract_ms`, `third_party_policy_fetch_ms`, `total_ms`
- `run_id`, `started_at`, `ended_at`

Artifacts live under `outputs/artifacts/<site>/`.

---

## Troubleshooting

**CrUX returns 403/401**
- Ensure Chrome UX Report API is enabled for your key
- Check referrer / IP restrictions in Google Cloud

**Dashboard cannot start scraper**
- Set `PRIVACY_DATASET_PYTHON` to correct Python
- Ensure `privacy_research_dataset` is importable in that environment

**No results in Explorer**
- Ensure `--explorer-out outputs/explorer.jsonl` is used
- The dashboard expects JSONL records with `site`, `rank`, `policyUrl`, and `thirdParties`

---

## Optional: OpenWPM

```bash
privacy-dataset --tranco-top 1000 --tranco-date 2026-01-01 \
  --tracker-radar-index tracker_radar_index.json \
  --third-party-engine openwpm --concurrency 1 \
  --out outputs/results.jsonl --artifacts-dir outputs/artifacts
```

OpenWPM is heavier and typically installed via its Docker/conda instructions.
