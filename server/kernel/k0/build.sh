#!/usr/bin/env bash
set -euo pipefail
# Only the BUILD HOST runs tools. Customer UEFI image does NOT.
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$1"
CC="clang"
LINK="lld-link"
mkdir -p "$OUT"
SOURCE="$ROOT/server/kernel/k0/uefi_main.c"
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -c "$SOURCE" -o "$OUT/koschei-k0-release.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/koschei-k0-release.efi" "$OUT/koschei-k0-release.obj"
# QEMU-only exit device is not compiled into the release artifact.
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -DKOSCHEI_QEMU_TEST=1 -c "$SOURCE" -o "$OUT/koschei-k0-qemu.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/BOOTX64.EFI" "$OUT/koschei-k0-qemu.obj"
# Independent QEMU-only proof: supervisor write to a present read-only PDE.
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -DKOSCHEI_QEMU_TEST=1 -DKOSCHEI_QEMU_READONLY_TEST=1 \
  -c "$SOURCE" -o "$OUT/koschei-k0-qemu-ro.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/BOOTX64-RO.EFI" "$OUT/koschei-k0-qemu-ro.obj"
sha256sum "$OUT/koschei-k0-release.efi" "$OUT/BOOTX64.EFI" \
  "$OUT/BOOTX64-RO.EFI" > "$OUT/SHA256SUMS"
python3 "$ROOT/server/kernel/k0/verify_pe.py" "$OUT/koschei-k0-release.efi" "$OUT/BOOTX64.EFI" "$OUT/BOOTX64-RO.EFI"
echo "KOSCHEI-K0 BUILD/1 OK"
