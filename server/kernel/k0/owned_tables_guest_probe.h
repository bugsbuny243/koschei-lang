#ifndef KOSCHEI_K0_OWNED_TABLES_GUEST_PROBE_H
#define KOSCHEI_K0_OWNED_TABLES_GUEST_PROBE_H
/*
 * QEMU-only: materialize independent Koschei page-table bytes in six
 * claimed CONVENTIONAL physical frames, verify and erase all bytes.
 * Existing firmware CR3 and address translations remain active throughout.
 * No high-half VA access, mov %cr3, mapping installation, or isolation.
 *
 * On any rejection caller halts; never release potentially inconsistent
 * table frames while execution continues.
 */
#include "owned_tables_dryrun.h"

static K0_VM_PLAN k0_dryrun_plan;
static K0_VM_TABLE_MODEL k0_dryrun_tables;

typedef struct {
    K0_PAGE_POOL *pool;
    K_U64 frames[4];
} K0_OWNED_GUEST_READER;

static int k0_guest_read_claimed_table_entry(void *opaque, K_U64 page,
                                             K_U32 slot, K_U64 *out) {
    K0_OWNED_GUEST_READER *r = (K0_OWNED_GUEST_READER *)opaque;
    if (!r || !r->pool || !out || slot >= 512 ||
        (page & (K0_PAGE_SIZE - 1)) ||
        page > (256ULL * 1024ULL * 1024ULL - K0_PAGE_SIZE) ||
        !k0_pool_is_claimed(r->pool, page))
        return 0;
    for (K_U32 i = 0; i < 4; ++i) {
        if (page == r->frames[i]) {
            const volatile K_U64 *entries =
                (const volatile K_U64 *)(unsigned long long)page;
            *out = entries[slot]; /* firmware identity map, never own CR3 */
            return 1;
        }
    }
    return 0;
}

static int k0_guest_owned_tables_physical_dryrun(K0_PAGE_POOL *pool,
                                                   K_U64 firmware_cr3) {
    if (!pool || !pool->initialized || pool->active ||
        !firmware_cr3 || (firmware_cr3 & (K0_PAGE_SIZE - 1)) ||
        !k0_guest_nx_preflight())
        return 0;
    K_U64 claimed[6] = {0};
    for (K_U32 i = 0; i < 6; ++i) {
        if (!k0_pool_claim(pool, &claimed[i]) ||
            claimed[i] > (256ULL * 1024ULL * 1024ULL - K0_PAGE_SIZE))
            return 0;
    }
    if (claimed[0] == firmware_cr3 ||
        !k0_vm_plan_init(&k0_dryrun_plan, 1, 1) ||
        !k0_vm_plan_owned_leaf(&k0_dryrun_plan, pool,
                               K0_VM_HIGH_HALF_BASE, claimed[4], 1, 0) ||
        !k0_vm_plan_owned_leaf(&k0_dryrun_plan, pool,
                               K0_VM_HIGH_HALF_BASE + K0_PAGE_SIZE,
                               claimed[5], 0, 1) ||
        !k0_vm_tables_build(&k0_dryrun_tables, &k0_dryrun_plan,
                             pool, claimed))
        return 0;
    /* Distinct claimed physical data pages are prepared and verified only
     * using firmware's current identity mapping. No high-half VA touch.
     */
    for (K_U32 page = 4; page < 6; ++page) {
        volatile K_U8 *data = (volatile K_U8 *)(unsigned long long)claimed[page];
        for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i)
            data[i] = (K_U8)(page ^ i ^ (i >> 8));
        for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i)
            if (data[i] != (K_U8)(page ^ i ^ (i >> 8))) return 0;
    }
    for (K_U32 level = 0; level < 4; ++level) {
        volatile K_U64 *entries =
            (volatile K_U64 *)(unsigned long long)claimed[level];
        for (K_U32 slot = 0; slot < 512; ++slot)
            entries[slot] = k0_dryrun_tables.entries[level][slot];
    }
    K0_OWNED_GUEST_READER reader = {
        pool, {claimed[0], claimed[1], claimed[2], claimed[3]}
    };
    if (!k0_owned_tables_dryrun_verify(
            &k0_dryrun_tables, &k0_dryrun_plan, pool, firmware_cr3,
            k0_guest_read_claimed_table_entry, &reader))
        return 0;

    /* Scrub and verify every byte before returning ledger ownership.
     * Physical frames are NOT reserved or retained for a CR3 transition.
     */
    for (K_U32 page = 0; page < 6; ++page) {
        volatile K_U64 *entries =
            (volatile K_U64 *)(unsigned long long)claimed[page];
        for (K_U32 i = 0; i < 512; ++i) entries[i] = 0;
        for (K_U32 i = 0; i < 512; ++i)
            if (entries[i] != 0) return 0;
    }
    K_U64 after_cr3 = 0;
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(after_cr3));
    if (after_cr3 != firmware_cr3) return 0;
    for (K_U32 i = 0; i < 6; ++i)
        if (!k0_pool_release(pool, claimed[i])) return 0;
    return pool->active == 0;
}
#endif
