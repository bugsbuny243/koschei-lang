import pytest

from koschei.library_boundary_v1 import LibraryPrecursorFactV1
from koschei.library_quarantine_contract_v1 import (
    LibraryQuarantineContractError,
    evaluate_library_quarantine_v1,
    issue_library_execution_lease_v1,
    issue_library_recovery_proof_v1,
    recovery_proof_allows_fresh_lease_v1,
)
from koschei.library_risk_evidence_v1 import compose_library_risk_evidence_v1

ART = b"a" * 32
REV = b"r" * 32


def evidence(reasons):
    rows = [LibraryPrecursorFactV1(ART, "network", reason, bytes([i + 1]) * 32)
            for i, reason in enumerate(reasons)]
    return compose_library_risk_evidence_v1(artifact_digest=ART, precursors=rows)


def lease(start=100, end=130, epoch=7, rev=REV):
    return issue_library_execution_lease_v1(
        artifact_digest=ART, revision_digest=rev, epoch=epoch,
        not_before=start, expires_at=end, host_nonce=b"n" * 32,
    )


def test_compound_evidence_quarantines_active_library_lease():
    ev = evidence(["authority-expansion", "cpu-budget-exceeded"])
    decision = evaluate_library_quarantine_v1(lease=lease(), evidence=ev, now=110)
    assert decision.quarantined is True
    assert decision.reason == "compound-risk-evidence"


def test_single_dimension_evidence_does_not_mint_or_remove_authority_by_itself():
    ev = evidence(["authority-expansion"])
    decision = evaluate_library_quarantine_v1(lease=lease(), evidence=ev, now=110)
    assert decision.quarantined is False
    assert decision.reason == "single-dimension-evidence"
    assert not hasattr(decision, "grant")
    assert not hasattr(decision, "execute")


def test_inactive_or_expired_lease_fails_safe():
    ev = evidence(["authority-expansion"])
    assert evaluate_library_quarantine_v1(lease=lease(), evidence=ev, now=99).quarantined
    assert evaluate_library_quarantine_v1(lease=lease(), evidence=ev, now=130).quarantined


def test_execution_lease_has_hard_120_second_maximum():
    with pytest.raises(LibraryQuarantineContractError):
        lease(start=0, end=121)


def test_cross_artifact_evidence_cannot_control_other_library():
    wrong = LibraryPrecursorFactV1(b"x" * 32, "network", "authority-expansion", b"1" * 32)
    wrong_ev = compose_library_risk_evidence_v1(artifact_digest=b"x" * 32, precursors=[wrong])
    with pytest.raises(LibraryQuarantineContractError):
        evaluate_library_quarantine_v1(lease=lease(), evidence=wrong_ev, now=110)


def test_recovery_requires_new_revision_and_strictly_new_epoch():
    q = evaluate_library_quarantine_v1(
        lease=lease(), evidence=evidence(["authority-expansion", "cpu-budget-exceeded"]), now=110
    )
    proof = issue_library_recovery_proof_v1(
        quarantined=q, repaired_revision_digest=b"z" * 32,
        new_epoch=8, verifier_digest=b"v" * 32,
    )
    assert recovery_proof_allows_fresh_lease_v1(proof, prior_lease=lease()) is True

    same_revision = issue_library_recovery_proof_v1(
        quarantined=q, repaired_revision_digest=REV,
        new_epoch=8, verifier_digest=b"v" * 32,
    )
    assert recovery_proof_allows_fresh_lease_v1(same_revision, prior_lease=lease()) is False

    stale_epoch = issue_library_recovery_proof_v1(
        quarantined=q, repaired_revision_digest=b"z" * 32,
        new_epoch=7, verifier_digest=b"v" * 32,
    )
    assert recovery_proof_allows_fresh_lease_v1(stale_epoch, prior_lease=lease()) is False


def test_recovery_cannot_be_issued_from_non_quarantine_decision():
    decision = evaluate_library_quarantine_v1(
        lease=lease(), evidence=evidence(["authority-expansion"]), now=110
    )
    with pytest.raises(LibraryQuarantineContractError):
        issue_library_recovery_proof_v1(
            quarantined=decision, repaired_revision_digest=b"z" * 32,
            new_epoch=8, verifier_digest=b"v" * 32,
        )
