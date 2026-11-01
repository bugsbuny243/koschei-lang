#ifndef KOSCHEI_K0_IDENTITY_OWNERSHIP_H
#define KOSCHEI_K0_IDENTITY_OWNERSHIP_H
/*
 * K0.4 QEMU-only coarse physical identity aperture.
 * Accept only the validated PE LoaderCode/LoaderData pages, one bounded
 * active-stack footprint inside LoaderData/BootServicesData, and the
 * post-ExitBootServices 16-page conventional pool. Each required region
 * is retained through a whole 2MiB identity PDE, still RW+NX OUTSIDE PE.
 * Everything else in 0..1GiB is NONPRESENT; this is not a fine-grained
 * physical memory manager, robust stack reservation, or device policy.
 *
 * The firmware memory map is an untrusted external root. Validate it
 * before this helper with k0_memory_validate_plan; this helper also
 * revalidates the candidate and exact physical ownership.
 */
#include "memory_map.h"
#include "page_pool.h"

#define K0_OWNER_IDENTITY_LIMIT 0x40000000ULL
#define K0_OWNER_PDE_BYTES 0x200000ULL
#define K0_OWNER_SLOTS 512U
#define K0_OWNER_STACK_BACK_PAGES 4ULL
#define K0_OWNER_LOW_HOLE_VA 0x3fc00000ULL
#define K0_OWNER_LOW_HOLE_SLOT (K0_OWNER_LOW_HOLE_VA / K0_OWNER_PDE_BYTES)

typedef struct {
    K_U64 stack_floor;
    K_U64 stack_end;
    K_U64 firmware_gdt_base;
    K_U32 mapped_slots;
    K_U8 allowed[K0_OWNER_SLOTS];
} K0_IDENTITY_OWNER_PLAN;

/* Verify continuous coverage by accepted types, including across adjacent
 * descriptors; no gap, no overflow and no unknown memory type accepted.
 * Call only after the independent global overlap-checking map validator.
 */
static int k0_owner_covered(const K_U8 *map, K_U64 count, K_U64 stride,
                            K_U64 start, K_U64 end, K_U32 kind) {
    if (!start || start >= end || end > K0_OWNER_IDENTITY_LIMIT) return 0;
    K_U64 cursor = start;
    for (K_U64 step = 0; step < count && cursor < end; ++step) {
        int found = 0;
        for (K_U64 i = 0; i < count; ++i) {
            K0_MEMORY_DESCRIPTOR d = k0_read_descriptor(map + i * stride);
            /* Image: LoaderCode/Data (1,2). Stack: LoaderData/BootData
             * (2,4). Firmware GDT: typed Loader/Boot/Runtime (1..6).
             * GDT is a firmware trust dependency, not our owned RAM.
             */
            if (kind == 0U ? (d.type != 1U && d.type != 2U) :
                kind == 1U ? (d.type != 2U && d.type != 4U) :
                             (d.type < 1U || d.type > 6U))
                continue;
            if (!d.number_of_pages ||
                d.number_of_pages > ~(K_U64)0 / K0_PAGE_SIZE ||
                d.physical_start >
                    ~(K_U64)0 - d.number_of_pages * K0_PAGE_SIZE)
                return 0;
            K_U64 descriptor_end =
                d.physical_start + d.number_of_pages * K0_PAGE_SIZE;
            if (d.physical_start <= cursor && cursor < descriptor_end) {
                cursor = descriptor_end < end ? descriptor_end : end;
                found = 1;
                break;
            }
        }
        if (!found) return 0;
    }
    return cursor == end;
}
static int k0_owner_disjoint(K_U64 left, K_U64 left_end,
                             K_U64 right, K_U64 right_end) {
    return left_end <= right || right_end <= left;
}
static int k0_identity_owner_plan(const void *map_buffer, K_U64 bytes,
                                  K_U64 stride, K_U32 version,
                                  K_U64 image_base, K_U64 image_bytes,
                                  K_U64 pool_base, K_U64 pool_bytes,
                                  K_U64 stack_address, K_U64 idt_address,
                                  K_U64 gdt_base, K_U64 gdt_bytes,
                                  const K_U64 *frames, K_U32 frame_count,
                                  K0_IDENTITY_OWNER_PLAN *out) {
    if (!out || !frames || !frame_count || frame_count > K0_PLAN_PAGES ||
        !image_bytes || (image_base & (K0_PAGE_SIZE - 1)) ||
        (image_bytes & (K0_PAGE_SIZE - 1)) ||
        !pool_bytes || (pool_base & (K0_PAGE_SIZE - 1)) ||
        (pool_bytes & (K0_PAGE_SIZE - 1)) ||
        image_base < 0x100000ULL ||
        image_base >= K0_OWNER_IDENTITY_LIMIT ||
        image_bytes > K0_OWNER_IDENTITY_LIMIT - image_base ||
        pool_base < 0x100000ULL ||
        pool_base >= K0_OWNER_IDENTITY_LIMIT ||
        pool_bytes > K0_OWNER_IDENTITY_LIMIT - pool_base ||
        pool_bytes != K0_PLAN_PAGES * K0_PAGE_SIZE ||
        !stack_address || stack_address >= K0_OWNER_IDENTITY_LIMIT ||
        !gdt_base || gdt_base >= K0_OWNER_IDENTITY_LIMIT ||
        !gdt_bytes || gdt_bytes > K0_PAGE_SIZE ||
        gdt_bytes > K0_OWNER_IDENTITY_LIMIT - gdt_base ||
        !idt_address || idt_address < image_base ||
        idt_address - image_base >= image_bytes)
        return 0;
    K0_MEMORY_PLAN validated = {0};
    if (!k0_memory_validate_plan(map_buffer, bytes, stride, version,
                                 &validated) ||
        validated.candidate_start != pool_base ||
        validated.candidate_pages != K0_PLAN_PAGES)
        return 0;

    K_U64 stack_page = stack_address & ~(K0_PAGE_SIZE - 1ULL);
    if (stack_page < (K0_OWNER_STACK_BACK_PAGES * K0_PAGE_SIZE))
        return 0;
    K_U64 stack_floor =
        stack_page - K0_OWNER_STACK_BACK_PAGES * K0_PAGE_SIZE;
    K_U64 stack_end = stack_page + K0_PAGE_SIZE;
    const K_U64 image_end = image_base + image_bytes;
    const K_U64 pool_end = pool_base + pool_bytes;
    if (!k0_owner_disjoint(image_base, image_end, pool_base, pool_end) ||
        !k0_owner_disjoint(image_base, image_end, stack_floor, stack_end) ||
        !k0_owner_disjoint(pool_base, pool_end, stack_floor, stack_end))
        return 0;
    const K_U8 *map = (const K_U8 *)map_buffer;
    const K_U64 count = bytes / stride;
    if (!k0_owner_covered(map, count, stride, image_base, image_end, 0) ||
        !k0_owner_covered(map, count, stride, stack_floor, stack_end, 1) ||
        !k0_owner_covered(map, count, stride,
                          gdt_base, gdt_base + gdt_bytes, 2))
        return 0;

    for (K_U32 i = 0; i < frame_count; ++i) {
        if (!frames[i] || (frames[i] & (K0_PAGE_SIZE - 1ULL)) ||
            frames[i] < pool_base || frames[i] >= pool_end)
            return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (frames[i] == frames[j]) return 0;
    }

    /* No output mutation on a failed preflight. The explicit volatile
     * initialization prevents libc memset imports into freestanding EFI.
     */
    K0_IDENTITY_OWNER_PLAN next;
    next.stack_floor = stack_floor;
    next.stack_end = stack_end;
    next.firmware_gdt_base = gdt_base;
    next.mapped_slots = 0;
    volatile K_U8 *allowed = next.allowed;
    for (K_U32 i = 0; i < K0_OWNER_SLOTS; ++i)
        allowed[i] = 0;
    const K_U64 regions[4][2] = {
        {image_base, image_end}, {pool_base, pool_end},
        {stack_floor, stack_end}, {gdt_base, gdt_base + gdt_bytes}
    };
    for (K_U32 r = 0; r < 4; ++r) {
        K_U64 first = regions[r][0] / K0_OWNER_PDE_BYTES;
        K_U64 last = (regions[r][1] - 1ULL) / K0_OWNER_PDE_BYTES;
        if (last >= 511ULL) return 0; /* retain explicit fault slot 511 */
        for (K_U64 i = first; i <= last; ++i) {
            if (!next.allowed[i]) {
                next.allowed[i] = 1;
                ++next.mapped_slots;
            }
        }
    }
    if (!next.mapped_slots || next.mapped_slots > 8U ||
        next.allowed[K0_OWNER_LOW_HOLE_SLOT])
        return 0;
    out->stack_floor = next.stack_floor;
    out->stack_end = next.stack_end;
    out->firmware_gdt_base = next.firmware_gdt_base;
    out->mapped_slots = next.mapped_slots;
    volatile K_U8 *target = out->allowed;
    for (K_U32 i = 0; i < K0_OWNER_SLOTS; ++i)
        target[i] = next.allowed[i];
    return 1;
}

/* Exact correspondence between all live physical paging frames and the
 * post-firmware page-ledger bitmask. A simple range test is insufficient:
 * a page within the pool can be unclaimed, released, or already reused.
 * This is a single-threaded read-only snapshot, NOT a lifetime pin lock.
 */
static int k0_identity_owner_frames_match(const K0_PAGE_POOL *pool,
                                           const K_U64 *frames,
                                           K_U32 frame_count) {
    if (!pool || !pool->initialized || !pool->epoch || !frames ||
        !frame_count || frame_count > K0_PLAN_PAGES ||
        pool->active != frame_count) return 0;
    K_U32 observed = 0;
    for (K_U32 i = 0; i < frame_count; ++i) {
        if (!k0_pool_is_claimed(pool, frames[i])) return 0;
        K_U32 index =
            (K_U32)((frames[i] - pool->base) / K0_PAGE_SIZE);
        K_U32 bit = 1U << index;
        if (observed & bit) return 0;
        observed |= bit;
    }
    return observed == pool->claimed;
}
#endif
