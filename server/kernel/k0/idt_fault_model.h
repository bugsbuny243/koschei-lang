#ifndef KOSCHEI_K0_IDT_FAULT_MODEL_H
#define KOSCHEI_K0_IDT_FAULT_MODEL_H
/* K0.4 freestanding preflight: synthetic IDT/#PF contract, NOT a CPU trap. */
#include <stdint.h>
#include <stddef.h>

#define K0_IDT_VECTOR_DF 8U
#define K0_IDT_VECTOR_GP 13U
#define K0_IDT_VECTOR_PF 14U
#define K0_IDT_KERNEL_CS 0x08U
#define K0_IDT_INTERRUPT_GATE 0x8eU
#define K0_IDT_MAX_GATES 256U
#define K0_PF_PRESENT 0x01U
#define K0_PF_WRITE 0x02U
#define K0_PF_USER 0x04U
#define K0_PF_RESERVED 0x08U
#define K0_PF_INSTRUCTION 0x10U
#define K0_PF_KNOWN_MASK 0x1fU

typedef struct {
    uint16_t offset_low;
    uint16_t selector;
    uint8_t ist;
    uint8_t type_attributes;
    uint16_t offset_mid;
    uint32_t offset_high;
    uint32_t reserved;
} K0_IDT_GATE64;
_Static_assert(sizeof(K0_IDT_GATE64) == 16, "x86-64 IDT gate must be 16 bytes");
_Static_assert(offsetof(K0_IDT_GATE64, reserved) == 12, "IDT layout mismatch");

typedef enum {
    K0_WALK_FAULT_INVALID = 0,
    K0_WALK_FAULT_ABSENT = 1,
    K0_WALK_FAULT_READONLY_WRITE = 2,
    K0_WALK_FAULT_NX_EXEC = 3,
    K0_WALK_FAULT_RESERVED_BIT = 4
} K0_IDT_FAULT_CLASS;

typedef struct {
    uint64_t cr2;
    uint32_t error_code;
    K0_IDT_FAULT_CLASS fault_class;
    uint8_t present;
    uint8_t write;
    uint8_t user;
    uint8_t reserved_bit;
    uint8_t instruction;
} K0_IDT_PF_REPORT;

static inline int k0_idt_is_canonical48(uint64_t address) {
    uint64_t high = address >> 48;
    return (address & (1ULL << 47)) ? high == 0xffffULL : high == 0ULL;
}

static inline uint64_t k0_idt_handler_address(const K0_IDT_GATE64 *gate) {
    if (!gate) return 0;
    return (uint64_t)gate->offset_low |
           ((uint64_t)gate->offset_mid << 16) |
           ((uint64_t)gate->offset_high << 32);
}

static inline int k0_idt_gate_valid(const K0_IDT_GATE64 *gate,
                                    uint64_t code_begin, uint64_t code_end) {
    uint64_t target;
    if (!gate || code_begin == 0 || code_begin >= code_end ||
        !k0_idt_is_canonical48(code_begin) ||
        !k0_idt_is_canonical48(code_end - 1) ||
        gate->selector != K0_IDT_KERNEL_CS ||
        gate->type_attributes != K0_IDT_INTERRUPT_GATE ||
        (gate->ist & 0xf8U) != 0 || gate->reserved != 0) return 0;
    target = k0_idt_handler_address(gate);
    return target != 0 && (target & 0x0fU) == 0 &&
           k0_idt_is_canonical48(target) &&
           target >= code_begin && target < code_end;
}

static inline int k0_idt_required_fault_gates_valid(
    const K0_IDT_GATE64 *gates, size_t count,
    uint64_t code_begin, uint64_t code_end) {
    if (!gates || count <= K0_IDT_VECTOR_PF || count > K0_IDT_MAX_GATES)
        return 0;
    return k0_idt_gate_valid(&gates[K0_IDT_VECTOR_DF], code_begin, code_end) &&
           k0_idt_gate_valid(&gates[K0_IDT_VECTOR_GP], code_begin, code_end) &&
           k0_idt_gate_valid(&gates[K0_IDT_VECTOR_PF], code_begin, code_end);
}

/* Reject unsupported hardware bits and RSVD=1. Preserve RESERVED_BIT as
 * diagnostic classification, NEVER as an admitted fault.
 */
static inline int k0_idt_decode_pf(uint32_t error_code, uint64_t cr2,
                                   K0_IDT_PF_REPORT *out) {
    K0_IDT_PF_REPORT r = {0};
    if (!out) return 0;
    *out = r;
    r.cr2 = cr2;
    r.error_code = error_code;
    r.present = (uint8_t)((error_code & K0_PF_PRESENT) != 0);
    r.write = (uint8_t)((error_code & K0_PF_WRITE) != 0);
    r.user = (uint8_t)((error_code & K0_PF_USER) != 0);
    r.reserved_bit = (uint8_t)((error_code & K0_PF_RESERVED) != 0);
    r.instruction = (uint8_t)((error_code & K0_PF_INSTRUCTION) != 0);
    if (r.reserved_bit) r.fault_class = K0_WALK_FAULT_RESERVED_BIT;
    else if (!r.present) r.fault_class = K0_WALK_FAULT_ABSENT;
    /* The K0 paging model is supervisor-only. A present user fault may be
     * privilege/SMEP/SMAP related, not a readonly or NX translation fault. */
    else if (r.user) r.fault_class = K0_WALK_FAULT_INVALID;
    else if (r.write && !r.instruction) r.fault_class = K0_WALK_FAULT_READONLY_WRITE;
    else if (!r.write && r.instruction) r.fault_class = K0_WALK_FAULT_NX_EXEC;
    *out = r;
    return (error_code & ~K0_PF_KNOWN_MASK) == 0 &&
           k0_idt_is_canonical48(cr2) && !r.reserved_bit &&
           r.fault_class != K0_WALK_FAULT_INVALID &&
           !(r.write && r.instruction);
}

/* Caller passes K0_VM_WALK_RESULT.kind == K0_VM_WALK_PAGE_FAULT and the
 * corresponding predicted_error_code from paging_walk.h; model only.
 */
static inline int k0_idt_pf_matches_predicted_walk(
    const K0_IDT_PF_REPORT *report, uint64_t requested_address,
    int model_is_page_fault, uint32_t predicted_error_code) {
    K0_IDT_PF_REPORT checked;
    if (!report || !model_is_page_fault || report->cr2 != requested_address ||
        !k0_idt_decode_pf(report->error_code, report->cr2, &checked)) return 0;
    return checked.fault_class == report->fault_class &&
           checked.present == report->present &&
           checked.write == report->write &&
           checked.user == report->user &&
           checked.reserved_bit == report->reserved_bit &&
           checked.instruction == report->instruction &&
           predicted_error_code == report->error_code;
}

/* Model a ring-0 long-mode GDT pair (index 1 = CS 0x08,
 * index 2 = data selector 0x10). Descriptors are not loaded into GDTR.
 */
static inline int k0_idt_kernel_gdt_pair_valid(
    const uint64_t *descriptors, size_t count) {
    uint64_t code, data;
    const uint64_t present = 1ULL << 47;
    const uint64_t system = 1ULL << 44;
    const uint64_t executable = 1ULL << 43;
    const uint64_t rw = 1ULL << 41;
    const uint64_t long_mode = 1ULL << 53;
    const uint64_t db = 1ULL << 54;
    const uint64_t dpl = 3ULL << 45;
    if (!descriptors || count < 3 || descriptors[0] != 0) return 0;
    code = descriptors[1];
    data = descriptors[2];
    return (code & (present | system | executable | rw | long_mode))
               == (present | system | executable | rw | long_mode) &&
           (code & (dpl | db)) == 0 &&
           (data & (present | system | rw)) == (present | system | rw) &&
           (data & (dpl | executable | long_mode)) == 0;
}

/* Explicit software capture of a post-ISR exception context.
 * This is not the raw CPU stack layout: IST/CPL changes can push extra
 * slots and the interrupt stub MUST normalize it before validation.
 */
typedef struct {
    uint8_t vector;
    uint64_t error_code;
    uint64_t rip;
    uint64_t cs;
    uint64_t rflags;
    uint64_t rsp;
    uint64_t cr2;
} K0_IDT_EXCEPTION_SNAPSHOT;

static inline int k0_idt_fault_snapshot_valid(
    const K0_IDT_EXCEPTION_SNAPSHOT *frame, K0_IDT_PF_REPORT *pf) {
    K0_IDT_PF_REPORT decoded = {0};
    if (!frame || frame->cs != K0_IDT_KERNEL_CS ||
        !k0_idt_is_canonical48(frame->rip) ||
        !k0_idt_is_canonical48(frame->rsp) ||
        frame->rsp == 0 || (frame->rsp & 7ULL) != 0 ||
        (frame->rflags & 2ULL) == 0) return 0;
    if (frame->vector == K0_IDT_VECTOR_DF)
        return frame->error_code == 0;
    if (frame->vector == K0_IDT_VECTOR_GP)
        return frame->error_code <= 0xffffULL;
    if (frame->vector != K0_IDT_VECTOR_PF ||
        frame->error_code > 0xffffffffULL || !pf) return 0;
    if (!k0_idt_decode_pf((uint32_t)frame->error_code,
                          frame->cr2, &decoded)) return 0;
    *pf = decoded;
    return 1;
}
#endif
