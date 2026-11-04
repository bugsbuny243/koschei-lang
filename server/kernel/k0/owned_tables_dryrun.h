#ifndef KOSCHEI_K0_OWNED_TABLES_DRYRUN_H
#define KOSCHEI_K0_OWNED_TABLES_DRYRUN_H
/*
 * K0.4 OFFLINE OWNED TABLE-BYTE ATTESTATION, NOT A CR3 TRANSITION.
 * Rebuild the EXPECTED four-level high-half hierarchy from the claimed
 * pool, verify each physical table-frame entry, and independently walk
 * the candidate bytes as data. No virtual high-half address is dereferenced,
 * no CPU MMU registers are changed and no isolation is claimed.
 *
 * Single-threaded post-ExitBootServices or host diagnostic only.
 */
#include "paging_model.h"
#include "live_cr3_inspection.h"

static int k0_owned_tables_dryrun_verify(
    const K0_VM_TABLE_MODEL *candidate,
    const K0_VM_PLAN *plan,
    const K0_PAGE_POOL *pool,
    K_U64 active_firmware_cr3,
    K0_CR3_I_READ physical_read, void *reader_context) {
    if (!candidate || !candidate->initialized || !plan ||
        !plan->initialized || !pool || !pool->initialized ||
        !pool->epoch || !plan->pool_epoch ||
        plan->pool_epoch != pool->epoch ||
        candidate->pool_epoch != pool->epoch ||
        plan->count != 2 || !physical_read ||
        !active_firmware_cr3 || (active_firmware_cr3 & 4095ULL))
        return 0;

    /* A deliberately narrow, W^X, supervisor-only two-page example:
     * high half writable+NX data followed by read-only executable code.
     * It CANNOT map the running EFI image, current stack or exception IDT.
     */
    if (plan->leaves[0].virtual_page != K0_VM_HIGH_HALF_BASE ||
        plan->leaves[1].virtual_page != K0_VM_HIGH_HALF_BASE + K0_PAGE_SIZE ||
        plan->leaves[0].leaf_entry !=
            (plan->leaves[0].physical_page | K0_VM_PRESENT |
             K0_VM_WRITE | K0_VM_NO_EXECUTE) ||
        plan->leaves[1].leaf_entry !=
            (plan->leaves[1].physical_page | K0_VM_PRESENT))
        return 0;

    for (K_U32 i = 0; i < K0_VM_TABLE_LEVELS; ++i) {
        if (!k0_pool_is_claimed(pool, candidate->table_phys[i]) ||
            candidate->table_phys[i] == active_firmware_cr3)
            return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (candidate->table_phys[i] == candidate->table_phys[j])
                return 0;
    }

    /* Reconstruct all 2048 entries separately so forging both the proposed
     * model and physical frames does not pass. Statically allocated scratch
     * avoids __chkstk/memset in the freestanding Windows-x64 EFI image.
     * Diagnostic only, single-threaded and non-reentrant by design.
     */
    static K0_VM_TABLE_MODEL expected;
    expected.initialized = 0;
    if (!k0_vm_tables_build(&expected, plan, pool,
                             candidate->table_phys))
        return 0;

    for (K_U32 level = 0; level < K0_VM_TABLE_LEVELS; ++level) {
        for (K_U32 slot = 0; slot < K0_VM_ENTRIES_PER_TABLE; ++slot) {
            K_U64 observed = 0;
            if (!physical_read(reader_context, candidate->table_phys[level],
                               slot, &observed) ||
                observed != expected.entries[level][slot] ||
                candidate->entries[level][slot] != expected.entries[level][slot])
                return 0;
        }
    }

    K0_CR3_I_RESULT data = {0}, code = {0}, unexpected = {0};
    K_U64 root = candidate->table_phys[0];
    if (!k0_cr3_inspect_translation(root, K0_VM_HIGH_HALF_BASE,
                                    physical_read, reader_context, &data) ||
        !k0_cr3_inspect_translation(root, K0_VM_HIGH_HALF_BASE + K0_PAGE_SIZE,
                                    physical_read, reader_context, &code) ||
        data.physical_address != plan->leaves[0].physical_page ||
        code.physical_address != plan->leaves[1].physical_page ||
        data.leaf_page_shift != 12 || code.leaf_page_shift != 12 ||
        data.effective_user || code.effective_user ||
        !data.effective_write || !data.effective_nx ||
        code.effective_write || code.effective_nx ||
        k0_cr3_inspect_translation(root, K0_VM_HIGH_HALF_BASE +
                                    2 * K0_PAGE_SIZE, physical_read,
                                    reader_context, &unexpected) ||
        k0_cr3_inspect_translation(root, K0_VM_TOP_GUARD_START,
                                    physical_read, reader_context, &unexpected) ||
        k0_cr3_inspect_translation(root, 0x1000ULL,
                                    physical_read, reader_context, &unexpected))
        return 0;
    return 1;
}
#endif
