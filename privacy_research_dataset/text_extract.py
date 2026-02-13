from __future__ import annotations

from typing import Literal

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


ExtractionMethod = Literal["trafilatura", "fallback"]


def extract_main_text_with_method(
    html: str | None,
    *,
    source_url: str | None = None,
) -> tuple[str | None, ExtractionMethod | None]:
    """Extract main document text from HTML and return extraction method."""
    if not html:
        return None, None

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
