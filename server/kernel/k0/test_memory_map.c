#include "memory_map.h"
#include <assert.h>
#include <stdio.h>

static K0_MEMORY_DESCRIPTOR entries[] = {
    {7, 0, 0x400000, 0, 32, 0},
    {0, 0, 0x0, 0, 256, 0},
    {3, 0, 0x100000, 0, 256, 0},
    {7, 0, 0x200000, 0, 128, 0},
};
static void accept(void) {
    K0_MEMORY_PLAN p = {0};
    int result = k0_memory_validate_plan(entries, sizeof(entries), 40, 1, &p);
    assert(result == 1 && p.descriptors == 4 && p.conventional_pages == 160 &&
           p.candidate_start == 0x200000 && p.candidate_pages == 16);
}
int main(void) {
    accept();
    K0_MEMORY_PLAN p = {.descriptors = 999};
    assert(!k0_memory_validate_plan(0, sizeof(entries), 40, 1, &p));
    assert(!k0_memory_validate_plan(entries, sizeof(entries), 40, 0, &p));
    assert(!k0_memory_validate_plan(entries, sizeof(entries)-1, 40, 1, &p));
    assert(!k0_memory_validate_plan(entries, sizeof(entries), 39, 1, &p));
    assert(!k0_memory_validate_plan(entries, 65560, 40, 1, &p));
    assert(p.descriptors == 999);
    entries[0].physical_start = 0x200000;
    assert(!k0_memory_validate_plan(entries, sizeof(entries), 40, 1, &p));
    entries[0].physical_start = 0x400000;
    entries[0].number_of_pages = 0;
    assert(!k0_memory_validate_plan(entries, sizeof(entries), 40, 1, &p));
    entries[0].number_of_pages = 32;
    entries[0].physical_start++;
    assert(!k0_memory_validate_plan(entries, sizeof(entries), 40, 1, &p));
    entries[0].physical_start = ~(K_U64)0 - 4095;
    entries[0].number_of_pages = 2;
    assert(!k0_memory_validate_plan(entries, sizeof(entries), 40, 1, &p));
    entries[0].physical_start = 0x400000;
    entries[0].number_of_pages = 32;
    entries[3].type = 3;
    entries[0].type = 3;
    assert(!k0_memory_validate_plan(entries, sizeof(entries), 40, 1, &p));
    entries[0].type = 7;
    entries[3].type = 7;
    accept();
    puts("KOSCHEI-K0 MEMORY-UNIT/1 PASS");
    return 0;
}
