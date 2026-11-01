#ifndef KOSCHEI_K0_CR3_FAULT_PROBE_H
#define KOSCHEI_K0_CR3_FAULT_PROBE_H
/*
 * EMULATOR TEST BINARY ONLY. This is not secure production page isolation.
 * A temporary low-1GiB identity map retains broad RW+NX huge pages,
 * but active PE image windows are split into 4KiB RX/RW+NX leaves.
 * Other physical ranges and fault vectors remain test-only and unprotected.
 * It leaves the tested high-half address unmapped and uses a dedicated #PF
 * IDT gate. All other IDT vectors are absent; interrupts are masked.
 * Never compile, call, or advertise this as customer production MMU policy.
 */
#ifndef KOSCHEI_QEMU_TEST
#error "CR3 diagnostic must never be compiled into the release image"
#endif
#include "paging_identity_exec_nx_policy.h"
#include "paging_live_image_4k_wx.h"

#define K0_CR3_TEST_LIMIT 0x40000000ULL
#ifdef KOSCHEI_QEMU_MAPPED_TEST
#define K0_CR3_FRAME_COUNT 9U
#define K0_CR3_PE_PT_FIRST 7U
#define K0_CR3_MAPPING_VA 0xffff800000000000ULL
#else
#define K0_CR3_FRAME_COUNT 5U
#define K0_CR3_PE_PT_FIRST 3U
#endif
#if defined(KOSCHEI_QEMU_CODE_WX_TEST)
#define K0_CR3_EXPECTED_ERROR 3ULL /* supervisor write to image RX code */
#elif defined(KOSCHEI_QEMU_NX_TEST)
#define K0_CR3_FAULT_VA 0x3fe00000ULL
#define K0_CR3_EXPECTED_ERROR 17ULL /* present, instruction fetch denied */
#elif defined(KOSCHEI_QEMU_READONLY_TEST)
#define K0_CR3_FAULT_VA 0x3fe00000ULL /* last 2MiB huge-page slot */
#define K0_CR3_EXPECTED_ERROR 3ULL /* present, supervisor write denied */
#else
#define K0_CR3_FAULT_VA 0xffff800000400000ULL
#define K0_CR3_EXPECTED_ERROR 0ULL /* high-half not present */
#endif
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
#ifdef KOSCHEI_QEMU_CODE_WX_TEST
static volatile K_U64 k0_code_rx_fault_address;
#endif

/* The CPU pushes the page-fault error code at top of exception stack.
 * Windows x64 ABI requires RCX/RDX arguments and 32 bytes of shadow space.
 * This stub only enters a noreturn callback. No IRET or stack recovery.
 */
__attribute__((used,noreturn)) static void k0_cr3_pf_dispatch(
    K_U64 cr2, K_U64 error_code) {
    K_U64 observed_cr3 = 0;
    __asm__ __volatile__("movq %%cr3, %0" : "=r"(observed_cr3));
#ifdef KOSCHEI_QEMU_CODE_WX_TEST
    K_U64 expected_cr2 = k0_code_rx_fault_address;
#else
    K_U64 expected_cr2 = K0_CR3_FAULT_VA;
#endif
    if (cr2 != expected_cr2 ||
        error_code != K0_CR3_EXPECTED_ERROR ||
        observed_cr3 != k0_expected_cr3) {
        serial_line("KOSCHEI-KERNEL REJECT/1 UNEXPECTED-PAGE-FAULT");
        stop(0x11);
    }
    /* Only reachable through a real CPU vector-14 exception path. */
#if defined(KOSCHEI_QEMU_CODE_WX_TEST)
    serial_line("KOSCHEI-KERNEL K0 OWN-CR3-CODE-WRITE-DENIED");
#elif defined(KOSCHEI_QEMU_NX_TEST)
    serial_line("KOSCHEI-KERNEL K0 OWN-CR3-NX-EXEC-DENIED");
#elif defined(KOSCHEI_QEMU_READONLY_TEST)
    serial_line("KOSCHEI-KERNEL K0 OWN-CR3-RO-WRITE-DENIED");
#else
    serial_line("KOSCHEI-KERNEL K0 OWN-CR3-PF-DENIED");
#endif
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
    K_U64 frame[K0_CR3_FRAME_COUNT] = {0};
    K_U64 stack_witness = 0;
    K_U64 stack_addr = (K_U64)(unsigned long long)&stack_witness;
    K_U64 dispatcher = (K_U64)(unsigned long long)&k0_cr3_pf_dispatch;
    K_U64 stub = (K_U64)(unsigned long long)&k0_cr3_pf_stub;
    K_U64 serial = (K_U64)(unsigned long long)&serial_line;
    K_U64 exit_code = (K_U64)(unsigned long long)&stop;
    K_U64 idt_addr = (K_U64)(unsigned long long)&k0_cr3_idt[0];
    K_U64 cr0 = 0;
    __asm__ __volatile__("movq %%cr0, %0" : "=r"(cr0));
    /* Supervisor CR0.WP required for actual RX code protection. */
    if (!pool || pool->active || !k0_guest_nx_preflight() ||
        !(cr0 & (1ULL << 16)) ||
        stack_addr >= K0_CR3_TEST_LIMIT ||
        dispatcher >= K0_CR3_TEST_LIMIT ||
        stub >= K0_CR3_TEST_LIMIT ||
        serial >= K0_CR3_TEST_LIMIT ||
        exit_code >= K0_CR3_TEST_LIMIT ||
        idt_addr >= K0_CR3_TEST_LIMIT) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-PREFLIGHT");
        stop(0x11);
    }
#if defined(KOSCHEI_QEMU_READONLY_TEST) || defined(KOSCHEI_QEMU_NX_TEST)
    /* The dedicated test page is separate from all executable functions.
     * CR0.WP must be enabled for the read-only scenario.
     */
    if ((stack_addr >> 21) == 511ULL ||
        (dispatcher >> 21) == 511ULL ||
        (stub >> 21) == 511ULL ||
        (serial >> 21) == 511ULL ||
        (exit_code >> 21) == 511ULL ||
        (idt_addr >> 21) == 511ULL) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR0-WP-PREFLIGHT");
        stop(0x11);
    }
#endif
    for (K_U32 i = 0; i < K0_CR3_FRAME_COUNT; ++i) {
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
    /* Coarse identity executable hints are a preflight input only.
     * The separate PE 4KiB builder MUST split every executable huge PDE
     * before these page tables can be installed into CPU CR3.
     */
    const K_U64 code_locations[] = {
        (K_U64)(unsigned long long)&k0_cr3_qemu_probe,
        (K_U64)(unsigned long long)&k0_cr3_pf_dispatch,
        (K_U64)(unsigned long long)&k0_cr3_pf_stub,
        (K_U64)(unsigned long long)&serial_line,
        (K_U64)(unsigned long long)&serial_char,
        (K_U64)(unsigned long long)&stop
    };
    if (!k0_cr3_identity_build(pd, code_locations,
                               sizeof(code_locations) / sizeof(code_locations[0]))) {
        serial_line("KOSCHEI-KERNEL REJECT/1 EXEC-NX-PREFLIGHT");
        stop(0x11);
    }
#if defined(KOSCHEI_QEMU_READONLY_TEST) || defined(KOSCHEI_QEMU_NX_TEST)
    /* One dedicated unneeded 2MiB slot becomes protected; all executing
     * code, IDT, stack and table frames must remain outside it.
     */
    for (K_U32 i = 0; i < 3; ++i)
        if ((frame[i] >> 21) == 511ULL) {
            serial_line("KOSCHEI-KERNEL REJECT/1 CR3-RO-FRAME");
            stop(0x11);
        }
#if defined(KOSCHEI_QEMU_NX_TEST)
    /* Present 2MiB page, NX bit must be enforced by EFER.NXE. */
    pd[511] = ((K_U64)511 << 21) | 0x83ULL | (1ULL << 63);
    const K_U64 last_entry = ((K_U64)511 << 21) | 0x83ULL | (1ULL << 63);
#else
    pd[511] = ((K_U64)511 << 21) | 0x81ULL | K0_CR3_IDENTITY_NX;
    const K_U64 last_entry = ((K_U64)511 << 21) | 0x81ULL | K0_CR3_IDENTITY_NX;
#endif
#else
    const K_U64 last_entry = ((K_U64)511 << 21) | 0x83ULL | K0_CR3_IDENTITY_NX;
#endif
#ifdef KOSCHEI_QEMU_MAPPED_TEST
    /* A real, present 4 KiB high-half leaf on the new CPU CR3.
     * NX, supervisor-only; current low identity still deliberately RWX.
     */
    volatile K_U64 *high_pdpt = (volatile K_U64 *)(unsigned long long)frame[3];
    volatile K_U64 *high_pd = (volatile K_U64 *)(unsigned long long)frame[4];
    volatile K_U64 *high_pt = (volatile K_U64 *)(unsigned long long)frame[5];
    for (K_U32 i = 0; i < 512; ++i) {
        high_pdpt[i] = 0;
        high_pd[i] = 0;
        high_pt[i] = 0;
    }
    pml4[256] = frame[3] | 3ULL;
    high_pdpt[0] = frame[4] | 3ULL;
    high_pd[0] = frame[5] | 3ULL;
    high_pt[0] = frame[6] | 3ULL | (1ULL << 63);
    const K_U64 high_root_expected = frame[3] | 3ULL;
    if (high_pdpt[0] != (frame[4] | 3ULL) ||
        high_pd[0] != (frame[5] | 3ULL) ||
        high_pt[0] != (frame[6] | 3ULL | (1ULL << 63)) ||
        high_pt[1] != 0) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-4K-PREFLIGHT");
        stop(0x11);
    }
#else
    const K_U64 high_root_expected = 0;
#endif
    K0_LIVE_WX_RECEIPT image_wx;
    if (!k0_live_image_4k_build(
            pd,
            (volatile K_U64 *)(unsigned long long)frame[K0_CR3_PE_PT_FIRST],
            (volatile K_U64 *)(unsigned long long)frame[K0_CR3_PE_PT_FIRST + 1U],
            frame[K0_CR3_PE_PT_FIRST], frame[K0_CR3_PE_PT_FIRST + 1U],
            k0_image_bounds.base, &k0_loaded_pe_layout, stack_addr,
            code_locations, sizeof(code_locations) / sizeof(code_locations[0]),
            &image_wx)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 LIVE-PE-4K-WX-PREFLIGHT");
        stop(0x11);
    }
    const K_U32 image_first_slot = (K_U32)(k0_image_bounds.base >> 21);
    const K_U64 expected_pd0 = image_first_slot == 0U
        ? (frame[K0_CR3_PE_PT_FIRST] | 3ULL)
        : (0x83ULL | K0_CR3_IDENTITY_NX);
    if (image_wx.split_count < 1U || image_wx.split_count > 2U ||
        pd[image_first_slot] != (frame[K0_CR3_PE_PT_FIRST] | 3ULL) ||
        (image_wx.split_count == 2U &&
         pd[image_first_slot+1U] !=
         (frame[K0_CR3_PE_PT_FIRST+1U] | 3ULL))) {
        serial_line("KOSCHEI-KERNEL REJECT/1 LIVE-PE-4K-WX-READBACK");
        stop(0x11);
    }
    if (pml4[0] != (frame[1] | 3ULL) ||
        pdpt[0] != (frame[2] | 3ULL) ||
        pml4[256] != high_root_expected ||
        pd[0] != expected_pd0 ||
        pd[511] != last_entry) {
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
#ifdef KOSCHEI_QEMU_CODE_WX_TEST
    /* RX witness: actual executable PE section, no alias with a RW huge PDE. */
    k0_code_rx_fault_address =
        (K_U64)(unsigned long long)&k0_cr3_pf_stub;
    if (k0_code_rx_fault_address < k0_image_bounds.base ||
        k0_code_rx_fault_address >= k0_image_bounds.base +
                                     k0_image_bounds.size ||
        k0_loaded_pe_layout.pages[
            (k0_code_rx_fault_address - k0_image_bounds.base) /
            K0_PAGE_SIZE] != K0_PE_WX_CODE_RX) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CODE-RX-FAULT-PREFLIGHT");
        stop(0x11);
    }
#endif

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
    /* Execution now uses PE code RX PTEs, writable globals RW+NX, with
     * CR0.WP and EFER.NXE checked; this is still a test-only transition.
     */
    serial_line("KOSCHEI-KERNEL K0 OWN-CR3-PE-4K-WX");
#ifdef KOSCHEI_QEMU_MAPPED_TEST
    volatile K_U8 *virtual_page =
        (volatile K_U8 *)(unsigned long long)K0_CR3_MAPPING_VA;
    volatile K_U8 *identity_page =
        (volatile K_U8 *)(unsigned long long)frame[6];
    virtual_page[0] = 0xa5U;
    virtual_page[K0_PAGE_SIZE - 1] = 0x5aU;
    if (identity_page[0] != 0xa5U ||
        identity_page[K0_PAGE_SIZE - 1] != 0x5aU) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-4K-ALIAS");
        stop(0x11);
    }
    identity_page[1] = 0x3cU;
    if (virtual_page[1] != 0x3cU) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-4K-READBACK");
        stop(0x11);
    }
    virtual_page[0] = 0;
    virtual_page[1] = 0;
    virtual_page[K0_PAGE_SIZE - 1] = 0;
    if (identity_page[0] || identity_page[1] ||
        identity_page[K0_PAGE_SIZE - 1]) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-4K-CLEANUP");
        stop(0x11);
    }
    serial_line("KOSCHEI-KERNEL K0 OWN-CR3-4K-MAPPED");
#endif
    /* Only a real #PF handler can produce the final success and exit=33. */
#if defined(KOSCHEI_QEMU_CODE_WX_TEST)
    const K_U64 code_rx = k0_code_rx_fault_address;
    __asm__ __volatile__("movb $0x5a, (%0)" : : "r"(code_rx) : "memory");
#elif defined(KOSCHEI_QEMU_NX_TEST)
    const K_U64 no_execute = K0_CR3_FAULT_VA;
    __asm__ __volatile__("callq *%0" : : "r"(no_execute) : "memory");
#elif defined(KOSCHEI_QEMU_READONLY_TEST)
    const K_U64 read_only = K0_CR3_FAULT_VA;
    __asm__ __volatile__("movb $0x5a, (%0)" : : "r"(read_only) : "memory");
#else
    K_U64 value = 0;
    const K_U64 missing = K0_CR3_FAULT_VA;
    __asm__ __volatile__("movq (%1), %0" : "=r"(value) : "r"(missing) : "memory");
    (void)value;
#endif
    serial_line("KOSCHEI-KERNEL REJECT/1 PAGE-FAULT-NOT-RAISED");
    stop(0x11);
}
#endif
