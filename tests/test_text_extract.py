from privacy_research_dataset.text_extract import extract_main_text_with_method


def test_onetrust_notice_container_preferred_over_cookie_panel():
    html = """
    <html>
      <body>
        <div id="otnotice-abc123" class="otnotice">
          <div class="otnotice-content">
            <h1>OneTrust Privacy Notice</h1>
            <h2>Introduction</h2>
            <p>
              This Privacy Notice covers the personal information that OneTrust
              collects, stores, uses, and otherwise processes.
            </p>
            <h2>Personal Information we collect</h2>
            <p>
              OneTrust collects personal information that has been provided by
              you directly through your interactions with us.
            </p>
          </div>
        </div>

        <section id="cookie-panel">
          <h2>How can you manage your preferences?</h2>
          <p>Why we use cookies and other tracking technologies?</p>
          <p>Cookie List</p>
        </section>
      </body>
    </html>
    """

    text, method = extract_main_text_with_method(
        html,
        source_url="https://www.onetrust.com/privacy-notice/",
    )

    assert method == "onetrust_container"
    assert text is not None
    assert "OneTrust Privacy Notice" in text
    assert "Personal Information we collect" in text
    assert "How can you manage your preferences?" not in text
    assert "Cookie List" not in text
