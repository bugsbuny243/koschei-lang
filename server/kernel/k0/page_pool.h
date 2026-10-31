#ifndef KOSCHEI_K0_PAGE_POOL_H
#define KOSCHEI_K0_PAGE_POOL_H
#include "memory_map.h"
/* K0.2: bounded 16-page physical-page pool AFTER ExitBootServices.
 * The pool never confers ownership itself; creation is permitted only by
 * the firmware-exit call site after successful UEFI handoff. Neither a
 * page-table owner nor a production-grade cross-core allocator.
 */
typedef struct {
    K_U64 base;
    K_U64 count;
    K_U64 occupied;
} K0_PAGE_POOL;

static int k0_page_pool_init(K0_PAGE_POOL *out, K_U64 base, K_U64 pages) {
    if (!out || base < 0x100000ULL || (base & (K0_PAGE_SIZE - 1)) ||
        pages != K0_PLAN_PAGES || pages > 64 ||
        base > (~(K_U64)0 - pages * K0_PAGE_SIZE)) return 0;
    K0_PAGE_POOL next = {base, pages, 0};
    *out = next;
    return 1;
}
static int k0_page_claim(K0_PAGE_POOL *pool, K_U64 *address) {
    if (!pool || !address || pool->count != K0_PLAN_PAGES) return 0;
    for (K_U64 index = 0; index < pool->count; ++index) {
        K_U64 bit = 1ULL << index;
        if (!(pool->occupied & bit)) {
            pool->occupied |= bit;
            *address = pool->base + index * K0_PAGE_SIZE;
            return 1;
        }
    }
    return 0;
}
static int k0_page_release(K0_PAGE_POOL *pool, K_U64 address) {
    if (!pool || pool->count != K0_PLAN_PAGES || address < pool->base ||
        (address - pool->base) % K0_PAGE_SIZE != 0) return 0;
    K_U64 index = (address - pool->base) / K0_PAGE_SIZE;
    if (index >= pool->count) return 0;
    K_U64 bit = 1ULL << index;
    if (!(pool->occupied & bit)) return 0;
    pool->occupied &= ~bit;
    return 1;
}
#endif
