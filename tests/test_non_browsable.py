from privacy_research_dataset.crawler import _classify_non_browsable
from privacy_research_dataset.crawl4ai_client import Crawl4AIResult


def _res(html: str, text: str | None = None, status_code: int | None = 200) -> Crawl4AIResult:
    return Crawl4AIResult(
        url="https://example.com",
        success=True,
        status_code=status_code,
        raw_html=html,
        cleaned_html=html,
        text=text,
        network_requests=[],
        error_message=None,
    )


def test_classify_error_page():
    html = "<html><body><h1>403 Forbidden</h1><p>Access Denied</p></body></html>"
    is_nb, reason = _classify_non_browsable(_res(html))
    assert is_nb
    assert reason in {"error_page_text", "http_status_403"}


def test_classify_sparse_page():
    html = "<html><body>OK</body></html>"
    is_nb, reason = _classify_non_browsable(_res(html))
    assert is_nb
    assert reason in {"no_links_short_text", "very_sparse_page"}
