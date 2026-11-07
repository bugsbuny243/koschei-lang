#ifndef KOSCHEI_K0_MULTI_PT_PHYSICAL_H
#define KOSCHEI_K0_MULTI_PT_PHYSICAL_H
/*
 * Diagnostic 3-PT byte layout, NOT a live transition or an owned CR3.
 * Exactly six CLAIMED table frames and three distinct claimed data frames
 * in the old firmware identity map. Three nonadjacent 2MiB windows live
 * under ONE PML4 and ONE PDPT. No current EFI code/stack/IDT/GDT is mapped.
 * The caller must not touch the candidate VA or write CR3.
 */
#include "page_pool.h"
#include "live_cr3_inspection.h"

#define K0_MPT_TABLES 6U
#define K0_MPT_FRAMES 9U
#define K0_MPT_ENTRIES 512U
#define K0_MPT_VA 0xffff800000000000ULL
#define K0_MPT_P 1ULL
#define K0_MPT_RW 2ULL
#define K0_MPT_NX (1ULL << 63)
#define K0_MPT_PHYS_LIMIT (256ULL * 1024ULL * 1024ULL)

typedef struct {
    K_U64 frames[K0_MPT_FRAMES];
    K_U64 ptes[K0_MPT_TABLES][K0_MPT_ENTRIES];
    K_U64 pool_epoch;
    K_U32 ready;
} K0_MPT_MODEL;

/* Stateless, no page table writes. out is only ready on full acceptance.
 * Single-threaded diagnostic use; a partial rejected out is NOT reusable.
 */
static int k0_mpt_build(K0_MPT_MODEL *out, const K0_PAGE_POOL *pool,
                        const K_U64 frames[K0_MPT_FRAMES],
                        K_U64 firmware_cr3) {
    if (!out) return 0;
    out->ready = 0;
    if (!pool || !pool->initialized || !pool->epoch ||
        pool->active != K0_MPT_FRAMES || !frames || !firmware_cr3 ||
        (firmware_cr3 & (K0_PAGE_SIZE - 1)) ||
        (firmware_cr3 & ~K0_CR3_I_ADDR_4K))
        return 0;
    for (K_U32 i = 0; i < K0_MPT_FRAMES; ++i) {
        if (!frames[i] || frames[i] == firmware_cr3 ||
            frames[i] > K0_MPT_PHYS_LIMIT - K0_PAGE_SIZE ||
            !k0_pool_is_claimed(pool, frames[i]))
            return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (frames[i] == frames[j]) return 0;
    }
    for (K_U32 i = 0; i < K0_MPT_FRAMES; ++i) out->frames[i] = frames[i];
    for (K_U32 i = 0; i < K0_MPT_TABLES; ++i)
        for (K_U32 slot = 0; slot < K0_MPT_ENTRIES; ++slot)
            out->ptes[i][slot] = 0;
    /* The three mappings are separated by one 2MiB window each. */
    K_U32 pml4 = (K_U32)((K0_MPT_VA >> 39) & 511ULL);
    K_U32 pdpt = (K_U32)((K0_MPT_VA >> 30) & 511ULL);
    K_U32 pd = (K_U32)((K0_MPT_VA >> 21) & 511ULL);
    K_U32 pt = (K_U32)((K0_MPT_VA >> 12) & 511ULL);
    out->ptes[0][pml4] = frames[1] | K0_MPT_P | K0_MPT_RW;
    out->ptes[1][pdpt] = frames[2] | K0_MPT_P | K0_MPT_RW;
    for (K_U32 i = 0; i < 3; ++i)
        out->ptes[2][pd + i * 2] =
            frames[3 + i] | K0_MPT_P | K0_MPT_RW;
    out->ptes[3][pt] = frames[6] | K0_MPT_P | K0_MPT_RW | K0_MPT_NX;
    out->ptes[4][pt] = frames[7] | K0_MPT_P; /* RO + executable */
    out->ptes[5][pt] = frames[8] | K0_MPT_P | K0_MPT_NX; /* RO + NX */
    out->pool_epoch = pool->epoch;
    out->ready = 1;
    return 1;
}

typedef int (*K0_MPT_READ)(void *context, K_U64 frame,
                            K_U32 slot, K_U64 *out);

/* Independently regenerate expected bytes, compare all 3072 slots in
 * physical pages, then walk the physical bytes via the independent x64
 * decoder. Expected scratch is static to keep freestanding EFI free of
 * __chkstk/memset imports. NOT thread safe or reentrant.
 */
static int k0_mpt_verify(const K0_MPT_MODEL *candidate,
                          const K0_PAGE_POOL *pool, K_U64 firmware_cr3,
                          K0_MPT_READ reader, void *reader_context) {
    static K0_MPT_MODEL expected;
    if (!candidate || !candidate->ready || !pool || !reader ||
        !pool->epoch || pool->epoch != candidate->pool_epoch ||
        !k0_mpt_build(&expected, pool, candidate->frames, firmware_cr3) ||
        expected.pool_epoch != candidate->pool_epoch)
        return 0;
    for (K_U32 i = 0; i < K0_MPT_TABLES; ++i) {
        for (K_U32 slot = 0; slot < K0_MPT_ENTRIES; ++slot) {
            K_U64 actual = 0;
            if (!reader(reader_context, candidate->frames[i], slot, &actual) ||
                actual != expected.ptes[i][slot] ||
                candidate->ptes[i][slot] != expected.ptes[i][slot])
                return 0;
        }
    }
    for (K_U32 i = 0; i < 3; ++i) {
        K0_CR3_I_RESULT result = {0};
        K_U64 va = K0_MPT_VA + (K_U64)i * (2ULL << 21);
        if (!k0_cr3_inspect_translation(
             candidate->frames[0], va, reader, reader_context, &result) ||
            result.physical_address != candidate->frames[6 + i] ||
            result.leaf_page_shift != 12 ||
            result.effective_user ||
            result.effective_write != (i == 0) ||
            result.effective_nx != (i != 1))
            return 0;
    }
    K0_CR3_I_RESULT unexpected = {0};
    if (k0_cr3_inspect_translation(candidate->frames[0],
            K0_MPT_VA + K0_PAGE_SIZE, reader, reader_context, &unexpected) ||
        k0_cr3_inspect_translation(candidate->frames[0],
            K0_MPT_VA + (1ULL << 21), reader, reader_context, &unexpected) ||
        k0_cr3_inspect_translation(candidate->frames[0],
            0x1000ULL, reader, reader_context, &unexpected) ||
        k0_cr3_inspect_translation(candidate->frames[0],
            0xfffffffffffff000ULL, reader, reader_context, &unexpected))
        return 0;
    return 1;
}
#endif
