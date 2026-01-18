from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .crawl4ai_client import Crawl4AIClient
from .policy_finder import (
    extract_link_candidates,
    extract_legal_hub_urls,
    fallback_privacy_urls,
    policy_likeliness_score,
    LinkCandidate,
)
from .third_party import third_parties_from_network_logs
from .tracker_radar import TrackerRadarIndex
from .openwpm_engine import run_openwpm_for_third_parties
from .utils.etld import etld1
from .utils.logging import log, warn

def _safe_dirname(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in s)[:200]

def _write_text(p: Path, text: str | None) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text or "", encoding="utf-8")

def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

async def _fetch_best_policy(
    client: Crawl4AIClient,
    site_url: str,
    home_cleaned_html: str,
    *,
    max_candidates: int = 10,
    max_hub_pages: int = 2,
) -> dict[str, Any]:
    site_et = etld1(site_url) or ""

    candidates = extract_link_candidates(home_cleaned_html, site_url, site_et)
    tried: list[dict[str, Any]] = []
    chosen: dict[str, Any] | None = None

    async def try_candidate(c: LinkCandidate) -> dict[str, Any]:
        res = await client.fetch(c.url, capture_network=False, remove_overlays=True, magic=False, scan_full_page=False)
        rec = dict(
            url=c.url,
            anchor_text=c.anchor_text,
            score=c.score,
            source=c.source,
            candidate_etld1=c.candidate_etld1,
            is_same_site=c.is_same_site,
            fetch_success=res.success,
            status_code=res.status_code,
            error_message=res.error_message,
        )
        text = (res.text or "").strip()
        rec["text_len"] = len(text)
        rec["likeliness_score"] = policy_likeliness_score(text)
        return rec | {"text": text, "cleaned_html": res.cleaned_html, "raw_html": res.raw_html}

    # 1) Try top candidates directly
    for c in candidates[:max_candidates]:
        rec = await try_candidate(c)
        tried.append({k: rec[k] for k in rec.keys() if k not in ("text", "cleaned_html", "raw_html")})
        if rec["fetch_success"] and rec["likeliness_score"] >= 3.0 and rec["text_len"] >= 800:
            chosen = rec
            break

    # 2) Fallback common paths
    if chosen is None:
        for c in fallback_privacy_urls(site_url, site_et):
            rec = await try_candidate(c)
            tried.append({k: rec[k] for k in rec.keys() if k not in ("text", "cleaned_html", "raw_html")})
            if rec["fetch_success"] and rec["likeliness_score"] >= 3.0 and rec["text_len"] >= 800:
                chosen = rec
                break

    # 3) Legal hub expansion (depth 1): fetch 1-2 legal/terms pages and rescan for privacy links
    if chosen is None and candidates:
        hub_urls = extract_legal_hub_urls(candidates, limit=max_hub_pages)
        for hub in hub_urls:
            hub_res = await client.fetch(hub, capture_network=False, remove_overlays=True, magic=False)
            if not hub_res.success or not hub_res.cleaned_html:
                continue
            hub_cands = extract_link_candidates(hub_res.cleaned_html, hub_res.url, site_et)
            for c in hub_cands[:max_candidates]:
                # mark as hub source
                c2 = LinkCandidate(
                    url=c.url, anchor_text=c.anchor_text, score=c.score + 0.2, source="hub",
                    candidate_etld1=c.candidate_etld1, is_same_site=c.is_same_site
                )
                rec = await try_candidate(c2)
                tried.append({k: rec[k] for k in rec.keys() if k not in ("text", "cleaned_html", "raw_html")})
                if rec["fetch_success"] and rec["likeliness_score"] >= 3.0 and rec["text_len"] >= 800:
                    chosen = rec
                    break
            if chosen is not None:
                break

    return {
        "site_etld1": site_et,
        "candidates_top": [
            {
                "url": c.url,
                "anchor_text": c.anchor_text,
                "score": c.score,
                "source": c.source,
                "candidate_etld1": c.candidate_etld1,
                "is_same_site": c.is_same_site,
            }
            for c in candidates[:25]
        ],
        "tried": tried,
        "chosen": (None if chosen is None else {k: chosen[k] for k in chosen.keys() if k in (
            "url","anchor_text","score","source","candidate_etld1","is_same_site","status_code","likeliness_score","text_len"
        )}) ,
        "_chosen_full": chosen,  # internal (includes text/html)
    }

async def process_site(
    client: Crawl4AIClient,
    domain_or_url: str,
    *,
    rank: int | None,
    artifacts_dir: str | Path,
    tracker_radar: TrackerRadarIndex | None = None,
    fetch_third_party_policies: bool = True,
    third_party_policy_max: int = 30,
    third_party_engine: str = "crawl4ai",  # crawl4ai|openwpm
) -> dict[str, Any]:
    """
    Process a single website:
    - Fetch homepage
    - Find and fetch best privacy policy
    - Extract third-party domains from network logs (Crawl4AI) or OpenWPM (optional)
    - Map third parties via Tracker Radar (+ optionally fetch their policy texts)
    """
    site_url = domain_or_url.strip()
    if not site_url:
        return {"input": domain_or_url, "error": "empty_input"}
    if "://" not in site_url:
        site_url = "https://" + site_url

    site_art_dir = Path(artifacts_dir) / _safe_dirname(etld1(site_url) or domain_or_url)
    site_art_dir.mkdir(parents=True, exist_ok=True)

    # 1) Homepage fetch
    capture_net = (third_party_engine == "crawl4ai")
    home = await client.fetch(site_url, capture_network=capture_net, remove_overlays=True, magic=False, scan_full_page=False)
    if not home.success or not home.cleaned_html:
        if home.raw_html:
            _write_text(site_art_dir / "home.raw.html", home.raw_html)
        if home.cleaned_html:
            _write_text(site_art_dir / "home.cleaned.html", home.cleaned_html)
        return {
            "rank": rank,
            "input": domain_or_url,
            "site_url": site_url,
            "final_url": home.url,
            "site_etld1": etld1(home.url),
            "status": "home_fetch_failed",
            "status_code": home.status_code,
            "error_message": home.error_message,
        }

    _write_text(site_art_dir / "home.raw.html", home.raw_html)
    _write_text(site_art_dir / "home.cleaned.html", home.cleaned_html)
    if home.text:
        _write_text(site_art_dir / "home.txt", home.text)

    # 2) Privacy policy discovery + fetch
    policy_info = await _fetch_best_policy(client, home.url, home.cleaned_html)
    _write_json(site_art_dir / "policy.discovery.json", {
        k: policy_info[k] for k in ("site_etld1","candidates_top","tried","chosen")
    })

    chosen_full = policy_info.get("_chosen_full")
    first_party_policy = None
    if chosen_full:
        first_party_policy = {
            "url": chosen_full.get("url"),
            "status_code": chosen_full.get("status_code"),
            "likeliness_score": chosen_full.get("likeliness_score"),
            "text_len": chosen_full.get("text_len"),
        }
        _write_text(site_art_dir / "policy.url.txt", chosen_full.get("url"))
        _write_text(site_art_dir / "policy.txt", chosen_full.get("text"))
        _write_text(site_art_dir / "policy.cleaned.html", chosen_full.get("cleaned_html"))
        if chosen_full.get("raw_html"):
            _write_text(site_art_dir / "policy.raw.html", chosen_full.get("raw_html"))

    # 3) Third-party extraction
    if third_party_engine == "openwpm":
        openwpm_dir = site_art_dir / "openwpm"
        try:
            urls = run_openwpm_for_third_parties(home.url, out_dir=openwpm_dir, headless=True)
            network_like = [{"url": u} for u in urls]
            obs = third_parties_from_network_logs(home.url, network_like)
        except Exception as e:
            warn(f"[{etld1(home.url)}] OpenWPM failed; falling back to Crawl4AI network logs: {e}")
            obs = third_parties_from_network_logs(home.url, home.network_requests)
    else:
        obs = third_parties_from_network_logs(home.url, home.network_requests)

    third_party_etlds = obs.third_party_etld1s

    third_party_records: list[dict[str, Any]] = []
    for tp in third_party_etlds:
        entry = tracker_radar.lookup(tp) if tracker_radar else None
        third_party_records.append({
            "third_party_etld1": tp,
            "entity": (entry.entity if entry else None),
            "categories": (entry.categories if entry else []),
            "prevalence": (entry.prevalence if entry else None),
            "policy_url": (entry.policy_url if entry else None),
            "tracker_radar_source_domain_file": (entry.source_domain_file if entry else None),
        })

    # 4) Optional: fetch third-party policy texts (best-effort)
    third_party_policy_fetches: list[dict[str, Any]] = []
    if fetch_third_party_policies and tracker_radar:
        def sort_key(r: dict[str, Any]):
            p = r.get("prevalence")
            return (-(p if isinstance(p, (int, float)) else -1.0), r["third_party_etld1"])

        for rec in sorted(third_party_records, key=sort_key)[:third_party_policy_max]:
            purl = rec.get("policy_url")
            if not purl:
                continue
            tp_dir = site_art_dir / "third_party" / _safe_dirname(rec["third_party_etld1"])
            tp_dir.mkdir(parents=True, exist_ok=True)
            res = await client.fetch(purl, capture_network=False, remove_overlays=True, magic=False)
            tp_text = (res.text or "").strip()
            _write_text(tp_dir / "policy.url.txt", purl)
            _write_text(tp_dir / "policy.txt", tp_text)
            third_party_policy_fetches.append({
                "third_party_etld1": rec["third_party_etld1"],
                "policy_url": purl,
                "fetch_success": res.success,
                "status_code": res.status_code,
                "text_len": len(tp_text),
                "error_message": res.error_message,
            })

    # 5) Final record
    status = "ok" if first_party_policy else "policy_not_found"
    if status != "ok":
        warn(f"[{etld1(home.url)}] Privacy policy not found.")

    return {
        "rank": rank,
        "input": domain_or_url,
        "site_url": site_url,
        "final_url": home.url,
        "site_etld1": etld1(home.url),
        "status": status,
        "home_status_code": home.status_code,
        "first_party_policy": first_party_policy,
        "third_parties": third_party_records,
        "third_party_policy_fetches": third_party_policy_fetches,
    }
