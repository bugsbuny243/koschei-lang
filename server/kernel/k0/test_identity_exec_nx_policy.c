#include "paging_identity_exec_nx_policy.h"
#include <assert.h>
#include <stdio.h>

static K_U64 pdes[K0_CR3_IDENTITY_PDE_COUNT];

static void mark_sentinel(void) {
    for (K_U32 i=0; i < K0_CR3_IDENTITY_PDE_COUNT; ++i)
        pdes[i] = 0xbaddcafeULL;
}
static void expect_untouched(void) {
    for (K_U32 i=0; i < K0_CR3_IDENTITY_PDE_COUNT; ++i)
        assert(pdes[i] == 0xbaddcafeULL);
}
int main(void) {
    /* Exercise the same UEFI descriptor validator supplying the page-ledger
     * plan; the policy itself still does not touch any firmware service.
     */
    K0_MEMORY_DESCRIPTOR map[] = {
        {7, 0, 0x200000ULL, 0, 128, 0},
        {3, 0, 0x100000ULL, 0, 256, 0}
    };
    K0_MEMORY_PLAN memory = {0};
    assert(k0_memory_validate_plan(map, sizeof(map), sizeof(map[0]), 1,
                                   &memory));
    assert(memory.candidate_start == 0x200000ULL);
    const K_U64 code[] = {0x200000ULL, 0x200ffcULL,
                          0x600123ULL, 0x200000ULL};
    mark_sentinel();
    assert(!k0_cr3_identity_build(0, code, 4));
    expect_untouched();
    assert(!k0_cr3_identity_build(pdes, 0, 4));
    assert(!k0_cr3_identity_build(pdes, code, 0));
    expect_untouched();
    K_U64 invalid[] = {0x200000ULL, 0};
    assert(!k0_cr3_identity_build(pdes, invalid, 2));
    expect_untouched();
    invalid[1] = K0_CR3_IDENTITY_LIMIT;
    assert(!k0_cr3_identity_build(pdes, invalid, 2));
    expect_untouched();
    invalid[1] = K0_CR3_IDENTITY_LIMIT - 1ULL;
    assert(!k0_cr3_identity_build(pdes, invalid, 2));
    expect_untouched();
    K_U64 too_many[9] = {0};
    for (K_U32 i=0; i<9; ++i) too_many[i] = ((K_U64)i + 1ULL) << 21;
    assert(!k0_cr3_identity_build(pdes, too_many, 9));
    expect_untouched();
    assert(!k0_cr3_identity_build(pdes, code, 17));
    expect_untouched();

    assert(k0_cr3_identity_build(pdes, code, 4));
    K_U32 exec_count = 0;
    for (K_U32 i=0; i<K0_CR3_IDENTITY_PDE_COUNT; ++i) {
        assert((pdes[i] & ~K0_CR3_IDENTITY_NX) ==
               (((K_U64)i << 21) | 0x83ULL));
        if (!(pdes[i] & K0_CR3_IDENTITY_NX)) {
            ++exec_count;
            assert(i==1 || i==3);
        } else {
            assert(i!=1 && i!=3);
        }
    }
    assert(exec_count == 2);
    assert(pdes[0] & K0_CR3_IDENTITY_NX);
    assert(pdes[511] & K0_CR3_IDENTITY_NX);
    puts("KOSCHEI-K0 IDENTITY-EXEC-NX/1 PASS (coarse RWX code windows; not W^X)");
    return 0;
}
