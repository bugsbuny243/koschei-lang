from __future__ import annotations

import json

from benchmarks.security_v1 import CASES, SCHEMA, build_report, render_text


def test_benchmark_report_is_versioned_and_native_only():
    report = build_report()
    assert report["schema"] == SCHEMA
    assert report["language"] == "koschei"
    assert report["measurement_mode"] == "native"
    assert report["claim_policy"]["cross_language_claims_enabled"] is False


def test_every_case_is_digest_bound_and_matches_expected_domains():
    report = build_report()
    assert len(report["cases"]) == len(CASES)
    for case in report["cases"]:
        assert case["source_sha256"].startswith("sha256:")
        assert len(case["source_sha256"]) == 71
        assert case["observed_domains"] == case["expected_domains"]


def test_pure_case_has_zero_ambient_authority_grants():
    report = build_report()
    pure = next(case for case in report["cases"] if case["name"] == "pure")
    assert pure["grant_count"] == 0
    assert pure["observed_domains"] == []


def test_dynamic_scope_case_is_reported_inexact():
    report = build_report()
    dynamic = next(case for case in report["cases"] if case["name"] == "dynamic_disk_scope")
    assert dynamic["observed_domains"] == ["disk"]
    assert dynamic["exact"] is False


def test_report_is_deterministic_json():
    first = json.dumps(build_report(), sort_keys=True, separators=(",", ":"))
    second = json.dumps(build_report(), sort_keys=True, separators=(",", ":"))
    assert first == second


def test_text_output_does_not_make_cross_language_safety_claim():
    text = render_text(build_report())
    assert "cross-language claims: disabled" in text
    assert "100x" not in text.lower()
