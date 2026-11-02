#ifndef KOSCHEI_K0_MULTI_PT_GUEST_PROBE_H
#define KOSCHEI_K0_MULTI_PT_GUEST_PROBE_H
/*
 * QEMU 256MiB OVMF diagnostic ONLY. Physical table bytes are written as
 * ordinary data via the *existing firmware* identity map, never loaded
 * with MOV CR3. Not the live UEFI image, stack, GDT or IDT mappings.
 * If validation fails, halt: do not release possibly dirty claimed pages.
 */
#include "multi_pt_physical.h"

static K0_MPT_MODEL k0_mpt_guest_model;

typedef struct {
    const K0_PAGE_POOL *pool;
    K_U64 tables[K0_MPT_TABLES];
} K0_MPT_GUEST_READER;

static int k0_mpt_guest_read(void *context, K_U64 frame,
                            K_U32 slot, K_U64 *out) {
    const K0_MPT_GUEST_READER *r = (const K0_MPT_GUEST_READER *)context;
    if (!r || !r->pool || !out || slot >= K0_MPT_ENTRIES ||
        !frame || (frame & (K0_PAGE_SIZE - 1)) ||
        frame > K0_MPT_PHYS_LIMIT - K0_PAGE_SIZE ||
        !k0_pool_is_claimed(r->pool, frame)) return 0;
    for (K_U32 i = 0; i < K0_MPT_TABLES; ++i) {
        if (r->tables[i] == frame) {
            const volatile K_U64 *physical =
                (const volatile K_U64 *)(unsigned long long)frame;
            *out = physical[slot];
            return 1;
        }
    }
    return 0;
}

static int k0_mpt_guest_physical_dryrun(
    K0_PAGE_POOL *pool, K_U64 firmware_cr3,
    const void *map, K_U64 map_bytes, K_U64 stride, K_U32 version) {
    K0_MEMORY_PLAN validated = {0};
    if (!pool || !pool->initialized || pool->active ||
        !k0_guest_nx_preflight() || !firmware_cr3 ||
        !k0_memory_validate_plan(map, map_bytes, stride, version, &validated) ||
        validated.candidate_start != pool->base ||
        validated.candidate_pages != K0_PLAN_PAGES ||
        pool->base > K0_MPT_PHYS_LIMIT - K0_PLAN_PAGES * K0_PAGE_SIZE ||
        !k0_live_img_in_descriptor(map, map_bytes, stride, pool->base,
            K0_CONVENTIONAL_MEMORY, K0_CONVENTIONAL_MEMORY,
            K0_CONVENTIONAL_MEMORY) ||
        !k0_live_img_in_descriptor(map, map_bytes, stride,
            pool->base + K0_PLAN_PAGES * K0_PAGE_SIZE - 1,
            K0_CONVENTIONAL_MEMORY, K0_CONVENTIONAL_MEMORY,
            K0_CONVENTIONAL_MEMORY))
        return 0;
    K_U64 claimed[K0_MPT_FRAMES] = {0};
    for (K_U32 i = 0; i < K0_MPT_FRAMES; ++i) {
        if (!k0_pool_claim(pool, &claimed[i])) return 0;
    }
    if (!k0_mpt_build(&k0_mpt_guest_model, pool, claimed, firmware_cr3))
        return 0;
    /* Populate three PHYSICAL sample pages, not their high-half VAs.
     * The RO-executable leaf contains pattern bytes, never executed.
     */
    for (K_U32 page = K0_MPT_TABLES; page < K0_MPT_FRAMES; ++page) {
        volatile K_U8 *bytes = (volatile K_U8 *)(unsigned long long)claimed[page];
        for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i)
            bytes[i] = (K_U8)(0x53U ^ page ^ i ^ (i >> 8));
        for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i)
            if (bytes[i] != (K_U8)(0x53U ^ page ^ i ^ (i >> 8)))
                return 0;
    }
    for (K_U32 t = 0; t < K0_MPT_TABLES; ++t) {
        volatile K_U64 *physical =
            (volatile K_U64 *)(unsigned long long)claimed[t];
        for (K_U32 slot = 0; slot < K0_MPT_ENTRIES; ++slot)
            physical[slot] = k0_mpt_guest_model.ptes[t][slot];
    }
    K0_MPT_GUEST_READER reader = {
        pool, {claimed[0], claimed[1], claimed[2],
               claimed[3], claimed[4], claimed[5]}
    };
    if (!k0_mpt_verify(&k0_mpt_guest_model, pool, firmware_cr3,
                       k0_mpt_guest_read, &reader))
        return 0;
    /* Zero and read back all nine frames BEFORE releasing the ledger.
     * The modeled page tables must not remain available as stale data.
     */
    for (K_U32 t = 0; t < K0_MPT_FRAMES; ++t) {
        volatile K_U64 *physical =
            (volatile K_U64 *)(unsigned long long)claimed[t];
        for (K_U32 slot = 0; slot < K0_MPT_ENTRIES; ++slot)
            physical[slot] = 0;
        for (K_U32 slot = 0; slot < K0_MPT_ENTRIES; ++slot)
            if (physical[slot] != 0) return 0;
    }
    K_U64 after = 0;
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(after));
    if (after != firmware_cr3) return 0;
    for (K_U32 i = 0; i < K0_MPT_FRAMES; ++i)
        if (!k0_pool_release(pool, claimed[i])) return 0;
    return pool->active == 0;
}
#endif
