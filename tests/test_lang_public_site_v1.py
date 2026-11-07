"""Static Koschei Lang website truth, navigation and pricing checks."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re

SITE = Path(__file__).resolve().parents[1] / "commercial" / "lang-site" / "index.html"
POLAR = "https://buy.polar.sh/polar_cl_H3mMbTpBdziezC3ooJARCQIMHqzVHEeM15E1v0C7XlR"


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.translations, self.buttons = [], [], [], []
        self.lang = None
        self.scripts = 0
        self.styles = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "a":
            self.links.append(a)
        if tag == "button":
            self.buttons.append(a)
        if "data-en" in a or "data-tr" in a:
            self.translations.append(a)
        if tag == "script":
            self.scripts += 1
            assert "src" not in a, "No external scripts"
        if tag == "style":
            self.styles += 1


def parsed():
    source = SITE.read_text(encoding="utf-8")
    p = Parser()
    p.feed(source)
    return source, p


def test_static_responsive_no_tracking_or_fake_live_compiler():
    source, p = parsed()
    assert p.lang == "en" and p.styles == 1 and p.scripts == 2  # one site script and one JSON-LD script
    assert 'name="viewport"' in source
    assert "@media(max-width:640px)" in source
    assert not re.search(r"<(?:img|iframe|embed|object)\b", source, re.I)
    assert "fetch(" not in source
    assert "not an interactive compiler" in source
    assert "navigator.clipboard.writeText" in source


def test_bilingual_switch_and_all_site_anchors():
    source, p = parsed()
    assert len(p.translations) > 35
    assert all(a.get("data-en") and a.get("data-tr") for a in p.translations)
    assert len(p.ids) == len(set(p.ids))
    for link in p.links:
        href = link.get("href", "")
        assert href
        if href.startswith("#"):
            assert href[1:] in p.ids
        if link.get("target") == "_blank":
            assert {"noopener", "noreferrer"} <= set(link.get("rel", "").split())
    assert any(x.get("id") == "lang-toggle" for x in p.buttons)
    assert "document.documentElement.lang=locale" in source


def test_current_checkout_and_pricing_only():
    source, p = parsed()
    assert sum(x.get("href") == POLAR for x in p.links) >= 2
    assert all(a.get("href") in (POLAR, "/security-guide.html") or a.get("href", "").startswith("#") for a in p.links)
    for expected in ("$49", "49 USD", "One-time purchase", "12 months", "Perpetual", "Python 3.12+", "Go 1.24+"):
        assert expected in source
    for false_claim in ("49 EUR", "49€", "EVM-compatible", "hack-proof", "100x safer", "bank certified"):
        assert false_claim not in source


def test_bundled_real_security_demo_and_examples():
    source, _ = parsed()
    for expected in (
        "KS2401", "./install.sh", "ks run examples/hello.ks",
        "ks check examples/supply_chain/main.ks",
        "ks caps --deny net examples/apps/secretscan/main.ks",
        "Go-based adapter", "pre-1.0",
    ):
        assert expected in source


def test_public_technical_guide_and_search_discovery():
    root = SITE.parent
    index, parser = parsed()
    guide = (root / "security-guide.html").read_text(encoding="utf-8")
    robots = (root / "robots.txt").read_text(encoding="utf-8")
    sitemap = (root / "sitemap.xml").read_text(encoding="utf-8")
    nginx = (root / "nginx.conf").read_text(encoding="utf-8")
    docker = (root / "Dockerfile").read_text(encoding="utf-8")
    hostname = "https://koschei-lang-web-production.up.railway.app"
    assert f'<link rel="canonical" href="{hostname}/">' in index
    assert any(x.get("href") == "/security-guide.html" for x in parser.links)
    assert f'{hostname}/security-guide.html' in guide
    assert 'KS2401' in guide and 'pre-1.0' in guide
    assert 'not a browser-based live compiler' in guide
    assert 'Go-based adapter' in guide
    assert 'https://buy.polar.sh/' in guide
    assert 'EVM-compatible' not in guide and 'hack-proof' not in guide
    assert f'{hostname}/sitemap.xml' in robots
    assert f'{hostname}/security-guide.html' in sitemap
    for path in ("security-guide.html", "robots.txt", "sitemap.xml"):
        assert f'location = /{path}' in nginx
        assert path in docker
    assert 'add_header Cache-Control' not in nginx, "would override server-level security headers"


def test_localized_technical_article_and_structured_product_metadata():
    root = SITE.parent
    index, parser = parsed()
    en = (root / "security-guide.html").read_text(encoding="utf-8")
    tr = (root / "security-guide.tr.html").read_text(encoding="utf-8")
    sitemap = (root / "sitemap.xml").read_text(encoding="utf-8")
    nginx = (root / "nginx.conf").read_text(encoding="utf-8")
    docker = (root / "Dockerfile").read_text(encoding="utf-8")
    assert '<html lang="tr">' in tr
    assert 'hreflang="en"' in tr and 'hreflang="tr"' in tr
    assert 'hreflang="en"' in en and 'hreflang="tr"' in en
    assert 'KS2401' in tr and '49 USD' in tr
    assert 'canlı bir tarayıcı derleyicisi değil' in tr
    assert 'Go tabanlı bir adaptör' in tr
    assert 'https://buy.polar.sh/' in tr
    assert '/security-guide.tr.html' in sitemap
    assert '/security-guide.tr.html' in nginx
    assert 'security-guide.tr.html' in docker
    assert 'id="security-guide-link"' in index
    assert 'locale==="tr"?"/security-guide.tr.html":"/security-guide.html"' in index
    assert index.count('type="application/ld+json"') == 1
    match = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', index, re.S)
    assert match is not None
    schema = json.loads(match.group(1))
    assert schema["@type"] == "SoftwareApplication"
    assert schema["name"] == "Koschei Lang"
    assert schema["softwareVersion"] == "0.10.0"
    assert schema["applicationCategory"] == "DeveloperApplication"
    assert schema["offers"]["price"] == "49.00"
    assert schema["offers"]["priceCurrency"] == "USD"
    assert schema["offers"]["url"] == POLAR
    assert schema.get("aggregateRating") is None
