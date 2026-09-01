"""Audited Go transport companion for Koschei Library HTTP v1.

`ks build` compiles a temporary Go package rather than a single mandatory file,
while `ks emit-go` exposes one buildable Go source file. This module therefore
owns the native HTTP representation and body-budget policy and renders it either
as a package companion or as an import-free fragment for generated source that
already imports fmt/io/http/strings.
"""
from __future__ import annotations

from .http_response_budget_v1 import (
    HTTP_CONTENT_ENCODING_ERROR_V1,
    HTTP_RESPONSE_BUDGET_ERROR_V1,
    HTTP_RESPONSE_MAX_BYTES_V1,
)


_NATIVE_HTTP_TRANSPORT_FRAGMENT_TEMPLATE_V1 = r'''
const ksHTTPResponseMaxBytesGuardV1 int64 = __KOSCHEI_HTTP_RESPONSE_MAX_BYTES_V1__

type ksBoundedResponseBodyV1 struct {
    body io.ReadCloser
    read int64
}

func (body *ksBoundedResponseBodyV1) Read(buffer []byte) (int, error) {
    remaining := ksHTTPResponseMaxBytesGuardV1 + 1 - body.read
    if remaining <= 0 {
        return 0, fmt.Errorf("__KOSCHEI_HTTP_RESPONSE_BUDGET_ERROR_V1__: HTTP response body exceeds %d byte budget", ksHTTPResponseMaxBytesGuardV1)
    }
    if int64(len(buffer)) > remaining {
        buffer = buffer[:int(remaining)]
    }

    count, err := body.body.Read(buffer)
    body.read += int64(count)
    if body.read > ksHTTPResponseMaxBytesGuardV1 {
        return count, fmt.Errorf("__KOSCHEI_HTTP_RESPONSE_BUDGET_ERROR_V1__: HTTP response body exceeds %d byte budget", ksHTTPResponseMaxBytesGuardV1)
    }
    return count, err
}

func (body *ksBoundedResponseBodyV1) Close() error {
    return body.body.Close()
}

type ksIdentityTransportV1 struct {
    base http.RoundTripper
}

func (transport ksIdentityTransportV1) RoundTrip(request *http.Request) (*http.Response, error) {
    clone := request.Clone(request.Context())
    clone.Header = request.Header.Clone()
    if clone.Header == nil {
        clone.Header = make(http.Header)
    }
    clone.Header.Set("Accept-Encoding", "identity")

    response, err := transport.base.RoundTrip(clone)
    if err != nil {
        return nil, err
    }

    encoding := strings.TrimSpace(strings.ToLower(response.Header.Get("Content-Encoding")))
    if encoding != "" && encoding != "identity" {
        response.Body.Close()
        return nil, fmt.Errorf("__KOSCHEI_HTTP_CONTENT_ENCODING_ERROR_V1__: unsupported HTTP content encoding: %s", encoding)
    }
    if response.Uncompressed {
        response.Body.Close()
        return nil, fmt.Errorf("__KOSCHEI_HTTP_CONTENT_ENCODING_ERROR_V1__: transparent HTTP decompression is forbidden")
    }
    if response.ContentLength > ksHTTPResponseMaxBytesGuardV1 {
        response.Body.Close()
        return nil, fmt.Errorf("__KOSCHEI_HTTP_RESPONSE_BUDGET_ERROR_V1__: HTTP response body exceeds %d byte budget", ksHTTPResponseMaxBytesGuardV1)
    }
    response.Body = &ksBoundedResponseBodyV1{body: response.Body}
    return response, nil
}

func init() {
    base, ok := http.DefaultTransport.(*http.Transport)
    if !ok {
        panic("__KOSCHEI_HTTP_CONTENT_ENCODING_ERROR_V1__: canonical default HTTP transport is unavailable")
    }
    bounded := base.Clone()
    bounded.DisableCompression = true
    http.DefaultTransport = ksIdentityTransportV1{base: bounded}
}
'''

_NATIVE_HTTP_TRANSPORT_FILE_HEADER_V1 = r'''package main

import (
    "fmt"
    "io"
    "net/http"
    "strings"
)
'''


def native_http_transport_guard_fragment_go_v1() -> str:
    """Return the import-free native HTTP guard fragment for generated Go."""

    return (
        _NATIVE_HTTP_TRANSPORT_FRAGMENT_TEMPLATE_V1.replace(
            "__KOSCHEI_HTTP_CONTENT_ENCODING_ERROR_V1__",
            HTTP_CONTENT_ENCODING_ERROR_V1,
        )
        .replace(
            "__KOSCHEI_HTTP_RESPONSE_BUDGET_ERROR_V1__",
            HTTP_RESPONSE_BUDGET_ERROR_V1,
        )
        .replace(
            "__KOSCHEI_HTTP_RESPONSE_MAX_BYTES_V1__",
            str(HTTP_RESPONSE_MAX_BYTES_V1),
        )
    )


def native_http_transport_guard_go_v1() -> str:
    """Return a standalone Go companion file for package-based native builds."""

    return (
        _NATIVE_HTTP_TRANSPORT_FILE_HEADER_V1
        + native_http_transport_guard_fragment_go_v1()
    )
