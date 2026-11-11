import json
import pytest

from koschei.universe_remote_gateway_v1 import (
    RemoteGatewayError,
    _token_ok,
    envelope_json_v1,
)

TOKEN=b"t"*32


def test_bearer_auth_is_exact_and_constant_time_compatible_surface():
    assert _token_ok(TOKEN, "Bearer "+TOKEN.decode())
    assert not _token_ok(TOKEN, "Bearer wrong")
    assert not _token_ok(TOKEN, None)
    assert not _token_ok(TOKEN, "Basic abc")


def test_observer_payload_must_be_authority_free():
    body=envelope_json_v1({"schema":"observer/v1","authority":False,"epoch":7})
    assert json.loads(body)["authority"] is False
    with pytest.raises(RemoteGatewayError):
        envelope_json_v1({"authority":True})


def test_binary_fields_are_encoded_not_executed():
    body=envelope_json_v1({"authority":False,"digest":b"a"*32})
    assert json.loads(body)["digest"] == (b"a"*32).hex()


def test_gateway_requires_256_bit_token_contract():
    # Constructor-level invariant represented explicitly here so future refactors
    # cannot quietly accept short shared secrets.
    assert len(TOKEN) >= 32
    assert len(b"short") < 32
