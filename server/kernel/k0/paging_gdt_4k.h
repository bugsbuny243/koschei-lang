#ifndef KOSCHEI_K0_GDT_4K_H
#define KOSCHEI_K0_GDT_4K_H
/*
 * QEMU-only firmware GDTR isolation. Validate the live GDTR against the
 * post-EBS descriptor owner plan, then keep exactly the pages intersecting
 * GDTR supervisor RO+NX. Unrelated pages in a newly split 2MiB GDT slot
 * become nonpresent. Existing image/stack/pool 4KiB PTs are not overwritten:
 * if a GDT page is already mapped, verify its exact RO+NX identity leaf.
 *
 * Two extra PT frames are reserved from the claimed physical pool; this
 * single-core experiment does not protect against firmware mutation,
 * live descriptor reloads, DMA, or an independently owned kernel GDT.
 */
#include "paging_pool_4k.h"

#define K0_GDT_4K_PT_FRAMES 2U
#define K0_GDT_4K_NX (1ULL << 63)
#define K0_GDT_4K_RO_NX (1ULL | K0_GDT_4K_NX)
#define K0_GDT_4K_SLOT_BYTES 0x200000ULL
#define K0_GDT_4K_ADDR_MASK 0x000ffffffffff000ULL

static int k0_gdt_4k_build(volatile K_U64 *pd,
                           const K0_PAGE_POOL *pool,
                           const K0_IDENTITY_OWNER_PLAN *owner,
                           K_U64 gdt_base, K_U64 gdt_bytes,
                           const K_U64 *all_frames, K_U32 frame_count,
                           const K_U64 *pt_frames,
                           volatile K_U64 * const *pt_buffers,
                           K_U64 *gdt_writable_probe) {
    if (!pd || !pool || !owner || !all_frames || !pt_frames ||
        !pt_buffers || !gdt_writable_probe ||
        !k0_identity_owner_frames_match(pool,all_frames,frame_count) ||
        gdt_base != owner->firmware_gdt_base ||
        !gdt_base ||
        gdt_base >= K0_OWNER_IDENTITY_LIMIT ||
        !gdt_bytes || gdt_bytes > K0_PAGE_SIZE ||
        gdt_bytes > K0_OWNER_IDENTITY_LIMIT-gdt_base)
        return 0;
    K_U64 end=gdt_base+gdt_bytes;
    K_U64 first=gdt_base/K0_GDT_4K_SLOT_BYTES;
    K_U64 last=(end-1ULL)/K0_GDT_4K_SLOT_BYTES;
    if (last>=511ULL || last<first ||
        last-first >= K0_GDT_4K_PT_FRAMES)
        return 0;
    for (K_U32 i=0;i<K0_GDT_4K_PT_FRAMES;++i) {
        if (!pt_frames[i] || !pt_buffers[i] ||
            (pt_frames[i] & (K0_PAGE_SIZE-1ULL)) ||
            !k0_pool_is_claimed(pool,pt_frames[i]))
            return 0;
        for (K_U32 j=0;j<i;++j)
            if (pt_frames[i]==pt_frames[j] ||
                pt_buffers[i]==pt_buffers[j])
                return 0;
    }
    /* Complete read-only preflight before any PT page or PD publication.
     * The frame claims were proven earlier by the page-pool exact bitmap.
     */
    for (K_U64 slot=first;slot<=last;++slot) {
        if (!owner->allowed[slot]) return 0;
        K_U64 existing=pd[slot];
        K_U64 huge=(slot<<21)|0x83ULL|K0_GDT_4K_NX;
        if (existing==huge) continue;
        /* A non-huge PDE must already be a valid supervisor PT root,
         * physically among the exact claimed tables, never arbitrary.
         */
        if ((existing & 0x83ULL)!=3ULL ||
            (existing & K0_GDT_4K_NX))
            return 0;
        K_U64 root=existing & K0_GDT_4K_ADDR_MASK;
        int owned=0;
        for (K_U32 i=0;i<frame_count;++i)
            if (root==all_frames[i]) { owned=1; break; }
        if (!owned) return 0;
        volatile K_U64 *pt=(volatile K_U64 *)(unsigned long long)root;
        for (K_U32 i=0;i<512;++i) {
            K_U64 page=(slot<<21)+(K_U64)i*K0_PAGE_SIZE;
            if (!k0_stack_guard_overlap(page,page+K0_PAGE_SIZE,
                                        gdt_base,end))
                continue;
            if (pt[i] != (page|K0_GDT_4K_RO_NX))
                return 0;
        }
    }
    /* At most two slots; the frames exist even when a split was already
     * installed by the stack or pool builder. Never free active frames.
     */
    K_U32 used=0;
    for (K_U64 slot=first;slot<=last;++slot) {
        K_U64 huge=(slot<<21)|0x83ULL|K0_GDT_4K_NX;
        if (pd[slot]!=huge) continue;
        volatile K_U64 *pt=pt_buffers[used];
        for (K_U32 i=0;i<512;++i) {
            K_U64 page=(slot<<21)+(K_U64)i*K0_PAGE_SIZE;
            pt[i]=k0_stack_guard_overlap(page,page+K0_PAGE_SIZE,
                                         gdt_base,end)
                   ? page|K0_GDT_4K_RO_NX : 0;
        }
        pd[slot]=pt_frames[used]|3ULL;
        ++used;
    }
    *gdt_writable_probe=gdt_base;
    return 1;
}
#endif
