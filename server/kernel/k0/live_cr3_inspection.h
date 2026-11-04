#ifndef KOSCHEI_K0_LIVE_CR3_INSPECTION_H
#define KOSCHEI_K0_LIVE_CR3_INSPECTION_H
/*
 * Read-only x86-64 four-level CR3 TABLE-BYTE inspection, not owned paging.
 * A caller-supplied reader must independently establish that a table frame
 * is readable. QEMU may use the *firmware's* identity mapping to read the
 * physical bytes. Model results are never an independent CPU translation
 * attestation or a safe permission proof for a replacement CR3.
 */
#include "memory_map.h"

#define K0_CR3_I_PRESENT 1ULL
#define K0_CR3_I_RW (1ULL << 1)
#define K0_CR3_I_USER (1ULL << 2)
#define K0_CR3_I_PS (1ULL << 7)
#define K0_CR3_I_NX (1ULL << 63)
#define K0_CR3_I_ADDR_4K 0x000ffffffffff000ULL
#define K0_CR3_I_ADDR_2M 0x000fffffffe00000ULL
#define K0_CR3_I_ADDR_1G 0x000fffffc0000000ULL
#define K0_CR3_I_MAX_STEPS 4U

typedef int (*K0_CR3_I_READ)(void *context, K_U64 page, K_U32 slot,
                              K_U64 *entry);

typedef struct {
    K_U64 virtual_address;
    K_U64 physical_address;
    K_U64 root_cr3;
    K_U32 levels_read;
    K_U32 leaf_page_shift; /* exactly 12, 21 or 30 */
    K_U32 effective_user;
    K_U32 effective_write;
    K_U32 effective_nx;
} K0_CR3_I_RESULT;

static int k0_cr3_i_canonical48(K_U64 a) {
    return (a >> 48) == ((a & (1ULL << 47)) ? 0xffffULL : 0ULL);
}

static int k0_cr3_inspect_translation(K_U64 cr3, K_U64 virtual_address,
                                       K0_CR3_I_READ read,
                                       void *context, K0_CR3_I_RESULT *out) {
    if (!read || !out || !cr3 || (cr3 & 4095ULL) ||
        (cr3 & ~K0_CR3_I_ADDR_4K) ||
        !k0_cr3_i_canonical48(virtual_address)) return 0;
    K0_CR3_I_RESULT next = {0};
    next.virtual_address = virtual_address;
    next.root_cr3 = cr3;
    K_U64 table = cr3;
    const K_U32 shifts[] = {39U, 30U, 21U, 12U};
    K_U32 user = 1, write = 1, nx = 0;
    for (K_U32 level = 0; level < K0_CR3_I_MAX_STEPS; ++level) {
        K_U64 entry = 0;
        K_U32 slot = (K_U32)((virtual_address >> shifts[level]) & 511ULL);
        if (!read(context, table, slot, &entry) ||
            !(entry & K0_CR3_I_PRESENT))
            return 0;
        ++next.levels_read;
        user &= (entry & K0_CR3_I_USER) != 0;
        write &= (entry & K0_CR3_I_RW) != 0;
        nx |= (entry & K0_CR3_I_NX) != 0;
        /* PML4E is never a large-page leaf. Bit 7 is PS in PDPT/PD. */
        if (level == 0 && (entry & K0_CR3_I_PS)) return 0;
        K_U32 page_shift = shifts[level];
        if (level == 3 || (level >= 1 && (entry & K0_CR3_I_PS))) {
            K_U64 mask = page_shift == 30 ? K0_CR3_I_ADDR_1G :
                           page_shift == 21 ? K0_CR3_I_ADDR_2M :
                                              K0_CR3_I_ADDR_4K;
            /* Large-page 4 KiB address slot 12 is PAT, not address;
             * bits 13..20 (2MiB) or 13..29 (1GiB) are reserved.
             */
            if (page_shift > 12 &&
                (entry & ((1ULL << page_shift) - 1ULL) &
                 ~((1ULL << 13) - 1ULL))) return 0;
            next.physical_address = (entry & mask) |
                (virtual_address & ((1ULL << page_shift) - 1ULL));
            next.leaf_page_shift = page_shift;
            next.effective_user = user;
            next.effective_write = write;
            next.effective_nx = nx;
            *out = next;
            return 1;
        }
        table = entry & K0_CR3_I_ADDR_4K;
        if (!table) return 0;
    }
    return 0;
}
#endif
