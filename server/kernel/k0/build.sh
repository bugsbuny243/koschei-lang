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
# Independent QEMU-only proof: CPU NX instruction-fetch fault (P=1, I/D=1).
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -DKOSCHEI_QEMU_TEST=1 -DKOSCHEI_QEMU_NX_TEST=1 \
  -c "$SOURCE" -o "$OUT/koschei-k0-qemu-nx.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/BOOTX64-NX.EFI" "$OUT/koschei-k0-qemu-nx.obj"
# Experimental four-level high-half 4KiB writable NX mapping, guest only.
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -DKOSCHEI_QEMU_TEST=1 -DKOSCHEI_QEMU_MAPPED_TEST=1 \
  -c "$SOURCE" -o "$OUT/koschei-k0-qemu-mapped.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/BOOTX64-MAPPED.EFI" "$OUT/koschei-k0-qemu-mapped.obj"
# A fifth isolated QEMU-only EFI writes to its own actual PE .text
# under CR0.WP and must receive CPU #PF error=3.
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -DKOSCHEI_QEMU_TEST=1 -DKOSCHEI_QEMU_WX_TEST=1 \
  -c "$SOURCE" -o "$OUT/koschei-k0-qemu-wx.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/BOOTX64-WX.EFI" "$OUT/koschei-k0-qemu-wx.obj"
# Independent QEMU-only proof: instruction fetch from actual PE .bss
# must fault with CPU hardware #PF=17 after installing image RX/RW+NX.
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -DKOSCHEI_QEMU_TEST=1 -DKOSCHEI_QEMU_DATA_NX_TEST=1 \
  -c "$SOURCE" -o "$OUT/koschei-k0-qemu-data-nx.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/BOOTX64-DATA-NX.EFI" "$OUT/koschei-k0-qemu-data-nx.obj"
# Seventh guest proof: reject an unowned lower-1GiB identity slot
# with a real CPU present=0 #PF after installing our limited CR3.
"$CC" -target x86_64-pc-windows-msvc -ffreestanding -fno-stack-protector \
  -fno-builtin -mno-red-zone -fshort-wchar -Wall -Wextra -Werror -O2 \
  -DKOSCHEI_QEMU_TEST=1 -DKOSCHEI_QEMU_LOW_HOLE_TEST=1 \
  -c "$SOURCE" -o "$OUT/koschei-k0-qemu-low-hole.obj"
"$LINK" /subsystem:efi_application /entry:efi_main /nodefaultlib \
  /machine:x64 "/out:$OUT/BOOTX64-LOW-HOLE.EFI" "$OUT/koschei-k0-qemu-low-hole.obj"
sha256sum "$OUT/koschei-k0-release.efi" "$OUT/BOOTX64.EFI" \
  "$OUT/BOOTX64-RO.EFI" "$OUT/BOOTX64-NX.EFI" \
  "$OUT/BOOTX64-MAPPED.EFI" "$OUT/BOOTX64-WX.EFI" \
  "$OUT/BOOTX64-DATA-NX.EFI" "$OUT/BOOTX64-LOW-HOLE.EFI" > "$OUT/SHA256SUMS"
python3 "$ROOT/server/kernel/k0/verify_pe.py" "$OUT/koschei-k0-release.efi" "$OUT/BOOTX64.EFI" \
  "$OUT/BOOTX64-RO.EFI" "$OUT/BOOTX64-NX.EFI" \
  "$OUT/BOOTX64-MAPPED.EFI" "$OUT/BOOTX64-WX.EFI" \
  "$OUT/BOOTX64-DATA-NX.EFI" "$OUT/BOOTX64-LOW-HOLE.EFI"
echo "KOSCHEI-K0 BUILD/1 OK"
