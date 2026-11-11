# Koschei Sahip Eylem Listesi v1

Bu adımlar kaynak koddan yapılamaz: sahibin hesabı, imzası veya kararı
gerekir. Her biri tamamlandığında kanıtını (ekran görüntüsü, bağlantı) depo
dışında saklayın ve aşağıdaki tabloyu güncelleyin.

**Satış modeli (2026-10-27, sahibin kararı):** proje bütünüyle devredilmiyor;
Koschei Lang ticari lisansla satılıyor. Kişisel kullanım ücretsiz, ticari
lisans tek seferlik ve kalıcı, satın almadan sonraki 12 ay içinde çıkan
sürümleri kapsıyor. Fiyatlar 49 / 249 / 999 USD. İndirme ve ödeme Polar
(polar.sh) üzerinden. Ayrıntılar: `LICENSE`, `LICENSE.tr.md`,
`LICENSING.tr.md`.

| # | Eylem | Neden | Nasıl | Durum |
|---|---|---|---|---|
| S1 | `main` dalını koruma altına almak | Geçmişin sessizce yeniden yazılamadığını gösterir | `main-koruma` kuralı (ruleset) kuruldu: PR zorunlu, `test` kontrolü zorunlu, force push ve silme yasak. Depo özel olduğu için GitHub ücretli plana geçmeden kuralı **uygulamıyor** (sayfadaki sarı uyarı); GitHub Pro'ya geçince uyarının kalktığını kontrol edin | Kısmi |
| S2 | Satış adayını `main`'e almak | Ürün tek dalda olmalı | PR #314 birleşti (`b383f9c`) | Tamam |
| S3 | Sürüm imza anahtarı | İndirilen paketin sizden geldiğini doğrulatır | Kendi bilgisayarınızda anahtar üretin (`ssh-keygen -t ed25519` veya Sigstore); özel anahtarı **asla** depoya, sohbete veya bulut oturumuna koymayın; açık anahtarı depoya ekletin | Yok |
| S4 | Lisans modeli | Müşteri ne aldığını bilmeli | Ticari lisans: kişisel ücretsiz, kalıcı ticari lisans + 12 ay güncelleme (`LICENSE`, `LICENSE.tr.md`) | Tamam |
| S5 | Sahiplik beyanı | Lisans verebilmek için kodun sizin olması gerekir | Tek yazar sizseniz kısa bir yazılı beyan yeterli; başka katkı veren varsa onlardan hak devri alın | Yok |
| S6 | Hukuki inceleme | Lisans metninin uygulanabilirliği | Sahip kararıyla yapılmıyor; lisans metni avukat incelemesinden geçmedi | Sahip kararı |
| S7 | Fiyat | Müşteriye net teklif | Bireysel 49 USD, Ekip (10 geliştirici) 249 USD, Kurumsal 999 USD; tek seferlik (`LICENSING.tr.md`) | Tamam |
| S8 | Bağımsız güvenlik denetimi (isteğe bağlı) | Güveni artırır; zorunlu değil | Bir güvenlik firmasına `docs/THREAT_MODEL_V1.md` kapsamıyla denetim yaptırın | Yok |
| S9 | Polar mağazası | Ödeme ve indirme | 1) Polar hesabı açın ve **Türkiye'ye ödeme (payout) desteğini doğrulayın**. 2) Dört ürün: Kişisel (ücretsiz), Bireysel 49 USD, Ekip 249 USD, Kurumsal 999 USD; hepsi tek seferlik. 3) Her ürüne indirme dosyası olarak `python tools/polar_bundle_v1.py` ile üretilen `dist/polar/koschei-lang-<sürüm>.zip` dosyasını ekleyin. 4) Ürün açıklamasına `LICENSING.md` özetini ve `LICENSE` bağlantısını koyun. 5) İade politikasını belirleyin | Yok |
| S10 | Duyuru | Kullanıcıya ulaşmak | Mağaza açılınca: kişisel web sayfası, GitHub profili, geliştirici toplulukları; müşteri README'si `distribution/polar/README.md` | Yok |

## Benim yapabileceklerim (geliştirme)

Geliştirme kapıları `KOSCHEI_SATISA_HAZIRLIK_V1.md`'de. Yeni bir sürümde
indirme paketini yeniden üretirim, mağaza ve duyuru metinlerinin taslağını
sizin onayınızla hazırlarım. S3'te özel anahtarı benimle paylaşmayın.
