#ifndef KOSCHEI_K0_POOL_4K_H
#define KOSCHEI_K0_POOL_4K_H
/*
 * QEMU-only 4KiB identity mappings of EXACTLY the claimed post-EBS pool
 * frames. Unclaimed pool pages become nonpresent, even though they are
 * conventional memory. Physical frames used by an active CR3 are pinned
 * by the single-threaded test invariant, not a production allocator lock.
 *
 * The two 4KiB PT frames support a 64KiB pool crossing one 2MiB boundary.
 * This builder refuses to overwrite existing PE RX or stack-guard PTs.
 * If the firmware GDT shares a pool PDE, its pages remain supervisor RO+NX.
 * Other firmware GDT PDEs remain coarse and are a separate acceptance gap.
 */
#include "paging_stack_guard_4k.h"

#define K0_POOL_4K_PT_FRAMES 2U
#define K0_POOL_4K_SLOT_BYTES 0x200000ULL
#define K0_POOL_4K_NX (1ULL << 63)
#define K0_POOL_4K_RW_NX (3ULL | K0_POOL_4K_NX)
#define K0_POOL_4K_RO_NX (1ULL | K0_POOL_4K_NX)

static int k0_pool_4k_build(volatile K_U64 *pd,
                            const K0_PAGE_POOL *pool,
                            const K0_IDENTITY_OWNER_PLAN *owner,
                            K_U64 image_base, K_U64 image_size,
                            K_U64 gdt_base, K_U64 gdt_bytes,
                            const K_U64 *all_frames, K_U32 frame_count,
                            const K_U64 *pt_frames,
                            volatile K_U64 * const *pt_buffers,
                            K_U64 *unclaimed_va) {
    if (!pd || !pool || !owner || !all_frames || !pt_frames ||
        !pt_buffers || !unclaimed_va ||
        !k0_identity_owner_frames_match(pool, all_frames, frame_count) ||
        !pool->base || (pool->base & (K0_PAGE_SIZE-1ULL)) ||
        pool->base >= K0_OWNER_IDENTITY_LIMIT ||
        K0_PLAN_PAGES*K0_PAGE_SIZE > K0_OWNER_IDENTITY_LIMIT-pool->base ||
        !image_size || image_base >= K0_OWNER_IDENTITY_LIMIT ||
        image_size > K0_OWNER_IDENTITY_LIMIT-image_base ||
        !gdt_base || !gdt_bytes ||
        gdt_base >= K0_OWNER_IDENTITY_LIMIT ||
        gdt_bytes > K0_OWNER_IDENTITY_LIMIT-gdt_base ||
        !owner->stack_floor || !owner->stack_end ||
        owner->stack_end > K0_OWNER_IDENTITY_LIMIT ||
        owner->stack_floor < K0_PAGE_SIZE ||
        owner->stack_end <= owner->stack_floor)
        return 0;
    const K_U64 pool_end=pool->base+K0_PLAN_PAGES*K0_PAGE_SIZE;
    const K_U64 image_end=image_base+image_size;
    const K_U64 gdt_end=gdt_base+gdt_bytes;
    const K_U64 guard=owner->stack_floor-K0_PAGE_SIZE;
    if (k0_stack_guard_overlap(pool->base,pool_end,image_base,image_end) ||
        k0_stack_guard_overlap(pool->base,pool_end,guard,owner->stack_end) ||
        k0_stack_guard_overlap(pool->base,pool_end,gdt_base,gdt_end))
        return 0;
    const K_U64 first=pool->base/K0_POOL_4K_SLOT_BYTES;
    const K_U64 last=(pool_end-1ULL)/K0_POOL_4K_SLOT_BYTES;
    if (last>=511ULL || last<first ||
        last-first >= K0_POOL_4K_PT_FRAMES ||
        pool->active >= K0_PLAN_PAGES)
        return 0;

    for (K_U64 s=first;s<=last;++s) {
        K_U64 left=s*K0_POOL_4K_SLOT_BYTES;
        K_U64 right=left+K0_POOL_4K_SLOT_BYTES;
        /* Never overwrite a prior image or stack PT; additional GDT
         * pages in the same slot are preserved explicitly as RO+NX.
         */
        if (!owner->allowed[s] ||
            k0_stack_guard_overlap(left,right,image_base,image_end) ||
            k0_stack_guard_overlap(left,right,guard,owner->stack_end) ||
            pd[s] != (left|0x83ULL|K0_POOL_4K_NX))
            return 0;
    }
    for (K_U32 j=0;j<K0_POOL_4K_PT_FRAMES;++j) {
        if (!pt_frames[j] || !pt_buffers[j] ||
            (pt_frames[j] & (K0_PAGE_SIZE-1ULL)) ||
            !k0_pool_is_claimed(pool,pt_frames[j]))
            return 0;
        for (K_U32 k=0;k<j;++k)
            if (pt_frames[j]==pt_frames[k] ||
                pt_buffers[j]==pt_buffers[k])
                return 0;
    }
    K_U64 missing=0;
    for (K_U32 i=0;i<K0_PLAN_PAGES;++i) {
        K_U64 physical=pool->base+(K_U64)i*K0_PAGE_SIZE;
        if (!k0_pool_is_claimed(pool,physical)) {
            missing=physical;
            break;
        }
    }
    if (!missing || (missing>=gdt_base && missing<gdt_end)) return 0;

    /* All checks above are read-only. Build the two pinned PT frames, then
     * atomically publish each PDE; no libc memset or hidden allocator.
     */
    for (K_U32 t=0;t<K0_POOL_4K_PT_FRAMES;++t)
        for (K_U32 k=0;k<512;++k)
            pt_buffers[t][k]=0;
    for (K_U64 s=first;s<=last;++s) {
        volatile K_U64 *pt=pt_buffers[s-first];
        for (K_U32 k=0;k<512;++k) {
            K_U64 page=(s<<21)+(K_U64)k*K0_PAGE_SIZE;
            if (k0_pool_is_claimed(pool,page))
                pt[k]=page|K0_POOL_4K_RW_NX;
            else if (k0_stack_guard_overlap(page,page+K0_PAGE_SIZE,
                                            gdt_base,gdt_end))
                pt[k]=page|K0_POOL_4K_RO_NX;
        }
    }
    for (K_U64 s=first;s<=last;++s)
        pd[s]=pt_frames[s-first]|3ULL;
    *unclaimed_va=missing;
    return 1;
}
#endif
