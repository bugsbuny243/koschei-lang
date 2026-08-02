# Koschei Foreign Contract v1

Koschei'nin hedefi yalnızca kendi kodunu güvenli çalıştırmak değildir. C, C++, Rust, Go, Python, JavaScript, Java, .NET ve WebAssembly ekosistemleriyle birlikte çalışırken **yabancı kodun Koschei güvenlik modelini delmesini engellemektir**.

Foreign Contract v1 bu hedefin ilk fail-closed katmanıdır. Bu sürüm yabancı artifact'ı çalıştırmaz veya yüklemez. Önce sözleşmeyi, artifact kimliğini, veri tiplerini ve kaynak bütçelerini doğrular.

## Komutlar

```bash
ks foreign validate examples/interop/text_tools.foreign.json
ks foreign validate examples/interop/text_tools.foreign.json --json
ks foreign fingerprint examples/interop/text_tools.foreign.json
```

`validate` aşağıdakilerin tamamını doğrular:

- Şema tam olarak `koschei.foreign/v1` olmalıdır.
- C, C++, Rust, Go, Python, JavaScript, Java ve .NET adapter'ları `process` izolasyonu kullanmalıdır.
- WebAssembly adapter'ı `wasm` izolasyonu kullanmalıdır.
- Mesaj protokolü tam olarak `koschei-json/v1` olmalıdır.
- Artifact yolu göreli olmalı, sözleşme dizininin dışına çıkmamalı ve sembolik bağ içermemelidir.
- Artifact SHA-256 özeti dosyanın gerçek bytes içeriğiyle eşleşmelidir.
- Girdi, çıktı, süre, bellek ve çağrı bütçeleri zorunlu ve sınırlı olmalıdır.
- Fonksiyon ve parametre isimleri benzersiz ve kanonik olmalıdır.
- İmzalarda yalnızca izin verilen veri tipleri bulunmalıdır.
- `effects` listesi boş olmalıdır. Foreign ABI v1 hiçbir capability taşımaz.
- JSON içinde yinelenen anahtarlar reddedilir.
- Tanımsız alanlar sessizce yok sayılmaz; sözleşme fail-closed reddedilir.

## Güvenlik modeli

Foreign Contract v1, klasik FFI yaklaşımını bilinçli olarak kullanmaz. Shared library yüklemek, host belleğine pointer vermek veya yabancı runtime'ı Koschei sürecine import etmek şu aşamada yasaktır.

V1 sınırı şu şekildedir:

```text
Koschei programı
      │
      │ yalnız doğrulanmış, kanonik veri mesajı
      ▼
izole process veya WASM sandbox
      │
      │ yalnız doğrulanmış dönüş tipi ve byte bütçesi
      ▼
Koschei programı
```

Yabancı kodun disk, ağ, environment veya process yetkisi yoktur. Bir gün kontrollü yetki aktarımı eklenecekse bu, `effects: []` kuralını gevşetmek yerine ayrı bir sürümlü protokol ve açık capability broker üzerinden yapılacaktır.

## İzin verilen adapter dilleri

- `c`
- `cpp`
- `rust`
- `go`
- `python`
- `javascript`
- `java`
- `dotnet`
- `wasm`

Dil adı yalnızca adapter türünü tanımlar. Güvenlik, yabancı dilin kendi iddialarına değil Koschei'nin izolasyon, artifact hash, protokol ve bütçe denetimine dayanır.

## İzin verilen tipler

Temel tipler:

- `Bool`
- `Int`
- `Float`
- `String`
- `Data`
- `Void` — yalnızca dönüş tipi

Generic tipler:

- `List<T>`
- `Map<String,T>`
- `Option<T>`
- `Result<T,E>`

`SystemCaps`, `NetCaps`, `DiskCaps`, `EnvCaps`, `ProcessCaps` ve bütün `*Root` / `*Caps` tipleri Foreign ABI sınırından geçirilemez. `Void` generic içine konamaz ve parametre tipi olamaz.

## Örnek sözleşme

```json
{
  "schema": "koschei.foreign/v1",
  "module": "text.tools",
  "adapter": {
    "language": "python",
    "isolation": "process",
    "protocol": "koschei-json/v1"
  },
  "artifact": {
    "path": "text_worker.py",
    "sha256": "40b6a86bee0dab23f1c621d15cdb03a12203a6de14f3b5d7b59302df9d7140fe"
  },
  "limits": {
    "max_request_bytes": 65536,
    "max_response_bytes": 65536,
    "max_millis": 1000,
    "max_memory_bytes": 67108864,
    "max_calls": 1000
  },
  "functions": [
    {
      "name": "normalize",
      "parameters": [
        {"name": "value", "type": "String"}
      ],
      "returns": "String",
      "effects": []
    }
  ]
}
```

## Hata kodları

- `KS3801` — bozuk JSON, yanlış şema veya sözleşme yapısı
- `KS3802` — güvensiz adapter, izolasyon, protokol veya effect talebi
- `KS3803` — desteklenmeyen veya capability taşıyan ABI tipi
- `KS3804` — eksik, yanlış veya sınır dışı kaynak bütçesi
- `KS3805` — geçersiz, yinelenen veya ayrılmış isim
- `KS3806` — güvensiz artifact yolu, symlink, dosya eksikliği veya SHA-256 uyuşmazlığı

## Sonraki kapı

Foreign Contract v1 yalnızca sözleşme ve artifact kimliğini mühürler. Sonraki sürümde execution broker eklenecektir. Broker şu koşullar sağlanmadan main'e girmeyecektir:

1. Shell kullanılmadan doğrudan process başlatma.
2. Temiz environment ve kapalı file descriptor mirası.
3. İşletim sistemi seviyesinde süre, bellek ve çıktı sınırları.
4. Kanonik, uzunluk çerçeveli mesaj protokolü.
5. Her çağrıda fonksiyon adı, argüman tipi ve dönüş tipi doğrulaması.
6. Artifact hash değişirse çalıştırmayı reddetme.
7. Interpreter/native ve Linux sandbox parity testleri.
8. Capability kaçış corpus'u ve supply-chain saldırı testleri.

Bu sıra bilinçlidir: önce güvenlik sınırı kanıtlanır, sonra yabancı kod çalıştırılır.
