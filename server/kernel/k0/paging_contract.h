#ifndef KOSCHEI_K0_PAGING_CONTRACT_H
#define KOSCHEI_K0_PAGING_CONTRACT_H
/*
 * K0.4 STAGING: data-only x86-64 4K leaf-entry validation/encoding.
 * Does NOT construct a PML4/PDP/PT, install CR3, install an IDT, or prove
 * a hardware page fault. Firmware mappings are NOT Koschei-owned mappings.
 * Never pass this plan to the CPU as a live page table.
 */
#include "page_pool.h"

#define K0_VM_MAX_LEAVES 16U
#define K0_VM_PHYSICAL_MASK 0x000ffffffffff000ULL
#define K0_VM_HIGH_HALF_BASE 0xffff800000000000ULL
/* Koschei-owned virtual-address policy: reserve the final 64 KiB as a
 * high-half unmapped guard, even though those pages are x86-64 canonical.
 * This is a PLANNING rule only; no live guard is installed yet.
 */
#define K0_VM_TOP_GUARD_START 0xffffffffffff0000ULL
#define K0_VM_PRESENT 0x1ULL
#define K0_VM_WRITE 0x2ULL
#define K0_VM_NO_EXECUTE (1ULL << 63)

typedef struct {
    K_U64 virtual_page;
    K_U64 physical_page;
    K_U64 leaf_entry;
} K0_VM_LEAF;

typedef struct {
    K0_VM_LEAF leaves[K0_VM_MAX_LEAVES];
    K_U32 count;
    K_U32 initialized;
    /* Snapshotted when first leaf is entered. Reject pool mutations later. */
    K_U64 pool_epoch;
} K0_VM_PLAN;

/* NX is meaningful only when both CPU support AND EFER.NXE are established.
 * Neither detection nor EFER programming occurs in this staging module.
 */
static int k0_vm_plan_init(K0_VM_PLAN *plan, int cpu_has_nx, int efer_nxe_enabled) {
    if (!plan || plan->initialized || !cpu_has_nx || !efer_nxe_enabled)
        return 0;
    plan->count = 0;
    plan->pool_epoch = 0;
    plan->initialized = 1;
    return 1;
}

/* High-half, 48-bit canonical address plus Koschei's top 64 KiB guard.
 * Architectural canonicality alone does not imply permission to map a page.
 * Null/low mappings intentionally denied; LA57 is not supported.
 */
static int k0_vm_high_canonical_page(K_U64 virt) {
    return virt >= K0_VM_HIGH_HALF_BASE &&
           (virt >> 48) == 0xffffULL &&
           (virt & (K0_PAGE_SIZE - 1)) == 0 &&
           virt < K0_VM_TOP_GUARD_START;
}

/* Only claimed pool pages; no duplicate physical or virtual aliases.
 * Every encoded PTE stays supervisor-only (US bit clear), with W^X.
 * This is a proposed 4K leaf entry, not installed hardware state.
 */
static int k0_vm_plan_owned_leaf(K0_VM_PLAN *plan, const K0_PAGE_POOL *pool,
                                 K_U64 virt, K_U64 phys,
                                 int writable, int executable) {
    if (!plan || !plan->initialized || !pool ||
        plan->count >= K0_VM_MAX_LEAVES ||
        !k0_vm_high_canonical_page(virt) ||
        (phys & (K0_PAGE_SIZE - 1)) ||
        (phys & ~K0_VM_PHYSICAL_MASK) ||
        !k0_pool_is_claimed(pool, phys) ||
        !pool->epoch ||
        (plan->count && plan->pool_epoch != pool->epoch) ||
        (writable && executable))
        return 0;
    for (K_U32 i = 0; i < plan->count; ++i)
        if (plan->leaves[i].virtual_page == virt ||
            plan->leaves[i].physical_page == phys) return 0;
    K_U64 leaf = phys | K0_VM_PRESENT;
    if (writable) leaf |= K0_VM_WRITE;
    if (!executable) leaf |= K0_VM_NO_EXECUTE;
    K0_VM_LEAF entry = {virt, phys, leaf};
    if (!plan->count) plan->pool_epoch = pool->epoch;
    plan->leaves[plan->count++] = entry;
    return 1;
}
#endif
