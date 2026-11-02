#include "cr3_firmware_map_provenance.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static K0_PAGE_POOL pool;
static K0_CR3_PROPOSAL manifest;
static K0_MEMORY_DESCRIPTOR descriptors[] = {
    {7, 0, 0x200000ULL, 0, 128, 0},     /* claimed table frames */
    {1, 0, 0x400000ULL, 0, 2, 0},       /* EFI LoaderCode image */
    {2, 0, 0x600000ULL, 0, 2, 0},       /* EFI LoaderData stack */
    {4, 0, 0x700000ULL, 0, 1, 0},       /* BootServicesData IDT */
    {2, 0, 0x710000ULL, 0, 1, 0},       /* LoaderData GDT */
    {5, 0, 0x900000ULL, 0, 2, 1ULL << 63}, /* runtime code */
    {9, 0, 0x920000ULL, 0, 1, 0},       /* ACPI reclaim */
    {11, 0, 0xfec00000ULL, 0, 1, 0}    /* MMIO */
};
#define DESCRIPTOR_COUNT (sizeof(descriptors) / sizeof(descriptors[0]))
#define MAP_BYTES (sizeof(descriptors))
#define MAP_STRIDE (sizeof(descriptors[0]))

static void setup(void) {
    K0_MEMORY_PLAN plan = {0};
    assert(k0_memory_validate_plan(descriptors, MAP_BYTES,
                                   MAP_STRIDE, 1, &plan));
    assert(k0_pool_init(&pool, &plan, 1));
    for (K_U32 i = 0; i < 4; ++i)
        assert(k0_pool_claim(&pool, &manifest.root_frames[i]));
    manifest.pool_epoch = pool.epoch;
    manifest.mapping_count = 5;
    manifest.mappings[0] = (K0_CR3_MAPPING){
        0x400000ULL, 0x400000ULL, 2, K0_CR3_EXEC, K0_CR3_PROV_IMAGE};
    manifest.mappings[1] = (K0_CR3_MAPPING){
        0x600000ULL, 0x600000ULL, 2, K0_CR3_WRITE, K0_CR3_PROV_STACK};
    manifest.mappings[2] = (K0_CR3_MAPPING){
        0x700000ULL, 0x700000ULL, 1, 0, K0_CR3_PROV_CONTROL};
    manifest.mappings[3] = (K0_CR3_MAPPING){
        0x710000ULL, 0x710000ULL, 1, 0, K0_CR3_PROV_CONTROL};
    manifest.mappings[4] = (K0_CR3_MAPPING){
        0x200000ULL, 0x200000ULL, 4, K0_CR3_WRITE, K0_CR3_PROV_POOL};

    manifest.reservation_count = 4;
    manifest.reservations[0] = (K0_CR3_RESERVATION){
        0x400000ULL, 2, K0_CR3_PROV_IMAGE};
    manifest.reservations[1] = (K0_CR3_RESERVATION){
        0x600000ULL, 2, K0_CR3_PROV_STACK};
    manifest.reservations[2] = (K0_CR3_RESERVATION){
        0x700000ULL, 1, K0_CR3_PROV_CONTROL};
    manifest.reservations[3] = (K0_CR3_RESERVATION){
        0x710000ULL, 1, K0_CR3_PROV_CONTROL};

    manifest.live = (K0_CR3_LIVE_CONTEXT){
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

static int accepted(const K0_MEMORY_DESCRIPTOR *map, K_U64 bytes,
                    K_U64 stride, K_U32 version, int exited,
                    const K0_CR3_PROPOSAL *proposal) {
    return k0_cr3_uefi_map_provenance_preflight(
        proposal, &pool, map, bytes, stride, version, exited);
}
#define REJECT_MAP(change) do {                                       \
    K0_MEMORY_DESCRIPTOR wrong[DESCRIPTOR_COUNT];                    \
    memcpy(wrong, descriptors, sizeof(wrong));                         \
    change;                                                            \
    assert(!accepted(wrong, sizeof(wrong), MAP_STRIDE, 1, 1, &manifest));\
    assert(accepted(descriptors, MAP_BYTES, MAP_STRIDE, 1, 1, &manifest));\
} while (0)

int main(void) {
    setup();
    assert(k0_cr3_transition_preflight(&manifest, &pool));
    assert(accepted(descriptors, MAP_BYTES, MAP_STRIDE, 1, 1, &manifest));
    assert(!accepted(descriptors, MAP_BYTES, MAP_STRIDE, 1, 0, &manifest));
    assert(!accepted(descriptors, MAP_BYTES, MAP_STRIDE, 1, 2, &manifest));
    assert(!accepted(0, MAP_BYTES, MAP_STRIDE, 1, 1, &manifest));
    assert(!accepted(descriptors, MAP_BYTES, MAP_STRIDE, 2, 1, &manifest));
    assert(!accepted(descriptors, MAP_BYTES - 1, MAP_STRIDE, 1, 1, &manifest));
    assert(!accepted(descriptors, MAP_BYTES, MAP_STRIDE - 8, 1, 1, &manifest));
    assert(!accepted(descriptors, MAP_BYTES, MAP_STRIDE, 1, 1, 0));

    /* Reject all unsafe substitution of the claimed physical pool type. */
    REJECT_MAP(wrong[0].type = 4);
    REJECT_MAP(wrong[0].type = 11);
    REJECT_MAP(wrong[0].type = 5);
    REJECT_MAP(wrong[0].physical_start = 0x210000ULL);
    REJECT_MAP(wrong[0].number_of_pages = 15);
    REJECT_MAP(wrong[0].attributes = K0_EFI_MEMORY_RUNTIME);

    /* Code only in proven loader/boot-services CODE, never data/MMIO. */
    REJECT_MAP(wrong[1].type = 2);
    REJECT_MAP(wrong[1].type = 11);
    REJECT_MAP(wrong[1].type = 5);
    REJECT_MAP(wrong[1].attributes = K0_EFI_MEMORY_RUNTIME);
    REJECT_MAP(wrong[1].number_of_pages = 1);

    /* Stack/IDT/GDT must stay in reserved loader/boot-services DATA. */
    REJECT_MAP(wrong[2].type = 1);
    REJECT_MAP(wrong[2].type = 9);
    REJECT_MAP(wrong[3].type = 3);
    REJECT_MAP(wrong[4].type = 11);
    REJECT_MAP(wrong[3].attributes = K0_EFI_MEMORY_RUNTIME);
    REJECT_MAP(wrong[4].physical_start = 0x720000ULL);

    /* Global descriptor overlap, even far from the candidate, is unsafe. */
    REJECT_MAP(wrong[7].physical_start = 0x200000ULL);
    REJECT_MAP(wrong[6].number_of_pages = 0);
    REJECT_MAP(wrong[7].number_of_pages = ~(K_U64)0);

    /* A valid looking reservation cannot impersonate the actual image. */
    K0_CR3_PROPOSAL forged = manifest;
    forged.reservations[0].pa = 0x900000ULL;
    forged.mappings[0].va = 0x900000ULL;
    forged.mappings[0].pa = 0x900000ULL;
    forged.live.code_start = 0x900000ULL;
    forged.live.code_end = 0x902000ULL;
    forged.live.rip = 0x900120ULL;
    forged.live.pf_entry = 0x900200ULL;
    forged.live.gp_entry = 0x900300ULL;
    forged.live.df_entry = 0x900400ULL;
    forged.live.transition_entry = 0x901050ULL;
    assert(k0_cr3_transition_preflight(&forged, &pool));
    assert(!accepted(descriptors, MAP_BYTES, MAP_STRIDE, 1, 1, &forged));

    /* ABA metadata mutation invalidates preflight even when pool base
     * and physical address are unchanged after release/reclaim. */
    K_U64 old_root = manifest.root_frames[0];
    assert(k0_pool_release(&pool, old_root));
    K_U64 reused = 0;
    assert(k0_pool_claim(&pool, &reused) && reused == old_root);
    assert(!accepted(descriptors, MAP_BYTES, MAP_STRIDE, 1, 1, &manifest));
    for (K_U32 i = 0; i < 4; ++i)
        assert(k0_pool_release(&pool, manifest.root_frames[i]));
    assert(!pool.active);
    puts("KOSCHEI-K0 CR3-UEFI-MAP-PROVENANCE/1 PASS (synthetic, no CR3 write)");
    return 0;
}
