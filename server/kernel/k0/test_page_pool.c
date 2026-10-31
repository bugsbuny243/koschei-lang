#include "page_pool.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    K0_MEMORY_DESCRIPTOR known = {7, 0, 0x200000, 0, 16, 0};
    K0_MEMORY_PLAN plan = {0};
    assert(k0_memory_validate_plan(&known, sizeof(known), sizeof(known), 1, &plan));
    assert(plan.candidate_start == 0x200000 && plan.candidate_pages == 16);
    K0_PAGE_POOL pool = {.base = 0, .count = 0};
    assert(!k0_page_pool_init(NULL, 0x200000, 16));
    assert(!k0_page_pool_init(&pool, 0x1000, 16));
    assert(!k0_page_pool_init(&pool, 0x200001, 16));
    assert(!k0_page_pool_init(&pool, 0x200000, 17));
    assert(!k0_page_pool_init(&pool, ~(K_U64)0 - 4095, 16));
    assert(pool.count == 0);
    assert(k0_page_pool_init(&pool, 0x200000, 16));
    K_U64 address = 0;
    assert(!k0_page_claim(NULL, &address));
    assert(!k0_page_claim(&pool, NULL));
    assert(!k0_page_release(&pool, 0x200000));
    assert(!k0_page_release(&pool, 0x1ff000));
    assert(!k0_page_release(&pool, 0x200001));
    assert(!k0_page_release(&pool, 0x210000));
    for (K_U64 i = 0; i < 16; i++) {
        assert(k0_page_claim(&pool, &address));
        assert(address == 0x200000 + i * 4096);
        assert(!k0_page_release(&pool, address + 1));
    }
    assert(pool.occupied == 0xffff);
    assert(!k0_page_claim(&pool, &address));
    assert(k0_page_release(&pool, 0x200000 + 8 * 4096));
    assert(!k0_page_release(&pool, 0x200000 + 8 * 4096));
    assert(k0_page_claim(&pool, &address));
    assert(address == 0x200000 + 8 * 4096);
    assert(!k0_page_claim(&pool, &address));
    for (K_U64 i = 0; i < 16; i++)
        assert(k0_page_release(&pool, 0x200000 + i * 4096));
    assert(pool.occupied == 0);
    puts("KOSCHEI-K0 PAGE-POOL-UNIT/1 PASS");
    return 0;
}
