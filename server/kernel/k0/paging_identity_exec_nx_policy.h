#ifndef KOSCHEI_K0_IDENTITY_EXEC_NX_POLICY_H
#define KOSCHEI_K0_IDENTITY_EXEC_NX_POLICY_H
/*
 * QEMU-only transitional identity-map execute policy.
 * Default: supervisor RW+NX for each lower-1GiB 2MiB PDE.
 * Only the 2MiB windows containing observed executable code are RWX.
 * This does NOT meet production W^X: code windows remain writable,
 * and image/stack may share a huge page. No domain isolation.
 *
 * Transactional preflight. No page tables are written after a failed check.
 */
#include "memory_map.h"

#define K0_CR3_IDENTITY_PDE_COUNT 512U
#define K0_CR3_IDENTITY_EXEC_MAX_HINTS 16U
#define K0_CR3_IDENTITY_EXEC_MAX_WINDOWS 8U
#define K0_CR3_IDENTITY_LIMIT 0x40000000ULL
#define K0_CR3_IDENTITY_NX (1ULL << 63)

static int k0_cr3_identity_build(volatile K_U64 *out,
                                 const K_U64 *exec_addresses,
                                 K_U32 count) {
    if (!out || !exec_addresses || !count ||
        count > K0_CR3_IDENTITY_EXEC_MAX_HINTS) return 0;
    K_U8 executable[K0_CR3_IDENTITY_PDE_COUNT] = {0};
    K_U32 unique = 0;
    for (K_U32 i = 0; i < count; ++i) {
        if (!exec_addresses[i] ||
            exec_addresses[i] >= K0_CR3_IDENTITY_LIMIT)
            return 0;
        K_U32 slot = (K_U32)(exec_addresses[i] >> 21);
        /* Test-only fault slot is always non-executable. */
        if (slot == K0_CR3_IDENTITY_PDE_COUNT - 1U) return 0;
        if (!executable[slot]) {
            executable[slot] = 1;
            if (++unique > K0_CR3_IDENTITY_EXEC_MAX_WINDOWS) return 0;
        }
    }
    for (K_U32 i = 0; i < K0_CR3_IDENTITY_PDE_COUNT; ++i)
        out[i] = ((K_U64)i << 21) | 0x83ULL |
                 (executable[i] ? 0ULL : K0_CR3_IDENTITY_NX);
    return 1;
}
#endif
