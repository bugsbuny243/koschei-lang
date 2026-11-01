#!/usr/bin/env bash
set -euo pipefail
# Real QEMU/OVMF boot evidence; no guest Windows/Linux/container kernel.
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$1"
MODE="${2:-missing}"
case "$MODE" in
  missing)
    BOOT_BINARY="$OUT/BOOTX64.EFI"
    SUFFIX=""
    ;;
  ro)
    BOOT_BINARY="$OUT/BOOTX64-RO.EFI"
    SUFFIX="-ro"
    ;;
  nx)
    BOOT_BINARY="$OUT/BOOTX64-NX.EFI"
    SUFFIX="-nx"
    ;;
  mapped)
    BOOT_BINARY="$OUT/BOOTX64-MAPPED.EFI"
    SUFFIX="-mapped"
    ;;
  codewx)
    BOOT_BINARY="$OUT/BOOTX64-CODEWX.EFI"
    SUFFIX="-codewx"
    ;;
  *)
    echo "KOSCHEI-K0 FAIL unknown QEMU scenario" >&2
    exit 1
    ;;
esac
IMAGE="$OUT/koschei-k0-fat${SUFFIX}.img"
SERIAL="$OUT/koschei-k0-serial${SUFFIX}.log"
QLOG="$OUT/koschei-k0-qemu${SUFFIX}.log"
truncate -s 64M "$IMAGE"
mkfs.vfat -F 32 -n KOSCHEIK0 "$IMAGE" >/dev/null
mmd -i "$IMAGE" ::/EFI
mmd -i "$IMAGE" ::/EFI/BOOT
mcopy -i "$IMAGE" "$BOOT_BINARY" ::/EFI/BOOT/BOOTX64.EFI

OVMF=""
for candidate in \
  /usr/share/OVMF/OVMF_CODE_4M.fd \
  /usr/share/OVMF/OVMF_CODE.fd \
  /usr/share/ovmf/OVMF.fd
do
    if test -f "$candidate"; then OVMF="$candidate"; break; fi
done
if test -z "$OVMF"; then echo "KOSCHEI-K0 FAIL no OVMF firmware" >&2; exit 1; fi
# OVMF 4M images must be attached as pflash, not -bios (QEMU BIOS ROM
# has a smaller size limit). Give the guest its own disposable variable store.
case "$OVMF" in
  */OVMF_CODE_4M.fd) VARS="/usr/share/OVMF/OVMF_VARS_4M.fd" ;;
  */OVMF_CODE.fd) VARS="/usr/share/OVMF/OVMF_VARS.fd" ;;
  *) echo "KOSCHEI-K0 FAIL unsupported OVMF image layout" >&2; exit 1 ;;
esac
test -f "$VARS" || { echo "KOSCHEI-K0 FAIL OVMF variable store missing" >&2; exit 1; }
cp "$VARS" "$OUT/koschei-k0-vars${SUFFIX}.fd"

# Successful QEMU isa-debug-exit value 0x10 gives process exit status 33.
# Never count a timeout (124), emulator failure, or a printed string alone as PASS.
set +e
timeout 60 qemu-system-x86_64 \
  -machine q35 -m 256 -cpu qemu64 \
  -drive "if=pflash,format=raw,readonly=on,file=$OVMF" \
  -drive "if=pflash,format=raw,file=$OUT/koschei-k0-vars${SUFFIX}.fd" \
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
python3 "$ROOT/server/kernel/k0/verify_serial.py" "$SERIAL" "$MODE"
sha256sum "$SERIAL" > "$OUT/SERIAL${SUFFIX}-SHA256"
echo "KOSCHEI-K0 QEMU/1 PASS mode=$MODE"
