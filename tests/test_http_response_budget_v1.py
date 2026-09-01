from io import BytesIO

import pytest

from koschei.http_response_budget_v1 import (
    HTTP_RESPONSE_BUDGET_ERROR_V1,
    HTTP_RESPONSE_MAX_BYTES_V1,
    HttpResponseBudgetV1Error,
    read_bounded_response_body_v1,
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


def test_response_budget_rejects_invalid_budget_values():
    with pytest.raises(ValueError):
        read_bounded_response_body_v1(BytesIO(b""), limit=-1)
    with pytest.raises(ValueError):
        read_bounded_response_body_v1(BytesIO(b""), limit=True)
