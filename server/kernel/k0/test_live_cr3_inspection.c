#include "live_cr3_inspection.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define C_PRESENT K0_CR3_I_PRESENT
#define C_RW K0_CR3_I_RW
#define C_PS K0_CR3_I_PS
static K_U64 frames[4][512];
static K_U32 read_calls;
static int deny_read;
static int fake_read(void *context, K_U64 physical, K_U32 slot, K_U64 *entry) {
    (void)context;
    ++read_calls;
    if (deny_read || slot >= 512 || !entry) return 0;
    if (physical < 0x1000 || physical > 0x4000 ||
        (physical & 4095ULL)) return 0;
    *entry = frames[(physical >> 12) - 1][slot];
    return 1;
}
static void setup(void) {
    memset(frames, 0, sizeof(frames));
    read_calls = 0;
    deny_read = 0;
    frames[0][0] = 0x2000 | C_PRESENT | C_RW;
    frames[1][0] = 0x3000 | C_PRESENT | C_RW;
    frames[2][2] = 0x4000 | C_PRESENT | C_RW;
    frames[3][0] = 0x8000 | C_PRESENT | C_RW;
}
static void reject(K_U64 va, K_U64 root) {
    K0_CR3_I_RESULT result;
    memset(&result, 0xA5, sizeof(result));
    K0_CR3_I_RESULT before = result;
    assert(!k0_cr3_inspect_translation(root, va, fake_read, 0, &result));
    assert(memcmp(&result, &before, sizeof(result)) == 0);
}
int main(void) {
    const K_U64 va = 0x0000000000400123ULL;
    K0_CR3_I_RESULT result = {0};
    setup();
    assert(k0_cr3_inspect_translation(0x1000, va, fake_read, 0, &result));
    assert(result.physical_address == 0x8123);
    assert(result.levels_read == 4 && result.leaf_page_shift == 12);
    assert(result.effective_write && !result.effective_user &&
           !result.effective_nx && result.root_cr3 == 0x1000);
    assert(read_calls == 4);

    /* The output is transactional if the reader rejects a physical frame. */
    deny_read = 1; reject(va, 0x1000); deny_read = 0;
    reject(va, 0);
    reject(va, 0x1001);
    reject(0x0000800000000000ULL, 0x1000);
    reject(va, 0x0010000000001000ULL);
    setup(); frames[0][0] = 0; reject(va, 0x1000);
    setup(); frames[1][0] = 0; reject(va, 0x1000);
    setup(); frames[2][2] = 0; reject(va, 0x1000);
    setup(); frames[3][0] = 0; reject(va, 0x1000);
    setup(); frames[0][0] |= C_PS; reject(va, 0x1000);
    setup(); frames[2][2] = 0xdead000 | C_PRESENT; reject(va, 0x1000);
    setup(); frames[1][0] = 0x3001; reject(va, 0x1000); /* non-present */
    setup(); frames[2][2] = 0x0 | C_PRESENT | C_RW;
    reject(va, 0x1000);

    /* Hierarchical permission and NX restriction accumulation. */
    setup();
    frames[0][0] |= K0_CR3_I_USER;
    frames[1][0] |= K0_CR3_I_USER;
    frames[2][2] |= K0_CR3_I_USER;
    frames[3][0] |= K0_CR3_I_USER;
    frames[1][0] |= K0_CR3_I_NX;
    frames[2][2] &= ~C_RW;
    assert(k0_cr3_inspect_translation(0x1000, va, fake_read, 0, &result));
    assert(result.effective_user && !result.effective_write && result.effective_nx);

    /* Physical 2 MiB and 1 GiB leaves are present in modern firmware. */
    setup();
    frames[2][2] = 0x800000 | C_PRESENT | C_RW | C_PS;
    assert(k0_cr3_inspect_translation(0x1000, va, fake_read, 0, &result));
    assert(result.levels_read == 3 && result.leaf_page_shift == 21);
    assert(result.physical_address == 0x800123);
    frames[2][2] |= 0x2000ULL; /* reserved bit 13 */
    reject(va, 0x1000);
    setup();
    frames[1][0] = 0x40000000 | C_PRESENT | C_RW | C_PS;
    assert(k0_cr3_inspect_translation(0x1000, va, fake_read, 0, &result));
    assert(result.levels_read == 2 && result.leaf_page_shift == 30);
    assert(result.physical_address == 0x40400123);
    frames[1][0] |= 0x4000ULL; /* reserved bit 14 */
    reject(va, 0x1000);

    setup();
    assert(!k0_cr3_inspect_translation(0x1000, va, 0, 0, &result));
    assert(!k0_cr3_inspect_translation(0x1000, va, fake_read, 0, 0));
    puts("KOSCHEI-K0 ACTIVE-CR3-TABLE-WALK/1 PASS (software PTE read; not owned CR3)");
    return 0;
}
