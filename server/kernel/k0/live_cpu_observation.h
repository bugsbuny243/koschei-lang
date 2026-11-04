#ifndef KOSCHEI_K0_LIVE_CPU_OBSERVATION_H
#define KOSCHEI_K0_LIVE_CPU_OBSERVATION_H
/*
 * QEMU-only live x86-64 register observation under FIRMWARE-OWNED CR3.
 * This reads privileged CPU state but never writes CR0/CR3/CR4/EFER,
 * changes page tables, or proves image/stack physical-page custody.
 * The caller disables interrupts before collection.
 */
#include <stdint.h>
#include <stddef.h>

typedef struct __attribute__((packed)) {
    uint16_t limit;
    uint64_t base;
} K0_LIVE_DESCRIPTOR;
_Static_assert(sizeof(K0_LIVE_DESCRIPTOR) == 10, "x64 descriptor register width");

typedef struct {
    uint64_t cr0, cr3, cr4, efer, rflags;
    uint64_t rip, rsp;
    K0_LIVE_DESCRIPTOR gdtr, idtr;
    uint16_t cs;
    uint8_t cpu_nx;
} K0_LIVE_CPU_STATE;

static int k0_live_canonical48(uint64_t a) {
    return (a >> 48) == ((a & (1ULL << 47)) ? 0xffffULL : 0ULL);
}

static int k0_live_snapshot_guest(K0_LIVE_CPU_STATE *out) {
    K_U32 a, b, c, d;
    if (!out) return 0;
    k0_guest_cpuid(1U, &a, &b, &c, &d);
    if (!(d & (1U << 5))) return 0; /* RDMSR supported */
    k0_guest_cpuid(0x80000000U, &a, &b, &c, &d);
    if (a < 0x80000001U) return 0;
    k0_guest_cpuid(0x80000001U, &a, &b, &c, &d);
    out->cpu_nx = (uint8_t)((d & (1U << 20)) != 0);
    __asm__ __volatile__("movq %%cr0, %0" : "=r"(out->cr0));
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(out->cr3));
    __asm__ __volatile__("movq %%cr4, %0" : "=r"(out->cr4));
    K_U32 lo, hi;
    __asm__ __volatile__("rdmsr" : "=a"(lo), "=d"(hi) : "c"(0xc0000080U));
    out->efer = (uint64_t)lo | ((uint64_t)hi << 32);
    __asm__ __volatile__("pushfq; popq %0" : "=r"(out->rflags));
    __asm__ __volatile__("movw %%cs, %0" : "=r"(out->cs));
    __asm__ __volatile__("sgdt %0" : "=m"(out->gdtr));
    __asm__ __volatile__("sidt %0" : "=m"(out->idtr));
    __asm__ __volatile__("movq %%rsp, %0" : "=r"(out->rsp));
    /* A RIP-relative LEA observes this actual instruction site. Merely
     * storing &k0_live_snapshot_guest would be a static symbol address,
     * not a captured instruction pointer.
     */
    __asm__ __volatile__(
        "leaq 1f(%%rip), %0\n"
        "1:\n"
        : "=r"(out->rip));
    return 1;
}

/* Preflight only. Passing shows the CPU was observed in a compatible mode,
 * NOT that proposed or active tables cover any VA or own a physical page.
 */
static int k0_live_state_admissible(const K0_LIVE_CPU_STATE *s) {
    const uint64_t cr0_required = (1ULL << 0) | (1ULL << 16) | (1ULL << 31);
    const uint64_t efer_required = (1ULL << 8) | (1ULL << 10) | (1ULL << 11);
    if (!s || s->cpu_nx != 1 || (s->cr0 & cr0_required) != cr0_required ||
        (s->cr4 & (1ULL << 5)) == 0 ||
        (s->cr4 & ((1ULL << 12) | (1ULL << 17))) != 0 ||
        (s->efer & efer_required) != efer_required ||
        (s->rflags & (2ULL | (1ULL << 9))) != 2 ||
        !s->cs || (s->cs & 3U) ||
        !s->cr3 || (s->cr3 & 4095ULL) ||
        (s->cr3 & ~0x000ffffffffff000ULL) ||
        !s->rip || !s->rsp ||
        !k0_live_canonical48(s->rip) || !k0_live_canonical48(s->rsp) ||
        !s->gdtr.base || !s->idtr.base ||
        !k0_live_canonical48(s->gdtr.base) ||
        !k0_live_canonical48(s->idtr.base) ||
        s->gdtr.limit < 23 || s->idtr.limit < (14U * 16U + 15U))
        return 0;
    return 1;
}
#endif
