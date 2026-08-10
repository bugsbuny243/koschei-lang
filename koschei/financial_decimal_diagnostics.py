"""Human-readable diagnostics for the financial Decimal ABI."""

from __future__ import annotations

from . import diagnostics

_INSTALLED = False


def install_financial_decimal_diagnostics() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    turkish = {
        "KS3801": diagnostics.Diagnostic(
            code="KS3801",
            title="Geçersiz Decimal sözleşmesi",
            summary="Decimal metni, scale veya değer tipi exact finans sözleşmesine uymuyor.",
            why=(
                "Finansal sayıların host Float'a veya örtük dönüşümlere düşmesi farklı "
                "backend'lerde farklı para sonuçları üretebilir. Decimal girdisi bu yüzden "
                "kanonik ve açık scale ile doğrulanır."
            ),
            fix=(
                "decimal(\"101.2500\", 4) gibi kanonik String ve 0..18 scale kullanın; "
                "üs gösterimi, baş/son boşluk, '+' öneki ve gereksiz baştaki sıfırları kaldırın."
            ),
            example='let price = decimal("101.2500", 4) or return',
        ),
        "KS3802": diagnostics.Diagnostic(
            code="KS3802",
            title="Decimal scale uyuşmazlığı",
            summary="İki Decimal farklı scale taşıyor ve işlem örtük rescale gerektiriyor.",
            why=(
                "Örtük rescale finans kodunda rounding ve birim hatalarını saklayabilir. "
                "Koschei v1 farklı scale değerlerini otomatik olarak eşitlemez."
            ),
            fix=(
                "Aynı market/asset sözleşmesindeki değerleri aynı scale ile oluşturun. "
                "Rescale ve rounding ileride ayrı, açık bir finans API'si olarak tanımlanacaktır."
            ),
            example=(
                'let left = decimal("1.00", 2) or return\n'
                'let right = decimal("2.50", 2) or return\n'
                "let total = decimal_add(left, right) or return"
            ),
        ),
        "KS3803": diagnostics.Diagnostic(
            code="KS3803",
            title="Decimal int64 taşması",
            summary="Decimal atom hesabı işaretli 64-bit sınırını aştı.",
            why=(
                "Decimal atomları interpreter ve native backend'de aynı signed-int64 "
                "sözleşmesini taşır; wraparound para üretmek yerine işlem reddedilir."
            ),
            fix=(
                "Daha küçük atom ölçeği/pozisyon büyüklüğü kullanın veya hesabı parçalara "
                "ayırın. Taşmayı sessizce sarmalamayın."
            ),
            example='let total = decimal_add(a, b) or return',
        ),
    }
    english_fields = {
        "KS3801": (
            "Invalid Decimal contract",
            "Decimal text, scale, or value type violates the exact-finance contract.",
            "Financial values must never fall through host Float or implicit conversion semantics.",
            "Use canonical String input and an explicit scale from 0 through 18.",
        ),
        "KS3802": (
            "Decimal scale mismatch",
            "Two Decimal values have different scales and the operation would require implicit rescaling.",
            "Implicit rescaling can hide rounding and unit errors in financial code.",
            "Construct values under the same market/asset scale; use an explicit future rescale API when required.",
        ),
        "KS3803": (
            "Decimal int64 overflow",
            "A Decimal atom calculation exceeded the signed 64-bit range.",
            "Checked atoms keep interpreter and native money arithmetic identical and prevent wraparound.",
            "Reduce the atom magnitude or split the calculation; do not rely on overflow.",
        ),
    }

    for code, item in turkish.items():
        diagnostics.CATALOG[code] = item
        fields = english_fields[code]
        diagnostics.ENGLISH_CATALOG[code] = diagnostics.Diagnostic(
            code=code,
            title=fields[0],
            summary=fields[1],
            why=fields[2],
            fix=fields[3],
            example=item.example,
        )

    diagnostics.CATALOGS["tr"] = diagnostics.CATALOG
    diagnostics.CATALOGS["en"] = diagnostics.ENGLISH_CATALOG
    _INSTALLED = True
