#include "owned_tables_dryrun.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static K0_PAGE_POOL pool;
static K0_VM_PLAN plan;
static K0_VM_TABLE_MODEL model;
static K_U64 pages[6];
static K_U64 physical_tables[4][512];
static int refuse_read;
static unsigned calls;

static int memory_read(void *ctx, K_U64 physical, K_U32 slot, K_U64 *out) {
    (void)ctx;
    ++calls;
    if (refuse_read || slot >= 512 || !out) return 0;
    for (unsigned j = 0; j < 4; ++j) {
        if (physical == pages[j] && k0_pool_is_claimed(&pool, pages[j])) {
            *out = physical_tables[j][slot];
            return 1;
        }
    }
    return 0;
}
static void fixture(void) {
    const K0_MEMORY_DESCRIPTOR map[] = {
        {7, 0, 0x200000ULL, 0, 128, 0},
        {3, 0, 0x100000ULL, 0, 128, 0},
    };
    K0_MEMORY_PLAN mem = {0};
    assert(k0_memory_validate_plan(map, sizeof(map), sizeof(map[0]), 1,
                                   &mem));
    assert(k0_pool_init(&pool, &mem, 1));
    for (unsigned i = 0; i < 6; ++i)
        assert(k0_pool_claim(&pool, &pages[i]));
    assert(k0_vm_plan_init(&plan, 1, 1));
    assert(k0_vm_plan_owned_leaf(&plan, &pool, K0_VM_HIGH_HALF_BASE,
                                 pages[4], 1, 0));
    assert(k0_vm_plan_owned_leaf(&plan, &pool,
                                 K0_VM_HIGH_HALF_BASE + K0_PAGE_SIZE,
                                 pages[5], 0, 1));
    assert(k0_vm_tables_build(&model, &plan, &pool, pages));
    for (unsigned i = 0; i < 4; ++i)
        memcpy(physical_tables[i], model.entries[i], sizeof(physical_tables[i]));
}
static int verify(void) {
    return k0_owned_tables_dryrun_verify(&model, &plan, &pool,
                                         0x800000ULL, memory_read, 0);
}
int main(void) {
    fixture();
    assert(verify());
    assert(calls >= 2048U + 8U);
    assert(!k0_owned_tables_dryrun_verify(&model, &plan, &pool,
                                          0x800000ULL, 0, 0));
    assert(!k0_owned_tables_dryrun_verify(0, &plan, &pool,
                                          0x800000ULL, memory_read, 0));
    assert(!k0_owned_tables_dryrun_verify(&model, &plan, &pool,
                                          pages[0], memory_read, 0));
    assert(!k0_owned_tables_dryrun_verify(&model, &plan, &pool,
                                          0, memory_read, 0));
    refuse_read = 1; assert(!verify()); refuse_read = 0;

    /* Changing even a nominally unused PTE must invalidate readback. */
    physical_tables[0][400] ^= 1ULL;
    assert(!verify());
    physical_tables[0][400] ^= 1ULL;
    assert(verify());

    /* Reconstructed expected tables reject a matched forgery of both
     * model bytes AND physical frame data, including silent W+X aliases.
     */
    physical_tables[3][0] &= ~K0_VM_NO_EXECUTE;
    model.entries[3][0] &= ~K0_VM_NO_EXECUTE;
    assert(!verify());
    physical_tables[3][0] |= K0_VM_NO_EXECUTE;
    model.entries[3][0] |= K0_VM_NO_EXECUTE;
    assert(verify());

    physical_tables[3][1] |= K0_VM_WRITE;
    model.entries[3][1] |= K0_VM_WRITE;
    assert(!verify());
    physical_tables[3][1] &= ~K0_VM_WRITE;
    model.entries[3][1] &= ~K0_VM_WRITE;
    assert(verify());

    physical_tables[3][1] |= K0_VM_NO_EXECUTE;
    assert(!verify());
    physical_tables[3][1] &= ~K0_VM_NO_EXECUTE;
    assert(verify());

    K0_VM_PLAN illegal = plan;
    illegal.leaves[0].virtual_page = 0x1000ULL;
    assert(!k0_owned_tables_dryrun_verify(&model, &illegal, &pool,
                                           0x800000ULL, memory_read, 0));
    illegal = plan;
    illegal.leaves[0].leaf_entry &= ~K0_VM_NO_EXECUTE;
    assert(!k0_owned_tables_dryrun_verify(&model, &illegal, &pool,
                                           0x800000ULL, memory_read, 0));
    illegal = plan;
    illegal.leaves[1].physical_page = pages[4];
    assert(!k0_owned_tables_dryrun_verify(&model, &illegal, &pool,
                                           0x800000ULL, memory_read, 0));
    illegal = plan;
    illegal.count = 1;
    assert(!k0_owned_tables_dryrun_verify(&model, &illegal, &pool,
                                           0x800000ULL, memory_read, 0));

    K0_VM_TABLE_MODEL forged = model;
    forged.table_phys[3] = forged.table_phys[0];
    assert(!k0_owned_tables_dryrun_verify(&forged, &plan, &pool,
                                           0x800000ULL, memory_read, 0));
    assert(verify());

    /* Releasing and re-claiming the same frame must invalidate epoch. */
    assert(k0_pool_release(&pool, pages[4]));
    assert(!verify());
    K_U64 reclaimed = 0;
    assert(k0_pool_claim(&pool, &reclaimed) && reclaimed == pages[4]);
    assert(!verify());
    for (unsigned i = 0; i < 6; ++i)
        assert(k0_pool_release(&pool, pages[i]));
    assert(!pool.active);
    puts("KOSCHEI-K0 OWNED-TABLES-DRYRUN/1 PASS (physical byte model; NO CR3 write)");
    return 0;
}
