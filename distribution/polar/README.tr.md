# Koschei Lang

Yetki güvenli (capability-secure) bir programlama dili: içe aktardığınız bir
paket, siz ona bir yetki vermedikçe diskinize, ağınıza veya ortam
değişkenlerinize dokunamaz. `ks run` bir programı çalıştırmadan önce
tamamen denetler; `ks build` aynı programı aynı baytları yazdıran native bir
ikiliye derler.

Kişisel kullanım ücretsizdir; ticari kullanım için lisans gerekir
(`LICENSING.tr.md`).

## Kurulum

Python 3.12 veya daha yenisi gerekir. Go 1.24 veya daha yenisi isteğe
bağlıdır; `ks build` için gerekir.

```sh
./install.sh
```

Kurulum betiği `~/.koschei` içinde bir sanal ortam kurar ve `ks` komutunu
`~/.local/bin` altına bağlar. Başka yerler için `KOSCHEI_HOME` veya
`KOSCHEI_BIN` değişkenlerini kullanın.

## İlk adımlar

```sh
ks run examples/hello.ks
printf 'the cat saw the dog\n' | ks run examples/apps/wordfreq/main.ks
ks caps examples/apps/release_gate/main.ks     # bu program neye dokunabilir
ks check examples/supply_chain/main.ks         # reddedilir: bir bağımlılık gizli dosyaya uzanıyor
ks build examples/apps/keygen/main.ks -o keygen && ./keygen 2
```

Hazır iki güvenlik aracı; her biri yalnızca verdiğiniz klasörü okuyabilir ve
ağa çıkamaz (`ks caps` bunu gösterir):

```sh
ks build examples/apps/secretscan/main.ks -o secretscan
./secretscan proje/klasoru        # sızmış anahtar ve token'lar; bulursa çıkış kodu 1
ks build examples/apps/integrity/main.ks -o integrity
./integrity snapshot site > manifest.txt
./integrity verify site < manifest.txt   # CHANGED / MISSING / NEW; fark varsa çıkış kodu 1
```

## Belgeler

- `docs/guide/LANGUAGE_GUIDE.tr.md`: dil rehberi (İngilizcesi
  `LANGUAGE_GUIDE.en.md`); içindeki her örnek test edilir.
- `docs/reference/CORE_LIBRARY.md`: Core Library başvurusu.
- `docs/reference/ERROR_CODES.md`: bütün hata kodları ve çözümleri;
  `ks explain <kod>` aynı metni yazdırır.

## Lisans

Koschei Lang Lisansı 1.0: `LICENSE.tr.md` (İngilizcesi `LICENSE`). Fiyatlar
ve kişisel ile ticari kullanım arasındaki fark: `LICENSING.tr.md`.

English: `README.md`
