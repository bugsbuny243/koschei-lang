import pytest

from koschei.planetary_console_v1 import PLANETS, HTML, universe_payload_v1, serve_planetary_console_v1


def test_universe_exposes_exact_six_convergence_domains():
    payload = universe_payload_v1()
    assert payload["schema"] == "koschei.planetary-console.v1"
    assert len(payload["planets"]) == 6
    assert {p["domain"] for p in payload["planets"]} == {
        "identity/provenance", "authority", "integrity", "behavior", "evidence/prediction", "recovery/time"
    }


def test_sentinel_is_explicitly_non_authoritative():
    payload = universe_payload_v1()
    assert payload["sentinel"]["authority"] is False


def test_frontend_contains_no_external_script_dependency():
    lower = HTML.lower()
    assert "three.js" not in lower
    assert "cdn." not in lower
    assert "http://" not in lower
    assert "https://" not in lower


def test_planets_have_unique_ids_orbits_and_names():
    assert len({p.id for p in PLANETS}) == 6
    assert len({p.name for p in PLANETS}) == 6
    assert len({p.orbit for p in PLANETS}) == 6


def test_console_rejects_non_loopback_host_before_server_start():
    with pytest.raises(ValueError):
        serve_planetary_console_v1("0.0.0.0", 8787)


def test_console_rejects_invalid_port_before_server_start():
    with pytest.raises(ValueError):
        serve_planetary_console_v1("127.0.0.1", 0)
