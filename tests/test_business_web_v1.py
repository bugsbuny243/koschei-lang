"""Koschei Business Web acceptance tests: real .ks execution, HTTP and fail-closed Playground."""
from __future__ import annotations

import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "commercial" / "lang-site" / "business-tools.html"
ENGINE = ROOT / "products" / "business_web" / "engine.ks"
SERVER = ROOT / "server" / "playground" / "app.py"
spec = importlib.util.spec_from_file_location("business_web_app_under_test", SERVER)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def test_browser_app_is_not_a_mockup():
    html = SITE.read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    for item in ("quote-panel", "stock-panel", "cash-panel", "quote-rows", "stock-rows", "cash-rows"):
        assert f'id="{item}"' in html
    assert 'fetch("/api/business/calculate"' in html
    assert 'Tarayıcıdan' in html or 'tarayıcıdan' in html
    assert "window.print()" in html
    assert "localStorage" not in html
    assert "eval(" not in html
    assert "Koschei hesaplama motoru" in html
    assert "<iframe" not in html and "<script src=" not in html


def test_engine_source_is_fixed_and_explicitly_input_only():
    text = ENGINE.read_text(encoding="utf-8")
    assert "caps.input.allow(8192)" in text
    for banned in ("caps.net.", "caps.disk.", "caps.db.", "caps.env.", "caps.process.", "caps.serve."):
        assert banned not in text
    assert "fn quote(" in text and "fn stock(" in text and "fn cash(" in text


@pytest.mark.parametrize(("payload", "expected"), [
    (
        {"kind":"quote","discount":10,"vat":20,"items":[
            {"quantity":1,"price":"100.00"},
            {"quantity":2,"price":"5.00"}]},
        {"subtotal":11000,"discount":1100,"vat":1980,"total":11880,"count":2},
    ),
    (
        {"kind":"stock","items":[
            {"quantity":1,"minimum":3,"cost":"1.00"},
            {"quantity":10,"minimum":3,"cost":"2.00"}]},
        {"count":2,"alerts":1,"inventory_value":2100,"items":[{"low":True,"reorder":5},{"low":False,"reorder":0}]},
    ),
    (
        {"kind":"cash","opening":"10.00","items":[
            {"type":"income","amount":"20.00"},
            {"type":"expense","amount":"5.00"}]},
        {"opening":1000,"income":2000,"expenses":500,"closing":2500,"income_count":1,"expense_count":1},
    ),
])
def test_actual_koschei_engine_math(payload, expected):
    kind, stdin, rows = app._business_request(payload)
    result = app._business_run(kind, stdin, rows)  # subprocess -> real Koschei runtime
    for key, value in expected.items():
        assert result[key] == value


@pytest.mark.parametrize("bad", [
    {"kind":"quote","discount":0,"vat":20,"items":[{"quantity":True,"price":"5.00"}]},
    {"kind":"quote","discount":101,"vat":20,"items":[{"quantity":1,"price":"5.00"}]},
    {"kind":"quote","discount":0,"vat":20,"items":[{"quantity":1,"price":"NaN"}]},
    {"kind":"cash","opening":"0.00","items":[{"type":"income","amount":"-9.00"}]},
    {"kind":"stock","items":[{"quantity":-1,"minimum":10,"cost":"1.00"}]},
    {"kind":"stock","items":[{"quantity":1,"minimum":0,"cost":"1.00"}]*41},
    {"kind":"arbitrary_code","source":"fn main() { println(\"pwn\") }"},
])
def test_validation_rejects_untrusted_or_out_of_bounds_data(bad):
    with pytest.raises(ValueError):
        app._business_request(bad)


@pytest.fixture
def http_server(monkeypatch):
    monkeypatch.setattr(app, "PLAYGROUND_MODE", "disabled")
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=4)


def test_http_page_csp_and_real_calculation(http_server):
    with urllib.request.urlopen(http_server + "/tools", timeout=8) as response:
        assert response.status == 200
        assert b"business" in response.read().lower()
        assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
    payload = {"kind":"cash","opening":"1.00","items":[{"type":"expense","amount":"2.00"}]}
    req = urllib.request.Request(
        http_server + "/api/business/calculate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read())
        assert response.status == 200
        assert data["closing"] == -100


def test_public_code_evaluation_remains_disabled(http_server):
    req = urllib.request.Request(
        http_server + "/api/evaluate",
        data=b'{"source":"fn main() { println(1) }","action":"run"}',
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=8)
    assert err.value.code == 503
    assert json.loads(err.value.read())["error"] == "evaluation_disabled"


def test_business_api_rejects_fake_source_and_cross_origin(http_server):
    req = urllib.request.Request(
        http_server + "/api/business/calculate",
        data=b'{"source":"fn main() {}","kind":"run"}',
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=8)
    assert err.value.code == 400
    req = urllib.request.Request(
        http_server + "/api/business/calculate",
        data=b'{"kind":"cash"}',
        headers={"Content-Type":"application/json","Origin":"https://not-koschei.example"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=8)
    assert err.value.code == 403


def test_touch_browser_uses_stack_and_reveals_result():
    html = SITE.read_text(encoding="utf-8")
    # Some Android embedded browsers present a desktop-width viewport despite touch input.
    assert "@media (max-width:1200px), (hover:none) and (pointer:coarse)" in html
    assert ".workarea{grid-template-columns:minmax(0,1fr);gap:18px}" in html
    assert ".receipt{position:static;min-height:320px}" in html
    assert "scrollIntoView({" in html
    assert "prefers-reduced-motion:reduce" in html
