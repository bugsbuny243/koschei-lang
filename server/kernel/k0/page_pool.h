#ifndef KOSCHEI_K0_PAGE_POOL_H
#define KOSCHEI_K0_PAGE_POOL_H
/* K0.3: metadata ledger for a previously validated 16-page conventional
 * range. Call only after successful ExitBootServices. This does NOT install
 * new page tables or independently establish physical/virtual isolation.
 */
#include "memory_map.h"

typedef struct {
    K_U64 base;
    K_U32 claimed;
    K_U32 active;
    K_U32 initialized;
    /* Metadata mutation epoch: detects stale single-thread preflight plans.
     * Overflow fails closed rather than wrapping into an old epoch.
     */
    K_U64 epoch;
} K0_PAGE_POOL;

static int k0_pool_init(K0_PAGE_POOL *pool, const K0_MEMORY_PLAN *plan,
                        int boot_services_exited) {
    if (!pool || !plan || !boot_services_exited || pool->initialized ||
        plan->candidate_pages != K0_PLAN_PAGES ||
        plan->candidate_start < 0x100000ULL ||
        (plan->candidate_start & (K0_PAGE_SIZE - 1)) ||
        plan->candidate_start > ~(K_U64)0 - K0_PLAN_PAGES * K0_PAGE_SIZE)
        return 0;
    pool->base = plan->candidate_start;
    pool->claimed = 0;
    pool->active = 0;
    pool->initialized = 1;
    pool->epoch = 1;
    return 1;
}

static int k0_pool_claim(K0_PAGE_POOL *pool, K_U64 *address) {
    if (!pool || !pool->initialized || !address ||
        !pool->epoch || pool->epoch == ~(K_U64)0 ||
        pool->active >= K0_PLAN_PAGES)
        return 0;
    for (K_U32 i = 0; i < (K_U32)K0_PLAN_PAGES; ++i) {
        K_U32 mask = 1u << i;
        if (!(pool->claimed & mask)) {
            pool->claimed |= mask;
            ++pool->active;
            ++pool->epoch;
            *address = pool->base + (K_U64)i * K0_PAGE_SIZE;
            return 1;
        }
    }
    return 0;
}

static int k0_pool_is_claimed(const K0_PAGE_POOL *pool, K_U64 address) {
    if (!pool || !pool->initialized || address < pool->base ||
        (address & (K0_PAGE_SIZE - 1))) return 0;
    K_U64 offset = address - pool->base;
    if (offset >= K0_PLAN_PAGES * K0_PAGE_SIZE) return 0;
    return (pool->claimed & (1u << (K_U32)(offset / K0_PAGE_SIZE))) != 0;
}

static int k0_pool_release(K0_PAGE_POOL *pool, K_U64 address) {
    if (!k0_pool_is_claimed(pool, address) || !pool->active ||
        !pool->epoch || pool->epoch == ~(K_U64)0) return 0;
    K_U32 index = (K_U32)((address - pool->base) / K0_PAGE_SIZE);
    pool->claimed &= ~(1u << index);
    --pool->active;
    ++pool->epoch;
    return 1;
}
#endif
