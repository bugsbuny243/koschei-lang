#!/usr/bin/env bash
set -euo pipefail
# Real QEMU/OVMF boot evidence; no guest Windows/Linux/container kernel.
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$1"
IMAGE="$OUT/koschei-k0-fat.img"
SERIAL="$OUT/koschei-k0-serial.log"
QLOG="$OUT/koschei-k0-qemu.log"
truncate -s 64M "$IMAGE"
mkfs.vfat -F 32 -n KOSCHEIK0 "$IMAGE" >/dev/null
mmd -i "$IMAGE" ::/EFI
mmd -i "$IMAGE" ::/EFI/BOOT
mcopy -i "$IMAGE" "$OUT/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI

OVMF=""
for candidate in \
  /usr/share/OVMF/OVMF_CODE_4M.fd \
  /usr/share/OVMF/OVMF_CODE.fd \
  /usr/share/ovmf/OVMF.fd
do
    if test -f "$candidate"; then OVMF="$candidate"; break; fi
done
if test -z "$OVMF"; then echo "KOSCHEI-K0 FAIL no OVMF firmware" >&2; exit 1; fi

# Successful QEMU isa-debug-exit value 0x10 gives process exit status 33.
# Never count a timeout (124), emulator failure, or a printed string alone as PASS.
set +e
timeout 60 qemu-system-x86_64 \
  -machine q35 -m 256 -cpu qemu64 \
  -bios "$OVMF" \
  -drive "if=none,id=usbdisk,file=$IMAGE,format=raw" \
  -device qemu-xhci \
  -device usb-storage,drive=usbdisk,bootindex=1 \
  -device isa-debug-exit,iobase=0xf4,iosize=0x04 \
  -display none -monitor none \
  -serial "file:$SERIAL" \
  -no-reboot -net none >"$QLOG" 2>&1
STATUS=$?
set -e
echo "KOSCHEI-K0 QEMU/1 exit=$STATUS"
if test "$STATUS" -ne 33; then
  cat "$QLOG" >&2
  if test -f "$SERIAL"; then tail -60 "$SERIAL" >&2; fi
  exit 1
fi
python3 "$ROOT/server/kernel/k0/verify_serial.py" "$SERIAL"
sha256sum "$SERIAL" > "$OUT/SERIAL-SHA256"
echo "KOSCHEI-K0 QEMU/1 PASS"
