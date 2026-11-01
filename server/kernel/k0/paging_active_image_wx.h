#ifndef KOSCHEI_K0_ACTIVE_IMAGE_WX_H
#define KOSCHEI_K0_ACTIVE_IMAGE_WX_H
/*
 * QEMU-only executable-image identity mapping. Substitutes real 4KiB
 * page tables for the 2MiB huge PDE(s) overlapping the firmware-loaded PE.
 * Code: supervisor RX; data/headers: supervisor RW+NX; readonly: RO+NX.
 * Holes within the PE image are non-present. Identity pages *outside*
 * the image remain supervisor RW+NX, so this is not process isolation.
 *
 * Requires CPU EFER.NXE and CR0.WP preflight before active CR3.
 * The caller must pin both PT frames; never release active page tables.
 */
#include "uefi_loaded_image_preflight.h"

#define K0_IMAGE_WX_PTE_NX (1ULL << 63)
#define K0_IMAGE_WX_PDE_SIZE (2ULL * 1024ULL * 1024ULL)
#define K0_IMAGE_WX_PT_COUNT 2U
#define K0_IMAGE_WX_MAX_CODE_HINTS 16U

static int k0_image_wx_in_rx(const K0_LOADED_IMAGE_BOUNDS *image,
                             const K0_PE_WX_LAYOUT *layout, K_U64 address) {
    if (address < image->base || address - image->base >= image->size)
        return 0;
    return layout->pages[(address-image->base)/K0_PAGE_SIZE] ==
           K0_PE_WX_CODE_RX;
}

static int k0_image_wx_preflight(const K0_LOADED_IMAGE_BOUNDS *image,
                                const K0_PE_WX_LAYOUT *layout,
                                const K_U64 *code, K_U32 code_count,
                                K_U64 stack, K_U64 idt,
                                const K_U64 *frames) {
    if (!image || !layout || !code || !frames ||
        !code_count || code_count > K0_IMAGE_WX_MAX_CODE_HINTS ||
        !k0_pe_wx_identity_range(image->base, layout) ||
        image->size != layout->image_size ||
        !image->entry || !k0_image_wx_in_rx(image, layout, image->entry) ||
        !stack || !idt || stack >= 0x40000000ULL ||
        idt >= 0x40000000ULL)
        return 0;
    K_U64 first = image->base >> 21;
    K_U64 last = (image->base + image->size - 1ULL) >> 21;
    if (last >= 511ULL || last-first >= K0_IMAGE_WX_PT_COUNT)
        return 0;
    for (K_U32 i = 0; i < code_count; ++i)
        if (!k0_image_wx_in_rx(image, layout, code[i])) return 0;
    for (K_U32 i = 0; i < K0_IMAGE_WX_PT_COUNT; ++i) {
        if (!frames[i] || (frames[i] & (K0_PAGE_SIZE - 1ULL)) ||
            frames[i] >= 0x40000000ULL ||
            (frames[i] >= image->base &&
             frames[i] - image->base < image->size))
            return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (frames[i] == frames[j]) return 0;
    }
    /* Stack and live IDT must remain writable and non-executable. */
    K_U64 special[] = {stack, idt};
    for (K_U32 i = 0; i < 2; ++i)
        if (special[i] >= image->base &&
            special[i]-image->base < image->size &&
            layout->pages[(special[i]-image->base)/K0_PAGE_SIZE] !=
                K0_PE_WX_DATA_RW_NX &&
            layout->pages[(special[i]-image->base)/K0_PAGE_SIZE] !=
                K0_PE_WX_HEADERS_RW_NX)
            return 0;
    return 1;
}

static int k0_image_wx_activate_tables(volatile K_U64 *pd,
                                        const K0_LOADED_IMAGE_BOUNDS *image,
                                        const K0_PE_WX_LAYOUT *layout,
                                        const K_U64 *code, K_U32 code_count,
                                        K_U64 stack, K_U64 idt,
                                        const K_U64 *frames) {
    if (!pd || !k0_image_wx_preflight(image, layout, code, code_count,
                                      stack, idt, frames))
        return 0;
    K_U64 first = image->base >> 21;
    K_U64 last = (image->base+image->size-1ULL) >> 21;
    for (K_U64 slot = first; slot <= last; ++slot)
        if ((pd[slot] & ~K0_IMAGE_WX_PTE_NX) !=
            ((slot << 21) | 0x83ULL))
            return 0;
    /* All slots and page frames are checked before table publication. */
    for (K_U64 slot = first; slot <= last; ++slot) {
        volatile K_U64 *pt =
            (volatile K_U64 *)(unsigned long long)frames[slot-first];
        for (K_U32 i = 0; i < 512; ++i) {
            K_U64 physical = (slot << 21) + (K_U64)i*K0_PAGE_SIZE;
            K_U64 entry = physical | 3ULL | K0_IMAGE_WX_PTE_NX;
            if (physical >= image->base &&
                physical-image->base < image->size) {
                switch (layout->pages[(physical-image->base)/K0_PAGE_SIZE]) {
                case K0_PE_WX_CODE_RX:
                    entry = physical | 1ULL;
                    break;
                case K0_PE_WX_READ_RO_NX:
                    entry = physical | 1ULL | K0_IMAGE_WX_PTE_NX;
                    break;
                case K0_PE_WX_DATA_RW_NX:
                case K0_PE_WX_HEADERS_RW_NX:
                    break;
                default:
                    entry = 0; /* PE gap is not present */
                    break;
                }
            }
            pt[i] = entry;
        }
    }
    for (K_U64 slot = first; slot <= last; ++slot)
        pd[slot] = frames[slot-first] | 3ULL;
    /* Fail closed if *any* 2MiB writable+executable PDE remains.
     * All executable mappings are now RX 4KiB leaves in the PE windows.
     */
    for (K_U32 slot = 0; slot < 512; ++slot)
        if ((pd[slot] & 0x80ULL) &&
            !(pd[slot] & K0_IMAGE_WX_PTE_NX))
            return 0;
    return 1;
}
#endif
