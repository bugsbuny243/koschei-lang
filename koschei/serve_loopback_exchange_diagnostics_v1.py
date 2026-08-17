"""Diagnostics for the one-shot loopback HTTP exchange runtime."""

from __future__ import annotations

from . import diagnostics as _diagnostics

_INSTALLED = False


def install_serve_loopback_exchange_diagnostics_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _diagnostics.CATALOG["KS3410"] = _diagnostics.Diagnostic(
        code="KS3410",
        title="HTTP ingress mesajı güvenlik sözleşmesini ihlal etti",
        summary=(
            "Gelen HTTP mesajı veya hazırlanacak yanıt, exchange v1 protokol/byte "
            "sınırlarından birini aştı."
        ),
        why=(
            "İlk ingress çekirdeği tek ve açıkça çerçevelenmiş bir HTTP/1.x mesajı kabul "
            "eder. Chunked aktarım, pipelining, çelişkili Content-Length, aşırı byte veya "
            "UTF-8 olmayan body belirsizlik/smuggling yüzeyi oluşturduğu için reddedilir."
        ),
        fix=(
            "Tek bir HTTP/1.0 veya HTTP/1.1 isteği gönderin, body için geçerli tek bir "
            "Content-Length kullanın, Transfer-Encoding kullanmayın ve request/response "
            "boyutlarını ServeCaps bütçesinin içinde tutun."
        ),
        example=(
            "POST /orders HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}"
        ),
    )
    _diagnostics.ENGLISH_CATALOG["KS3410"] = _diagnostics.Diagnostic(
        code="KS3410",
        title="HTTP ingress message violated the security contract",
        summary=(
            "The inbound HTTP message or outbound response exceeded an exchange-v1 "
            "protocol or byte boundary."
        ),
        why=(
            "The first ingress core accepts exactly one unambiguous HTTP/1.x message. "
            "Chunked transfer, pipelining, conflicting Content-Length, excess bytes and "
            "non-UTF-8 bodies are rejected to reduce framing/smuggling ambiguity."
        ),
        fix=(
            "Send one HTTP/1.0 or HTTP/1.1 request with one valid Content-Length, no "
            "Transfer-Encoding, and keep request/response sizes inside the ServeCaps budget."
        ),
        example=(
            "POST /orders HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}"
        ),
    )

    _diagnostics.CATALOG["KS3411"] = _diagnostics.Diagnostic(
        code="KS3411",
        title="HTTP ingress I/O sınırı aşıldı",
        summary="Listener accept/read/write işlemi I/O deadline içinde tamamlanamadı veya socket hatası oluştu.",
        why=(
            "ServeCaps I/O bütçesi yalnızca ağ bekleme/okuma/yazma süresini sınırlar. "
            "Bir peer sonsuza kadar bağlantıyı açık tutamaz; süre dolunca exchange fail-closed döner."
        ),
        fix=(
            "Peer'in isteği bütçe süresinde tamamladığını doğrulayın, loopback bind'in boş "
            "olduğunu kontrol edin veya açıkça izin verilen I/O deadline bütçesini ayarlayın."
        ),
        example='caps.serve.allow("127.0.0.1:8080", 8, 4096, 4096, 2000)',
    )
    _diagnostics.ENGLISH_CATALOG["KS3411"] = _diagnostics.Diagnostic(
        code="KS3411",
        title="HTTP ingress I/O boundary expired",
        summary=(
            "Listener accept/read/write did not complete inside the I/O deadline or the "
            "socket returned an operating-system error."
        ),
        why=(
            "ServeCaps bounds network waiting/reading/writing so a peer cannot hold the "
            "one-shot exchange indefinitely."
        ),
        fix=(
            "Ensure the peer completes the request within budget, verify the loopback bind "
            "is available, or adjust the explicit I/O deadline within the authority limits."
        ),
        example='caps.serve.allow("127.0.0.1:8080", 8, 4096, 4096, 2000)',
    )

    _INSTALLED = True
