from __future__ import annotations

from io import BytesIO

from koschei.http_response_budget_v1 import (
    HTTP_CONTENT_ENCODING_ERROR_V1,
    HTTP_RESPONSE_BUDGET_ERROR_V1,
    HTTP_RESPONSE_MAX_BYTES_V1,
)
from koschei.interpreter import KsError, NetCaps, Response


class _Headers:
    def __init__(self, content_encoding: str | None = None) -> None:
        self.content_encoding = content_encoding

    @staticmethod
    def get_content_charset():
        return "utf-8"

    def get(self, name: str):
        if name.lower() == "content-encoding":
            return self.content_encoding
        return None


class _Response(BytesIO):
    status = 200

    def __init__(self, payload: bytes, content_encoding: str | None = None) -> None:
        super().__init__(payload)
        self.headers = _Headers(content_encoding)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class _Opener:
    def __init__(self, payload: bytes, content_encoding: str | None = None) -> None:
        self.payload = payload
        self.content_encoding = content_encoding
        self.timeout = None
        self.request = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return _Response(self.payload, self.content_encoding)


def _caps(payload: bytes, content_encoding: str | None = None) -> NetCaps:
    caps = NetCaps("https://example.com")
    caps._opener = _Opener(payload, content_encoding)
    return caps


def test_interpreter_net_get_accepts_exact_response_budget():
    payload = b"x" * HTTP_RESPONSE_MAX_BYTES_V1
    result = _caps(payload).get("https://example.com/data")
    assert isinstance(result, Response)
    assert result.status_code == 200
    assert result.body == "x" * HTTP_RESPONSE_MAX_BYTES_V1


def test_interpreter_net_get_rejects_one_byte_over_budget():
    payload = b"x" * (HTTP_RESPONSE_MAX_BYTES_V1 + 1)
    result = _caps(payload).get("https://example.com/data")
    assert isinstance(result, KsError)
    assert HTTP_RESPONSE_BUDGET_ERROR_V1 in result.message


def test_interpreter_net_get_accepts_explicit_identity_content_encoding():
    result = _caps(b"ok", "identity").get("https://example.com/data")
    assert isinstance(result, Response)
    assert result.body == "ok"


def test_interpreter_net_get_rejects_non_identity_content_encoding():
    result = _caps(b"compressed", "gzip").get("https://example.com/data")
    assert isinstance(result, KsError)
    assert HTTP_CONTENT_ENCODING_ERROR_V1 in result.message


def test_interpreter_net_get_keeps_existing_origin_scope_guard():
    result = _caps(b"ok").get("https://evil.example/data")
    assert isinstance(result, KsError)
    assert result.message.startswith("KS3402:")
