import pytest

from koschei.library_boundary_v1 import LibraryPrecursorFactV1
from koschei.library_behavior_baseline_v1 import LibraryBehaviorDeltaV1
from koschei.library_risk_evidence_v1 import (
    LibraryRiskEvidenceError,
    compose_library_risk_evidence_v1,
)

ART = b"a" * 32
BASE = b"b" * 32
OBS = b"o" * 32


def precursor(reason, digest=OBS):
    return LibraryPrecursorFactV1(ART, "network", reason, digest)


def delta(kind, digest=b"d" * 32):
    return LibraryBehaviorDeltaV1(kind, "network", OBS, BASE, digest)


def test_single_fact_is_evidence_but_not_compound():
    ev = compose_library_risk_evidence_v1(
        artifact_digest=ART, precursors=[precursor("authority-expansion")]
    )
    assert ev.compound is False
    assert ev.dimensions[0].dimension == "authority"
    assert len(ev.evidence_digest) == 32


def test_multiple_security_dimensions_form_compound_evidence():
    ev = compose_library_risk_evidence_v1(
        artifact_digest=ART,
        precursors=[
            precursor("authority-expansion", b"1" * 32),
            precursor("cpu-budget-exceeded", b"2" * 32),
            precursor("missing-exact-target", b"3" * 32),
        ],
    )
    assert ev.compound is True
    assert {x.dimension for x in ev.dimensions} == {"authority", "resource", "target"}


def test_behavior_delta_is_canonical_fact_not_model_score():
    ev = compose_library_risk_evidence_v1(
        artifact_digest=ART, deltas=[delta("new-effect")]
    )
    assert ev.dimensions[0].reason == "behavior-new-effect"
    assert ev.dimensions[0].dimension == "authority"
    assert not hasattr(ev, "score")
    assert not hasattr(ev, "probability")


def test_order_does_not_change_evidence_identity():
    rows = [
        precursor("authority-expansion", b"1" * 32),
        precursor("cpu-budget-exceeded", b"2" * 32),
        precursor("missing-exact-target", b"3" * 32),
    ]
    a = compose_library_risk_evidence_v1(artifact_digest=ART, precursors=rows)
    b = compose_library_risk_evidence_v1(artifact_digest=ART, precursors=reversed(rows))
    assert a.evidence_digest == b.evidence_digest


def test_duplicate_facts_do_not_inflate_evidence():
    p = precursor("authority-expansion")
    a = compose_library_risk_evidence_v1(artifact_digest=ART, precursors=[p])
    b = compose_library_risk_evidence_v1(artifact_digest=ART, precursors=[p, p, p])
    assert a.evidence_digest == b.evidence_digest
    assert len(b.dimensions) == 1


def test_cross_artifact_evidence_fails_closed():
    wrong = LibraryPrecursorFactV1(b"x" * 32, "network", "authority-expansion", OBS)
    with pytest.raises(LibraryRiskEvidenceError):
        compose_library_risk_evidence_v1(artifact_digest=ART, precursors=[wrong])


def test_empty_evidence_fails_closed():
    with pytest.raises(LibraryRiskEvidenceError):
        compose_library_risk_evidence_v1(artifact_digest=ART)
