#include "multi_pt_physical.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static K0_PAGE_POOL pool;
static K0_MPT_MODEL model;
static K_U64 frames[K0_MPT_FRAMES];
static K_U64 actual[K0_MPT_TABLES][K0_MPT_ENTRIES];
static K_U32 reads;
static int deny;

static int read_physical(void *ctx, K_U64 frame, K_U32 slot, K_U64 *out) {
    (void)ctx;
    ++reads;
    if (deny || !out || slot >= K0_MPT_ENTRIES) return 0;
    for (K_U32 i = 0; i < K0_MPT_TABLES; ++i) {
        if (frame == frames[i]) {
            *out = actual[i][slot];
            return 1;
        }
    }
    return 0;
}
static int verify(void) {
    return k0_mpt_verify(&model, &pool, 0x800000ULL, read_physical, 0);
}
static void fixture(void) {
    K0_MEMORY_DESCRIPTOR map[] = {
        {7, 0, 0x200000ULL, 0, 128, 0},
        {5, 0, 0x900000ULL, 0, 1, 1ULL << 63}
    };
    K0_MEMORY_PLAN plan = {0};
    assert(k0_memory_validate_plan(map, sizeof(map), sizeof(map[0]),
                                   1, &plan));
    assert(k0_pool_init(&pool, &plan, 1));
    for (K_U32 i = 0; i < K0_MPT_FRAMES; ++i)
        assert(k0_pool_claim(&pool, &frames[i]));
    assert(k0_mpt_build(&model, &pool, frames, 0x800000ULL));
    for (K_U32 i = 0; i < K0_MPT_TABLES; ++i)
        memcpy(actual[i], model.ptes[i], sizeof(actual[i]));
}
int main(void) {
    fixture();
    assert(verify());
    assert(reads >= 6U * 512U + 3U * 4U);
    assert(!k0_mpt_verify(0, &pool, 0x800000ULL, read_physical, 0));
    assert(!k0_mpt_verify(&model, 0, 0x800000ULL, read_physical, 0));
    assert(!k0_mpt_verify(&model, &pool, 0x800000ULL, 0, 0));
    assert(!k0_mpt_verify(&model, &pool, 0x0ULL, read_physical, 0));
    assert(!k0_mpt_verify(&model, &pool, frames[0], read_physical, 0));
    deny = 1; assert(!verify()); deny = 0;
    assert(verify());

    /* Every unreferenced slot is part of the physical integrity receipt. */
    actual[0][400] ^= 1ULL;
    assert(!verify());
    actual[0][400] ^= 1ULL;
    assert(verify());
    actual[2][15] ^= 1ULL;
    assert(!verify());
    actual[2][15] ^= 1ULL;
    assert(verify());

    /* Modifying BOTH model and physical bytes cannot forge independent
     * model regeneration, even if the new leaf appears self-consistent.
     */
    actual[3][0] &= ~K0_MPT_NX; model.ptes[3][0] &= ~K0_MPT_NX;
    assert(!verify());
    actual[3][0] |= K0_MPT_NX; model.ptes[3][0] |= K0_MPT_NX;
    assert(verify());
    actual[4][0] |= K0_MPT_RW; model.ptes[4][0] |= K0_MPT_RW;
    assert(!verify());
    actual[4][0] &= ~K0_MPT_RW; model.ptes[4][0] &= ~K0_MPT_RW;
    assert(verify());
    actual[5][0] |= K0_MPT_RW; model.ptes[5][0] |= K0_MPT_RW;
    assert(!verify());
    actual[5][0] &= ~K0_MPT_RW; model.ptes[5][0] &= ~K0_MPT_RW;
    assert(verify());
    actual[2][0] = 0; assert(!verify());
    actual[2][0] = model.ptes[2][0];
    assert(verify());

    /* Count, aliasing, foreign frames and forbidden CR3 root. */
    K0_MPT_MODEL rejected = {0};
    K_U64 bad[K0_MPT_FRAMES];
    memcpy(bad, frames, sizeof(bad));
    bad[5] = bad[3];
    assert(!k0_mpt_build(&rejected, &pool, bad, 0x800000ULL));
    bad[5] = 0x900000ULL;
    assert(!k0_mpt_build(&rejected, &pool, bad, 0x800000ULL));
    bad[5] = frames[5];
    bad[0] = 0x800000ULL;
    assert(!k0_mpt_build(&rejected, &pool, bad, 0x800000ULL));
    assert(!k0_mpt_build(&rejected, &pool, frames, 0));
    assert(verify());

    /* Frame release / reclaim (ABA) invalidates the already-built model. */
    assert(k0_pool_release(&pool, frames[8]));
    K_U64 renewed = 0;
    assert(k0_pool_claim(&pool, &renewed) && renewed == frames[8]);
    assert(!verify());
    for (K_U32 i = 0; i < K0_MPT_FRAMES; ++i)
        assert(k0_pool_release(&pool, frames[i]));
    assert(pool.active == 0);
    puts("KOSCHEI-K0 MULTI-PT-PHYSICAL/1 PASS (three 2MiB windows; NO CR3 write)");
    return 0;
}
