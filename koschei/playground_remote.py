"""Authenticated HTTPS transport to a separately confined Playground worker.

No redirects, environment proxy discovery, or local-execution fallback.
The endpoint is operator configuration, never part of submitted source.
"""

from __future__ import annotations

import http.client
import json
import os
import re
from urllib.parse import urlsplit

from .untrusted import MAX_OUTPUT_BYTES, MAX_SOURCE_BYTES, SandboxUnavailable

MAX_RESPONSE_BYTES = 128 * 1024
REQUEST_TIMEOUT_SECONDS = 25


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
    def __init__(self, endpoint: str, token: str):
        url = urlsplit(endpoint)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.password is not None or url.path not in ("", "/")
                or url.query or url.fragment):
            raise ValueError("KOSCHEI_WORKER_URL must be an HTTPS origin without credentials or a path")
        self.host, self.port = url.hostname, url.port or 443
        self.token = worker_token(token)

    @classmethod
    def from_environment(cls) -> RemoteEvaluator:
        return cls(os.environ.get("KOSCHEI_WORKER_URL", ""),
                   os.environ.get("KOSCHEI_WORKER_TOKEN", ""))

    def _request(self, path: str, payload: dict | None = None) -> dict:
        connection = None
        try:
            connection = http.client.HTTPSConnection(self.host, self.port, timeout=REQUEST_TIMEOUT_SECONDS)
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
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Invalid worker response")
            return result
        except (OSError, http.client.HTTPException, ValueError, UnicodeError, RecursionError):
            # Do not expose worker URLs, credentials or internal errors to callers.
            raise SandboxUnavailable("Remote evaluation service unavailable") from None
        finally:
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
