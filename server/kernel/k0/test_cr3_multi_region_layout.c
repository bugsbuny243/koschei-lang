#include "cr3_multi_region_layout.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static K0_CR3_PROPOSAL proposal, altered;
static K0_PAGE_POOL pool;
static K0_MR_LAYOUT layout;
static K_U64 frames[6];
static K0_MEMORY_DESCRIPTOR memory[] = {
    {7, 0, 0x200000ULL, 0, 128, 0},   /* 16-page claimed pool inside */
    {1, 0, 0x400000ULL, 0, 2, 0},     /* LoaderCode */
    {2, 0, 0x600000ULL, 0, 2, 0},     /* LoaderData stack */
    {4, 0, 0x700000ULL, 0, 1, 0},     /* BootServicesData IDT */
    {2, 0, 0x710000ULL, 0, 1, 0},     /* LoaderData GDT */
    {5, 0, 0x900000ULL, 0, 2, 1ULL << 63},
    {9, 0, 0x920000ULL, 0, 1, 0},
    {11, 0, 0xfec00000ULL, 0, 1, 0},
    {1, 0, 0x50000000ULL, 0, 1, 0} /* valid code across a 1GiB boundary */
};
#define MAP_BYTES (sizeof(memory))
#define MAP_STRIDE (sizeof(memory[0]))

static void fixture(void) {
    K0_MEMORY_PLAN plan = {0};
    assert(k0_memory_validate_plan(memory, MAP_BYTES, MAP_STRIDE, 1, &plan));
    assert(k0_pool_init(&pool, &plan, 1));
    for (K_U32 i = 0; i < 6; ++i)
        assert(k0_pool_claim(&pool, &frames[i]));
    for (K_U32 i = 0; i < 4; ++i)
        proposal.root_frames[i] = frames[i];
    proposal.pool_epoch = pool.epoch;
    proposal.mapping_count = 5;
    proposal.mappings[0] = (K0_CR3_MAPPING){
        0x400000ULL, 0x400000ULL, 2, K0_CR3_EXEC, K0_CR3_PROV_IMAGE};
    proposal.mappings[1] = (K0_CR3_MAPPING){
        0x600000ULL, 0x600000ULL, 2, K0_CR3_WRITE, K0_CR3_PROV_STACK};
    proposal.mappings[2] = (K0_CR3_MAPPING){
        0x700000ULL, 0x700000ULL, 1, 0, K0_CR3_PROV_CONTROL};
    proposal.mappings[3] = (K0_CR3_MAPPING){
        0x710000ULL, 0x710000ULL, 1, 0, K0_CR3_PROV_CONTROL};
    proposal.mappings[4] = (K0_CR3_MAPPING){
        0x200000ULL, 0x200000ULL, 6, K0_CR3_WRITE, K0_CR3_PROV_POOL};
    proposal.reservation_count = 4;
    proposal.reservations[0] = (K0_CR3_RESERVATION){
        0x400000ULL, 2, K0_CR3_PROV_IMAGE};
    proposal.reservations[1] = (K0_CR3_RESERVATION){
        0x600000ULL, 2, K0_CR3_PROV_STACK};
    proposal.reservations[2] = (K0_CR3_RESERVATION){
        0x700000ULL, 1, K0_CR3_PROV_CONTROL};
    proposal.reservations[3] = (K0_CR3_RESERVATION){
        0x710000ULL, 1, K0_CR3_PROV_CONTROL};
    proposal.live = (K0_CR3_LIVE_CONTEXT){
        .old_cr3 = 0x800000ULL,
        .cr0 = 1ULL | (1ULL << 16) | (1ULL << 31),
        .cr4 = 1ULL << 5,
        .efer = (1ULL << 8) | (1ULL << 10) | (1ULL << 11),
        .rflags = 2, .cs = 8, .nx_cpuid_supported = 1,
        .rip = 0x400120ULL, .rsp = 0x601ff0ULL,
        .pf_entry = 0x400200ULL, .gp_entry = 0x400300ULL,
        .df_entry = 0x400400ULL, .transition_entry = 0x401050ULL,
        .code_start = 0x400000ULL, .code_end = 0x402000ULL,
        .stack_start = 0x600000ULL, .stack_end = 0x602000ULL,
        .idt_start = 0x700000ULL, .idt_end = 0x701000ULL,
        .gdt_start = 0x710000ULL, .gdt_end = 0x711000ULL
    };
}
static int attempt(const K0_CR3_PROPOSAL *p, const K_U64 *f, K_U32 n,
                   const K0_MEMORY_DESCRIPTOR *map, int exited) {
    return k0_mr_build(p, &pool, map, MAP_BYTES, MAP_STRIDE, 1,
                       exited, f, n, &layout);
}
#define REFUSE(change) do {                                 \
    altered = proposal;                                      \
    change;                                                  \
    assert(!attempt(&altered, frames, 6, memory, 1));         \
    assert(attempt(&proposal, frames, 6, memory, 1));         \
} while (0)

static void check(K_U64 va, K_U64 pa, K_U32 write, K_U32 nx) {
    K0_CR3_I_RESULT got = {0};
    assert(k0_cr3_inspect_translation(layout.root, va,
                                      k0_mr_read, &layout, &got));
    assert(got.physical_address == pa && got.leaf_page_shift == 12);
    assert(got.effective_write == write && got.effective_nx == nx);
    assert(got.effective_user == 0);
}
int main(void) {
    fixture();
    assert(attempt(&proposal, frames, 6, memory, 1));
    assert(layout.ready && layout.frame_count == 6 &&
           layout.pt_count == 3 && layout.mapped_pages == 12 &&
           layout.root == frames[0] && layout.pool_epoch == pool.epoch);
    assert(k0_mr_verify(&layout, &proposal, &pool, memory,
                         MAP_BYTES, MAP_STRIDE, 1, 1, frames, 6));
    check(0x400000ULL, 0x400000ULL, 0, 0);
    check(0x401fffULL, 0x401fffULL, 0, 0);
    check(0x600000ULL, 0x600000ULL, 1, 1);
    check(0x601fffULL, 0x601fffULL, 1, 1);
    check(0x700000ULL, 0x700000ULL, 0, 1);
    check(0x710000ULL, 0x710000ULL, 0, 1);
    check(0x205000ULL, 0x205000ULL, 1, 1);
    K0_CR3_I_RESULT absent = {0};
    assert(!k0_cr3_inspect_translation(layout.root, 0x500000ULL,
                                      k0_mr_read, &layout, &absent));
    assert(!k0_cr3_inspect_translation(layout.root, 0x702000ULL,
                                      k0_mr_read, &layout, &absent));
    assert(!k0_cr3_inspect_translation(layout.root, 0x1000ULL,
                                      k0_mr_read, &layout, &absent));
    assert(!k0_cr3_inspect_translation(layout.root, 0xfffffffffffff000ULL,
                                      k0_mr_read, &layout, &absent));

    /* Capacity, duplicate/foreign frames and wrong primary frame order. */
    assert(!attempt(&proposal, frames, 5, memory, 1));
    assert(!attempt(&proposal, frames, 7, memory, 1));
    K_U64 saved = frames[5];
    frames[5] = frames[3];
    assert(!attempt(&proposal, frames, 6, memory, 1));
    frames[5] = 0x210000ULL;
    assert(!attempt(&proposal, frames, 6, memory, 1));
    frames[5] = saved;
    saved = frames[3]; frames[3] = frames[4];
    assert(!attempt(&proposal, frames, 6, memory, 1));
    frames[3] = saved;
    assert(!attempt(&proposal, frames, 6, memory, 0));
    assert(attempt(&proposal, frames, 6, memory, 1));

    /* Model result is invalidated when its physical-page bytes change. */
    K_U64 original = layout.tables[3].entries[0];
    layout.tables[3].entries[0] = (original | K0_MR_RW) | K0_MR_NX;
    check(0x400000ULL, 0x400000ULL, 1, 1);
    assert(!k0_mr_verify(&layout, &proposal, &pool, memory,
                          MAP_BYTES, MAP_STRIDE, 1, 1, frames, 6));
    layout.tables[3].entries[0] = original;
    assert(k0_mr_verify(&layout, &proposal, &pool, memory,
                         MAP_BYTES, MAP_STRIDE, 1, 1, frames, 6));
    layout.tables[0].entries[400] |= 1ULL;
    assert(!k0_mr_verify(&layout, &proposal, &pool, memory,
                          MAP_BYTES, MAP_STRIDE, 1, 1, frames, 6));
    assert(attempt(&proposal, frames, 6, memory, 1));
    check(0x400000ULL, 0x400000ULL, 0, 0);

    /* Mutation of any declared transition requirement fails closed. */
    REFUSE(altered.mappings[0].pages = 1);
    REFUSE(altered.mappings[1].flags = K0_CR3_EXEC | K0_CR3_WRITE);
    REFUSE(altered.live.pf_entry = 0x500000ULL);
    REFUSE(altered.live.rsp = 0x700000ULL);
    REFUSE(altered.mappings[4].pages = 5);
    REFUSE(altered.reservations[2].pa = 0x720000ULL);
    REFUSE(altered.pool_epoch -= 1);

    /* This extra mapping is semantically legitimate (and fully reserved
     * in the final UEFI map), but requires a SECOND PDPT/PD hierarchy.
     * This deliberately bounded builder must reject it rather than
     * silently dropping an executable region from the proposed CR3.
     */
    altered = proposal;
    altered.mappings[5] = (K0_CR3_MAPPING){
        0x50000000ULL, 0x50000000ULL, 1,
        K0_CR3_EXEC, K0_CR3_PROV_IMAGE};
    altered.reservations[4] = (K0_CR3_RESERVATION){
        0x50000000ULL, 1, K0_CR3_PROV_IMAGE};
    altered.mapping_count = 6;
    altered.reservation_count = 5;
    assert(k0_cr3_uefi_map_provenance_preflight(
        &altered, &pool, memory, MAP_BYTES, MAP_STRIDE, 1, 1));
    assert(!attempt(&altered, frames, 6, memory, 1));
    assert(attempt(&proposal, frames, 6, memory, 1));

    /* Firmware type corruption is caught before table construction. */
    K0_MEMORY_DESCRIPTOR corrupted[sizeof(memory)/sizeof(memory[0])];
    memcpy(corrupted, memory, sizeof(corrupted));
    corrupted[1].type = 2;
    assert(!attempt(&proposal, frames, 6, corrupted, 1));
    memcpy(corrupted, memory, sizeof(corrupted));
    corrupted[0].attributes = 1ULL << 63;
    assert(!attempt(&proposal, frames, 6, corrupted, 1));

    /* A release and same-frame reclaim still invalidates pool epoch. */
    assert(k0_pool_release(&pool, frames[5]));
    K_U64 reclaim = 0;
    assert(k0_pool_claim(&pool, &reclaim) && reclaim == frames[5]);
    assert(!attempt(&proposal, frames, 6, memory, 1));
    for (K_U32 i = 0; i < 6; ++i)
        assert(k0_pool_release(&pool, frames[i]));
    assert(!pool.active);
    puts("KOSCHEI-K0 MULTI-REGION-CR3-LAYOUT/1 PASS (host data only; NO CR3 write)");
    return 0;
}
