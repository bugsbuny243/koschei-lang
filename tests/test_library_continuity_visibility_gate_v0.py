import hashlib
import pytest

from koschei.library_adversary_learning_resistance_v0 import VisibilityPosture
from koschei.library_adaptive_visibility_v0 import AdaptiveVisibilityEnvelopeV0
from koschei.library_cross_session_continuity_v0 import CrossSessionDecisionV0
from koschei.library_continuity_visibility_gate_v0 import (
    ContinuityVisibilityGateError,
    bind_visibility_to_cross_session_v0,
)


def d(x:bytes)->bytes:
    return hashlib.sha3_256(x).digest()


def continuity(posture=VisibilityPosture.NORMAL,allowed=True,sessions=None):
    sessions=(d(b"s1"),) if sessions is None else sessions
    return CrossSessionDecisionV0(
        7,d(b"token"),sessions,10,2,1,len(sessions),posture,allowed,d(b"cross"),False
    )


def envelope(session=None,allowed=True,roots=8,relations=12,detail=3):
    session=d(b"s1") if session is None else session
    return AdaptiveVisibilityEnvelopeV0(
        "obs",session,d(b"learning"),9,roots,relations,detail,False,d(b"seed"),d(b"env"),allowed,False
    )


def test_normal_preserves_session_envelope():
    g=bind_visibility_to_cross_session_v0(continuity=continuity(),envelope=envelope())
    assert g.allowed
    assert g.root_budget==8
    assert g.relation_budget==12
    assert g.diagnostic_detail_ceiling==3


def test_minimal_cross_session_tightens_surface():
    g=bind_visibility_to_cross_session_v0(
        continuity=continuity(VisibilityPosture.MINIMAL,True),
        envelope=envelope(roots=8,relations=12,detail=3),
    )
    assert g.allowed
    assert g.root_budget==1
    assert g.relation_budget==1
    assert g.diagnostic_detail_ceiling==1


def test_contained_cross_session_forces_zero_surface():
    g=bind_visibility_to_cross_session_v0(
        continuity=continuity(VisibilityPosture.CONTAINED,False),
        envelope=envelope(),
    )
    assert not g.allowed
    assert (g.root_budget,g.relation_budget,g.diagnostic_detail_ceiling)==(0,0,0)


def test_disallowed_session_cannot_be_reopened_by_normal_continuity():
    g=bind_visibility_to_cross_session_v0(
        continuity=continuity(VisibilityPosture.NORMAL,True),
        envelope=envelope(allowed=False,roots=0,relations=0,detail=0),
    )
    assert not g.allowed
    assert g.effective_posture is VisibilityPosture.CONTAINED


def test_uncovered_session_rejected():
    with pytest.raises(ContinuityVisibilityGateError):
        bind_visibility_to_cross_session_v0(
            continuity=continuity(),
            envelope=envelope(session=d(b"other")),
        )


def test_digest_deterministic():
    a=bind_visibility_to_cross_session_v0(continuity=continuity(),envelope=envelope())
    b=bind_visibility_to_cross_session_v0(continuity=continuity(),envelope=envelope())
    assert a==b
