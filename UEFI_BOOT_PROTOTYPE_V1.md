# Koschei x86-64 UEFI Önyükleme ve Donanım Seri Port Sürücüsü v1

Durum: **Çalışan Prototip (`koschei/uefi_boot_v1.py`, `ks uefi-boot`)**

Bu prototip, başka hiçbir işletim sistemi (Linux, Windows veya macOS) yüklenmeden doğrudan **x86-64 UEFI (`BOOTX64.EFI`)** uygulaması olarak açılan ve donanımdaki **16550 UART (`COM1 / 0x3F8`)** seri port denetleyicisine doğrudan x86-64 `out dx, al` / `in al, dx` buyruklarıyla yazan ilk Koschei bare-metal (yalın donanım) önyükleme katmanıdır.

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
5. **Deterministik PE32+ ve FAT16 ESP İmajı:** Haricî C derleyicisi veya `root`/`mount` yetkisi gerektirmeden doğrudan `BOOTX64.EFI` ve 4 MiB boyutunda önyüklenebilir `koschei_uefi_esp.img` üretilir.

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
```
