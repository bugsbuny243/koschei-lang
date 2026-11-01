#ifndef KOSCHEI_K0_CR3_FAULT_PROBE_H
#define KOSCHEI_K0_CR3_FAULT_PROBE_H
/*
 * EMULATOR TEST BINARY ONLY. This is not secure production page isolation.
 * A temporary 0..1 GiB supervisor identity map has RWX 2 MiB huge pages
 * to retain firmware-loaded code and the existing stack after switching CR3.
 * It leaves the tested high-half address unmapped and uses a dedicated #PF
 * IDT gate. All other IDT vectors are absent; interrupts are masked.
 * Never compile, call, or advertise this as customer production MMU policy.
 */
#ifndef KOSCHEI_QEMU_TEST
#error "CR3 diagnostic must never be compiled into the release image"
#endif

#define K0_CR3_TEST_LIMIT 0x40000000ULL
#define K0_CR3_FAULT_VA 0xffff800000400000ULL
#define K0_CR3_PF_VECTOR 14U

typedef struct __attribute__((packed)) {
    K_U16 offset_low;
    K_U16 selector;
    K_U8 ist;
    K_U8 type;
    K_U16 offset_middle;
    K_U32 offset_high;
    K_U32 reserved;
} K0_CR3_IDT_GATE;

typedef struct __attribute__((packed)) {
    K_U16 limit;
    K_U64 base;
} K0_CR3_IDT_REGISTER;

_Static_assert(sizeof(K0_CR3_IDT_GATE) == 16, "x86-64 IDT gate");
_Static_assert(sizeof(K0_CR3_IDT_REGISTER) == 10, "x86-64 IDTR");

static K0_CR3_IDT_GATE k0_cr3_idt[16];
static K0_CR3_IDT_REGISTER k0_cr3_idtr;
static volatile K_U64 k0_expected_cr3;

/* The CPU pushes the page-fault error code at top of exception stack.
 * Windows x64 ABI requires RCX/RDX arguments and 32 bytes of shadow space.
 * This stub only enters a noreturn callback. No IRET or stack recovery.
 */
__attribute__((used,noreturn)) static void k0_cr3_pf_dispatch(
    K_U64 cr2, K_U64 error_code) {
    K_U64 observed_cr3 = 0;
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(observed_cr3));
    if (cr2 != K0_CR3_FAULT_VA || error_code != 0 ||
        observed_cr3 != k0_expected_cr3) {
        serial_line("KOSCHEI-KERNEL REJECT/1 UNEXPECTED-PAGE-FAULT");
        stop(0x11);
    }
    /* Only reachable through a real CPU vector-14 exception path. */
    serial_line("KOSCHEI-KERNEL K0 OWN-CR3-PF-DENIED");
    serial_line("KOSCHEI-KERNEL K0 HALT-NO-POLICY");
    stop(0x10);
}

__attribute__((naked)) static void k0_cr3_pf_stub(void) {
    __asm__ __volatile__(
        "cli\n\t"
        "movq %cr2, %rcx\n\t"
        "movq (%rsp), %rdx\n\t"
        "andq $-16, %rsp\n\t"
        "subq $32, %rsp\n\t"
        "callq k0_cr3_pf_dispatch\n\t"
        "ud2\n\t");
}

__attribute__((noreturn)) static void k0_cr3_qemu_probe(K0_PAGE_POOL *pool) {
    K_U64 frame[3] = {0};
    K_U64 stack_witness = 0;
    K_U64 stack_addr = (K_U64)(unsigned long long)&stack_witness;
    K_U64 dispatcher = (K_U64)(unsigned long long)&k0_cr3_pf_dispatch;
    K_U64 stub = (K_U64)(unsigned long long)&k0_cr3_pf_stub;
    K_U64 serial = (K_U64)(unsigned long long)&serial_line;
    K_U64 exit_code = (K_U64)(unsigned long long)&stop;
    K_U64 idt_addr = (K_U64)(unsigned long long)&k0_cr3_idt[0];
    if (!pool || pool->active || !k0_guest_nx_preflight() ||
        stack_addr >= K0_CR3_TEST_LIMIT ||
        dispatcher >= K0_CR3_TEST_LIMIT ||
        stub >= K0_CR3_TEST_LIMIT ||
        serial >= K0_CR3_TEST_LIMIT ||
        exit_code >= K0_CR3_TEST_LIMIT ||
        idt_addr >= K0_CR3_TEST_LIMIT) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-PREFLIGHT");
        stop(0x11);
    }
    for (K_U32 i = 0; i < 3; ++i) {
        if (!k0_pool_claim(pool, &frame[i]) ||
            frame[i] >= K0_CR3_TEST_LIMIT ||
            frame[i] == 0) {
            serial_line("KOSCHEI-KERNEL REJECT/1 CR3-PAGES");
            stop(0x11);
        }
    }
    volatile K_U64 *pml4 = (volatile K_U64 *)(unsigned long long)frame[0];
    volatile K_U64 *pdpt = (volatile K_U64 *)(unsigned long long)frame[1];
    volatile K_U64 *pd = (volatile K_U64 *)(unsigned long long)frame[2];
    for (K_U32 i = 0; i < 512; ++i) {
        pml4[i] = 0;
        pdpt[i] = 0;
        pd[i] = 0;
    }
    pml4[0] = frame[1] | 3ULL;
    pdpt[0] = frame[2] | 3ULL;
    for (K_U32 i = 0; i < 512; ++i)
        pd[i] = ((K_U64)i << 21) | 0x83ULL; /* present/write/2MiB */
    if (pml4[0] != (frame[1] | 3ULL) ||
        pdpt[0] != (frame[2] | 3ULL) ||
        pml4[256] != 0 || pd[0] != 0x83ULL ||
        pd[511] != (((K_U64)511 << 21) | 0x83ULL)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-MAP");
        stop(0x11);
    }
    K_U16 cs = 0;
    __asm__ __volatile__("movw %%cs, %0" : "=r"(cs));
    if (!cs) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-SELECTOR");
        stop(0x11);
    }
    K0_CR3_IDT_GATE *gate = &k0_cr3_idt[K0_CR3_PF_VECTOR];
    gate->offset_low = (K_U16)stub;
    gate->selector = cs;
    gate->ist = 0;
    gate->type = 0x8eU; /* present 64-bit kernel interrupt gate */
    gate->offset_middle = (K_U16)(stub >> 16);
    gate->offset_high = (K_U32)(stub >> 32);
    gate->reserved = 0;
    k0_cr3_idtr.limit = (K_U16)(sizeof(k0_cr3_idt) - 1);
    k0_cr3_idtr.base = idt_addr;
    k0_expected_cr3 = frame[0];

    /* QEMU-only: keep firmware-loaded image/stack identity-mapped, then
     * swap to our page tables. This blanket RWX identity map is NOT secure
     * and must never be adopted for Koschei's production kernel.
     */
    __asm__ __volatile__("cli\n\tlidt %0" : : "m"(k0_cr3_idtr) : "memory");
    __asm__ __volatile__("movq %0, %%cr3" : : "r"(frame[0]) : "memory");
    K_U64 observed = 0;
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(observed));
    if (observed != frame[0]) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-NOT-INSTALLED");
        stop(0x11);
    }
    /* Only the #PF handler can produce the success marker and exit=33. */
    K_U64 value = 0;
    const K_U64 missing = K0_CR3_FAULT_VA;
    __asm__ __volatile__("movq (%1), %0" : "=r"(value) : "r"(missing) : "memory");
    (void)value;
    serial_line("KOSCHEI-KERNEL REJECT/1 PAGE-FAULT-NOT-RAISED");
    stop(0x11);
}
#endif
