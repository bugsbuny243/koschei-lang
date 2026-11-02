#ifndef KOSCHEI_K0_PAGING_MODEL_H
#define KOSCHEI_K0_PAGING_MODEL_H
/*
 * K0.4 host-testable FOUR-LEVEL PAGE TABLE DATA MODEL, NOT CPU TABLES.
 * Logical arrays below are NOT installed at their claimed physical addresses:
 * no CR3, IDT, CPU policy, executing stack mapping, or isolation proof.
 *
 * Only one 2 MiB virtual region / PT is supported. All four model table
 * frames must be independently claimed in the K0.3 16-page pool, distinct
 * from each other and every mapped data frame. Real hardware activation is
 * a separate fail-closed acceptance step.
 */
#include "paging_contract.h"
#define K0_VM_TABLE_LEVELS 4U
#define K0_VM_ENTRIES_PER_TABLE 512U

typedef struct {
    K_U64 table_phys[K0_VM_TABLE_LEVELS]; /* order: PML4, PDPT, PD, PT */
    K_U64 entries[K0_VM_TABLE_LEVELS][K0_VM_ENTRIES_PER_TABLE];
    K_U32 initialized;
    K_U64 pool_epoch; /* snapshot used by later model-only access walks */
} K0_VM_TABLE_MODEL;

static K_U32 k0_vm_level_index(K_U64 virtual_page, K_U32 shift) {
    return (K_U32)((virtual_page >> shift) & 511ULL);
}

/* Failure is transactional: output is never written until all preflight
 * checks pass. No live paging memory is read or written by this function.
 */
static int k0_vm_tables_build(K0_VM_TABLE_MODEL *out, const K0_VM_PLAN *plan,
                              const K0_PAGE_POOL *pool, const K_U64 frame[4]) {
    if (!out || out->initialized || !plan || !plan->initialized ||
        !plan->count || plan->count > K0_VM_MAX_LEAVES || !pool || !frame ||
        !pool->epoch || plan->pool_epoch != pool->epoch)
        return 0;
    for (K_U32 i = 0; i < K0_VM_TABLE_LEVELS; ++i) {
        if ((frame[i] & (K0_PAGE_SIZE - 1)) ||
            (frame[i] & ~K0_VM_PHYSICAL_MASK) ||
            !k0_pool_is_claimed(pool, frame[i])) return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (frame[i] == frame[j]) return 0;
    }
    K_U64 region = plan->leaves[0].virtual_page >> 21;
    for (K_U32 i = 0; i < plan->count; ++i) {
        const K0_VM_LEAF *p = &plan->leaves[i];
        if (!k0_vm_high_canonical_page(p->virtual_page) ||
            p->virtual_page >> 21 != region ||
            (p->physical_page & (K0_PAGE_SIZE - 1)) ||
            (p->physical_page & ~K0_VM_PHYSICAL_MASK) ||
            !k0_pool_is_claimed(pool, p->physical_page) ||
            (p->leaf_entry & K0_VM_PRESENT) == 0 ||
            (p->leaf_entry & 4ULL) != 0 || /* US must remain zero */
            (p->leaf_entry & ~(K0_VM_PHYSICAL_MASK | K0_VM_PRESENT |
                                K0_VM_WRITE | K0_VM_NO_EXECUTE)) != 0 ||
            (p->leaf_entry & K0_VM_PHYSICAL_MASK) != p->physical_page ||
            ((p->leaf_entry & K0_VM_WRITE) &&
             !(p->leaf_entry & K0_VM_NO_EXECUTE))) return 0;
        for (K_U32 f = 0; f < K0_VM_TABLE_LEVELS; ++f)
            if (p->physical_page == frame[f]) return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (p->virtual_page == plan->leaves[j].virtual_page ||
                p->physical_page == plan->leaves[j].physical_page) return 0;
    }
    for (K_U32 i = 0; i < K0_VM_TABLE_LEVELS; ++i) {
        out->table_phys[i] = frame[i];
        for (K_U32 j = 0; j < K0_VM_ENTRIES_PER_TABLE; ++j)
            out->entries[i][j] = 0;
    }
    const K_U64 v = plan->leaves[0].virtual_page;
    out->entries[0][k0_vm_level_index(v, 39)] = frame[1] | K0_VM_PRESENT | K0_VM_WRITE;
    out->entries[1][k0_vm_level_index(v, 30)] = frame[2] | K0_VM_PRESENT | K0_VM_WRITE;
    out->entries[2][k0_vm_level_index(v, 21)] = frame[3] | K0_VM_PRESENT | K0_VM_WRITE;
    for (K_U32 i = 0; i < plan->count; ++i)
        out->entries[3][k0_vm_level_index(plan->leaves[i].virtual_page, 12)] =
            plan->leaves[i].leaf_entry;
    out->pool_epoch = pool->epoch;
    out->initialized = 1;
    return 1;
}
#endif
