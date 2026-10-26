# Koschei Sahip Eylem Listesi v1

Bu adımlar kaynak koddan yapılamaz: sahibin hesabı, imzası veya kararı
gerekir. Her biri tamamlandığında kanıtını (ekran görüntüsü, imzalı belge,
bağlantı) depo dışında saklayın ve aşağıdaki tabloyu güncelleyin.

| # | Eylem | Neden | Nasıl | Durum |
|---|---|---|---|---|
| S1 | `main` dalını koruma altına almak | Alıcı, geçmişin sessizce yeniden yazılamadığını görmek ister (`KOSCHEI_ACQUISITION_READINESS_V1.md` P0) | GitHub → depo → Settings → Branches → Add rule: `main`; "Require a pull request", "Require status checks" (tests, verify), "Do not allow force pushes" | Yok |
| S2 | Bu dalı `main`'e almak | Satış adayı tek bir dalda olmalı | `claude/koschei-lang-ctpww4` için bir pull request açıp birleştirin (isterseniz ben açarım) | Yok |
| S3 | Sürüm imza anahtarı | İmzalı sürüm, alıcının ikiliyi doğrulamasını sağlar | Kendi bilgisayarınızda anahtar üretin (`ssh-keygen -t ed25519` veya Sigstore); özel anahtarı **asla** depoya, sohbete veya bulut oturumuna koymayın; açık anahtarı depoya ekletin | Yok |
| S4 | Lisans kararı | Alıcı ne satın aldığını bilmeli: tam devir (asset sale) mı, ticari lisans mı | Avukatla birlikte seçin; `LICENSE` bugün "proprietary"; geçmişte MIT ile yayımlanmış sürümler `KOSCHEI_LICENSE_LINEAGE_V1.md`'de | Yok |
| S5 | Sahiplik beyanı (chain of title) | Kodun tümünün size ait olduğunu ve devredilebildiğini gösterir | İmzalı bir beyan: tek yazar sizsiniz, katkıların bir kısmı yapay zekâ yardımıyla üretildi ve bu araçların kullanım şartları çıktının size ait olmasına izin veriyor; başka katkıcı varsa devir sözleşmeleri | Yok |
| S6 | Hukuki inceleme | Lisans, devir ve yapay zekâ destekli kodun telif durumu ülkeye göre değişir | Bir avukata S4 ve S5'i inceletin | Yok |
| S7 | Fiyat ve şartlar | 10.000 USD hedefi sizin kararınız | İlan metnine fiyat, ödeme (escrow önerilir), devir süresi, destek süresi (ör. 30 gün e-posta) yazın | Yok |
| S8 | Bağımsız güvenlik denetimi (isteğe bağlı) | Değeri artırır; zorunlu değil | Bir güvenlik firmasına `docs/THREAT_MODEL_V1.md` kapsamıyla denetim yaptırın | Yok |
| S9 | Hesap ve alan adı envanteri | Devirde nelerin verileceği net olmalı | GitHub deposu, alan adları, paket kayıtları, sosyal hesaplar: hangisi devredilecek, listeleyin | Yok |
| S10 | İlan | Alıcıya ulaşmak | Acquire.com, Flippa, Microns gibi bir pazar yerinde `SALE_PACKAGE_V1.md`'yi ilan metni olarak kullanın; depoya erişimi yalnızca gizlilik sözleşmesi (NDA) imzalayan alıcıya verin | Yok |

## Benim yapabileceklerim (geliştirme)

Geliştirme kapıları `KOSCHEI_SATISA_HAZIRLIK_V1.md`'de. Yukarıdaki listeden
S2 (pull request) ve S10 için ilan metni taslağını sizin onayınızla hazırlarım.
S3'te özel anahtarı benimle paylaşmayın.
