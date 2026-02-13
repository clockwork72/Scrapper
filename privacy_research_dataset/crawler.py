from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict
from datetime import datetime
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse, urlunparse

import aiohttp
from bs4 import BeautifulSoup

from .crawl4ai_client import Crawl4AIClient, Crawl4AIResult
from .policy_finder import (
    extract_link_candidates,
    extract_legal_hub_urls,
    fallback_privacy_urls,
    policy_likeliness_score,
    LinkCandidate,
)
from .third_party import third_parties_from_network_logs
from .tracker_radar import TrackerRadarIndex, TrackerRadarEntry
from .trackerdb import TrackerDbIndex, TrackerDbEntry
from .openwpm_engine import run_openwpm_for_third_parties
from .utils.etld import etld1
from .utils.logging import log, warn

_HTML_MARKER = re.compile(r"(?is)<\s*!doctype\s+html|<\s*html\b|<\s*head\b|<\s*body\b")
_NON_BROWSABLE_PATTERNS = [
    re.compile(pat, re.I)
    for pat in (
        r"access denied",
        r"forbidden",
        r"request blocked",
        r"service unavailable",
        r"temporarily unavailable",
        r"bad gateway",
        r"error\s*404",
        r"404\s*not\s*found",
        r"\bnot found\b",
        r"no such bucket",
        r"nosuchbucket",
        r"nosuchkey",
        r"invalid url",
        r"permission denied",
        r"not authorized",
        r"domain.*for sale",
        r"under construction",
        r"default web site page",
        r"iis windows server",
    )
]
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_PURE_LINK_LINE_RE = re.compile(
    r"^\s*(?P<prefix>(?:#{1,6}\s+|[-*•]\s+|\d+\.\s+)?)\[(?P<text>[^\]]+)\]\([^)]+\)\s*$"
)
_KEEP_KEYWORDS = (
    "last updated",
    "prior version",
    "definitions",
    "contact",
    "rights",
    "choices do i have",
)
_NAV_KEYWORDS = (
    "sign in",
    "your account",
    "account & lists",
    "your lists",
    "cart",
    "returns & orders",
    "returns and orders",
    "today's deals",
    "todays deals",
    "prime video",
    "registry",
    "gift cards",
    "customer service",
    "search amazon",
    "deliver to",
    "all departments",
    "select the department",
    "back to top",
    "get to know us",
    "make money with us",
    "amazon payment products",
    "let us help you",
    "privacy preferences",
    "was this information helpful",
    "thank you for your feedback",
    "this information is confusing",
    "this isn't the information i was looking for",
    "please select what best describes",
    "i don't like this policy",
    "we're unable to respond",
)
_SHORT_NAV_TOKENS = (
    "all",
    "en",
    "account",
    "orders",
    "recommendations",
    "browsing history",
    "watchlist",
    "cart",
    "registry",
    "create a list",
    "find a list",
    "content & devices",
    "subscribe & save items",
    "memberships & subscriptions",
    "music library",
    "find more solutions",
    "security and privacy",
    "legal policies",
    "submit",
    "yes",
    "no",
)
_FOOTER_TOKENS = (
    "conditions of use",
    "privacy notice",
    "consumer health data privacy disclosure",
    "your ads privacy choices",
    "all help topics",
)
_POLICY_SCAN_FULL_PAGE_DOMAINS = ("onetrust.com", "cookielaw.org", "cookiepro.com")


def _url_host(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _should_scan_full_page_policy(url: str | None) -> bool:
    host = _url_host(url)
    if not host:
        return False
    return any(host == d or host.endswith(f".{d}") for d in _POLICY_SCAN_FULL_PAGE_DOMAINS)

def _safe_dirname(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in s)[:200]

def _write_text(p: Path, text: str | None) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text or "", encoding="utf-8")

def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, "lxml")
        return "\n".join([ln.strip() for ln in soup.get_text("\n").splitlines() if ln.strip()])
    except Exception:
        return None


def _normalize_link_markup(line: str) -> str:
    return _INLINE_LINK_RE.sub(lambda m: m.group(1), line)


def _looks_like_heading(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    if any(k in lower for k in _KEEP_KEYWORDS):
        return True
    if len(text) > 90:
        return False
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return False
    titleish = sum(1 for w in words if w[:1].isupper())
    return titleish / max(len(words), 1) >= 0.6


def _is_nav_line(line: str, normalized: str, counts: dict[str, int]) -> bool:
    lower = normalized
    if any(k in lower for k in _FOOTER_TOKENS):
        return True
    if any(k in lower for k in _KEEP_KEYWORDS):
        return False
    if any(k in lower for k in _NAV_KEYWORDS):
        return True
    stripped = line.lstrip()
    if stripped.startswith("#####") or stripped.startswith("* #####"):
        return True
    if "©" in line or "copyright" in lower:
        return True
    if "yes" in lower and "no" in lower and len(lower) <= 12:
        return True
    plain = re.sub(r"^[#*•\-\d\.\s]+", "", lower).strip()
    if plain in _SHORT_NAV_TOKENS and len(plain) <= 30:
        return True
    if len(plain) <= 3 and plain in ("en", "all"):
        return True
    if counts.get(lower, 0) >= 3 and len(lower) <= 80:
        return True
    return False


def _clean_policy_text(text: str | None) -> str:
    if not text:
        return ""
    text = _MARKDOWN_IMAGE_RE.sub("", text)
    raw_lines = text.splitlines()
    counts: dict[str, int] = {}
    for ln in raw_lines:
        norm = re.sub(r"\s+", " ", ln.strip().lower())
        if norm:
            counts[norm] = counts.get(norm, 0) + 1

    candidates: list[dict[str, object]] = []
    pending_blank = False

    for line in raw_lines:
        line = line.strip()
        if not line:
            pending_blank = True
            continue
        if _MARKDOWN_IMAGE_RE.search(line):
            line = _MARKDOWN_IMAGE_RE.sub("", line).strip()
            if not line:
                continue

        pure_match = _PURE_LINK_LINE_RE.match(line)
        if pure_match:
            prefix = pure_match.group("prefix") or ""
            link_text = pure_match.group("text").strip()
            if prefix:
                line = f"{prefix}{link_text}"
            else:
                if _looks_like_heading(link_text):
                    line = link_text
                else:
                    continue
        else:
            line = _normalize_link_markup(line)

        if "](http" in line or "](https" in line:
            continue
        if line.startswith("http://") or line.startswith("https://") or line.startswith("www."):
            continue

        normalized = re.sub(r"\s+", " ", line.strip().lower())
        if not normalized:
            continue
        keep_force = any(k in normalized for k in _KEEP_KEYWORDS)
        nav_like = _is_nav_line(line, normalized, counts)

        candidates.append(
            {
                "line": line,
                "normalized": normalized,
                "keep": keep_force,
                "nav": nav_like,
                "pending_blank": pending_blank,
                "drop": False,
            }
        )
        pending_blank = False

    # Drop nav-like preamble before the first privacy heading/last-updated marker.
    content_start = None
    for idx, item in enumerate(candidates):
        norm = item["normalized"]
        if "last updated" in norm or ("privacy" in norm and ("policy" in norm or "notice" in norm)):
            content_start = idx
            break
    if content_start is not None:
        for idx in range(content_start):
            item = candidates[idx]
            if item["keep"]:
                continue
            norm = item["normalized"]
            if item["nav"] or len(norm) <= 30:
                item["drop"] = True

    # Drop footer block from the first footer marker near the end.
    footer_cut = None
    cutoff_threshold = int(len(candidates) * 0.6)
    for idx, item in enumerate(candidates):
        norm = item["normalized"]
        line = str(item["line"])
        if idx < cutoff_threshold:
            continue
        if any(k in norm for k in _FOOTER_TOKENS) or "©" in line or "copyright" in norm:
            footer_cut = idx
            break
    if footer_cut is not None:
        for idx in range(footer_cut, len(candidates)):
            if not candidates[idx]["keep"]:
                candidates[idx]["drop"] = True

    cleaned: list[str] = []
    for item in candidates:
        if item["drop"]:
            continue
        line = str(item["line"])
        normalized = str(item["normalized"])
        if item["nav"] and not item["keep"]:
            continue
        if not any(ch.isalnum() for ch in line):
            continue
        if item["pending_blank"] and cleaned:
            cleaned.append("")
        cleaned.append(line)

    return "\n".join(cleaned).strip()

def _combine_errors(*msgs: str | None) -> str | None:
    parts = [m for m in msgs if m and str(m).strip()]
    if not parts:
        return None
    return " | ".join(parts)


async def _fetch_home_with_retry(
    client: Crawl4AIClient,
    site_url: str,
    *,
    capture_network: bool,
    max_attempts: int = 3,
    retry_delay_s: float = 0.8,
) -> tuple[Crawl4AIResult | None, str, int, list[str]]:
    errors: list[str] = []
    total_ms = 0
    home_fetch_mode = "crawl4ai"
    for attempt in range(1, max_attempts + 1):
        t_home = time.perf_counter()
        home = await client.fetch(
            site_url,
            capture_network=capture_network,
            remove_overlays=True,
            magic=False,
            scan_full_page=False,
        )
        total_ms += int((time.perf_counter() - t_home) * 1000)

        if home.success and not home.cleaned_html and home.raw_html:
            home.cleaned_html = home.raw_html
        if home.success and not home.text and home.cleaned_html:
            home.text = _html_to_text(home.cleaned_html)

        if home.success and home.cleaned_html:
            return home, home_fetch_mode, total_ms, errors

        t_home_fb = time.perf_counter()
        fallback = await _simple_http_fetch(
            site_url,
            user_agent=client.user_agent,
            timeout_ms=client.page_timeout_ms,
            allow_http_fallback=True,
        )
        total_ms += int((time.perf_counter() - t_home_fb) * 1000)
        if fallback.success and fallback.cleaned_html:
            return fallback, "simple_http", total_ms, errors

        errors.append(_combine_errors(home.error_message, fallback.error_message) or "home_fetch_failed")

        if attempt < max_attempts:
            await asyncio.sleep(retry_delay_s * attempt)

    return None, home_fetch_mode, total_ms, errors

def _classify_non_browsable(home: Crawl4AIResult) -> tuple[bool, str | None]:
    # Treat explicit HTTP errors as non-browsable when we did get a page.
    if home.status_code and home.status_code >= 400:
        return True, f"http_status_{home.status_code}"

    text = (home.text or _html_to_text(home.cleaned_html) or "").strip()
    text_len = len(text)

    # Error page markers.
    low_text = text.lower()
    for pat in _NON_BROWSABLE_PATTERNS:
        if pat.search(low_text):
            return True, "error_page_text"

    # Link-sparse + short text: often infra/service or placeholder.
    if home.cleaned_html:
        try:
            soup = BeautifulSoup(home.cleaned_html, "lxml")
            anchor_count = len(soup.find_all("a", href=True))
        except Exception:
            anchor_count = 0
    else:
        anchor_count = 0

    if text_len < 200 and anchor_count == 0:
        return True, "no_links_short_text"
    if text_len < 80 and anchor_count <= 1:
        return True, "very_sparse_page"

    return False, None

async def _simple_http_fetch(
    url: str,
    *,
    user_agent: str | None,
    timeout_ms: int,
    max_bytes: int = 2_000_000,
    allow_http_fallback: bool = True,
) -> Crawl4AIResult:
    headers = {"User-Agent": user_agent} if user_agent else {}
    parsed = urlparse(url)
    urls_to_try = [url]
    if allow_http_fallback and parsed.scheme == "https":
        urls_to_try.append(urlunparse(parsed._replace(scheme="http")))

    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with aiohttp.ClientSession(headers=headers) as session:
        last_error: str | None = None
        for u in urls_to_try:
            try:
                async with session.get(u, timeout=timeout, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        last_error = f"http_status_{resp.status}"
                        continue
                    ctype = (resp.headers.get("content-type") or "").lower()
                    raw = await resp.content.read(max_bytes)
                    if not raw:
                        last_error = "empty_body"
                        continue
                    text = raw.decode("utf-8", errors="ignore")
                    if ("text/html" not in ctype) and ("application/xhtml" not in ctype):
                        if not _HTML_MARKER.search(text):
                            last_error = f"non_html_content_type:{ctype}"
                            continue
                    if not _HTML_MARKER.search(text):
                        last_error = "html_marker_missing"
                        continue

                    cleaned = text
                    extracted_text = _html_to_text(cleaned)
                    return Crawl4AIResult(
                        url=str(resp.url),
                        success=True,
                        status_code=resp.status,
                        raw_html=text,
                        cleaned_html=cleaned,
                        text=extracted_text,
                        network_requests=[],
                        error_message=None,
                    )
            except Exception as e:
                last_error = str(e)
                continue

    return Crawl4AIResult(
        url=url,
        success=False,
        status_code=None,
        raw_html=None,
        cleaned_html=None,
        text=None,
        network_requests=None,
        error_message=last_error or "simple_http_fetch_failed",
    )

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
    best_fallback: dict[str, Any] | None = None
    best_key: tuple[float, int] | None = None

    async def try_candidate(c: LinkCandidate) -> dict[str, Any]:
        res = await client.fetch(
            c.url,
            capture_network=False,
            remove_overlays=True,
            magic=False,
            scan_full_page=_should_scan_full_page_policy(c.url),
        )
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
            text_extraction_method=res.text_extraction_method,
        )
        text = (res.text or "").strip()
        rec["text_len"] = len(text)
        rec["likeliness_score"] = policy_likeliness_score(text)
        return rec | {"text": text, "cleaned_html": res.cleaned_html, "raw_html": res.raw_html}

    def is_policy_candidate(rec: dict[str, Any]) -> bool:
        if not rec.get("fetch_success"):
            return False
        score = float(rec.get("likeliness_score") or -10.0)
        text_len = int(rec.get("text_len") or 0)
        if score >= 5.0 and text_len >= 300:
            return True
        if score >= 4.0 and text_len >= 500:
            return True
        return score >= 3.0 and text_len >= 800

    def consider_best(rec: dict[str, Any]) -> None:
        nonlocal best_fallback, best_key
        if not rec.get("fetch_success"):
            return
        score = float(rec.get("likeliness_score") or -10.0)
        text_len = int(rec.get("text_len") or 0)
        if score < 3.0 or text_len < 200:
            return
        key = (score, text_len)
        if best_key is None or key > best_key:
            best_key = key
            best_fallback = rec

    # 1) Try top candidates directly
    for c in candidates[:max_candidates]:
        rec = await try_candidate(c)
        tried.append({k: rec[k] for k in rec.keys() if k not in ("text", "cleaned_html", "raw_html")})
        consider_best(rec)
        if is_policy_candidate(rec):
            chosen = rec
            break

    # 2) Fallback common paths
    if chosen is None:
        for c in fallback_privacy_urls(site_url, site_et):
            rec = await try_candidate(c)
            tried.append({k: rec[k] for k in rec.keys() if k not in ("text", "cleaned_html", "raw_html")})
            consider_best(rec)
            if is_policy_candidate(rec):
                chosen = rec
                break

    # 3) Legal hub expansion (depth 1): fetch 1-2 legal/terms pages and rescan for privacy links
    if chosen is None and candidates:
        hub_urls = extract_legal_hub_urls(candidates, limit=max_hub_pages)
        for hub in hub_urls:
            hub_res = await client.fetch(
                hub,
                capture_network=False,
                remove_overlays=True,
                magic=False,
                scan_full_page=_should_scan_full_page_policy(hub),
            )
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
                consider_best(rec)
                if is_policy_candidate(rec):
                    chosen = rec
                    break
            if chosen is not None:
                break

    # 4) Best-effort fallback: pick the strongest policy-like page even if shorter.
    if chosen is None and best_fallback is not None:
        chosen = best_fallback

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
            "url","anchor_text","score","source","candidate_etld1","is_same_site","status_code","likeliness_score","text_len","text_extraction_method"
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
    trackerdb: TrackerDbIndex | None = None,
    fetch_third_party_policies: bool = True,
    third_party_policy_max: int = 30,
    third_party_engine: str = "crawl4ai",  # crawl4ai|openwpm
    run_id: str | None = None,
    stage_callback: Callable[[str], None] | None = None,
    exclude_same_entity: bool = False,
    third_party_policy_fetcher: Callable[[str], Awaitable[Crawl4AIResult]] | None = None,
) -> dict[str, Any]:
    """
    Process a single website:
    - Fetch homepage
    - Find and fetch best privacy policy
    - Extract third-party domains from network logs (Crawl4AI) or OpenWPM (optional)
    - Map third parties via Tracker Radar / Ghostery TrackerDB (+ optionally fetch their policy texts)
    """
    started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    t_total = time.perf_counter()

    site_url = domain_or_url.strip()
    if not site_url:
        return {"input": domain_or_url, "error": "empty_input"}
    if "://" not in site_url:
        site_url = "https://" + site_url

    site_art_dir = Path(artifacts_dir) / _safe_dirname(etld1(site_url) or domain_or_url)
    site_art_dir.mkdir(parents=True, exist_ok=True)

    # 1) Homepage fetch
    if stage_callback:
        stage_callback("home_fetch")
    capture_net = (third_party_engine == "crawl4ai")
    home, home_fetch_mode, home_fetch_ms, home_errors = await _fetch_home_with_retry(
        client,
        site_url,
        capture_network=capture_net,
    )

    if not home:
        return {
            "rank": rank,
            "input": domain_or_url,
            "site_url": site_url,
            "final_url": site_url,
            "site_etld1": etld1(site_url),
            "status": "home_fetch_failed",
            "status_code": None,
            "error_message": _combine_errors(*home_errors),
            "home_fetch_mode": home_fetch_mode,
            "error_code": "home_fetch_failed",
            "home_fetch_ms": home_fetch_ms,
            "home_fetch_attempts": len(home_errors),
            "total_ms": int((time.perf_counter() - t_total) * 1000),
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

    _write_text(site_art_dir / "home.raw.html", home.raw_html)
    _write_text(site_art_dir / "home.cleaned.html", home.cleaned_html)
    if home.text:
        _write_text(site_art_dir / "home.txt", home.text)

    # 2) Privacy policy discovery + fetch
    if stage_callback:
        stage_callback("policy_discovery")
    t_policy = time.perf_counter()
    policy_info = await _fetch_best_policy(client, home.url, home.cleaned_html)
    policy_fetch_ms = int((time.perf_counter() - t_policy) * 1000)
    _write_json(site_art_dir / "policy.discovery.json", {
        k: policy_info[k] for k in ("site_etld1","candidates_top","tried","chosen")
    })

    chosen_full = policy_info.get("_chosen_full")
    if chosen_full is None and home.text:
        # If the homepage itself looks like a privacy policy, accept it.
        home_text = (home.text or "").strip()
        home_score = policy_likeliness_score(home_text)
        if home_score >= 3.0 and len(home_text) >= 300:
            chosen_full = {
                "url": home.url,
                "status_code": home.status_code,
                "likeliness_score": home_score,
                "text_len": len(home_text),
                "text": home_text,
                "cleaned_html": home.cleaned_html,
                "raw_html": home.raw_html,
                "text_extraction_method": home.text_extraction_method or "fallback",
            }
    first_party_policy = None
    if chosen_full:
        raw_text = chosen_full.get("text") or ""
        cleaned_text = _clean_policy_text(raw_text)
        first_party_policy = {
            "url": chosen_full.get("url"),
            "status_code": chosen_full.get("status_code"),
            "likeliness_score": chosen_full.get("likeliness_score"),
            "text_len": len(cleaned_text),
            "text_len_raw": chosen_full.get("text_len"),
            "extraction_method": chosen_full.get("text_extraction_method") or "fallback",
        }
        _write_text(site_art_dir / "policy.url.txt", chosen_full.get("url"))
        _write_text(site_art_dir / "policy.raw.txt", raw_text)
        _write_text(site_art_dir / "policy.txt", cleaned_text)
        _write_json(
            site_art_dir / "policy.extraction.json",
            {
                "method": first_party_policy["extraction_method"],
                "source_url": chosen_full.get("url"),
            },
        )
        _write_text(site_art_dir / "policy.cleaned.html", chosen_full.get("cleaned_html"))
        if chosen_full.get("raw_html"):
            _write_text(site_art_dir / "policy.raw.html", chosen_full.get("raw_html"))

    # 3) Third-party extraction
    if stage_callback:
        stage_callback("third_party_extract")
    t_tp = time.perf_counter()
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
    third_party_extract_ms = int((time.perf_counter() - t_tp) * 1000)

    third_party_etlds = obs.third_party_etld1s

    def _merge_entries(radar_entry: TrackerRadarEntry | None, db_entry: TrackerDbEntry | None) -> dict[str, Any]:
        # Mixed mode: prefer Tracker Radar if present; otherwise fall back to TrackerDB.
        if radar_entry:
            return {
                "entity": radar_entry.entity,
                "categories": list(radar_entry.categories or []),
                "prevalence": radar_entry.prevalence,
                "policy_url": radar_entry.policy_url,
                "tracker_radar_source_domain_file": radar_entry.source_domain_file,
                "trackerdb_source_pattern_file": None,
                "trackerdb_source_org_file": None,
            }
        if db_entry:
            return {
                "entity": db_entry.entity,
                "categories": list(db_entry.categories or []),
                "prevalence": db_entry.prevalence,
                "policy_url": db_entry.policy_url,
                "tracker_radar_source_domain_file": None,
                "trackerdb_source_pattern_file": db_entry.source_pattern_file,
                "trackerdb_source_org_file": db_entry.source_org_file,
            }
        return {
            "entity": None,
            "categories": [],
            "prevalence": None,
            "policy_url": None,
            "tracker_radar_source_domain_file": None,
            "trackerdb_source_pattern_file": None,
            "trackerdb_source_org_file": None,
        }

    site_entity: str | None = None
    site_etld = etld1(home.url) or ""
    if tracker_radar:
        site_entry = tracker_radar.lookup(site_etld)
        if site_entry and site_entry.entity:
            site_entity = site_entry.entity
    if not site_entity and trackerdb:
        site_entry_db = trackerdb.lookup(site_etld)
        if site_entry_db and site_entry_db.entity:
            site_entity = site_entry_db.entity

    third_party_records: list[dict[str, Any]] = []
    for tp in third_party_etlds:
        radar_entry = tracker_radar.lookup(tp) if tracker_radar else None
        db_entry = trackerdb.lookup(tp) if trackerdb else None
        merged = _merge_entries(radar_entry, db_entry)
        tp_entity = merged.get("entity")
        if exclude_same_entity and site_entity and tp_entity and tp_entity == site_entity:
            continue
        third_party_records.append({
            "third_party_etld1": tp,
            "entity": merged.get("entity"),
            "categories": merged.get("categories") or [],
            "prevalence": merged.get("prevalence"),
            "policy_url": merged.get("policy_url"),
            "tracker_radar_source_domain_file": merged.get("tracker_radar_source_domain_file"),
            "trackerdb_source_pattern_file": merged.get("trackerdb_source_pattern_file"),
            "trackerdb_source_org_file": merged.get("trackerdb_source_org_file"),
        })

    # 4) Optional: fetch third-party policy texts (best-effort)
    if stage_callback:
        stage_callback("third_party_policy_fetch")
    t_tp_policy = time.perf_counter()
    third_party_policy_fetches: list[dict[str, Any]] = []
    if fetch_third_party_policies and (tracker_radar or trackerdb):
        def sort_key(r: dict[str, Any]):
            p = r.get("prevalence")
            return (-(p if isinstance(p, (int, float)) else -1.0), r["third_party_etld1"])

        for rec in sorted(third_party_records, key=sort_key)[:third_party_policy_max]:
            purl = rec.get("policy_url")
            if not purl:
                continue
            tp_dir = site_art_dir / "third_party" / _safe_dirname(rec["third_party_etld1"])
            tp_dir.mkdir(parents=True, exist_ok=True)
            if third_party_policy_fetcher is not None:
                res = await third_party_policy_fetcher(purl)
            else:
                res = await client.fetch(
                    purl,
                    capture_network=False,
                    remove_overlays=True,
                    magic=False,
                    scan_full_page=_should_scan_full_page_policy(purl),
                )
            tp_text_raw = (res.text or "").strip()
            tp_text = _clean_policy_text(tp_text_raw)
            _write_text(tp_dir / "policy.url.txt", purl)
            _write_text(tp_dir / "policy.raw.txt", tp_text_raw)
            _write_text(tp_dir / "policy.txt", tp_text)
            tp_method = res.text_extraction_method or "fallback"
            _write_json(
                tp_dir / "policy.extraction.json",
                {
                    "method": tp_method,
                    "source_url": purl,
                },
            )
            third_party_policy_fetches.append({
                "third_party_etld1": rec["third_party_etld1"],
                "policy_url": purl,
                "fetch_success": res.success,
                "status_code": res.status_code,
                "text_len": len(tp_text),
                "text_len_raw": len(tp_text_raw),
                "extraction_method": tp_method,
                "error_message": res.error_message,
            })
    third_party_policy_fetch_ms = int((time.perf_counter() - t_tp_policy) * 1000)

    fetch_method_by_tp = {
        str(item.get("third_party_etld1")): item.get("extraction_method")
        for item in third_party_policy_fetches
        if item.get("third_party_etld1")
    }
    if fetch_method_by_tp:
        for tp in third_party_records:
            et = str(tp.get("third_party_etld1") or "")
            tp["policy_extraction_method"] = fetch_method_by_tp.get(et)

    # 5) Final record
    status = "ok" if first_party_policy else "policy_not_found"
    non_browsable_reason: str | None = None
    if status != "ok":
        is_nb, reason = _classify_non_browsable(home)
        if is_nb:
            status = "non_browsable"
            non_browsable_reason = reason
            warn(f"[{etld1(home.url)}] Classified as non-browsable ({reason}).")
        else:
            warn(f"[{etld1(home.url)}] Privacy policy not found.")

    return {
        "rank": rank,
        "input": domain_or_url,
        "site_url": site_url,
        "final_url": home.url,
        "site_etld1": etld1(home.url),
        "status": status,
        "home_status_code": home.status_code,
        "home_fetch_mode": home_fetch_mode,
        "home_fetch_attempts": max(1, len(home_errors) + 1),
        "first_party_policy": first_party_policy,
        "non_browsable_reason": non_browsable_reason,
        "third_parties": third_party_records,
        "third_party_policy_fetches": third_party_policy_fetches,
        "error_code": (None if status == "ok" else status),
        "home_fetch_ms": home_fetch_ms,
        "policy_fetch_ms": policy_fetch_ms,
        "third_party_extract_ms": third_party_extract_ms,
        "third_party_policy_fetch_ms": third_party_policy_fetch_ms,
        "total_ms": int((time.perf_counter() - t_total) * 1000),
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
