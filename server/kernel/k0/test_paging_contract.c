#include "paging_contract.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    const K_U64 virt = K0_VM_HIGH_HALF_BASE;
    const K_U64 base = 0x200000ULL;
    K0_MEMORY_DESCRIPTOR desc[] = {
        {7, 0, base, 0, 128, 0},
        {3, 0, 0x100000ULL, 0, 256, 0}
    };
    K0_MEMORY_PLAN candidate = {0};
    K0_PAGE_POOL pool = {0};
    K0_VM_PLAN plan = {0};
    K_U64 pages[16] = {0};
    assert(k0_memory_validate_plan(desc, sizeof(desc), sizeof(desc[0]), 1, &candidate));
    assert(k0_pool_init(&pool, &candidate, 1));
    assert(!k0_vm_plan_init(&plan, 0, 1));
    assert(!k0_vm_plan_init(&plan, 1, 0));
    assert(!plan.initialized);
    assert(k0_vm_plan_init(&plan, 1, 1));
    assert(!k0_vm_plan_init(&plan, 1, 1));
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt, base, 1, 0)); /* unclaimed */
    for (unsigned i = 0; i < 16; ++i) {
        assert(k0_pool_claim(&pool, &pages[i]));
        assert(pages[i] == base + (K_U64)i * K0_PAGE_SIZE);
    }
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt, pages[0], 1, 1)); /* W+X */
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt + 1, pages[0], 1, 0));
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, 0x400000ULL, pages[0], 1, 0));
    /* A canonical address may still be forbidden by Koschei policy. */
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, K0_VM_TOP_GUARD_START, pages[0], 1, 0));
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, 0xfffffffffffff000ULL, pages[0], 1, 0));
    assert(k0_vm_high_canonical_page(K0_VM_TOP_GUARD_START - K0_PAGE_SIZE));
    assert(!k0_vm_high_canonical_page(K0_VM_TOP_GUARD_START));
    assert(!k0_vm_high_canonical_page(0x0000800000000000ULL)); /* noncanonical */
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt, pages[0] + 1, 1, 0));
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt, pages[0] - 4096, 1, 0));
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt, pages[0] + 16 * K0_PAGE_SIZE, 1, 0));
    assert(!plan.count);
    assert(k0_vm_plan_owned_leaf(&plan, &pool, virt, pages[0], 1, 0));
    assert(plan.leaves[0].leaf_entry ==
           (pages[0] | K0_VM_PRESENT | K0_VM_WRITE | K0_VM_NO_EXECUTE));
    assert(!(plan.leaves[0].leaf_entry & 0x4ULL)); /* supervisor-only */
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt, pages[1], 1, 0));
    assert(!k0_vm_plan_owned_leaf(&plan, &pool, virt + K0_PAGE_SIZE, pages[0], 1, 0));
    assert(plan.count == 1);
    /* Stage an executable read-only entry; never permit W+X. */
    assert(k0_vm_plan_owned_leaf(&plan, &pool,
                                 virt + K0_PAGE_SIZE, pages[1], 0, 1));
    assert(plan.leaves[1].leaf_entry == (pages[1] | K0_VM_PRESENT));
    for (unsigned i = 2; i < 16; ++i)
        assert(k0_vm_plan_owned_leaf(&plan, &pool,
                                     virt + (K_U64)i * K0_PAGE_SIZE, pages[i], 1, 0));
    assert(plan.count == K0_VM_MAX_LEAVES);
    assert(!k0_vm_plan_owned_leaf(&plan, &pool,
                                  virt + 16 * K0_PAGE_SIZE, pages[0], 1, 0));
    assert(plan.count == K0_VM_MAX_LEAVES);
    assert(plan.pool_epoch == pool.epoch);
    for (unsigned i = 0; i < 16; ++i)
        assert(k0_pool_release(&pool, pages[i]));
    assert(!pool.active && !pool.claimed);
    puts("KOSCHEI-K0 PAGING-CONTRACT-UNIT/1 PASS (not CR3 or isolation)");
    return 0;
}
