from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .utils.logging import warn

try:
    import trafilatura  # type: ignore
except Exception:
    trafilatura = None


def _bs4_extract(html: str) -> str | None:
    try:
        soup = BeautifulSoup(html, "lxml")
        text = "\n".join([ln.strip() for ln in soup.get_text("\n").splitlines() if ln.strip()])
        return text or None
    except Exception:
        return None


_ONETRUST_DOMAINS = ("onetrust.com", "cookielaw.org", "cookiepro.com")
_ONETRUST_STRONG_POLICY_HINTS = (
    "this privacy notice",
    "personal information we collect",
    "how we use your personal information",
    "your privacy rights and choices",
)
_ONETRUST_COOKIE_PANEL_MARKERS = (
    "why we use cookies and other tracking technologies?",
    "how can you manage your preferences?",
    "cookie list",
)


def _is_onetrust_source(source_url: str | None) -> bool:
    if not source_url:
        return False
    try:
        host = urlparse(source_url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    return any(host == d or host.endswith(f".{d}") for d in _ONETRUST_DOMAINS)


def _extract_onetrust_notice_container(
    html: str,
    *,
    source_url: str | None = None,
) -> str | None:
    # OneTrust privacy notices are frequently rendered into `.otnotice` containers.
    # On the same pages, cookie preference-center text can also be present and can
    # dominate generic extractors, so we prefer this known notice container.
    if not _is_onetrust_source(source_url) and "otnotice" not in html.lower():
        return None

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    seen: set[int] = set()
    candidates = (
        list(soup.select("div.otnotice-content"))
        + list(soup.select("div[id^='otnotice-']"))
        + list(soup.select("div.otnotice"))
    )
    for node in candidates:
        marker = id(node)
        if marker in seen:
            continue
        seen.add(marker)
        text = "\n".join([ln.strip() for ln in node.get_text("\n").splitlines() if ln.strip()])
        if len(text) < 120:
            continue

        lower = text.lower()
        if not any(hint in lower for hint in _ONETRUST_STRONG_POLICY_HINTS):
            continue

        cut_positions = [lower.find(tok) for tok in _ONETRUST_COOKIE_PANEL_MARKERS if tok in lower]
        if cut_positions:
            cut = min(cut_positions)
            if cut > 0:
                text = text[:cut].rstrip()

        if len(text) >= 120:
            return text

    # Fallback for aggressively cleaned HTML where class/id attributes are removed.
    full_text = _bs4_extract(html)
    if not full_text:
        return None

    lower = full_text.lower()
    if not any(hint in lower for hint in _ONETRUST_STRONG_POLICY_HINTS):
        return None

    start = lower.find("this privacy notice")
    if start == -1:
        start = lower.find("privacy notice")
    if start == -1:
        start = 0
    else:
        start = max(0, start - 120)

    end = len(full_text)
    cookie_positions = [
        lower.find(tok, start + 1)
        for tok in _ONETRUST_COOKIE_PANEL_MARKERS
        if lower.find(tok, start + 1) != -1
    ]
    if cookie_positions:
        end = min(cookie_positions)

    candidate = full_text[start:end].strip()
    if len(candidate) >= 120:
        return candidate
    return None


ExtractionMethod = Literal["onetrust_container", "trafilatura", "fallback"]


def extract_main_text_with_method(
    html: str | None,
    *,
    source_url: str | None = None,
) -> tuple[str | None, ExtractionMethod | None]:
    """Extract main document text from HTML and return extraction method."""
    if not html:
        return None, None

    onetrust_text = _extract_onetrust_notice_container(html, source_url=source_url)
    if onetrust_text:
        return onetrust_text, "onetrust_container"

    if trafilatura is not None:
        # Prefer markdown to keep headings/lists for downstream section parsing.
        try:
            text = trafilatura.extract(
                html,
                url=source_url,
                output_format="markdown",
                include_links=False,
                include_images=False,
                include_tables=True,
                deduplicate=False,
                favor_precision=True,
            )
            if isinstance(text, str) and text.strip():
                return text.strip(), "trafilatura"
        except TypeError:
            # Keep compatibility with older trafilatura signatures.
            try:
                text = trafilatura.extract(html)
                if isinstance(text, str) and text.strip():
                    return text.strip(), "trafilatura"
            except Exception as e:
                warn(f"Trafilatura extraction failed: {e}")
        except Exception as e:
            warn(f"Trafilatura extraction failed: {e}")

    text = _bs4_extract(html)
    if text and text.strip():
        return text, "fallback"
    return None, None


def extract_main_text_from_html(
    html: str | None,
    *,
    source_url: str | None = None,
) -> str | None:
    """Backward-compatible text-only API."""
    text, _method = extract_main_text_with_method(html, source_url=source_url)
    return text
