from koschei.hela_authority_death_v1 import bury_authority_v1, resurrection_attempt_v1
from koschei.captain_marvel_blast_radius_v1 import issue_blast_radius_budget_v1, evaluate_propagation_v1

P=b"p"*32; R=b"r"*32; C=b"c"*32

def test_hela_blocks_same_principal_authority_after_death_epoch():
    t=bury_authority_v1(principal_digest=P,authority_id="network:egress",death_epoch=8,reality_digest=R,cause_digest=C)
    assert resurrection_attempt_v1(t,principal_digest=P,authority_id="network:egress",candidate_epoch=8)
    assert resurrection_attempt_v1(t,principal_digest=P,authority_id="network:egress",candidate_epoch=99)
    assert not resurrection_attempt_v1(t,principal_digest=P,authority_id="process:spawn",candidate_epoch=99)

def test_blast_radius_blocks_unknown_destination():
    b=issue_blast_radius_budget_v1(origin_reality="A",allowed_destinations=frozenset({"B"}),max_hops=2,max_effects=2)
    v=evaluate_propagation_v1(b,destination="C",hops_used=0,effects_used=0)
    assert not v.allowed and v.reason=="destination-outside-blast-radius"

def test_blast_radius_consumes_budget_without_granting_authority():
    b=issue_blast_radius_budget_v1(origin_reality="A",allowed_destinations=frozenset({"B"}),max_hops=2,max_effects=2)
    v=evaluate_propagation_v1(b,destination="B",hops_used=0,effects_used=0)
    assert v.allowed and v.remaining_hops==1 and v.remaining_effects==1
    assert v.authority is False

def test_exhausted_budget_fails_closed():
    b=issue_blast_radius_budget_v1(origin_reality="A",allowed_destinations=frozenset({"B"}),max_hops=1,max_effects=1)
    assert not evaluate_propagation_v1(b,destination="B",hops_used=1,effects_used=0).allowed
    assert not evaluate_propagation_v1(b,destination="B",hops_used=0,effects_used=1).allowed
