from privacy_research_dataset.policy_finder import extract_link_candidates

HTML = """
<html>
  <body>
    <footer>
      <a href="/privacy-policy">Privacy Policy</a>
      <a href="/terms">Terms</a>
    </footer>
  </body>
</html>
"""

def test_extract_candidates():
    cands = extract_link_candidates(HTML, "https://example.com", "example.com")
    assert any("privacy" in c.url for c in cands)
    # privacy should rank high
    assert cands[0].url.endswith("/privacy-policy")

def test_external_privacy_policy_link_allowed():
    html = """
    <html>
      <body>
        <footer>
          <a href="https://policies.google.com/privacy">Privacy Policy</a>
          <a href="https://twitter.com/example">Twitter</a>
        </footer>
      </body>
    </html>
    """
    cands = extract_link_candidates(html, "https://googleapis.com", "googleapis.com")
    assert any("policies.google.com/privacy" in c.url for c in cands)
    assert all("twitter.com" not in c.url for c in cands)
