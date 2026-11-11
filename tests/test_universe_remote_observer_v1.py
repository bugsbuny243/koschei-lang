from dataclasses import replace
import pytest
from koschei.universe_remote_observer_v1 import (
    RemoteObserverError, issue_remote_observer_v1, verify_remote_observer_v1,
)

KEY=b"k"*32
PAYLOAD={
    "schema":"koschei.universe-web/v1",
    "project":"ab"*32,
    "epoch":4,
    "authority":False,
    "nodes":[{"id":"root","kind":"project","digest":"cd"*32,"events":[]}],
    "edges":[],
}

def test_short_lived_snapshot_verifies_only_inside_window():
    e=issue_remote_observer_v1(payload=PAYLOAD,signing_key=KEY,issued_at_unix=100,ttl_seconds=30)
    assert verify_remote_observer_v1(e,signing_key=KEY,now_unix=100)
    assert verify_remote_observer_v1(e,signing_key=KEY,now_unix=130)
    assert not verify_remote_observer_v1(e,signing_key=KEY,now_unix=131)

def test_payload_tamper_breaks_signature():
    e=issue_remote_observer_v1(payload=PAYLOAD,signing_key=KEY,issued_at_unix=100)
    bad=replace(e,payload={**PAYLOAD,"epoch":5})
    assert not verify_remote_observer_v1(bad,signing_key=KEY,now_unix=120)

def test_authority_payload_is_rejected():
    with pytest.raises(RemoteObserverError):
        issue_remote_observer_v1(payload={**PAYLOAD,"authority":True},signing_key=KEY,issued_at_unix=100)

def test_sensitive_fields_are_rejected_recursively():
    with pytest.raises(RemoteObserverError):
        issue_remote_observer_v1(payload={**PAYLOAD,"nodes":[{"id":"x","secret":"nope"}]},signing_key=KEY,issued_at_unix=100)

def test_bad_key_and_long_lived_share_fail_closed():
    with pytest.raises(RemoteObserverError):
        issue_remote_observer_v1(payload=PAYLOAD,signing_key=b"x",issued_at_unix=100)
    with pytest.raises(RemoteObserverError):
        issue_remote_observer_v1(payload=PAYLOAD,signing_key=KEY,issued_at_unix=100,ttl_seconds=301)
