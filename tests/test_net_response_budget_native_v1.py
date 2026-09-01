from koschei.http_response_budget_v1 import (
    HTTP_RESPONSE_BUDGET_ERROR_V1,
    HTTP_RESPONSE_MAX_BYTES_V1,
)
from koschei.native_http_transport_v1 import (
    native_http_transport_guard_fragment_go_v1,
)


def test_native_transport_embeds_canonical_response_budget():
    guard = native_http_transport_guard_fragment_go_v1()

    assert (
        f"const ksHTTPResponseMaxBytesGuardV1 int64 = {HTTP_RESPONSE_MAX_BYTES_V1}"
        in guard
    )
    assert HTTP_RESPONSE_BUDGET_ERROR_V1 in guard
    assert "ksBoundedResponseBodyV1" in guard
    assert "ksHTTPResponseMaxBytesGuardV1 + 1 - body.read" in guard
    assert "body.read > ksHTTPResponseMaxBytesGuardV1" in guard
    assert "response.ContentLength > ksHTTPResponseMaxBytesGuardV1" in guard
    assert "response.Body = &ksBoundedResponseBodyV1{body: response.Body}" in guard
    assert "__KOSCHEI_HTTP_RESPONSE_MAX_BYTES_V1__" not in guard
    assert "__KOSCHEI_HTTP_RESPONSE_BUDGET_ERROR_V1__" not in guard


def test_native_transport_rejects_over_budget_instead_of_truncating():
    guard = native_http_transport_guard_fragment_go_v1()

    assert "return count, fmt.Errorf(\"KSNET_RESPONSE_BUDGET:" in guard
    assert "return nil, fmt.Errorf(\"KSNET_RESPONSE_BUDGET:" in guard
