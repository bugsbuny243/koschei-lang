"""Human-readable diagnostics for exact-object persistence v1."""

from __future__ import annotations

from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

_INSTALLED = False


def _entry(code: str, tr: str, en: str, why_tr: str, why_en: str, fix_tr: str, fix_en: str):
    CATALOG[code] = Diagnostic(
        code,
        tr,
        tr + ".",
        why_tr,
        fix_tr,
        'let state = caps.persist.allow("/var/lib/app/state.json", 65536, 2000)',
    )
    ENGLISH_CATALOG[code] = Diagnostic(
        code,
        en,
        en + ".",
        why_en,
        fix_en,
        'let state = caps.persist.allow("/var/lib/app/state.json", 65536, 2000)',
    )


def install_persistence_diagnostics_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _entry(
        "KS2420",
        "Persistence policy statik değil",
        "Persistence policy is not static",
        "Exact state object ve bütçeler derleme zamanında sabitlenemedi.",
        "The exact state object and budgets could not be sealed at compile time.",
        "Absolute literal file path ve literal Int bütçeleri kullanın.",
        "Use an absolute literal file path and literal Int budgets.",
    )
    _entry(
        "KS2421",
        "Persistence policy güvenlik sınırı dışında",
        "Persistence policy is outside the security envelope",
        "Path veya byte/deadline bütçesi v1 güvenlik zarfını aşıyor.",
        "The path or byte/deadline budget exceeds the v1 security envelope.",
        "Tek bir absolute file hedefi ve desteklenen bütçe aralığını kullanın.",
        "Use one absolute file target and supported budget ranges.",
    )
    _entry(
        "KS3420",
        "Persistence nesne sözleşmesi ihlali",
        "Persistence object contract violation",
        "Target symlink/non-regular olabilir veya payload UTF-8 sözleşmesini ihlal ediyor.",
        "The target may be a symlink/non-regular object or the payload violates UTF-8.",
        "Regular exact state object ve UTF-8 String kullanın.",
        "Use a regular exact state object and a UTF-8 String.",
    )
    _entry(
        "KS3421",
        "Persistence byte bütçesi aşıldı",
        "Persistence byte budget exceeded",
        "Load veya commit max_bytes sınırını aştı.",
        "Load or commit exceeded max_bytes.",
        "State'i küçültün veya authority oluştururken bilinçli bir bütçe yükseltin.",
        "Reduce state size or deliberately raise the sealed authority budget.",
    )
    _entry(
        "KS3422",
        "Persistence sequence deadline aşıldı",
        "Persistence sequence deadline exceeded",
        "V1 cooperative deadline kontrolü I/O adımları arasında süre aşımı gördü.",
        "The v1 cooperative deadline check expired between I/O steps.",
        "Deadline'ı gözden geçirin; bunu kernel syscall preemption garantisi sanmayın.",
        "Review the deadline; do not treat it as kernel-syscall preemption.",
    )
    _entry(
        "KS3423",
        "Persistence commit durumu belirsiz",
        "Persistence commit state is uncertain",
        "Atomic replace gerçekleşti ancak parent-directory durability teyidi alınamadı.",
        "Atomic replace occurred but parent-directory durability could not be confirmed.",
        "Kör retry yapmayın; exact state'i load ederek sonucu doğrulayın.",
        "Do not blindly retry; load the exact state object and reconcile the result.",
    )
    _entry(
        "KS3424",
        "Persistence I/O reddedildi",
        "Persistence I/O failed closed",
        "Descriptor anchor, file I/O, fsync veya atomic replace tamamlanamadı.",
        "Descriptor anchoring, file I/O, fsync, or atomic replace could not complete.",
        "Platform/filesystem koşulunu düzeltin; runtime daha zayıf bir path I/O'ya düşmez.",
        "Fix the platform/filesystem condition; runtime will not fall back to weaker path I/O.",
    )
    _INSTALLED = True
