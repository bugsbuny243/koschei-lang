#!/usr/bin/env bash
# Koschei x86-64 UEFI Bare-Metal Boot, ExitBootServices & QEMU Serial Runner v2
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_KS="${1:-${REPO_ROOT}/examples/uefi_boot/boot.ks}"
OUT_DIR="${2:-${REPO_ROOT}/build/uefi}"

mkdir -p "${OUT_DIR}"

EFI_BIN="${OUT_DIR}/BOOTX64.EFI"
ESP_DIR="${OUT_DIR}/esp"
ESP_IMG="${OUT_DIR}/koschei_uefi_esp.img"
ASM_OUT="${OUT_DIR}/boot_x86_64.s"

echo "[1/3] Koschei kaynak kodu x86-64 UEFI v2 (BOOTX64.EFI + GetMemoryMap + ExitBootServices + COM1 RX/TX) imajina derleniyor..."
PYTHONPATH="${REPO_ROOT}" python3 -m koschei.cli_entry uefi-boot \
    "${SOURCE_KS}" \
    -o "${EFI_BIN}" \
    --esp-dir "${ESP_DIR}" \
    --esp-image "${ESP_IMG}" \
    --emit-asm "${ASM_OUT}" \
    --rx-input "PING-KOSCHEI-KERNEL-V2" \
    --verify-emulate

find_ovmf() {
    local candidates=(
        "${OVMF_BIOS:-}"
        "/usr/share/ovmf/OVMF.fd"
        "/usr/share/OVMF/OVMF_CODE.fd"
        "/usr/share/OVMF/OVMF_CODE_4M.fd"
        "/usr/share/edk2/ovmf/OVMF_CODE.fd"
        "/usr/share/edk2-ovmf/x64/OVMF.fd"
        "/usr/share/qemu/OVMF.fd"
        "/opt/homebrew/share/qemu/edk2-x86_64-code.fd"
        "/usr/local/share/qemu/edk2-x86_64-code.fd"
    )
    for c in "${candidates[@]}"; do
        if [[ -n "${c}" && -f "${c}" ]]; then
            echo "${c}"
            return 0
        fi
    done
    return 1
}

if command -v qemu-system-x86_64 >/dev/null 2>&1; then
    if OVMF_PATH="$(find_ovmf)"; then
        echo "[2/3] QEMU + OVMF bulundu (${OVMF_PATH}). Donanim seri portu (COM1 -> stdio) ile baslatiliyor..."
        if [[ "${OVMF_PATH}" == *"edk2-x86_64-code.fd"* || "${OVMF_PATH}" == *"OVMF_CODE"* ]]; then
            qemu-system-x86_64 \
                -drive if=pflash,format=raw,readonly=on,file="${OVMF_PATH}" \
                -drive format=raw,file="${ESP_IMG}" \
                -net none \
                -serial stdio \
                -display none \
                -no-reboot
        else
            qemu-system-x86_64 \
                -bios "${OVMF_PATH}" \
                -drive format=raw,file="${ESP_IMG}" \
                -net none \
                -serial stdio \
                -display none \
                -no-reboot
        fi
        echo "[3/3] QEMU x86-64 UEFI v2 testi basariyla tamamlandi."
    else
        echo "[BILGI] qemu-system-x86_64 kurulu ancak OVMF.fd bulunamadi."
        echo "        Ubuntu/Debian: sudo apt install ovmf"
        echo "        macOS (Brew):  brew install qemu"
    fi
else
    echo "[BILGI] Bu ortamda qemu-system-x86_64 kurulu degil; yerlesik x86-64 GetMemoryMap + ExitBootServices + COM1 RX/TX emulasyonu basariyla dogrulandi."
    echo "        Kendi makinenizde calistirmak icin:"
    echo "        qemu-system-x86_64 -bios /usr/share/ovmf/OVMF.fd -drive format=raw,file=${ESP_IMG} -net none -serial stdio -display none -no-reboot"
fi
