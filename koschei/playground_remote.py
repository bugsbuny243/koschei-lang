"""Authenticated HTTPS transport to a separately confined Playground worker.

No redirects, environment proxy discovery, or local-execution fallback.
The endpoint is operator configuration, never part of submitted source.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from urllib.parse import urlsplit

from .untrusted import MAX_OUTPUT_BYTES, MAX_SOURCE_BYTES, SandboxUnavailable

MAX_RESPONSE_BYTES = 128 * 1024
# One deadline for the whole exchange: DNS, TCP and TLS setup, sending, and
# reading the full response. A per-socket timeout alone resets on every byte,
# so a worker that drips data could hold a frontend thread indefinitely.
REQUEST_DEADLINE_SECONDS = 25
REQUEST_TIMEOUT_SECONDS = REQUEST_DEADLINE_SECONDS  # per-socket-operation ceiling
# getaddrinfo() cannot be interrupted, so connection setup runs on a small,
# bounded pool. A stuck resolver occupies a slot until it returns; once every
# slot is stuck, new requests wait at most their deadline and then fail closed.
_CONNECT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="koschei-worker-connect")


def worker_token(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("KOSCHEI_WORKER_TOKEN must contain 64 hexadecimal characters")
    return value


def _process_result(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("Invalid process result")
    code = value.get("exit_code")
    if code is not None and type(code) is not int:
        raise ValueError("Invalid exit code")
    if type(value.get("timed_out")) is not bool:
        raise ValueError("Invalid timeout flag")
    if value["timed_out"] != (code is None):
        raise ValueError("Inconsistent exit/timeout state")
    for key in ("stdout", "stderr"):
        if not isinstance(value.get(key), str) or len(value[key].encode("utf-8")) > MAX_OUTPUT_BYTES + 128:
            raise ValueError("Invalid process output")


def validate_result(result: object, action: str) -> dict:
    if not isinstance(result, dict) or result.get("action") != action:
        raise ValueError("Invalid evaluation result")
    if result.get("stage") not in ("policy", "check", "run") or type(result.get("ran")) is not bool:
        raise ValueError("Invalid evaluation state")
    _process_result(result.get("policy"))
    if result["ran"]:
        if action != "run" or result["stage"] != "run" or result["policy"]["exit_code"] != 0:
            raise ValueError("Invalid execution state")
        _process_result(result.get("run"))
    elif result["stage"] == "run" or "run" in result:
        raise ValueError("Unexpected execution result")
    manifest = result.get("manifest")
    if manifest is not None:
        if not isinstance(manifest, dict):
            raise ValueError("Invalid manifest")
        grants = manifest.get("grants", [])
        domains = manifest.get("required_domains", [])
        if not isinstance(grants, list) or not all(
            isinstance(g, dict) and isinstance(g.get("domain"), str) for g in grants
        ) or not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
            raise ValueError("Invalid manifest domains")
    return result


class RemoteEvaluator:
    def __init__(self, endpoint: str, token: str, ca_file: str = "", ca_pem: str = ""):
        url = urlsplit(endpoint)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.password is not None or url.path not in ("", "/")
                or url.query or url.fragment):
            raise ValueError("KOSCHEI_WORKER_URL must be an HTTPS origin without credentials or a path")
        self.host, self.port = url.hostname, url.port or 443
        self.token = worker_token(token)
        # A private worker usually has a certificate from a private CA. When a
        # CA file is given it is the *only* trust anchor (public CAs are not
        # consulted); hostname verification stays on either way.
        if ca_file and ca_pem:
            raise ValueError("Set KOSCHEI_WORKER_CA_FILE or KOSCHEI_WORKER_CA_PEM, not both")
        if ca_file:
            self.context = ssl.create_default_context(cafile=ca_file)
        elif ca_pem:
            # Platforms that only offer variables (Railway) pass the CA itself.
            if "-----BEGIN CERTIFICATE-----" not in ca_pem:
                raise ValueError("KOSCHEI_WORKER_CA_PEM must contain a PEM certificate")
            self.context = ssl.create_default_context(cadata=ca_pem)
        else:
            self.context = ssl.create_default_context()
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.check_hostname = True
        self.context.verify_mode = ssl.CERT_REQUIRED
        # Python 3.13 turns strict X.509 checks on by default; do it on every
        # version so a non-conforming worker certificate fails in tests and
        # not later, after a runtime upgrade of the frontend.
        self.context.verify_flags |= ssl.VERIFY_X509_STRICT

    @classmethod
    def from_environment(cls) -> RemoteEvaluator:
        return cls(os.environ.get("KOSCHEI_WORKER_URL", ""),
                   os.environ.get("KOSCHEI_WORKER_TOKEN", ""),
                   os.environ.get("KOSCHEI_WORKER_CA_FILE", ""),
                   os.environ.get("KOSCHEI_WORKER_CA_PEM", ""))

    def _request(self, path: str, payload: dict | None = None) -> dict:
        deadline = time.monotonic() + REQUEST_DEADLINE_SECONDS
        connection = None
        watchdog = None
        try:
            connection = http.client.HTTPSConnection(
                self.host, self.port, timeout=REQUEST_TIMEOUT_SECONDS, context=self.context)
            # DNS, TCP and the TLS handshake (with certificate and hostname
            # checks) happen in connect(); bound them by the deadline.
            future = _CONNECT_POOL.submit(connection.connect)
            try:
                future.result(timeout=max(0.0, deadline - time.monotonic()))
            except FutureTimeout:
                future.cancel()
                raise TimeoutError("worker connection deadline") from None

            def expire() -> None:
                # Unblock any pending send/recv once the deadline passes.
                sock = getattr(connection, "sock", None)
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

            watchdog = threading.Timer(max(0.0, deadline - time.monotonic()), expire)
            watchdog.daemon = True
            watchdog.start()
            body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            connection.request("GET" if body is None else "POST", path, body=body, headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            })
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("Worker did not accept the request")
            if response.getheader("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                raise ValueError("Invalid worker content type")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Worker response exceeded limit")
            if time.monotonic() > deadline:
                raise TimeoutError("worker deadline")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Invalid worker response")
            return result
        except (OSError, http.client.HTTPException, ValueError, UnicodeError, RecursionError):
            # Do not expose worker URLs, credentials or internal errors to callers.
            raise SandboxUnavailable("Remote evaluation service unavailable") from None
        finally:
            if watchdog is not None:
                watchdog.cancel()
            if connection is not None:
                connection.close()

    def require_ready(self) -> None:
        result = self._request("/health")
        if (result.get("ok") is not True or result.get("evaluation_enabled") is not True
                or type(result.get("protocol")) is not int or result["protocol"] != 1):
            raise SandboxUnavailable("Remote evaluation service unavailable")

    def evaluate(self, source: str, action: str, lang: str) -> dict:
        if action not in ("check", "run") or not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise ValueError("Invalid evaluation request")
        result = self._request("/api/evaluate", {"source": source, "action": action, "lang": lang})
        try:
            return validate_result(result, action)
        except (ValueError, TypeError, KeyError):
            raise SandboxUnavailable("Remote evaluation service unavailable") from None
