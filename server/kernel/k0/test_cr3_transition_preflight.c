#include "cr3_transition_preflight.h"
#include <assert.h>
#include <stdio.h>

static K0_CR3_PROPOSAL baseline;
static K0_CR3_PROPOSAL mutated;
static K0_PAGE_POOL pool;

static void fixture(void) {
    const K0_MEMORY_DESCRIPTOR desc[] = {
        {7, 0, 0x200000ULL, 0, 128, 0},
        {3, 0, 0x100000ULL, 0, 256, 0}
    };
    K0_MEMORY_PLAN memory = {0};
    assert(k0_memory_validate_plan(desc, sizeof(desc),
                                   sizeof(desc[0]), 1, &memory));
    assert(k0_pool_init(&pool, &memory, 1));
    for (K_U32 i = 0; i < 4; ++i)
        assert(k0_pool_claim(&pool, &baseline.root_frames[i]));
    baseline.pool_epoch = pool.epoch;
    baseline.mapping_count = 5;
    baseline.mappings[0] = (K0_CR3_MAPPING){
        0x400000ULL, 0x400000ULL, 2, K0_CR3_EXEC, K0_CR3_PROV_IMAGE
    };
    baseline.mappings[1] = (K0_CR3_MAPPING){
        0x600000ULL, 0x600000ULL, 2, K0_CR3_WRITE, K0_CR3_PROV_STACK
    };
    baseline.mappings[2] = (K0_CR3_MAPPING){
        0x700000ULL, 0x700000ULL, 1, 0, K0_CR3_PROV_CONTROL
    };
    baseline.mappings[3] = (K0_CR3_MAPPING){
        0x710000ULL, 0x710000ULL, 1, 0, K0_CR3_PROV_CONTROL
    };
    baseline.mappings[4] = (K0_CR3_MAPPING){
        0x200000ULL, 0x200000ULL, 4, K0_CR3_WRITE, K0_CR3_PROV_POOL
    };
    baseline.reservation_count = 4;
    baseline.reservations[0] = (K0_CR3_RESERVATION){
        0x400000ULL, 2, K0_CR3_PROV_IMAGE
    };
    baseline.reservations[1] = (K0_CR3_RESERVATION){
        0x600000ULL, 2, K0_CR3_PROV_STACK
    };
    baseline.reservations[2] = (K0_CR3_RESERVATION){
        0x700000ULL, 1, K0_CR3_PROV_CONTROL
    };
    baseline.reservations[3] = (K0_CR3_RESERVATION){
        0x710000ULL, 1, K0_CR3_PROV_CONTROL
    };
    baseline.live = (K0_CR3_LIVE_CONTEXT){
        .old_cr3 = 0x800000ULL,
        .cr0 = (1ULL << 0) | (1ULL << 16) | (1ULL << 31),
        .cr4 = (1ULL << 5),
        .efer = (1ULL << 8) | (1ULL << 10) | (1ULL << 11),
        .rflags = 2,
        .cs = 8,
        .nx_cpuid_supported = 1,
        .rip = 0x400120ULL,
        .rsp = 0x601ff0ULL,
        .pf_entry = 0x400200ULL,
        .gp_entry = 0x400300ULL,
        .df_entry = 0x400400ULL,
        .transition_entry = 0x401050ULL,
        .code_start = 0x400000ULL,
        .code_end = 0x402000ULL,
        .stack_start = 0x600000ULL,
        .stack_end = 0x602000ULL,
        .idt_start = 0x700000ULL,
        .idt_end = 0x701000ULL,
        .gdt_start = 0x710000ULL,
        .gdt_end = 0x711000ULL
    };
}

#define REJECT(expression) do {                                      \
    mutated = baseline;                                               \
    expression;                                                       \
    assert(!k0_cr3_transition_preflight(&mutated, &pool));             \
    assert(k0_cr3_transition_preflight(&baseline, &pool));             \
} while (0)

int main(void) {
    fixture();
    assert(k0_cr3_transition_preflight(&baseline, &pool));
    assert(!k0_cr3_transition_preflight(0, &pool));
    assert(!k0_cr3_transition_preflight(&baseline, 0));

    /* Coverage must include every page, not merely RIP and current RSP. */
    REJECT(mutated.mappings[0].pages = 1);
    REJECT(mutated.mappings[1].pages = 1);
    REJECT(mutated.mapping_count = 4);
    REJECT(mutated.live.pf_entry = 0x500000ULL);
    REJECT(mutated.live.transition_entry = 0x402000ULL);
    REJECT(mutated.live.rsp = 0x602001ULL);
    REJECT(mutated.live.idt_end = 0x702000ULL);
    REJECT(mutated.live.code_end = 0x401fffULL);
    REJECT(mutated.live.stack_start = 0x600001ULL);
    REJECT(mutated.live.gdt_end = 0x710000ULL);
    REJECT(mutated.live.rip = 0x0000800000000000ULL);

    /* Privilege/W^X/NX/CR0.WP/LA57/PCID/IF are fail-closed. */
    REJECT(mutated.mappings[0].flags |= K0_CR3_WRITE);
    REJECT(mutated.mappings[1].flags |= K0_CR3_EXEC);
    REJECT(mutated.mappings[4].flags |= K0_CR3_USER);
    REJECT(mutated.live.cr0 &= ~(1ULL << 16));
    REJECT(mutated.live.cr0 &= ~(1ULL << 31));
    REJECT(mutated.live.cr4 &= ~(1ULL << 5));
    REJECT(mutated.live.cr4 |= (1ULL << 12));
    REJECT(mutated.live.cr4 |= (1ULL << 17));
    REJECT(mutated.live.efer &= ~(1ULL << 11));
    REJECT(mutated.live.nx_cpuid_supported = 0);
    REJECT(mutated.live.rflags |= (1ULL << 9));
    REJECT(mutated.live.cs = 0x1b);
    REJECT(mutated.live.old_cr3 = 0);
    REJECT(mutated.live.old_cr3 = 0x800008ULL);
    REJECT(mutated.pool_epoch = pool.epoch - 1);

    /* Physical ownership, reservation provenance, aliases and overflow. */
    REJECT(mutated.root_frames[0] = mutated.root_frames[1]);
    REJECT(mutated.root_frames[3] = 0x900000ULL);
    REJECT(mutated.mappings[4].pa = 0x300000ULL);
    REJECT(mutated.mappings[4].va = 0xffff800000200000ULL);
    REJECT(mutated.mappings[0].pa = 0x900000ULL);
    REJECT(mutated.mappings[2].provenance = K0_CR3_PROV_IMAGE);
    REJECT(mutated.reservations[0].pa = 0x200000ULL);
    REJECT(mutated.reservations[3].pa = 0x700000ULL);
    REJECT(mutated.mappings[0].pages = 0);
    REJECT(mutated.mappings[0].pages = ~(K_U64)0);
    REJECT(mutated.mappings[0].va = 0x00007fffffffe000ULL);
    REJECT(mutated.mappings[0].pa = 0x000ffffffffff000ULL);
    REJECT(mutated.mapping_count = K0_CR3_MAX_MAPPINGS + 1);
    REJECT(mutated.reservation_count = K0_CR3_MAX_RESERVATIONS + 1);

    mutated = baseline;
    mutated.mapping_count = 6;
    mutated.mappings[5] = (K0_CR3_MAPPING){
        0x400000ULL, 0x400000ULL, 1, K0_CR3_EXEC, K0_CR3_PROV_IMAGE
    };
    assert(!k0_cr3_transition_preflight(&mutated, &pool));
    assert(k0_cr3_transition_preflight(&baseline, &pool));

    /* A release+reclaim at the same address must still invalidate snapshot. */
    const K_U64 original = baseline.root_frames[0];
    assert(k0_pool_release(&pool, original));
    K_U64 reclaimed = 0;
    assert(k0_pool_claim(&pool, &reclaimed) && reclaimed == original);
    assert(!k0_cr3_transition_preflight(&baseline, &pool));
    for (K_U32 i = 0; i < 4; ++i)
        assert(k0_pool_release(&pool, baseline.root_frames[i]));
    assert(pool.active == 0);
    puts("KOSCHEI-K0 CR3-TRANSITION-PREFLIGHT/1 PASS (manifest only; NO CR3 write)");
    return 0;
}
