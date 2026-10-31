#ifndef KOSCHEI_K0_PAGE_LEDGER_H
#define KOSCHEI_K0_PAGE_LEDGER_H
#include "memory_map.h"

/*
 * K0.2 logical page-ownership ledger (NOT a real allocator yet).
 * It records unique 4KiB addresses from the previously validated candidate.
 * This code NEVER dereferences, maps or writes a physical address.
 */
typedef struct {
    K_U64 first;
    K_U64 next_index;
    K_U64 capacity;
} K0_PAGE_LEDGER;

static int k0_page_ledger_init(K0_PAGE_LEDGER *ledger,
                               const K0_MEMORY_PLAN *validated_plan,
                               int firmware_handoff_confirmed) {
    if (!ledger || !validated_plan || !firmware_handoff_confirmed ||
        validated_plan->candidate_pages != K0_PLAN_PAGES ||
        validated_plan->candidate_start < 0x100000ULL ||
        (validated_plan->candidate_start & (K0_PAGE_SIZE - 1)) != 0 ||
        validated_plan->candidate_start >
            ~(K_U64)0 - K0_PLAN_PAGES * K0_PAGE_SIZE)
        return 0;
    K0_PAGE_LEDGER next = {validated_plan->candidate_start, 0, K0_PLAN_PAGES};
    *ledger = next;
    return 1;
}

static int k0_page_ledger_take(K0_PAGE_LEDGER *ledger, K_U64 *address) {
    if (!ledger || !address || ledger->next_index >= ledger->capacity ||
        ledger->capacity != K0_PLAN_PAGES)
        return 0;
    *address = ledger->first + ledger->next_index * K0_PAGE_SIZE;
    ledger->next_index++;
    return 1;
}

#endif
