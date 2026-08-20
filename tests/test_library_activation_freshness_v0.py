import hashlib
import pytest

from koschei.library_activation_freshness_v0 import (
    ActivationFreshnessError,
    RevocationRecordV0,
    add_revocation_v0,
    advance_activation_epoch_v0,
    evaluate_fresh_activation_v0,
    make_activation_epoch_state_v0,
)
from koschei.library_graph_quorum_v0 import GraphActivationDecisionV0


def d(label: str) -> bytes:
    return hashlib.sha3_256(label.encode()).digest()


def decision(graph: bytes, *, active: bool = True) -> GraphActivationDecisionV0:
    return GraphActivationDecisionV0(graph, 1, ("ka",), d("decision"), active, False)


def test_fresh_activation_consumes_nonce_and_replay_fails():
    graph=d("graph")
    state=make_activation_epoch_state_v0(graph_digest=graph,current_epoch=7)
    receipt,next_state=evaluate_fresh_activation_v0(
        decision=decision(graph),state=state,nonce_digest=d("nonce-1"),subject_generations=(("ka",1),)
    )
    assert receipt.eligible is True
    assert next_state.last_activation_epoch==7
    with pytest.raises(ActivationFreshnessError,match="replay"):
        evaluate_fresh_activation_v0(
            decision=decision(graph),state=next_state,nonce_digest=d("nonce-1"),subject_generations=(("ka",1),)
        )


def test_epoch_is_strictly_monotonic():
    state=make_activation_epoch_state_v0(graph_digest=d("graph"),current_epoch=3)
    state2=advance_activation_epoch_v0(state,new_epoch=4)
    assert state2.current_epoch==4
    with pytest.raises(ActivationFreshnessError,match="monotonically"):
        advance_activation_epoch_v0(state2,new_epoch=4)


def test_revoked_generation_cannot_activate():
    graph=d("graph")
    state=make_activation_epoch_state_v0(graph_digest=graph,current_epoch=10)
    state=add_revocation_v0(state,RevocationRecordV0("ka",1,9,d("revoke-ka"),True))
    with pytest.raises(ActivationFreshnessError,match="revoked"):
        evaluate_fresh_activation_v0(
            decision=decision(graph),state=state,nonce_digest=d("nonce-2"),subject_generations=(("ka",1),)
        )


def test_future_revocation_does_not_apply_early():
    graph=d("graph")
    state=make_activation_epoch_state_v0(graph_digest=graph,current_epoch=10)
    state=add_revocation_v0(state,RevocationRecordV0("ka",1,11,d("future-revoke"),True))
    receipt,_=evaluate_fresh_activation_v0(
        decision=decision(graph),state=state,nonce_digest=d("nonce-3"),subject_generations=(("ka",1),)
    )
    assert receipt.eligible is True


def test_inactive_or_graph_mismatched_decision_fails_closed():
    graph=d("graph")
    state=make_activation_epoch_state_v0(graph_digest=graph,current_epoch=2)
    with pytest.raises(ActivationFreshnessError,match="inactive"):
        evaluate_fresh_activation_v0(
            decision=decision(graph,active=False),state=state,nonce_digest=d("n"),subject_generations=(("ka",1),)
        )
    with pytest.raises(ActivationFreshnessError,match="graph mismatch"):
        evaluate_fresh_activation_v0(
            decision=decision(d("other")),state=state,nonce_digest=d("n2"),subject_generations=(("ka",1),)
        )
