from io import BytesIO

import pytest

from koschei.http_response_budget_v1 import (
    HTTP_CONTENT_ENCODING_ERROR_V1,
    HTTP_RESPONSE_BUDGET_ERROR_V1,
    HTTP_RESPONSE_MAX_BYTES_V1,
    HttpContentEncodingV1Error,
    HttpResponseBudgetV1Error,
    read_bounded_response_body_v1,
    validate_http_content_encoding_v1,
)


def test_response_budget_accepts_exact_limit():
    payload = b"x" * HTTP_RESPONSE_MAX_BYTES_V1
    assert read_bounded_response_body_v1(BytesIO(payload)) == payload


def test_response_budget_rejects_one_byte_over_limit_without_truncation():
    payload = b"x" * (HTTP_RESPONSE_MAX_BYTES_V1 + 1)
    with pytest.raises(HttpResponseBudgetV1Error) as caught:
        read_bounded_response_body_v1(BytesIO(payload))
    assert caught.value.code == HTTP_RESPONSE_BUDGET_ERROR_V1


def test_response_budget_does_not_overread_more_than_limit_sentinel():
    class RecordingStream:
        def __init__(self) -> None:
            self.requested = None

        def read(self, size: int) -> bytes:
            self.requested = size
            return b""

    stream = RecordingStream()
    read_bounded_response_body_v1(stream, limit=17)
    assert stream.requested == 18


def test_response_budget_rejects_over_limit_across_short_reads():
    class ShortReadStream:
        def __init__(self, payload: bytes, chunk_size: int = 3) -> None:
            self.payload = payload
            self.chunk_size = chunk_size
            self.offset = 0
            self.requests: list[int] = []

        def read(self, size: int) -> bytes:
            self.requests.append(size)
            if self.offset >= len(self.payload):
                return b""
            count = min(size, self.chunk_size, len(self.payload) - self.offset)
            chunk = self.payload[self.offset : self.offset + count]
            self.offset += count
            return chunk

    stream = ShortReadStream(b"x" * 18)
    with pytest.raises(HttpResponseBudgetV1Error) as caught:
        read_bounded_response_body_v1(stream, limit=17)

    assert caught.value.code == HTTP_RESPONSE_BUDGET_ERROR_V1
    assert len(stream.requests) > 1
    assert stream.requests[0] == 18


def test_response_budget_rejects_invalid_budget_values():
    with pytest.raises(ValueError):
        read_bounded_response_body_v1(BytesIO(b""), limit=-1)
    with pytest.raises(ValueError):
        read_bounded_response_body_v1(BytesIO(b""), limit=True)


@pytest.mark.parametrize("encoding", [None, "", "identity", "Identity", " IDENTITY "])
def test_content_encoding_v1_accepts_only_identity_representation(encoding):
    validate_http_content_encoding_v1(encoding)


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "gzip, br"])
def test_content_encoding_v1_rejects_non_identity_representation(encoding):
    with pytest.raises(HttpContentEncodingV1Error) as caught:
        validate_http_content_encoding_v1(encoding)
    assert caught.value.code == HTTP_CONTENT_ENCODING_ERROR_V1
