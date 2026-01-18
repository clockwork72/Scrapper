from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any, Iterable

import aiohttp

from .crawl4ai_client import Crawl4AIClient
from .crawler import process_site
from .tracker_radar import TrackerRadarIndex
from .tranco_list import get_tranco_sites
from .utils.io import append_jsonl
from .utils.logging import log, warn


# ---------------------------
# Prefilter defaults
# ---------------------------

DEFAULT_EXCLUDE_SUFFIXES: set[str] = {
    # Infrastructure / authoritative DNS
    "gtld-servers.net",
    "root-servers.net",
    "iana-servers.net",
}

_HTML_MARKER = re.compile(r"(?is)<\s*!doctype\s+html|<\s*html\b|<\s*head\b|<\s*body\b")
_LINK_MARKER = re.compile(r"(?is)<\s*a\b")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="privacy-dataset",
        description="Build Step-1 dataset: websites -> first-party privacy policy + observed third-party tools (+ their policies via Tracker Radar).",
    )
    src = p.add_argument_group("Input source")
    src.add_argument("--input", type=str, default=None, help="Path to a newline-delimited list of domains/URLs. If omitted, uses Tranco.")
    src.add_argument("--tranco-top", type=int, default=100, help="How many Tranco sites to include (if --input not set).")
    src.add_argument("--tranco-date", type=str, default=None, help="Tranco snapshot date YYYY-MM-DD (recommended for reproducibility).")
    src.add_argument("--tranco-cache-dir", type=str, default=".tranco_cache", help="Tranco cache directory.")

    out = p.add_argument_group("Output")
    out.add_argument("--out", type=str, required=True, help="Output JSONL path (one record per site).")
    out.add_argument("--artifacts-dir", type=str, required=True, help="Directory to store HTML/text artifacts per site.")

    radar = p.add_argument_group("Tracker Radar")
    radar.add_argument("--tracker-radar-index", type=str, default=None, help="Path to tracker_radar_index.json (built with scripts/build_tracker_radar_index.py).")

    crawl = p.add_argument_group("Crawling")
    crawl.add_argument("--browser", type=str, default="chromium", choices=["chromium", "firefox", "webkit"], help="Browser engine (Playwright).")
    crawl.add_argument("--headed", action="store_true", help="Run with a visible browser window (debugging). Default is headless.")
    crawl.add_argument("--verbose", action="store_true", help="Verbose Crawl4AI logs.")
    crawl.add_argument("--user-agent", type=str, default=None, help="Custom User-Agent.")
    crawl.add_argument("--proxy", type=str, default=None, help="Proxy URL (e.g., http://user:pass@host:port).")
    crawl.add_argument("--locale", type=str, default="en-GB", help="Browser locale. Default: en-GB")
    crawl.add_argument("--timezone-id", type=str, default="Europe/Paris", help="Browser timezone id. Default: Europe/Paris")
    crawl.add_argument("--page-timeout-ms", type=int, default=15000, help="Page timeout in ms.")

    scale = p.add_argument_group("Scale / behavior")
    scale.add_argument("--max-sites", type=int, default=None, help="Hard cap on number of sites processed.")
    scale.add_argument("--concurrency", type=int, default=3, help="How many sites to process concurrently.")
    scale.add_argument("--third-party-engine", type=str, default="crawl4ai", choices=["crawl4ai", "openwpm"], help="How to collect third-party requests: crawl4ai (default) or openwpm (heavier).")
    scale.add_argument("--no-third-party-policy-fetch", action="store_true", help="Do not fetch third-party policy texts (still records mappings).")
    scale.add_argument("--third-party-policy-max", type=int, default=30, help="Max number of third-party policies to fetch per site (ranked by prevalence when available).")

    # ---------------------------
    # NEW: Website prefilter
    # ---------------------------
    pf = p.add_argument_group("Prefilter (drop non-browsable/infrastructure domains)")
    pf.add_argument(
        "--prefilter-websites",
        action="store_true",
        help="Before crawling, keep only domains that respond with HTML over HTTP(S). Helps remove infra domains like gtld-servers.net.",
    )
    pf.add_argument(
        "--prefilter-timeout-ms",
        type=int,
        default=7000,
        help="Timeout for the lightweight prefilter HTTP check (ms). Default: 7000",
    )
    pf.add_argument(
        "--prefilter-concurrency",
        type=int,
        default=50,
        help="Concurrency for the prefilter HTTP checks (independent of crawl concurrency). Default: 50",
    )
    pf.add_argument(
        "--prefilter-max-bytes",
        type=int,
        default=65536,
        help="Max bytes to read from response body during prefilter. Default: 65536 (64KB).",
    )
    pf.add_argument(
        "--prefilter-allow-http",
        action="store_true",
        help="Allow http:// fallback if https:// fails. Default: off (HTTPS only).",
    )
    pf.add_argument(
        "--prefilter-require-links",
        action="store_true",
        help="Require that the HTML contains at least one <a> link. Increases precision for 'real websites'.",
    )
    pf.add_argument(
        "--exclude-suffix",
        action="append",
        default=[],
        help="Exclude domains ending with this suffix (repeatable). Example: --exclude-suffix gtld-servers.net",
    )
    pf.add_argument(
        "--exclude-domains-file",
        type=str,
        default=None,
        help="Path to a file with domains to exclude (one per line; # comments allowed).",
    )

    return p.parse_args()


def _load_input_sites(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.input:
        path = Path(args.input)
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
        sites = [{"rank": None, "site": ln} for ln in lines]
    else:
        tranco = get_tranco_sites(args.tranco_top, args.tranco_date, args.tranco_cache_dir)
        sites = [{"rank": s.rank, "site": s.domain} for s in tranco]

    if args.max_sites:
        sites = sites[: args.max_sites]
    return sites


def _load_exclude_exact(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        warn(f"Exclude file not found: {path}")
        return set()
    exact: set[str] = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        exact.add(ln.lower().rstrip("."))
    return exact


def _normalize_suffix(s: str) -> str:
    s = s.strip().lower().lstrip(".")
    return s.rstrip(".")


def _is_excluded(domain: str, suffixes: set[str], exact: set[str]) -> bool:
    d = domain.strip().lower().rstrip(".")
    if d in exact:
        return True
    # suffix match: exact suffix or subdomain of suffix
    for suf in suffixes:
        if d == suf or d.endswith("." + suf):
            return True
    return False


async def _looks_like_website(
    session: aiohttp.ClientSession,
    domain: str,
    *,
    timeout_ms: int,
    max_bytes: int,
    allow_http: bool,
    require_links: bool,
) -> bool:
    # Prefer HTTPS; optionally fall back to HTTP.
    schemes = ["https"]
    if allow_http:
        schemes.append("http")

    for scheme in schemes:
        url = f"{scheme}://{domain}/"
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
            async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
                if resp.status >= 400:
                    continue

                ctype = (resp.headers.get("content-type") or "").lower()
                if ("text/html" not in ctype) and ("application/xhtml" not in ctype):
                    continue

                chunk = await resp.content.read(max_bytes)
                if not chunk:
                    continue

                text = chunk.decode("utf-8", errors="ignore")
                if not _HTML_MARKER.search(text):
                    continue
                if require_links and not _LINK_MARKER.search(text):
                    continue

                return True

        except Exception:
            continue

    return False


async def _prefilter_sites(args: argparse.Namespace, sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Combine default suffix excludes with user-provided.
    suffixes = set(DEFAULT_EXCLUDE_SUFFIXES)
    for s in args.exclude_suffix or []:
        suffixes.add(_normalize_suffix(s))

    exact = _load_exclude_exact(args.exclude_domains_file)

    # First apply cheap string-based excludes.
    pre = []
    excluded_count = 0
    for rec in sites:
        dom = str(rec["site"]).strip()
        if _is_excluded(dom, suffixes, exact):
            excluded_count += 1
            continue
        pre.append(rec)

    if excluded_count:
        log(f"Prefilter: excluded {excluded_count} sites by suffix/file rules.")

    if not pre:
        return pre

    # Now do HTTP checks.
    ua = args.user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    headers = {"User-Agent": ua}

    sem = asyncio.Semaphore(max(1, int(args.prefilter_concurrency)))

    async with aiohttp.ClientSession(headers=headers) as session:
        async def check_one(rec: dict[str, Any]) -> tuple[dict[str, Any], bool]:
            async with sem:
                dom = str(rec["site"]).strip()
                ok = await _looks_like_website(
                    session,
                    dom,
                    timeout_ms=int(args.prefilter_timeout_ms),
                    max_bytes=int(args.prefilter_max_bytes),
                    allow_http=bool(args.prefilter_allow_http),
                    require_links=bool(args.prefilter_require_links),
                )
                return rec, ok

        results = await asyncio.gather(*(check_one(r) for r in pre))
        kept = [rec for (rec, ok) in results if ok]

    log(f"Prefilter: kept {len(kept)}/{len(sites)} sites that look like browsable websites.")
    return kept


async def _run(args: argparse.Namespace) -> None:
    tracker_radar = TrackerRadarIndex(args.tracker_radar_index) if args.tracker_radar_index else None
    sites = _load_input_sites(args)

    log(f"Loaded {len(sites)} sites.")

    # ---------------------------
    # NEW: Prefilter stage
    # ---------------------------
    if args.prefilter_websites:
        try:
            sites = await _prefilter_sites(args, sites)
        except Exception as e:
            warn(f"Prefilter failed unexpectedly; continuing without prefilter. Error: {e}")

    if args.third_party_engine == "openwpm" and args.concurrency > 1:
        warn("OpenWPM engine is blocking/heavy; forcing --concurrency 1.")
        args.concurrency = 1
    if not tracker_radar:
        warn("No --tracker-radar-index provided. Third-party domains will be collected but not mapped to entities/policies.")

    sem = asyncio.Semaphore(max(1, int(args.concurrency)))

    async with Crawl4AIClient(
        browser_type=args.browser,
        headless=(not args.headed),
        verbose=args.verbose,
        user_agent=args.user_agent,
        proxy=args.proxy,
        locale=args.locale,
        timezone_id=args.timezone_id,
        page_timeout_ms=args.page_timeout_ms,
    ) as client:

        async def worker(rec: dict[str, Any]) -> None:
            async with sem:
                rank = rec["rank"]
                site = rec["site"]
                log(f"Processing {site} (rank={rank})")
                try:
                    result = await process_site(
                        client,
                        site,
                        rank=rank,
                        artifacts_dir=args.artifacts_dir,
                        tracker_radar=tracker_radar,
                        fetch_third_party_policies=not args.no_third_party_policy_fetch,
                        third_party_policy_max=args.third_party_policy_max,
                        third_party_engine=args.third_party_engine,
                    )
                except Exception as e:
                    warn(f"Unhandled error for {site}: {e}")
                    result = {
                        "rank": rank,
                        "input": site,
                        "status": "exception",
                        "error_message": str(e),
                    }

                append_jsonl(args.out, result)

                if result.get("status") != "ok":
                    warn(f"FAILED {site}: {result.get('status')}")

        await asyncio.gather(*[worker(r) for r in sites])


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
