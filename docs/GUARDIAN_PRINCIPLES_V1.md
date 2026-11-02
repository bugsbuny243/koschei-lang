# Bekçi İlkeleri v1: `odin`, `sokovia`, `quicksilver`

Durum: **Core Library'de, Koschei ile yazılmış; her yürütücüde ve native ikilide
aynı karar** (`tests/test_guardian_principles_v1.py`).

Bu üç modül, bilinen güvenlik ilkelerini Koschei kütüphanesinde karar olarak
yazar. Hiçbiri kendi başına yetki vermez: verdikleri karar düz bir değerdir.
Koschei'de çalışma zamanı yetkisi yalnızca yetki belirteçleriyle (capability
token) taşınır. Bu modüller, bir uygulamanın kendi verisi üzerindeki kararlar
içindir: API anahtarları ve alt anahtarlar, devredilen roller, büyük
çekimlerde onay, zaman penceresi sınırları.

## İlkeler ve karşılıkları

| İlke | Kaynak | Modül | Kural |
|---|---|---|---|
| Yetki türetme ağacı, daraltma, geri alma | seL4 (capability derivation tree) | `odin` | Bir yetki ancak daha dar türetilir: üst yetkinin haklarının alt kümesi, daha geç bitmeyen ömür, en çok `max_depth()` (16) seviye. Geri alınan bir yetki, ondan türeyen her şeyi düşürür. |
| Eksiksiz denetim | Saltzer–Schroeder (complete mediation) | `odin.check` | Zincirin her halkası kökten itibaren yeniden denetlenir; elle kurulmuş, hakları genişleten ya da ömrü uzayan bir halka reddedilir. |
| Süreli yetki, sürekli açık yetki yok | Zero Trust, en az yetki | `odin` | Her yetkinin bitiş zamanı (`not_after`) vardır; alt yetki üstünden uzun yaşayamaz. |
| Yetkinin ayrılması, iki kişi kuralı | Saltzer–Schroeder (separation of privilege) | `sokovia` | Bir eylem, isteyen dışında `threshold` farklı uygun onaylayıcı ister; aynı kişinin tekrarı bir kez sayılır. |
| Ne onaylandıysa o çalışır | WYSIWYS | `sokovia.action` | Onay, eylemin tam özetine bağlıdır (tür + her alan); bir eyleme verilen onay, ne kadar benzer görünürse görünsün başka bir eylem için sayılmaz. |
| Hız sınırı, zarar sınırı | Hata ve saldırı yayılımının sınırlanması | `quicksilver` | Herhangi bir `window` epoch içinde en çok `limit` birim. Her biri küçük çok sayıda hızlı adım da sınırı aşamaz. |
| Denetimli yeniden başlatma | Erlang/OTP (restart intensity) | `quicksilver` (`amount` = 1) | T sürede en çok N yeniden başlatma; aşılırsa dur ve yukarıya bildir. |

## Neyle test edildi

- **`odin`:** İki halkalı zincirlerde 2 hakkın her alt küme çifti, iki ömür,
  üç epoch, üç geri alma durumu ve hiç verilmemiş bir hak sorgusu: 864 durumun
  tamamı bağımsız Python modeliyle karşılaştırılır. Ayrıca Koschei'nin kendi
  cevabı üzerinde değişmez denetlenir: izin verildiyse hak her halkada vardır,
  hiçbir halka geri alınmamış ve süresi dolmamıştır. `derive`, 3 hakkın 192
  durumunun tamamında yalnızca daraltan türetmeyi kabul eder. 16 seviyelik
  zincirin her halkasının geri alınması, o halkadan aşağısını düşürür. Mühürler
  RFC 4231 ile doğrulanmış `hmac_sha256` ile hesaplanır.
- **`sokovia`:** 3 uygun onaylayıcı ve 1 yabancı için her onay örüntüsü (onay
  yok / bu eylem / başka eylem), tekrarlı onaylar, iki isteyen türü ve beş eşik:
  810 durum.
- **`quicksilver`:** 500 tohumlu geçmiş; en büyük Int değerleri dahil. Taşma
  yoktur ve izin verilen her harcama pencereyi sınırın içinde tutar.
- Aynı modüller native ikilide `ks run` ile aynı çıktıyı verir.

## Neyi kanıtlamaz

- **Matematiksel kanıt değildir.** seL4'ün kendisi makinece kanıtlanmıştır; buradaki
  güvence, küçük alanlarda bütün durumların denenmesidir.
- **Özet imza değildir.** Herkes kurallara uygun bir `Grant` kurabilir. Bir
  uygulamanın sakladığı yetkileri yalnızca kendisinin basabilmesi için
  `odin.seal` / `odin.check_sealed` gizli bir anahtarla HMAC-SHA256 kullanır.
  Anahtar kaynak koda girmez; `EnvCaps` ya da izinli bir dosyadan okunur.
- **Onayın kimden geldiğini `sokovia` bilmez.** Uygulama her onayı içeri almadan
  önce doğrulamalıdır (örneğin yalnızca onaylayıcının oturumunun bildiği bir
  anahtarla `hmac_sha256`). Koschei'de açık anahtarlı imza doğrulaması henüz
  yoktur: Python'un standart kütüphanesi Ed25519 içermez.
- **Saat güvenilir değilse zaman kuralları da güvenilir değildir.** Epoch'u
  çağıran verir; `ClockCaps` ya da güvenilir bir kaynak kullanılmalıdır.

## Binance saldırısı (29 Ekim 2026) yalnızca sınav olarak

Dil bu saldırıya göre tasarlanmadı. İlkeler genel; saldırı, onları denemek
için okundu. Kamuya açık bilgiye göre (tam teknik rapor henüz yayınlanmadı)
ele geçirilmiş bir mühendis bilgisayarı, çekim yetkisi olan bir servise
ulaştı. Yaklaşık 20 dakikada on zincirden 6,3 milyar dolar çekildi ve
Binance'e göre hiçbir özel anahtar sızmadı. Bu ilkelerle kurulmuş bir
sistemde:

- sürekli açık bir çekim yetkisi olmaz; yetki süreli ve dar türetilir (`odin`);
- tek bir kimliğin büyük bir çekimi onaylaması yetmez, onay da eylemin tam
  özetine bağlıdır (`sokovia`);
- pencere başına çekim sınırı, 20 dakikada her şeyin boşalmasını engeller
  (`quicksilver`).

Bunlar karar katmanıdır; uç nokta güvenliği, anahtar saklama ve bağımsız
denetim yerine geçmez.
