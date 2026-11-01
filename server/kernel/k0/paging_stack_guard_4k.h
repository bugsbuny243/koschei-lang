#ifndef KOSCHEI_K0_STACK_GUARD_4K_H
#define KOSCHEI_K0_STACK_GUARD_4K_H
/*
 * Test-only 4KiB identity stack PTs. Convert all huge PDE(s) covering the
 * observed 5-page stack plus one lower guard into pinned 4KiB page tables.
 * Guard -> nonpresent, observed stack -> supervisor RW+NX.
 *
 * Preserve independently validated pool or firmware-GDT *pages* if they
 * happen to share the 2MiB stack window. No other 4KiB leaf is present.
 * This restricts a QEMU snapshot, not a lifetime-safe stack reservation:
 * unknown firmware stack growth, other threads and hardware are unsupported.
 */
#include "paging_identity_ownership.h"

#define K0_STACK_GUARD_PT_FRAMES 2U
#define K0_STACK_GUARD_NX (1ULL << 63)
#define K0_STACK_GUARD_PTE_RW_NX (3ULL | K0_STACK_GUARD_NX)
#define K0_STACK_GUARD_PTE_RO_NX (1ULL | K0_STACK_GUARD_NX)
#define K0_STACK_GUARD_SLOT_BYTES 0x200000ULL

static int k0_stack_guard_overlap(K_U64 a, K_U64 a_end,
                                   K_U64 b, K_U64 b_end) {
    return a < b_end && b < a_end;
}

/* Prepared with the same validated UEFI LoadedImage and exact claimed
 * frame snapshot as the preceding identity-owner plan.
 * The table pointers are explicit to allow synthetic host adversarial tests
 * without dereferencing arbitrary physical memory addresses.
 * No table mutations occur if any preflight condition fails.
 */
static int k0_stack_guard_build(volatile K_U64 *pd,
                                const K0_IDENTITY_OWNER_PLAN *owner,
                                K_U64 image_base, K_U64 image_size,
                                K_U64 pool_base, K_U64 pool_size,
                                K_U64 gdt_base, K_U64 gdt_size,
                                const K_U64 *pt_frames,
                                volatile K_U64 * const *pt_buffers,
                                K_U64 *guard_va) {
    if (!pd || !owner || !pt_frames || !pt_buffers || !guard_va ||
        !owner->stack_floor || !owner->stack_end ||
        owner->stack_end <= owner->stack_floor ||
        owner->stack_end - owner->stack_floor !=
            (K0_OWNER_STACK_BACK_PAGES + 1ULL)*K0_PAGE_SIZE ||
        (owner->stack_floor & (K0_PAGE_SIZE - 1ULL)) ||
        (owner->stack_end & (K0_PAGE_SIZE - 1ULL)) ||
        owner->stack_floor < 0x100000ULL + K0_PAGE_SIZE ||
        !image_size || !pool_size || !gdt_size ||
        image_base >= K0_OWNER_IDENTITY_LIMIT ||
        image_size > K0_OWNER_IDENTITY_LIMIT - image_base ||
        pool_base >= K0_OWNER_IDENTITY_LIMIT ||
        pool_size > K0_OWNER_IDENTITY_LIMIT - pool_base ||
        gdt_base >= K0_OWNER_IDENTITY_LIMIT ||
        gdt_size > K0_OWNER_IDENTITY_LIMIT - gdt_base)
        return 0;

    K_U64 guard = owner->stack_floor - K0_PAGE_SIZE;
    K_U64 image_end = image_base + image_size;
    K_U64 pool_end = pool_base + pool_size;
    K_U64 gdt_end = gdt_base + gdt_size;
    if (owner->stack_end > K0_OWNER_IDENTITY_LIMIT ||
        k0_stack_guard_overlap(guard, guard+K0_PAGE_SIZE,
                               image_base, image_end) ||
        k0_stack_guard_overlap(guard, guard+K0_PAGE_SIZE,
                               pool_base, pool_end) ||
        k0_stack_guard_overlap(guard, guard+K0_PAGE_SIZE,
                               gdt_base, gdt_end))
        return 0;
    K_U64 first = guard / K0_STACK_GUARD_SLOT_BYTES;
    K_U64 last = (owner->stack_end - 1ULL) / K0_STACK_GUARD_SLOT_BYTES;
    if (last >= 511ULL || last < first ||
        last - first >= K0_STACK_GUARD_PT_FRAMES)
        return 0;

    for (K_U64 s = first; s <= last; ++s) {
        if (!owner->allowed[s] ||
            k0_stack_guard_overlap(s*K0_STACK_GUARD_SLOT_BYTES,
                        (s+1ULL)*K0_STACK_GUARD_SLOT_BYTES,
                        image_base, image_end) ||
            /* Require ordinary supervisor RW+NX huge-page identity slot;
             * never overwrite an executable PE PT or RO test PDE.
             */
            pd[s] != ((s << 21) | 0x83ULL | K0_STACK_GUARD_NX))
            return 0;
    }
    for (K_U32 i = 0; i < K0_STACK_GUARD_PT_FRAMES; ++i) {
        if (!pt_buffers[i] || !pt_frames[i] ||
            (pt_frames[i] & (K0_PAGE_SIZE - 1ULL)) ||
            pt_frames[i] < pool_base || pt_frames[i] >= pool_end)
            return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (pt_frames[i] == pt_frames[j] ||
                pt_buffers[i] == pt_buffers[j])
                return 0;
    }

    /* All validation above is read-only. Publish only after complete
     * leaf construction. A physical page used for the guard is absent even
     * when it shares the same 2MiB PDE as the live stack.
     */
    for (K_U32 t = 0; t < K0_STACK_GUARD_PT_FRAMES; ++t)
        for (K_U32 k = 0; k < 512; ++k)
            pt_buffers[t][k] = 0;
    for (K_U64 s = first; s <= last; ++s) {
        volatile K_U64 *pt = pt_buffers[s-first];
        for (K_U32 k = 0; k < 512; ++k) {
            K_U64 page = (s<<21) + (K_U64)k*K0_PAGE_SIZE;
            int within_stack = (page >= owner->stack_floor &&
                                page < owner->stack_end);
            int within_pool = (page >= pool_base && page < pool_end);
            int within_gdt = k0_stack_guard_overlap(
                page, page+K0_PAGE_SIZE, gdt_base, gdt_end);
            if (page != guard && (within_stack || within_pool))
                pt[k] = page | K0_STACK_GUARD_PTE_RW_NX;
            else if (page != guard && within_gdt)
                pt[k] = page | K0_STACK_GUARD_PTE_RO_NX;
        }
    }
    for (K_U64 s = first; s <= last; ++s)
        pd[s] = pt_frames[s-first] | 3ULL;
    *guard_va = guard;
    return 1;
}
#endif
