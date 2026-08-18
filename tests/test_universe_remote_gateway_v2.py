from dataclasses import replace

import pytest

from koschei.universe_remote_gateway_v2 import (
    RemoteGatewayV2Error,
    verified_envelope_json_v2,
)
from koschei.universe_remote_observer_v1 import issue_remote_observer_v1

KEY=b"k"*32


def env():
    return issue_remote_observer_v1(
        payload={"authority":False,"project":"ab"*32,"epoch":4,"nodes":[],"edges":[]},
        signing_key=KEY, issued_at_unix=1000, ttl_seconds=60,
    )


def test_verified_envelope_is_serializable_and_authority_free():
    body=verified_envelope_json_v2(envelope=env(),signing_key=KEY,now_unix=1030)
    assert b'"authority":false' in body
    assert b'"payload"' in body


def test_expired_envelope_fails_closed():
    with pytest.raises(RemoteGatewayV2Error):
        verified_envelope_json_v2(envelope=env(),signing_key=KEY,now_unix=1061)


def test_tampered_payload_fails_closed():
    e=env()
    bad=replace(e,payload={"authority":False,"project":"ab"*32,"epoch":4,"nodes":[{"id":"forged"}],"edges":[]})
    with pytest.raises(RemoteGatewayV2Error):
        verified_envelope_json_v2(envelope=bad,signing_key=KEY,now_unix=1030)


def test_wrong_signing_key_fails_closed():
    with pytest.raises(RemoteGatewayV2Error):
        verified_envelope_json_v2(envelope=env(),signing_key=b"x"*32,now_unix=1030)
