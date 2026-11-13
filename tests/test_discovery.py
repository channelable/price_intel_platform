from price_intel.scrapers.discovery import extract_product_links


def test_extracts_canonical_deduped_links():
    html = """
    <a href="/apple-iphone-17-black-256-gb/p/itm123?pid=ABC123&amp;lid=LSTABC123">x</a>
    <a href="/apple-iphone-17-black-256-gb/p/itm123?pid=ABC999&amp;lid=OTHER">x</a>
    <a href="/google-pixel-11-frost-256-gb/p/itm456?pid=DEF456">x</a>
    <a href="https://www.flipkart.com/samsung-galaxy/p/itm789?pid=GHI789">x</a>
    <a href="/help/p/faq">x</a>
    <a href="https://evil.example/p/x?pid=BAD">x</a>
    """

    assert extract_product_links(html) == [
        "https://www.flipkart.com/apple-iphone-17-black-256-gb/p/itm123?pid=ABC123",
        "https://www.flipkart.com/google-pixel-11-frost-256-gb/p/itm456?pid=DEF456",
        "https://www.flipkart.com/samsung-galaxy/p/itm789?pid=GHI789",
    ]
