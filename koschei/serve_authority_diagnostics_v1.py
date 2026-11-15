"""Human explanations for the provisional Serve authority boundary."""

from __future__ import annotations

from . import diagnostics as _diagnostics

_INSTALLED = False


def install_serve_authority_diagnostics_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _diagnostics.CATALOG["KS2410"] = _diagnostics.Diagnostic(
        code="KS2410",
        title="Serve yetkisi kesin politika gerektiriyor",
        summary=(
            "HTTP sunucu yetkisi daraltılırken bind adresi veya kaynak bütçeleri "
            "derleme anında kesin olarak kanıtlanamadı."
        ),
        why=(
            "Bir listener'ın nerede açılacağı ve kaç bağlantı/bayt/süre tüketebileceği "
            "dinamik bırakılırsa capability manifestosu gerçek saldırı yüzeyini kesin "
            "olarak gösteremez. Serve authority v1 bu belirsizliği kabul etmez."
        ),
        fix=(
            "ServeRoot.allow() çağrısında literal loopback bind ve dört literal Int bütçe "
            "verin: bağlantı, istek baytı, yanıt baytı ve deadline milisaniyesi."
        ),
        example=(
            'let server = caps.serve.allow("127.0.0.1:8080", '
            "64, 65536, 65536, 5000)"
        ),
    )
    _diagnostics.ENGLISH_CATALOG["KS2410"] = _diagnostics.Diagnostic(
        code="KS2410",
        title="Serve authority requires an exact policy",
        summary=(
            "The HTTP serve authority could not prove its bind address or resource "
            "budgets at compile time."
        ),
        why=(
            "A dynamic listener scope would make the capability manifest unable to state "
            "the real attack surface exactly. Serve authority v1 fails closed instead."
        ),
        fix=(
            "Pass a literal loopback bind and four literal Int budgets to "
            "ServeRoot.allow(): connections, request bytes, response bytes and deadline ms."
        ),
        example=(
            'let server = caps.serve.allow("127.0.0.1:8080", '
            "64, 65536, 65536, 5000)"
        ),
    )

    _diagnostics.CATALOG["KS2411"] = _diagnostics.Diagnostic(
        code="KS2411",
        title="Serve bind veya bütçe güvenlik sınırı dışında",
        summary=(
            "Serve yetkisi tanımadığı bir bind adresi ya da izin verilen sınırların "
            "dışında bir kaynak bütçesi aldı."
        ),
        why=(
            "Sunucu ya yalnız bu makineden (loopback) ya da bütün arayüzlerden "
            "(0.0.0.0 veya [::]) dinler; anlamı ağ ayarına bağlı başka bir adres kabul "
            "edilmez. Bağlantı, body ve deadline değerleri sert üst sınırlara sahiptir; "
            "aksi halde yetki jetonu kaynak tüketimi için sınırsız bir kapıya dönüşebilir."
        ),
        fix=(
            "localhost, 127.0.0.0/8 veya [::1] ile ya da herkese açık sunucu için tam "
            "olarak 0.0.0.0:PORT veya [::]:PORT ile açık bir port kullanın ve bütçeleri "
            "dokümante edilen aralıklarda tutun."
        ),
        example=(
            'let server = caps.serve.allow("[::1]:8080", '
            "32, 32768, 65536, 3000)"
        ),
    )
    _diagnostics.ENGLISH_CATALOG["KS2411"] = _diagnostics.Diagnostic(
        code="KS2411",
        title="Serve bind or budget is outside the security envelope",
        summary=(
            "The serve authority received a bind address it does not recognise or a "
            "resource budget outside its hard limits."
        ),
        why=(
            "A server listens on this machine only (loopback) or on every interface "
            "(0.0.0.0 or [::]); an address whose meaning depends on the host's network "
            "setup is refused. Budgets are hard-bounded so a capability token cannot "
            "silently become an unbounded resource grant."
        ),
        fix=(
            "Use localhost, a 127.0.0.0/8 address or [::1], or exactly 0.0.0.0:PORT or "
            "[::]:PORT for a public server, and keep all budgets inside the documented "
            "bounds."
        ),
        example=(
            'let server = caps.serve.allow("[::1]:8080", '
            "32, 32768, 65536, 3000)"
        ),
    )

    _INSTALLED = True
