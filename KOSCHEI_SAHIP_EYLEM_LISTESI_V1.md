# Koschei Sahip Eylem Listesi v1

Bu adımlar kaynak koddan yapılamaz: sahibin hesabı, imzası veya kararı
gerekir. Her biri tamamlandığında kanıtını (ekran görüntüsü, bağlantı) depo
dışında saklayın ve aşağıdaki tabloyu güncelleyin.

**Satış modeli (2026-10-27, sahibin kararı):** proje bütünüyle devredilmiyor;
Koschei Lang ticari lisansla satılıyor. Kişisel kullanım ücretsiz, ticari
lisans tek seferlik ve kalıcı, satın almadan sonraki 12 ay içinde çıkan
sürümleri kapsıyor. Fiyat geliştirici başına 49 USD; 2026-11-11'den beri
mağazada tek ücretli ürün var (Ekip ve Kurumsal paketleri kaldırıldı). İndirme ve ödeme Polar
(polar.sh) üzerinden. Ayrıntılar: `LICENSE`, `LICENSE.tr.md`,
`LICENSING.tr.md`.

| # | Eylem | Neden | Nasıl | Durum |
|---|---|---|---|---|
| S1 | `main` dalını koruma altına almak | Geçmişin sessizce yeniden yazılamadığını gösterir | `main-koruma` kuralı (ruleset): PR zorunlu, `test` kontrolü zorunlu, force push ve silme yasak. Depo 2026-11-10'da herkese açık yapıldı; GitHub kuralı açık depolarda ücretsiz uygular. Settings → Rules sayfasında uyarı kalmadığını doğrulayın | Kısmi (doğrulama bekliyor) |
| S2 | Satış adayını `main`'e almak | Ürün tek dalda olmalı | PR #314 birleşti (`b383f9c`) | Tamam |
| S3 | Sürüm imzası | İndirilen paketin sizden geldiğini doğrulatır | Özel anahtar gerektirmeyen Sigstore yolu kullanılıyor: PyPI dosyaları `publish-pypi.yml` ile yüklenirken kaynak kanıtı (attestation) taşır (0.10.1'de doğrulandı); Polar indirmesi `polar-bundle.yml` ile derlenip imzalanır, müşteri `gh attestation verify koschei-lang-<sürüm>.zip --repo bugsbuny243/koschei-lang` ile doğrular. Kendi anahtarınızla ek imza isterseniz anahtarı kendi bilgisayarınızda üretin; özel anahtarı **asla** depoya, sohbete veya bulut oturumuna koymayın | Kısmi (Polar paketi iş akışı ilk kez çalıştırılacak) |
| S4 | Lisans modeli | Müşteri ne aldığını bilmeli | Ticari lisans: kişisel ücretsiz, kalıcı ticari lisans + 12 ay güncelleme (`LICENSE`, `LICENSE.tr.md`) | Tamam |
| S5 | Sahiplik beyanı | Lisans verebilmek için kodun sizin olması gerekir | Tek yazar sizseniz kısa bir yazılı beyan yeterli; başka katkı veren varsa onlardan hak devri alın | Yok |
| S6 | Hukuki inceleme | Lisans metninin uygulanabilirliği | Sahip kararıyla yapılmıyor; lisans metni avukat incelemesinden geçmedi | Sahip kararı |
| S7 | Fiyat | Müşteriye net teklif | Geliştirici başına 49 USD, tek seferlik; bir kuruluş her geliştiricisi için bir lisans alır (`LICENSING.tr.md`). 2026-11-11: Ekip (249) ve Kurumsal (999) paketleri sahibin kararıyla kaldırıldı | Tamam |
| S8 | Bağımsız güvenlik denetimi (isteğe bağlı) | Güveni artırır; zorunlu değil | Bir güvenlik firmasına `docs/THREAT_MODEL_V1.md` kapsamıyla denetim yaptırın | Yok |
| S9 | Polar mağazası | Ödeme ve indirme | Mağazada tek ücretli ürün: Bireysel 49 USD (sitedeki satın alma bağlantısı çalışıyor). Kalan: ürüne indirme dosyası olarak `polar-bundle.yml` iş akışının ürettiği imzalı `koschei-lang-<sürüm>.zip` dosyasını eklemek; ürün açıklamasına `LICENSING.md` özetini ve `LICENSE` bağlantısını koymak; iade politikasını belirlemek | Kısmi |
| S10 | Duyuru | Kullanıcıya ulaşmak | Yapıldı: koschei.dev (playground ve ajanlar sayfası), depo herkese açık, PyPI ve MCP Registry kaydı, X ve LinkedIn paylaşımı, Product Hunt lansmanı (7 Kasım). Hacker News gönderisi moderatör yanıtı bekliyor: metinler sahibin kendi cümleleriyle yeniden yazılmalı | Kısmi |
| S11 | Güvenlik açığı bildirimi | `SECURITY.md` özel bildirimi GitHub üzerinden ister | Settings → Code security → **Private vulnerability reporting** → Enable | Yok |

## Benim yapabileceklerim (geliştirme)

Geliştirme kapıları `KOSCHEI_SATISA_HAZIRLIK_V1.md`'de. Yeni bir sürümde
indirme paketini yeniden üretirim, mağaza ve duyuru metinlerinin taslağını
sizin onayınızla hazırlarım. S3'te özel anahtarı benimle paylaşmayın.
