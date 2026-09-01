from koschei.codegen_go import generate_go
from koschei.http_response_budget_v1 import (
    HTTP_RESPONSE_BUDGET_ERROR_V1,
    HTTP_RESPONSE_MAX_BYTES_V1,
)
from koschei.parser import parse


def test_native_runtime_embeds_canonical_response_budget():
    generated = generate_go(parse('fn main() { println("ready") }'))

    assert (
        f"const ksHTTPResponseMaxBytes int64 = {HTTP_RESPONSE_MAX_BYTES_V1}"
        in generated
    )
    assert "io.LimitReader(response.Body, ksHTTPResponseMaxBytes+1)" in generated
    assert HTTP_RESPONSE_BUDGET_ERROR_V1 in generated
    assert "__KOSCHEI_HTTP_RESPONSE_MAX_BYTES_V1__" not in generated
    assert "__KOSCHEI_HTTP_RESPONSE_BUDGET_ERROR_V1__" not in generated


def test_native_runtime_rejects_over_budget_instead_of_silent_truncation():
    generated = generate_go(parse('fn main() { println("ready") }'))

    assert "if int64(len(body)) > ksHTTPResponseMaxBytes" in generated
    assert "return ksErrorf(\"KSNET_RESPONSE_BUDGET:" in generated
