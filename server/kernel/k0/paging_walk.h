#ifndef KOSCHEI_K0_PAGING_WALK_H
#define KOSCHEI_K0_PAGING_WALK_H
/*
 * K0.4 MODEL-ONLY access walk. No CR3/IDT, no generated CPU exceptions.
 * Error codes are predicted x86-64 #PF bits (P/W/U/I); a noncanonical
 * virtual address predicts #GP(0), not a #PF. All outputs are synthetic.
 */
#include "paging_model.h"

#define K0_VM_PF_PRESENT 1U
#define K0_VM_PF_WRITE 2U
#define K0_VM_PF_USER 4U
#define K0_VM_PF_INSTRUCTION 16U

typedef enum {
    K0_VM_WALK_ALLOW = 0,
    K0_VM_WALK_PAGE_FAULT = 1,
    K0_VM_WALK_GENERAL_PROTECTION = 2,
    K0_VM_WALK_INVALID_MODEL = 3
} K0_VM_WALK_KIND;

typedef struct {
    K0_VM_WALK_KIND kind;
    K_U32 predicted_error_code;
    K_U64 resolved_physical;
} K0_VM_WALK_RESULT;

static int k0_vm_canonical48(K_U64 address) {
    K_U64 high = address >> 48;
    return (address & (1ULL << 47)) ? high == 0xffffULL : high == 0ULL;
}

/* Only a static, in-memory model. A returned PAGE_FAULT is never evidence
 * that the CPU faulted or protected real memory.
 */
static K0_VM_WALK_RESULT k0_vm_model_walk(const K0_VM_TABLE_MODEL *tables,
                                         const K0_PAGE_POOL *pool,
                                         K_U64 address, int write,
                                         int execute, int user) {
    K0_VM_WALK_RESULT answer = {K0_VM_WALK_INVALID_MODEL, 0, 0};
    if (!tables || !pool || !pool->initialized || !tables->initialized ||
        !tables->pool_epoch || tables->pool_epoch != pool->epoch ||
        (write != 0 && write != 1) ||
        (execute != 0 && execute != 1) ||
        (user != 0 && user != 1) ||
        (write && execute)) return answer;

    if (!k0_vm_canonical48(address)) {
        answer.kind = K0_VM_WALK_GENERAL_PROTECTION;
        return answer;
    }

    K_U32 access_code = (write ? K0_VM_PF_WRITE : 0U) |
                        (user ? K0_VM_PF_USER : 0U) |
                        (execute ? K0_VM_PF_INSTRUCTION : 0U);

    /* The high-half terminal guard is a planning policy, not hardware state. */
    if (address >= K0_VM_TOP_GUARD_START) {
        answer.kind = K0_VM_WALK_PAGE_FAULT;
        answer.predicted_error_code = access_code;
        return answer;
    }

    const K_U32 shift[4] = {39U, 30U, 21U, 12U};
    /* A non-present entry takes precedence over permission restrictions at
     * higher levels: the CPU reports P=0, even on attempted user access.
     * Accumulate permissions only for a fully present translation.
     */
    int permission_denied = 0;
    for (K_U32 level = 0; level < K0_VM_TABLE_LEVELS; ++level) {
        if (!k0_pool_is_claimed(pool, tables->table_phys[level]))
            return answer;
        K_U64 entry = tables->entries[level][k0_vm_level_index(address, shift[level])];
        if (!(entry & K0_VM_PRESENT)) {
            answer.kind = K0_VM_WALK_PAGE_FAULT;
            answer.predicted_error_code = access_code;
            return answer;
        }
        if (entry & ~(K0_VM_PHYSICAL_MASK | K0_VM_PRESENT |
                       K0_VM_WRITE | K0_VM_NO_EXECUTE))
            return answer; /* unknown / unsupported entry bits */
        if (level < K0_VM_TABLE_LEVELS - 1) {
            if ((entry & K0_VM_PHYSICAL_MASK) != tables->table_phys[level + 1] ||
                !(entry & K0_VM_WRITE) || (entry & K0_VM_NO_EXECUTE))
                return answer;
        } else if (!k0_pool_is_claimed(pool, entry & K0_VM_PHYSICAL_MASK) ||
                   ((entry & K0_VM_WRITE) &&
                    !(entry & K0_VM_NO_EXECUTE))) {
            return answer;
        }
        /* All proposed levels are supervisor-only. Do not return a
         * protection fault until the last present leaf is reached.
         */
        if (user || (write && !(entry & K0_VM_WRITE)) ||
            (execute && (entry & K0_VM_NO_EXECUTE)))
            permission_denied = 1;
        if (level == K0_VM_TABLE_LEVELS - 1) {
            if (permission_denied) {
                answer.kind = K0_VM_WALK_PAGE_FAULT;
                answer.predicted_error_code = access_code | K0_VM_PF_PRESENT;
                return answer;
            }
            answer.kind = K0_VM_WALK_ALLOW;
            answer.resolved_physical =
                (entry & K0_VM_PHYSICAL_MASK) + (address & (K0_PAGE_SIZE - 1));
            return answer;
        }
    }
    return answer;
}
#endif
