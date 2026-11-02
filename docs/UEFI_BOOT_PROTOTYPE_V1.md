# Koschei x86-64 UEFI Önyükleme ve Donanım Seri Port Sürücüsü v1

Durum: **Gerçek QEMU/OVMF'de açılan prototip (`koschei/uefi_boot_v1.py`, `ks uefi-boot`)**.
Kanıt: `tests/test_uefi_boot_qemu_v1.py` ve `.github/workflows/koschei-uefi-prototype-qemu.yml`.
Bu, Koschei derleyicisinin mühürlü MIR'den doğrudan `BOOTX64.EFI` üreten yoludur;
asıl çekirdek çalışması `server/kernel/k0/` altındadır ve bu prototip onun
iddialarını genişletmez.

Bu prototip, başka hiçbir işletim sistemi (Linux, Windows veya macOS) yüklenmeden doğrudan **x86-64 UEFI (`BOOTX64.EFI`)** uygulaması olarak açılan ve donanımdaki **16550 UART (`COM1 / 0x3F8`)** seri port denetleyicisine doğrudan x86-64 `out dx, al` / `in al, dx` buyruklarıyla yazan ilk Koschei bare-metal (yalın donanım) önyükleme katmanıdır.

## 0. Gerçek QEMU'da ölçülen (2026-11-02, QEMU q35 + OVMF 4M, TCG)

Her satırdaki onaltılık değerler çalışma anında okunur; hiçbiri sabit metin değildir.

```text
[KOSCHEI-KERNEL-V2] ExitBootServices=OK attempt=0x0000000000000001 memory_map_bytes=0x00000000000017d0 descriptor_bytes=0x0000000000000030
[KOSCHEI-KERNEL-V3] gdt=loaded cs=0x08 ds=es=fs=gs=ss=0x10 idt=32_gates(0-31 -> fail-closed trap) image_text=0x000000000dfe6000
[KOSCHEI-KERNEL-V4] paging=firmware_identity own_page_tables=none
[KOSCHEI-KERNEL-V5] pic_8259=remapped_0x20_0x28_all_masked pit_8254=programmed_divisor_1193 interrupts=disabled tsc=0x000000016f50b558 epoch=2
[KOSCHEI-SHELL] ready: STATUS, MEM, MIR, EPOCH, TRAP, HALT
```

- **Hafıza haritası 6096 bayt.** İlk yüklenen sürüm 4096 baytlık tek bir tamponla
  `GetMemoryMap` çağırıyor, `EFI_BUFFER_TOO_SMALL` gelince sessizce vazgeçiyordu;
  bu yüzden gerçek firmware'de ExitBootServices'e hiç varılmıyordu. Tampon artık
  32 KiB'dır; yetmezse firmware'in istediği boyut ve durum kodu yazılır ve durum
  firmware'e döndürülür. Tek parça `OVMF.fd` ile harita 6000 bayt geldi.
- **Kod `0x0dfe6000`'e yüklendi**, bağlantı adresi `0x140001000`'e değil.
- **`TRAP` komutu** `ud2` çalıştırır. QEMU günlüğü `#UD`'nin (vektör 6) `CS=0x0008`,
  `SS=0x0010` ile Koschei IDT'sinden teslim edildiğini, Koschei hata yakalayıcısının
  da mesajını bastığını gösterir: GDT, IDT ve yeniden yüklenen CS gerçek işlemci
  modelinde çalışır.
- İlk sürümde aynı satırların iki kez görünmesi yeniden başlatma değildi: OVMF,
  `ConOut` çıktısını aynı seri porta da yansıtır.

### Sınırlar

- Sayfalama firmware'in kimlik eşlemesidir; Koschei'nin kendi sayfa tablosu,
  W^X'i veya bellek yalıtımı **yoktur**.
- `--experimental-page-tables` eski sayfa tablosu kodunu ekler. Yalnızca iki
  bağlantı adresi sayfasını eşler; çalışan kodu, yığını ve IDT'yi eşlemez. Gerçek
  QEMU'da `mov cr3` sonrası **triple fault** olur ve başarı satırı basılmaz; bu yol
  yalnızca deney içindir.
- ExitBootServices'ten sonra görüntü firmware'e dönmez, durur (`--halt-mode`
  yalnızca `--no-exit-boot-services` ile geçerlidir).
- Kanıt QEMU'dandır (TCG); fiziksel bir makinede açılış kanıtı değildir. Kesme
  denetleyicisi, zamanlayıcı kesmesi, zamanlayıcı, depolama ve ağ yoktur.

## 1. Mimari ve Anayasal Kurallar

1. **Ortamdan Gelen İşletim Sistemi Yetkisi Yok (`KS4010`):** Bare-metal UEFI hedefinde host işletim sistemi yetkileri (`net`, `disk`, `env`, `process`, `serve`, `persist`, `input`, `clock`, `random`) derleme aşamasında `KS4010` ile reddedilir.
2. **Mühürlü MIR Zorunluluğu:** Yalnızca tip denetiminden, yetki denetiminden ve `require_mir` mühürlemesinden geçmiş `MirGraph` nesneleri `BOOTX64.EFI` ikilisine dönüştürülebilir.
3. **16550 UART Donanım Sürücüsü (`COM1 = 0x3F8`):**
   - `0x3F9` (`IER = 0x00`): Tüm UART kesmelerini kapatır.
   - `0x3FB` (`LCR = 0x80`): Baud hızı bölen kilidini (`DLAB`) açar.
   - `0x3F8` (`DLL = 0x01`) ve `0x3F9` (`DLM = 0x00`): 115200 baud hızını ayarlar.
   - `0x3FB` (`LCR = 0x03`): `8N1` (8 veri biti, eşlik yok, 1 durdurma biti) çerçevelemesini seçer.
   - `0x3FA` (`FCR = 0xC7`): FIFO tamponlarını etkinleştirir ve temizler (14 bayt eşiği).
   - `0x3FC` (`MCR = 0x0B`): `RTS/DSR` sinyallerini hazır konuma getirir.
   - Her bayt gönderiminden önce `0x3FD` (`LSR`) yazmacının 5. bitini (`0x20` — *Transmit Holding Register Empty*) `in al, dx; test al, 0x20; jz` döngüsüyle yoklar ve hazır olduğunda `0x3F8` (`THR`) portuna `out dx, al` ile yazar.
4. **Çift Çıkış (COM1 + UEFI `ConOut`):** Seri portun yanı sıra `EFI_SYSTEM_TABLE->ConOut->OutputString` (ofset `0x40` -> `0x08`) üzerinden UTF-16LE akışı da yazılarak hem `-serial stdio` hem de grafiksel UEFI ekranında aynı çıktının görünmesi sağlanır.
5. **Deterministik PE32+ ve FAT16 ESP İmajı:** Haricî C derleyicisi veya `root`/`mount` yetkisi gerektirmeden doğrudan `BOOTX64.EFI` ve 4 MiB boyutunda önyüklenebilir `koschei_uefi_esp.img` üretilir. FAT türünü yalnızca küme sayısı belirler: ilk sürümdeki 2031 küme FAT12 sayıldığı için OVMF imajı okuyamıyordu; imaj artık 8095 kümeyle gerçek FAT16'dır ve `fsck.fat` temiz çıkar.
6. **ExitBootServices:** `GetMemoryMap` ve `ExitBootServices`, UEFI kuralına uygun olarak yeni bir harita anahtarıyla bir kez yeniden denenir. Çıkış girişiminden önceki bir hata firmware'e döndürülür; çıkış girişiminden sonraki bir hatada önyükleme servisleri yarı kapanmış olabileceği için görüntü durur.
7. **GDT ve IDT:** Kendi GDT'si yüklenir; `ds/es/fs/gs/ss=0x10` ve uzak dönüşle (`retfq`) `cs=0x08` yeniden yüklenir. Tanımlayıcıların "accessed" biti önceden ayarlıdır, işlemci salt okunur `.rdata`'ya yazmaz. 32 kapılı IDT her istisnayı seri porta yazıp duran yakalayıcıya bağlar.
8. **COM1 kabuğu:** Satır gelene kadar bekler; `STATUS`, `MEM`, `MIR`, `EPOCH`, `TRAP`, `HALT` komutlarına çalışma anında okunan değerlerle cevap verir, bilinmeyen komuta yardım yazar.

## 2. Hızlı Kullanım ve QEMU Testi

```bash
# 1. BOOTX64.EFI, ESP dizini ve önyüklenebilir FAT16 disk imajını üret ve yerleşik x86-64 emülatörüyle doğrula:
python3 -m koschei.cli_entry uefi-boot examples/uefi_boot/boot.ks \
    -o build/uefi/BOOTX64.EFI \
    --esp-dir build/uefi/esp \
    --esp-image build/uefi/koschei_uefi_esp.img \
    --emit-asm build/uefi/boot_x86_64.s \
    --verify-emulate

# 2. QEMU + OVMF ile doğrudan önyükleme (fiziksel bilgisayar gerektirmez):
qemu-system-x86_64 \
    -bios /usr/share/ovmf/OVMF.fd \
    -drive format=raw,file=build/uefi/koschei_uefi_esp.img \
    -net none \
    -serial stdio \
    -display none \
    -no-reboot
# Kabuk etkileşimlidir: STATUS, MEM, MIR, EPOCH, TRAP, HALT yazın; çıkış Ctrl-A X.

# 3. Otomatik gerçek QEMU kanıtı (QEMU ve OVMF kuruluysa):
python -m pytest -v tests/test_uefi_boot_qemu_v1.py
```

`tools/run_qemu_uefi_v1.sh` aynı adımları çalıştırır; bölünmüş `OVMF_CODE`
firmware'ini değişken deposuyla (`OVMF_VARS`) birlikte verir.

Kökte duran `BOOTX64.EFI`, `boot_x86_64.s` ve `cli_entry.py` ilk yüklemenin
dosyalarıdır ve olduğu gibi bırakılmıştır: `BOOTX64.EFI` düzeltmeden önceki
ikilidir (gerçek firmware'de hafıza haritası adımında kalır), `cli_entry.py`
paketteki `koschei/cli_entry.py`'nin eski kopyasıdır.
