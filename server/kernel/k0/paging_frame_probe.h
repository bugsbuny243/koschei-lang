#ifndef KOSCHEI_K0_PAGING_FRAME_PROBE_H
#define KOSCHEI_K0_PAGING_FRAME_PROBE_H
/*
 * K0.4 post-firmware physical frame WRITE/READBACK ONLY.
 * Direct pointers still rely on firmware's existing identity mapping.
 * Tables are NEVER loaded into CR3, and no IDT/#PF is installed here.
 */
#include "paging_model.h"

static K0_VM_PLAN k0_guest_plan;
static K0_VM_TABLE_MODEL k0_guest_tables;

static void k0_guest_cpuid(K_U32 leaf, K_U32 *a, K_U32 *b,
                           K_U32 *c, K_U32 *d) {
    K_U32 x, y, z, w;
    __asm__ __volatile__("cpuid"
                         : "=a"(x), "=b"(y), "=c"(z), "=d"(w)
                         : "a"(leaf), "c"(0));
    *a = x; *b = y; *c = z; *d = w;
}

/* Observation only: EFER.NXE must already be enabled by the CPU context.
 * This code never writes EFER or otherwise changes CPU paging policy.
 */
static int k0_guest_nx_preflight(void) {
    K_U32 a, b, c, d;
    k0_guest_cpuid(1U, &a, &b, &c, &d);
    if (!(d & (1U << 5))) return 0; /* MSR instruction */
    k0_guest_cpuid(0x80000000U, &a, &b, &c, &d);
    if (a < 0x80000001U) return 0;
    k0_guest_cpuid(0x80000001U, &a, &b, &c, &d);
    if (!(d & (1U << 20))) return 0; /* NX */
    K_U32 lo, hi;
    __asm__ __volatile__("rdmsr" : "=a"(lo), "=d"(hi)
                         : "c"(0xc0000080U)); /* IA32_EFER */
    (void)hi;
    return (lo & (1U << 11)) != 0; /* NXE */
}

static int k0_guest_roundtrip_table_frames(K0_PAGE_POOL *pool) {
    if (!pool || pool->active || !k0_guest_nx_preflight()) return 0;
    K_U64 claimed[6] = {0};
    K_U64 frames[4] = {0};
    for (K_U32 i = 0; i < 6; ++i) {
        if (!k0_pool_claim(pool, &claimed[i])) return 0;
        if (i < 4) frames[i] = claimed[i];
    }
    if (!k0_vm_plan_init(&k0_guest_plan, 1, 1) ||
        !k0_vm_plan_owned_leaf(&k0_guest_plan, pool,
                               K0_VM_HIGH_HALF_BASE, claimed[4], 1, 0) ||
        !k0_vm_plan_owned_leaf(&k0_guest_plan, pool,
                               K0_VM_HIGH_HALF_BASE + K0_PAGE_SIZE,
                               claimed[5], 0, 1) ||
        !k0_vm_tables_build(&k0_guest_tables, &k0_guest_plan, pool, frames))
        return 0;
    /* The 4 x 4096-byte frames are claimed conventional memory. This is
     * post-ExitBootServices, but current address translation is firmware's.
     * Write and read all 512 entries per frame, not merely a model checksum.
     */
    for (K_U32 level = 0; level < 4; ++level) {
        volatile K_U64 *physical =
            (volatile K_U64 *)(unsigned long long)frames[level];
        for (K_U32 i = 0; i < K0_VM_ENTRIES_PER_TABLE; ++i)
            physical[i] = k0_guest_tables.entries[level][i];
        for (K_U32 i = 0; i < K0_VM_ENTRIES_PER_TABLE; ++i)
            if (physical[i] != k0_guest_tables.entries[level][i]) return 0;
    }
    /* Nothing references these tables via CR3. Erase and release all frames. */
    for (K_U32 level = 0; level < 4; ++level) {
        volatile K_U64 *physical =
            (volatile K_U64 *)(unsigned long long)frames[level];
        for (K_U32 i = 0; i < K0_VM_ENTRIES_PER_TABLE; ++i)
            physical[i] = 0;
        for (K_U32 i = 0; i < K0_VM_ENTRIES_PER_TABLE; ++i)
            if (physical[i] != 0) return 0;
    }
    for (K_U32 i = 0; i < 6; ++i)
        if (!k0_pool_release(pool, claimed[i])) return 0;
    return pool->active == 0;
}
#endif
