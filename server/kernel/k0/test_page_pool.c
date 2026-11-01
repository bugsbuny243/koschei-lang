#include "page_pool.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    K0_MEMORY_DESCRIPTOR map[] = {
        {7, 0, 0x200000, 0, 128, 0},
        {3, 0, 0x100000, 0, 256, 0},
    };
    K0_MEMORY_PLAN plan = {0};
    K0_PAGE_POOL pool = {0};
    K_U64 first = 0, address = 0, saved = 0;
    assert(k0_memory_validate_plan(map, sizeof(map), sizeof(map[0]), 1, &plan));
    assert(!k0_pool_init(&pool, &plan, 0));
    assert(!pool.initialized);
    assert(k0_pool_init(&pool, &plan, 1));
    assert(pool.epoch == 1);
    assert(!k0_pool_init(&pool, &plan, 1));
    assert(!k0_pool_claim(&pool, 0));
    assert(!k0_pool_is_claimed(&pool, plan.candidate_start));
    assert(!k0_pool_release(&pool, plan.candidate_start));
    for (K_U32 i = 0; i < K0_PLAN_PAGES; ++i) {
        assert(k0_pool_claim(&pool, &address));
        if (!i) first = address;
        assert(address == first + (K_U64)i * K0_PAGE_SIZE);
        assert(k0_pool_is_claimed(&pool, address));
    }
    assert(pool.active == K0_PLAN_PAGES && pool.claimed == 0xffffU);
    assert(pool.epoch == 1 + K0_PLAN_PAGES);
    K0_PAGE_POOL exhausted_epoch = pool;
    exhausted_epoch.epoch = ~(K_U64)0;
    assert(!k0_pool_release(&exhausted_epoch, first));
    assert(exhausted_epoch.claimed == 0xffffU);
    saved = address;
    assert(!k0_pool_claim(&pool, &address) && address == saved);
    assert(!k0_pool_is_claimed(&pool, first + 1));
    assert(!k0_pool_release(&pool, first + 1));
    assert(!k0_pool_release(&pool, first - K0_PAGE_SIZE));
    assert(!k0_pool_release(&pool, first + K0_PLAN_PAGES * K0_PAGE_SIZE));
    assert(k0_pool_release(&pool, first));
    assert(!k0_pool_release(&pool, first));
    assert(k0_pool_claim(&pool, &address) && address == first);
    for (K_U32 i = 0; i < K0_PLAN_PAGES; ++i)
        assert(k0_pool_release(&pool, first + (K_U64)i * K0_PAGE_SIZE));
    assert(!pool.active && !pool.claimed);
    assert(pool.epoch == 1 + K0_PLAN_PAGES + 2 + K0_PLAN_PAGES);
    K0_PAGE_POOL wrapped_epoch = pool;
    wrapped_epoch.epoch = ~(K_U64)0;
    assert(!k0_pool_claim(&wrapped_epoch, &address));
    assert(!wrapped_epoch.claimed && !wrapped_epoch.active);
    K0_PAGE_POOL other = {0};
    K0_MEMORY_PLAN bad = plan;
    bad.candidate_start = ~(K_U64)0 - 4095ULL;
    assert(!k0_pool_init(&other, &bad, 1));
    bad = plan;
    bad.candidate_start++;
    assert(!k0_pool_init(&other, &bad, 1));
    bad = plan;
    bad.candidate_pages--;
    assert(!k0_pool_init(&other, &bad, 1));
    assert(!other.initialized);
    puts("KOSCHEI-K0 PAGE-POOL-UNIT/1 PASS");
    return 0;
}
