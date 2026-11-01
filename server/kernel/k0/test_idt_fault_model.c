#include "idt_fault_model.h"
/* Paging headers contain model-only static helpers unused by this focused
 * contract test; keep -Werror active for all code defined in this file.
 */
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "paging_walk.h"
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic pop
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>

static K0_IDT_GATE64 gate(uint64_t rip, uint8_t ist) {
    K0_IDT_GATE64 g = {0};
    g.offset_low = (uint16_t)rip;
    g.selector = K0_IDT_KERNEL_CS;
    g.ist = ist;
    g.type_attributes = K0_IDT_INTERRUPT_GATE;
    g.offset_mid = (uint16_t)(rip >> 16);
    g.offset_high = (uint32_t)(rip >> 32);
    return g;
}

static void test_gates(void) {
    K0_IDT_GATE64 g[15] = {0};
    const uint64_t start = 0xffffffff80001000ULL;
    const uint64_t end = 0xffffffff80002000ULL;
    g[8] = gate(start + 0x100, 1);
    g[13] = gate(start + 0x200, 0);
    g[14] = gate(start + 0x300, 0);
    assert(k0_idt_required_fault_gates_valid(g, 15, start, end));
    assert(!k0_idt_required_fault_gates_valid(g, 14, start, end));
    g[8] = (K0_IDT_GATE64){0};
    assert(!k0_idt_required_fault_gates_valid(g, 15, start, end));
    g[8] = gate(start + 0x100, 1);
    g[13].type_attributes = 0xee; /* DPL=3 */
    assert(!k0_idt_required_fault_gates_valid(g, 15, start, end));
    g[13] = gate(start + 0x200, 0);
    g[14].ist = 8;
    assert(!k0_idt_required_fault_gates_valid(g, 15, start, end));
    g[14] = gate(start + 0x301, 0);
    assert(!k0_idt_required_fault_gates_valid(g, 15, start, end));
    g[14] = gate(0x0000800000001000ULL, 0);
    assert(!k0_idt_required_fault_gates_valid(g, 15, start, end));
    g[14] = gate(end + 0x100, 0);
    assert(!k0_idt_required_fault_gates_valid(g, 15, start, end));
    g[14] = gate(start + 0x300, 0);
    g[14].reserved = 1;
    assert(!k0_idt_required_fault_gates_valid(g, 15, start, end));
}

static void test_faults(void) {
    K0_IDT_PF_REPORT pf;
    K0_VM_WALK_RESULT walk = {K0_VM_WALK_PAGE_FAULT, 0, 0};
    const uint64_t cr2 = 0xffffffff80004000ULL;
    assert(k0_idt_decode_pf(walk.predicted_error_code, cr2, &pf));
    assert(pf.fault_class == K0_WALK_FAULT_ABSENT);
    assert(k0_idt_pf_matches_predicted_walk(
        &pf, cr2, walk.kind == K0_VM_WALK_PAGE_FAULT, walk.predicted_error_code));
    assert(!k0_idt_pf_matches_predicted_walk(&pf, cr2 + 4096, 1, 0));
    assert(!k0_idt_pf_matches_predicted_walk(&pf, cr2, 0, 0));
    walk.predicted_error_code = K0_VM_PF_PRESENT | K0_VM_PF_WRITE;
    assert(k0_idt_decode_pf(walk.predicted_error_code, cr2, &pf));
    assert(pf.fault_class == K0_WALK_FAULT_READONLY_WRITE);
    assert(k0_idt_pf_matches_predicted_walk(&pf, cr2, 1, walk.predicted_error_code));
    walk.predicted_error_code = K0_VM_PF_PRESENT | K0_VM_PF_INSTRUCTION;
    assert(k0_idt_decode_pf(walk.predicted_error_code, cr2, &pf));
    assert(pf.fault_class == K0_WALK_FAULT_NX_EXEC);
    assert(k0_idt_pf_matches_predicted_walk(&pf, cr2, 1, walk.predicted_error_code));
    assert(!k0_idt_decode_pf(K0_PF_PRESENT | K0_PF_RESERVED, cr2, &pf));
    assert(pf.fault_class == K0_WALK_FAULT_RESERVED_BIT);
    assert(!k0_idt_decode_pf(K0_PF_PRESENT, cr2, &pf));
    assert(!k0_idt_decode_pf(1U << 5, cr2, &pf));
    assert(!k0_idt_decode_pf(0, 0x0000800000000000ULL, &pf));
    assert(!k0_idt_decode_pf(K0_PF_PRESENT | K0_PF_WRITE |
                             K0_PF_INSTRUCTION, cr2, &pf));
    assert(!k0_idt_decode_pf(K0_PF_PRESENT | K0_PF_USER, cr2, &pf));
    assert(!k0_idt_decode_pf(0, cr2, NULL));
}
static void test_real_paging_walk_interoperability(void) {
    const K_U64 va = K0_VM_HIGH_HALF_BASE;
    K0_MEMORY_DESCRIPTOR descriptors[] = {
        {7, 0, 0x200000ULL, 0, 128, 0},
        {3, 0, 0x100000ULL, 0, 256, 0}
    };
    K0_MEMORY_PLAN memory = {0};
    K0_PAGE_POOL pool = {0};
    K0_VM_PLAN plan = {0};
    static K0_VM_TABLE_MODEL tables;
    K_U64 pages[6] = {0};
    K_U64 frames[4] = {0};
    K0_VM_WALK_RESULT walk;
    K0_IDT_PF_REPORT pf;

    assert(k0_memory_validate_plan(descriptors, sizeof(descriptors),
                                   sizeof(descriptors[0]), 1, &memory));
    assert(k0_pool_init(&pool, &memory, 1));
    assert(k0_vm_plan_init(&plan, 1, 1));
    for (K_U32 i = 0; i < 6; ++i) assert(k0_pool_claim(&pool, &pages[i]));
    for (K_U32 i = 0; i < 4; ++i) frames[i] = pages[i];
    assert(k0_vm_plan_owned_leaf(&plan, &pool, va, pages[4], 1, 0));
    assert(k0_vm_plan_owned_leaf(&plan, &pool, va + K0_PAGE_SIZE,
                                 pages[5], 0, 1));
    assert(k0_vm_tables_build(&tables, &plan, &pool, frames));

    walk = k0_vm_model_walk(&tables, &pool, va + 2 * K0_PAGE_SIZE,
                            0, 0, 0);
    assert(walk.kind == K0_VM_WALK_PAGE_FAULT);
    assert(k0_idt_decode_pf(walk.predicted_error_code, va + 2 * K0_PAGE_SIZE, &pf));
    assert(pf.fault_class == K0_WALK_FAULT_ABSENT);
    assert(k0_idt_pf_matches_predicted_walk(&pf, va + 2 * K0_PAGE_SIZE,
             walk.kind == K0_VM_WALK_PAGE_FAULT, walk.predicted_error_code));

    walk = k0_vm_model_walk(&tables, &pool, va + K0_PAGE_SIZE,
                            1, 0, 0);
    assert(walk.kind == K0_VM_WALK_PAGE_FAULT);
    assert(k0_idt_decode_pf(walk.predicted_error_code, va + K0_PAGE_SIZE, &pf));
    assert(pf.fault_class == K0_WALK_FAULT_READONLY_WRITE);
    assert(k0_idt_pf_matches_predicted_walk(&pf, va + K0_PAGE_SIZE,
             walk.kind == K0_VM_WALK_PAGE_FAULT, walk.predicted_error_code));

    walk = k0_vm_model_walk(&tables, &pool, va, 0, 1, 0);
    assert(walk.kind == K0_VM_WALK_PAGE_FAULT);
    assert(k0_idt_decode_pf(walk.predicted_error_code, va, &pf));
    assert(pf.fault_class == K0_WALK_FAULT_NX_EXEC);
    assert(k0_idt_pf_matches_predicted_walk(&pf, va,
             walk.kind == K0_VM_WALK_PAGE_FAULT, walk.predicted_error_code));

    walk = k0_vm_model_walk(&tables, &pool, 0x0000800000000000ULL,
                            0, 0, 0);
    assert(walk.kind == K0_VM_WALK_GENERAL_PROTECTION);
    assert(!k0_idt_pf_matches_predicted_walk(
        &pf, 0x0000800000000000ULL,
        walk.kind == K0_VM_WALK_PAGE_FAULT, walk.predicted_error_code));

    for (K_U32 i = 0; i < 6; ++i) assert(k0_pool_release(&pool, pages[i]));
}

int main(void) {
    test_gates();
    test_faults();
    test_real_paging_walk_interoperability();
    puts("K0.4 IDT/FAULT-MODEL PREFLIGHT PASS (synthetic, not hardware proof)");
    return 0;
}
