#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

def _read_json(p: Path) -> dict[str, Any] | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _policy_from_obj(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None
    for k in ("privacyPolicy", "privacy_policy", "privacyPolicyUrl", "privacy_policy_url", "policyUrl", "policy_url", "policy"):
        v = obj.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None

def _prevalence_value(v: Any) -> float | None:
    # Some versions store prevalence as float, others nested.
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for k in ("total", "overall", "prevalence", "value"):
            if isinstance(v.get(k), (int, float)):
                return float(v[k])
    return None

def main() -> None:
    ap = argparse.ArgumentParser(description="Build a compact Tracker Radar index for fast third-party lookups.")
    ap.add_argument("--tracker-radar-dir", required=True, help="Path to a local clone of duckduckgo/tracker-radar")
    ap.add_argument("--out", required=True, help="Output JSON path")
    args = ap.parse_args()

    root = Path(args.tracker_radar_dir)
    entities_dir = root / "entities"
    domains_dir = root / "domains"

    if not entities_dir.exists() or not domains_dir.exists():
        raise SystemExit("Expected 'entities/' and 'domains/' directories. Did you clone tracker-radar?")

    # 1) Entities: name -> {display, policy_url}
    entity_policy: dict[str, str] = {}
    for p in entities_dir.rglob("*.json"):
        data = _read_json(p)
        if not data:
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            # fall back to filename
            name = p.stem
        pol = _policy_from_obj(data) or _policy_from_obj(data.get("properties"))
        if pol:
            entity_policy[name] = pol

    # 2) Domains: etld1 -> metadata
    out: dict[str, dict[str, Any]] = {}
    for p in domains_dir.rglob("*.json"):
        data = _read_json(p)
        if not data:
            continue

        dom = data.get("domain")
        if not isinstance(dom, str) or not dom.strip():
            dom = p.stem
        dom = dom.lower()

        owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        entity = None
        if isinstance(owner, dict):
            entity = owner.get("name") or owner.get("displayName")
        if not isinstance(entity, str) or not entity.strip():
            entity = data.get("entity") if isinstance(data.get("entity"), str) else None

        categories = data.get("categories")
        if isinstance(categories, str):
            categories = [categories]
        if not isinstance(categories, list):
            categories = []
        categories = [c for c in categories if isinstance(c, str)]

        prevalence = _prevalence_value(data.get("prevalence"))

        # Policy resolution:
        policy_url = (
            _policy_from_obj(data)
            or _policy_from_obj(owner)
            or (entity_policy.get(entity) if entity else None)
        )

        out[dom] = {
            "entity": entity,
            "categories": categories,
            "prevalence": prevalence,
            "policy_url": policy_url,
            "source_domain_file": str(p.relative_to(root)),
        }

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(out):,} domain entries to {args.out}")

if __name__ == "__main__":
    main()
