"""Canonical network rules for ``NetCaps.get`` (readiness gate G2, third step).

``ks run`` and native binaries must give the same answer to the same request,
so nothing below is left to a host HTTP library's defaults:

* **URL grammar.** ``scheme://host[:port][path][?query][#fragment]``; the
  scheme is ``http`` or ``https`` (any case); the host is a name of ASCII
  letters, digits, ``.``, ``-`` and ``_`` (lowercased) or a bracketed IPv6
  literal; the port, when written, is 1–65535; user information (``@``) is
  refused; every character is printable ASCII and the path and query use only
  RFC 3986 characters with well-formed ``%`` escapes. The fragment is never
  sent. Anything else is outside every origin.
* **Request.** ``GET`` with exactly ``User-Agent: koschei/1``,
  ``Accept-Encoding: identity`` and ``Connection: close``; the default port is
  left out of the ``Host`` header.
* **Redirects.** 301, 302, 303, 307 and 308 with a ``Location`` are followed
  by Koschei, at most five times, and every target must stay in the origin
  (``KS3402``). Locations are resolved without dot-segment removal.
* **Status.** Every other status is a ``Response``: ``status()`` tells 200
  from 404; there is no host ``HTTP Error`` text.
* **Body.** Identity encoding only, at most 1 MiB
  (``http_response_budget_v1``), then strict UTF-8 whatever the declared
  charset.
* **Errors.** A failed request is ``API isteği başarısız: <CODE>: <url>`` with
  a code from :data:`FAILURE_CODES`.
* **Proxy.** Chosen by :func:`proxy_for` from the environment, the same way
  in both executors; loopback hosts are never proxied.
"""

from __future__ import annotations

import errno
import ipaddress
import os
import socket
import ssl
import http.client
from collections.abc import Mapping

USER_AGENT = "koschei/1"
TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 5
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

OUTSIDE_PREFIX = "KS3402: Ağ origin kapsamı dışında erişim reddedildi: "
REDIRECT_PREFIX = "KS3402: Ağ yönlendirmesi kapsam dışına çıktı: "
FAILED_PREFIX = "API isteği başarısız: "
TOO_MANY_REDIRECTS = "çok fazla yönlendirme"
NOT_TEXT_PREFIX = "API yanıtı geçerli UTF-8 metin değil: "
INVALID_TARGET = "<geçersiz adres>"

FAILURE_CODES = (
    "ECONNREFUSED",  # nothing listens on the port
    "ECONNRESET",  # the peer closed the connection before a full response
    "ETIMEDOUT",  # no progress for TIMEOUT_SECONDS
    "EHOSTUNREACH",
    "ENETUNREACH",
    "EDNS",  # the name does not resolve
    "ETLS",  # handshake or certificate verification failed
    "EPROTO",  # the peer did not speak HTTP/1.x
    "EIO",  # anything else, including a refusing proxy
)

_ERRNO_CODES = {
    errno.ECONNREFUSED: "ECONNREFUSED",
    errno.ECONNRESET: "ECONNRESET",
    errno.EPIPE: "ECONNRESET",
    errno.ETIMEDOUT: "ETIMEDOUT",
    errno.EHOSTUNREACH: "EHOSTUNREACH",
    errno.ENETUNREACH: "ENETUNREACH",
}
_HOST_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-_")
_IPV6_CHARS = frozenset("0123456789abcdef:.")
_TARGET_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "-._~:/?[]@!$&'()*+,;=%"
)
_HEX = frozenset("0123456789abcdefABCDEF")
_SCHEME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789+.-")


class Url:
    __slots__ = ("scheme", "host", "port", "target")

    def __init__(self, scheme: str, host: str, port: int, target: str) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.target = target

    @property
    def origin(self) -> tuple[str, str, int]:
        return self.scheme, self.host, self.port

    def authority(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        default = 443 if self.scheme == "https" else 80
        return host if self.port == default else f"{host}:{self.port}"

    def text(self) -> str:
        return f"{self.scheme}://{self.authority()}{self.target}"


def _printable(text: str) -> bool:
    return all("\x21" <= character <= "\x7e" for character in text)


def _valid_target(target: str) -> bool:
    if any(character not in _TARGET_CHARS for character in target):
        return False
    index = target.find("%")
    while index != -1:
        if index + 2 >= len(target) or target[index + 1] not in _HEX or target[index + 2] not in _HEX:
            return False
        index = target.find("%", index + 3)
    return True


def parse_url(url: str, schemes: frozenset[str] | set[str]) -> Url | None:
    if not isinstance(url, str) or not _printable(url):
        return None
    separator = url.find("://")
    if separator <= 0:
        return None
    scheme = url[:separator].lower()
    if not scheme[0].isalpha() or any(character not in _SCHEME_CHARS for character in scheme):
        return None
    if scheme not in schemes or scheme not in ("http", "https"):
        return None
    rest = url[separator + 3 :]
    end = len(rest)
    for stop in "/?#":
        found = rest.find(stop)
        if found != -1 and found < end:
            end = found
    authority, remainder = rest[:end], rest[end:]
    if "@" in authority or not authority:
        return None
    port_text: str | None = None
    if authority.startswith("["):
        close = authority.find("]")
        if close == -1:
            return None
        host = authority[1:close].lower()
        after = authority[close + 1 :]
        if not host or any(character not in _IPV6_CHARS for character in host):
            return None
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None
        if after:
            if not after.startswith(":"):
                return None
            port_text = after[1:]
    else:
        host, colon, port_part = authority.partition(":")
        host = host.lower()
        if not host or any(character not in _HOST_CHARS for character in host):
            return None
        if colon:
            port_text = port_part
    if port_text is None:
        port = 443 if scheme == "https" else 80
    else:
        if not port_text or len(port_text) > 5 or not port_text.isascii() or not port_text.isdigit():
            return None
        port = int(port_text)
        if not 1 <= port <= 65535:
            return None
    target = remainder.split("#", 1)[0]
    if not target.startswith("/"):
        target = "/" + target
    if not _valid_target(target):
        return None
    return Url(scheme, host, port, target)


def resolve_location(base: Url, location: str, schemes: frozenset[str] | set[str]) -> Url | None:
    if not _printable(location):
        return None
    if "://" in location.split("?", 1)[0].split("#", 1)[0]:
        return parse_url(location, schemes)
    if location.startswith("//"):
        return parse_url(f"{base.scheme}:{location}", schemes)
    location = location.split("#", 1)[0]
    if location.startswith("/"):
        target = location
    elif location.startswith("?") or not location:
        target = base.target.split("?", 1)[0] + location
    else:
        path = base.target.split("?", 1)[0]
        target = path[: path.rfind("/") + 1] + location
    return parse_url(f"{base.scheme}://{base.authority()}{target}", schemes)


def _ip(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def _environment(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name.lower())
    if value is None:
        value = environ.get(name.upper())
    return (value or "").strip()


def _is_loopback(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    address = _ip(host)
    return address is not None and address.is_loopback


def _bypassed(host: str, port: int, no_proxy: str) -> bool:
    if no_proxy == "*":
        return True
    address = _ip(host)
    for raw in no_proxy.split(","):
        entry = raw.strip().lower()
        if not entry:
            continue
        entry_port = None
        if entry.startswith("["):
            close = entry.find("]")
            if close == -1:
                continue
            if entry[close + 1 :].startswith(":"):
                entry_port = entry[close + 2 :]
            entry = entry[1:close]
        elif entry.count(":") == 1:
            entry, entry_port = entry.split(":")
        if entry_port is not None and entry_port != str(port):
            continue
        if "/" in entry:
            try:
                network = ipaddress.ip_network(entry, strict=False)
            except ValueError:
                continue
            if address is not None and address.version == network.version and address in network:
                return True
            continue
        entry_address = _ip(entry)
        if entry_address is not None:
            if address is not None and address == entry_address:
                return True
            continue
        if entry.startswith("*"):
            entry = entry[1:]
        if entry.startswith("."):
            if host.endswith(entry) or host == entry[1:]:
                return True
        elif host == entry or host.endswith("." + entry):
            return True
    return False


def proxy_for(url: Url, environ: Mapping[str, str] | None = None) -> str | None:
    """The proxy URL for a request, or None for a direct connection."""

    environ = os.environ if environ is None else environ
    if _is_loopback(url.host):
        return None
    if _bypassed(url.host, url.port, _environment(environ, "no_proxy")):
        return None
    proxy = _environment(environ, f"{url.scheme}_proxy")
    if not proxy:
        return None
    if "://" not in proxy:
        proxy = "http://" + proxy
    return proxy


def failure_code(error: BaseException) -> str:
    """Map a host failure to one of :data:`FAILURE_CODES`."""

    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        reason = getattr(error, "reason", None)
        if isinstance(reason, BaseException) and reason is not error:
            error = reason
            continue
        if isinstance(error, ConnectionRefusedError):
            return "ECONNREFUSED"
        if isinstance(error, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, http.client.IncompleteRead)):
            return "ECONNRESET"
        if isinstance(error, (TimeoutError, socket.timeout)):
            return "ETIMEDOUT"
        if isinstance(error, socket.gaierror):
            return "EDNS"
        if isinstance(error, ssl.SSLError) or type(error).__name__ == "CertificateError":
            return "ETLS"
        if isinstance(error, http.client.HTTPException):
            return "EPROTO"
        if isinstance(error, OSError) and error.errno in _ERRNO_CODES:
            return _ERRNO_CODES[error.errno]
        cause = error.__cause__ or error.__context__
        if cause is None:
            break
        error = cause
    return "EIO"


def failure(code: str, url: str) -> str:
    return f"{FAILED_PREFIX}{code}: {url}"


def redirect_refused(target: str) -> str:
    return REDIRECT_PREFIX + (target if _printable(target) else INVALID_TARGET)
