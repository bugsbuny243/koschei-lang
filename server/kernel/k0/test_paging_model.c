#include "paging_model.h"
#include <assert.h>
#include <stdio.h>

static K0_VM_TABLE_MODEL tables;
static K0_VM_TABLE_MODEL invalid_tables;

int main(void) {
    const K_U64 virt = K0_VM_HIGH_HALF_BASE;
    K0_MEMORY_DESCRIPTOR map[] = {
        {7, 0, 0x200000ULL, 0, 128, 0},
        {3, 0, 0x100000ULL, 0, 256, 0},
    };
    K0_MEMORY_PLAN candidate = {0};
    K0_PAGE_POOL pool = {0};
    K0_VM_PLAN plan = {0};
    K_U64 pages[7] = {0};
    K_U64 frames[4] = {0};
    assert(k0_memory_validate_plan(map, sizeof(map), sizeof(map[0]), 1, &candidate));
    assert(k0_pool_init(&pool, &candidate, 1));
    assert(k0_vm_plan_init(&plan, 1, 1));
    for (K_U32 i = 0; i < 7; ++i) assert(k0_pool_claim(&pool, &pages[i]));
    for (K_U32 i = 0; i < 4; ++i) frames[i] = pages[i];
    assert(k0_vm_plan_owned_leaf(&plan, &pool, virt, pages[4], 1, 0));
    assert(k0_vm_plan_owned_leaf(&plan, &pool, virt + K0_PAGE_SIZE, pages[5], 0, 1));

    K_U64 alias_frames[4] = {pages[0], pages[0], pages[2], pages[3]};
    assert(!k0_vm_tables_build(&invalid_tables, &plan, &pool, alias_frames));
    assert(!invalid_tables.initialized);
    K_U64 unowned_frames[4] = {pages[0], pages[1], pages[2], 0x100000ULL};
    assert(!k0_vm_tables_build(&invalid_tables, &plan, &pool, unowned_frames));
    K_U64 data_alias_frames[4] = {pages[0], pages[1], pages[2], pages[4]};
    assert(!k0_vm_tables_build(&invalid_tables, &plan, &pool, data_alias_frames));

    K0_VM_PLAN cross_pt = plan;
    cross_pt.leaves[1].virtual_page = virt + 0x200000ULL;
    assert(!k0_vm_tables_build(&invalid_tables, &cross_pt, &pool, frames));
    K0_VM_PLAN forged_wx = plan;
    forged_wx.leaves[0].leaf_entry &= ~K0_VM_NO_EXECUTE;
    assert(!k0_vm_tables_build(&invalid_tables, &forged_wx, &pool, frames));
    K0_VM_PLAN forged_user = plan;
    forged_user.leaves[0].leaf_entry |= 4ULL;
    assert(!k0_vm_tables_build(&invalid_tables, &forged_user, &pool, frames));
    assert(!invalid_tables.initialized && !invalid_tables.entries[0][256]);

    assert(k0_vm_level_index(virt, 39) == 256U);
    assert(k0_vm_level_index(virt, 30) == 0U);
    assert(k0_vm_level_index(virt, 21) == 0U);
    assert(k0_vm_level_index(virt, 12) == 0U);
    assert(k0_vm_tables_build(&tables, &plan, &pool, frames));
    assert(tables.initialized);
    assert(tables.entries[0][256] == (frames[1] | K0_VM_PRESENT | K0_VM_WRITE));
    assert(tables.entries[1][0] == (frames[2] | K0_VM_PRESENT | K0_VM_WRITE));
    assert(tables.entries[2][0] == (frames[3] | K0_VM_PRESENT | K0_VM_WRITE));
    assert(tables.entries[3][0] == plan.leaves[0].leaf_entry);
    assert(tables.entries[3][1] == plan.leaves[1].leaf_entry);
    assert(tables.entries[3][2] == 0);
    assert(tables.entries[0][0] == 0);
    assert(!k0_vm_tables_build(&tables, &plan, &pool, frames));

    /* A stale model must not be built after losing page ownership. This
     * does NOT handle the separate generation/ABA reclamation problem.
     */
    assert(k0_pool_release(&pool, pages[4]));
    assert(!k0_vm_tables_build(&invalid_tables, &plan, &pool, frames));
    K_U64 reclaimed = 0;
    assert(k0_pool_claim(&pool, &reclaimed) && reclaimed == pages[4]);
    for (K_U32 i = 0; i < 7; ++i) assert(k0_pool_release(&pool, pages[i]));
    assert(!pool.active && !pool.claimed);
    puts("KOSCHEI-K0 PAGE-TABLE-MODEL-UNIT/1 PASS (not CR3 or isolation)");
    return 0;
}
