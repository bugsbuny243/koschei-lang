#include "paging_walk.h"
#include <assert.h>
#include <stdio.h>

static K0_VM_TABLE_MODEL tables;
static K0_VM_TABLE_MODEL corrupted;

static void expect(const K0_VM_TABLE_MODEL *table, const K0_PAGE_POOL *pool,
                   K_U64 va, int write, int execute, int user,
                   K0_VM_WALK_KIND kind, K_U32 code, K_U64 phys) {
    K0_VM_WALK_RESULT result =
        k0_vm_model_walk(table, pool, va, write, execute, user);
    assert(result.kind == kind);
    assert(result.predicted_error_code == code);
    assert(result.resolved_physical == phys);
}

int main(void) {
    const K_U64 va = K0_VM_HIGH_HALF_BASE;
    K0_MEMORY_DESCRIPTOR map[] = {
        {7, 0, 0x200000ULL, 0, 128, 0},
        {3, 0, 0x100000ULL, 0, 256, 0}
    };
    K0_MEMORY_PLAN memory = {0};
    K0_PAGE_POOL pool = {0};
    K0_VM_PLAN plan = {0};
    K_U64 pages[6] = {0};
    K_U64 frames[4] = {0};

    assert(k0_memory_validate_plan(map, sizeof(map), sizeof(map[0]), 1, &memory));
    assert(k0_pool_init(&pool, &memory, 1));
    assert(k0_vm_plan_init(&plan, 1, 1));
    for (K_U32 i = 0; i < 6; ++i) assert(k0_pool_claim(&pool, &pages[i]));
    for (K_U32 i = 0; i < 4; ++i) frames[i] = pages[i];
    assert(k0_vm_plan_owned_leaf(&plan, &pool, va, pages[4], 1, 0));
    assert(k0_vm_plan_owned_leaf(&plan, &pool, va + K0_PAGE_SIZE, pages[5], 0, 1));
    assert(k0_vm_tables_build(&tables, &plan, &pool, frames));

    expect(&tables, &pool, va + 0x75, 0, 0, 0, K0_VM_WALK_ALLOW, 0, pages[4] + 0x75);
    expect(&tables, &pool, va, 1, 0, 0, K0_VM_WALK_ALLOW, 0, pages[4]);
    expect(&tables, &pool, va, 0, 1, 0, K0_VM_WALK_PAGE_FAULT, 17, 0); /* NX */
    expect(&tables, &pool, va + K0_PAGE_SIZE, 0, 1, 0,
           K0_VM_WALK_ALLOW, 0, pages[5]);
    expect(&tables, &pool, va + K0_PAGE_SIZE, 1, 0, 0,
           K0_VM_WALK_PAGE_FAULT, 3, 0); /* read-only */
    expect(&tables, &pool, va, 0, 0, 1, K0_VM_WALK_PAGE_FAULT, 5, 0); /* US */
    expect(&tables, &pool, va + 2 * K0_PAGE_SIZE, 0, 0, 0,
           K0_VM_WALK_PAGE_FAULT, 0, 0); /* absent */
    expect(&tables, &pool, va + 2 * K0_PAGE_SIZE, 1, 0, 0,
           K0_VM_WALK_PAGE_FAULT, 2, 0); /* absent write */
    expect(&tables, &pool, va + 2 * K0_PAGE_SIZE, 0, 0, 1,
           K0_VM_WALK_PAGE_FAULT, 4, 0); /* absent USER: P must be 0 */
    expect(&tables, &pool, va + 2 * K0_PAGE_SIZE, 1, 0, 1,
           K0_VM_WALK_PAGE_FAULT, 6, 0); /* absent USER+WRITE: P=0 */
    expect(&tables, &pool, va + 2 * K0_PAGE_SIZE, 0, 1, 1,
           K0_VM_WALK_PAGE_FAULT, 20, 0); /* absent USER+INSTR: P=0 */
    expect(&tables, &pool, va + 2 * K0_PAGE_SIZE, 0, 1, 0,
           K0_VM_WALK_PAGE_FAULT, 16, 0); /* absent instruction */
    expect(&tables, &pool, K0_VM_TOP_GUARD_START, 0, 0, 0,
           K0_VM_WALK_PAGE_FAULT, 0, 0); /* policy guard */
    expect(&tables, &pool, 0x0000800000000000ULL, 0, 0, 0,
           K0_VM_WALK_GENERAL_PROTECTION, 0, 0); /* #GP != #PF */
    expect(&tables, &pool, 0x400000ULL, 0, 0, 0,
           K0_VM_WALK_PAGE_FAULT, 0, 0); /* low canonical */

    corrupted = tables;
    corrupted.entries[0][256] = 0;
    expect(&corrupted, &pool, va, 0, 0, 0, K0_VM_WALK_PAGE_FAULT, 0, 0);
    corrupted = tables;
    corrupted.entries[0][256] = pages[5] | K0_VM_PRESENT | K0_VM_WRITE;
    expect(&corrupted, &pool, va, 0, 0, 0, K0_VM_WALK_INVALID_MODEL, 0, 0);
    corrupted = tables;
    corrupted.entries[3][0] |= 4ULL; /* forged user bit */
    expect(&corrupted, &pool, va, 0, 0, 0, K0_VM_WALK_INVALID_MODEL, 0, 0);
    expect(0, &pool, va, 0, 0, 0, K0_VM_WALK_INVALID_MODEL, 0, 0);

    /* After an ABA release-and-reclaim, the logical table model is stale. */
    assert(k0_pool_release(&pool, pages[4]));
    K_U64 again = 0;
    assert(k0_pool_claim(&pool, &again) && again == pages[4]);
    expect(&tables, &pool, va, 0, 0, 0, K0_VM_WALK_INVALID_MODEL, 0, 0);

    for (K_U32 i = 0; i < 6; ++i) assert(k0_pool_release(&pool, pages[i]));
    assert(pool.claimed == 0 && pool.active == 0);
    puts("KOSCHEI-K0 PAGING-WALK-MODEL/1 PASS (synthetic #PF/#GP only)");
    return 0;
}
