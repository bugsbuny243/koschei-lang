#ifndef KOSCHEI_K0_CPU_PF_GUEST_PROBE_H
#define KOSCHEI_K0_CPU_PF_GUEST_PROBE_H
/*
 * QEMU-ONLY x86-64 CPU exception evidence under the EXISTING FIRMWARE CR3.
 * Not a production ISR, independent page table, or isolation proof.
 * The caller must have disabled interrupts and must never return to firmware.
 * The exception entry preserves integer registers and explicitly normalizes
 * the hardware #PF error-code/RIP stack layout before resuming at a known label.
 */
#include <stdint.h>
#include <stddef.h>

#define K0_CPU_PF_SENTINEL 0x0000400000000000ULL
typedef struct __attribute__((packed)) {
    uint16_t offset_lo;
    uint16_t selector;
    uint8_t ist;
    uint8_t type_attributes;
    uint16_t offset_mid;
    uint32_t offset_hi;
    uint32_t reserved;
} K0_CPU_IDT_GATE;
typedef struct __attribute__((packed)) {
    uint16_t limit;
    uint64_t base;
} K0_CPU_IDTR;
_Static_assert(sizeof(K0_CPU_IDT_GATE) == 16, "IDT descriptor size");
_Static_assert(sizeof(K0_CPU_IDTR) == 10, "IDTR descriptor size");

static K0_CPU_IDT_GATE k0_cpu_probe_idt[256] __attribute__((aligned(16)));
static volatile uint64_t k0_cpu_probe_faults;
static volatile uint64_t k0_cpu_probe_cr2;
static volatile uint64_t k0_cpu_probe_error;
static volatile uint64_t k0_cpu_probe_fault_rip;
static volatile uint64_t k0_cpu_probe_fault_cs;

extern void k0_cpu_pf_entry(void);
extern void k0_cpu_unexpected_fault(void);
extern char k0_cpu_pf_fault_site;
extern char k0_cpu_pf_recovery;

/* Saved integer registers occupy 15 slots. Hardware error_code is slot 15,
 * RIP 16, CS 17, RFLAGS 18; the handler does NOT inspect optional SS/RSP slots.
 * This callback is entered via a custom x64-ABI assembly stub.
 */
__attribute__((used, noinline))
static void k0_cpu_pf_record(uint64_t *saved) {
    uint64_t cr2 = 0;
    __asm__ __volatile__("movq %%cr2, %0" : "=r"(cr2));
    k0_cpu_probe_cr2 = cr2;
    k0_cpu_probe_error = saved[15];
    k0_cpu_probe_fault_rip = saved[16];
    k0_cpu_probe_fault_cs = saved[17];
    if (saved[16] == (uint64_t)(uintptr_t)&k0_cpu_pf_fault_site &&
        cr2 == K0_CPU_PF_SENTINEL && saved[15] == 0 &&
        (saved[17] & 3ULL) == 0 && (saved[18] & 2ULL) != 0)
        ++k0_cpu_probe_faults;
    /* Always leave the faulting instruction and fail closed if unexpected. */
    saved[16] = (uint64_t)(uintptr_t)&k0_cpu_pf_recovery;
}

/* All GPRs are saved around C; the Windows x64 ABI receives saved[] in RCX.
 * RSP is aligned to 16 bytes and reserves its mandatory 32-byte shadow area.
 * The CPU-pushed error code is discarded exactly once before IRETQ.
 */
__asm__(
".text\n"
".globl k0_cpu_pf_entry\n"
"k0_cpu_pf_entry:\n"
"pushq %rax\n"
"pushq %rcx\n"
"pushq %rdx\n"
"pushq %rbx\n"
"pushq %rbp\n"
"pushq %rsi\n"
"pushq %rdi\n"
"pushq %r8\n"
"pushq %r9\n"
"pushq %r10\n"
"pushq %r11\n"
"pushq %r12\n"
"pushq %r13\n"
"pushq %r14\n"
"pushq %r15\n"
"movq %rsp, %rbx\n"
"movq %rsp, %rcx\n"
"andq $-16, %rsp\n"
"subq $32, %rsp\n"
"call k0_cpu_pf_record\n"
"movq %rbx, %rsp\n"
"popq %r15\n"
"popq %r14\n"
"popq %r13\n"
"popq %r12\n"
"popq %r11\n"
"popq %r10\n"
"popq %r9\n"
"popq %r8\n"
"popq %rdi\n"
"popq %rsi\n"
"popq %rbp\n"
"popq %rbx\n"
"popq %rdx\n"
"popq %rcx\n"
"popq %rax\n"
"addq $8, %rsp\n"
"iretq\n"
".globl k0_cpu_unexpected_fault\n"
"k0_cpu_unexpected_fault:\n"
"cli\n"
"1: hlt\n"
"jmp 1b\n"
);

static void k0_cpu_gate_install(unsigned vector, void (*handler)(void),
                                 uint16_t cs) {
    uint64_t offset = (uint64_t)(uintptr_t)handler;
    K0_CPU_IDT_GATE *gate = &k0_cpu_probe_idt[vector];
    gate->offset_lo = (uint16_t)offset;
    gate->selector = cs;
    gate->ist = 0;
    gate->type_attributes = 0x8e;
    gate->offset_mid = (uint16_t)(offset >> 16);
    gate->offset_hi = (uint32_t)(offset >> 32);
    gate->reserved = 0;
}

static int k0_cpu_pf_real_guest_probe(void) {
    uint16_t cs = 0;
    uint64_t old_cr3 = 0, after_cr3 = 0;
    K0_CPU_IDTR idtr;
    __asm__ __volatile__("movw %%cs, %0" : "=r"(cs));
    if (!cs || (cs & 3U)) return 0;
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(old_cr3));
    if (!old_cr3 || (old_cr3 & 0xfffULL)) return 0;
    k0_cpu_gate_install(8U, k0_cpu_unexpected_fault, cs);
    k0_cpu_gate_install(13U, k0_cpu_unexpected_fault, cs);
    k0_cpu_gate_install(14U, k0_cpu_pf_entry, cs);
    idtr.limit = (uint16_t)(sizeof(k0_cpu_probe_idt) - 1);
    idtr.base = (uint64_t)(uintptr_t)k0_cpu_probe_idt;
    __asm__ __volatile__("cli; lidt %0" : : "m"(idtr) : "memory");

    /* Address is canonical but deliberately outside OVMF's identity mappings.
     * A successful load is NOT a pass. A missing #PF or wrong CR2/error/RIP
     * never generates the positive receipt; QEMU must fail closed.
     */
    __asm__ __volatile__(
        "movabs $0x0000400000000000, %%rax\n"
        ".globl k0_cpu_pf_fault_site\n"
        "k0_cpu_pf_fault_site:\n"
        "movq (%%rax), %%rax\n"
        ".globl k0_cpu_pf_recovery\n"
        "k0_cpu_pf_recovery:\n"
        : : : "rax", "memory");
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(after_cr3));
    return k0_cpu_probe_faults == 1 &&
           k0_cpu_probe_cr2 == K0_CPU_PF_SENTINEL &&
           k0_cpu_probe_error == 0 &&
           k0_cpu_probe_fault_rip == (uint64_t)(uintptr_t)&k0_cpu_pf_fault_site &&
           k0_cpu_probe_fault_cs == cs && after_cr3 == old_cr3;
}
#endif
