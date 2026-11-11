# Koschei Lang 0.10.0 — Global Commercial Store Listing

Status: copy approved for technical truth checking, **not** proof that the
Polar checkout is live. Product: **Koschei Lang**, sold separately from
Koschei Sentinel and Koschei Web3 Hub.

## EN — Product title

**Koschei Lang 0.10.0 — Capability-Secure Programming Language**

### Store short description

Build programs with explicit permissions. Imported Koschei modules do
not automatically inherit disk, network, environment or process authority.
Inspect a program's capability reach, reject unapproved capabilities
in CI and compile typed `.ks` source for native execution.

### Full product description

Koschei Lang is an independent programming language and toolchain built
around capability security. It gives developers a compiler, interpreter,
native build path, standard/Core Library, VS Code language support and
tested security-oriented examples.

**What's in version 0.10.0:**

- Explicit disk, network, environment and process capability values.
  Imported `.ks` code cannot use a capability absent from its scope.
- `ks check` for static diagnostics and authority checks; `ks caps`
  for the whole-program capability manifest; `ks caps --deny net`
  to fail builds that request forbidden network authority.
- `ks run` for checked interpreter execution and `ks build`
  for native compilation through the current Go-based adapter.
- Typed `Option<T>` and `Result<T,E>`, bounded values,
  checked imports and a growing Core Library written in Koschei.
- Language guide, bilingual error explanations and VS Code tooling.
- Examples: `secretscan` scans for credential-like patterns,
  `integrity` checks directory content against a stored snapshot,
  and a deliberately unauthorized dependency is rejected at compile
  time with error `KS2401`.

**Requirements:** Python 3.12+ and a Unix-like shell for the included
`install.sh`; Go 1.24+ for `ks build`. Additional platforms require
independent installation/compatibility checks. The repository remains
private; distribution is through licensed artifacts, not unrestricted
source publication.

**Limitations:** Pre-1.0 software. Does not promise protection against
malicious executables run outside the Koschei compiler, stolen developer
credentials, compromised hosts, unaudited AI agents or unauthorized
wallet signing. Not independently certified for critical financial
production workloads.

### Pricing — one-time, USD

| Plan | Licensed users | One-time price |
|---|---|---:|
| Personal | Noncommercial learning and projects | Free |
| Individual | 1 named commercial developer | $49 |

Each paid license permits perpetual use of acquired releases and
includes releases issued within 12 months after purchase. Programs and
generated binaries belong to their authors under the applicable license.
Companies may evaluate for 30 days under existing license terms.

### Suggested Polar product fulfillment

Create/verify the four product listings under the **same Koschei Lang
merchant identity**. Fulfill with the exact
`koschei-lang-0.10.0.zip` artifact from the validated commercial
workflow; retain `candidate-manifest.json`, `SHA256SUMS` and
`full-validation-receipt.json` in the release records. Check the payment,
invoice, entitlement, correct tier and actual authenticated download
from an external customer account before announcing "now available".
**Never** disclose proprietary repository credentials or CI secrets.

## TR — Ürün başlığı

**Koschei Lang 0.10.0 — Yetki Güvenli Programlama Dili**

### Kısa açıklama

Açıkça tanımlanmış yetkilerle yazılım geliştirin. Koschei modülleri
disk, ağ, ortam değişkeni veya işlem çalıştırma yetkilerini otomatik
olarak devralmaz. Derleme öncesi yetki denetimi, CI kısıtları, tipli
`.ks` kaynak kodu ve native derleme tek araç zincirinde.

### Ürün açıklaması

Koschei Lang; kendi derleyicisi, yorumlayıcısı, Core Library
kütüphaneleri, geliştirici araçları ve güvenlik örnekleriyle bağımsız
bir programlama dili ürünüdür.

**0.10.0 ile gelenler:**

- Disk, ağ, ortam ve işlem erişimi için açık yetki modeli.
- `ks check` ile derleyici denetimi, `ks caps` ile yetki
  manifestosu ve `ks caps --deny net` ile CI'da ağ erişimi reddi.
- `ks run` yorumlayıcısı ve Go tabanlı mevcut adaptör üzerinden
  `ks build` native derleme yolu.
- `Option<T>`, `Result<T,E>`, sınırlandırılmış değerler,
  Core Library, VS Code araçları, Türkçe/İngilizce hata açıklamaları.
- `secretscan`, `integrity` örnekleri ve `KS2401` ile
  derleme sırasında reddedilen yetkisiz bağımlılık gösterimi.

**Gereksinimler:** Python 3.12+, kurulum betiği için Unix benzeri
kabuk; native derleme için Go 1.24+. Diğer platformlar ayrıca
doğrulanmalıdır.

**Kapsam:** Ürün 1.0 öncesindedir. İşletim sistemi üzerindeki her zararlı
dosyayı engellediği, hesap ele geçirmeyi önlediği veya banka/borsa
üretim sistemleri için bağımsız sertifikasyon taşıdığı iddia edilmez.

### Fiyatlar — tek seferlik USD

| Lisans | Kapsam | Fiyat |
|---|---|---:|
| Personal | Ticari olmayan kullanım | Ücretsiz |
| Individual | 1 ticari geliştirici | 49 USD |

Ücretli lisanslar satın alınan sürümler için süresiz kullanım ve
satın alma tarihinden itibaren 12 ay içinde çıkan yeni sürümleri
kapsar. Kuruluşların 30 günlük değerlendirme hakkı mevcut lisans
metninde tanımlıdır.

## Commercial launch claims requiring proof

The sales pages may truthfully say "a capability-secure programming
language with explicit permissions" and refer to the checkable
`KS2401` demonstration. Do not say "prevents the Binance attack",
"100x safer than Rust", "self-hosted compiler", "certified banking
runtime", or "safe to execute arbitrary interview projects".
A successful release workflow is not proof of live checkout.
